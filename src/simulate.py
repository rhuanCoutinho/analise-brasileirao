from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone

import numpy as np

from src.config import league, relegation_spots, season, simulations
from src.logging_config import configure_logging
from src.warehouse import connect

LOG = logging.getLogger("simulation")
SHRINKAGE_MATCHES = 5


def poisson_outcomes(season_code: str, league_code: str, n_sims: int, seed: int, spots: int) -> dict:
    conn = connect()
    try:
        standings = conn.execute("""
            select team, points, wins, goal_difference, goals_for
            from mart_current_standings where season = ? and league = ? order by team
        """, [season_code, league_code]).fetchall()
        fixtures = conn.execute("""
            select match_id, home_team, away_team
            from int_remaining_fixtures where season = ? and league = ? order by match_date, match_id
        """, [season_code, league_code]).fetchall()
        history = conn.execute("""
            select home_team, away_team, home_goals, away_goals
            from stg_matches where season = ? and league = ? and match_status = 'finished'
        """, [season_code, league_code]).fetchall()
    finally:
        conn.close()
    if not standings:
        raise RuntimeError("No standings found. Run dbt staging/intermediate models before the simulation.")

    teams = [row[0] for row in standings]
    team_idx = {team: i for i, team in enumerate(teams)}
    n_teams = len(teams)
    points = np.repeat(np.array([row[1] for row in standings], dtype=np.int32)[None, :], n_sims, axis=0)
    wins = np.repeat(np.array([row[2] for row in standings], dtype=np.int32)[None, :], n_sims, axis=0)
    goal_diff = np.repeat(np.array([row[3] for row in standings], dtype=np.int32)[None, :], n_sims, axis=0)
    goals_for = np.repeat(np.array([row[4] for row in standings], dtype=np.int32)[None, :], n_sims, axis=0)

    totals = {team: {"h_n": 0, "h_gf": 0, "h_ga": 0, "a_n": 0, "a_gf": 0, "a_ga": 0} for team in teams}
    league_home_goals, league_away_goals = 0, 0
    for home, away, hg, ag in history:
        if home not in totals or away not in totals:
            continue
        h, a = totals[home], totals[away]
        h["h_n"] += 1; h["h_gf"] += hg; h["h_ga"] += ag
        a["a_n"] += 1; a["a_gf"] += ag; a["a_ga"] += hg
        league_home_goals += hg
        league_away_goals += ag
    matches_count = len(history)
    avg_home = league_home_goals / matches_count if matches_count else 1.45
    avg_away = league_away_goals / matches_count if matches_count else 1.15

    def shrunk(team: str, goals_key: str, games_key: str, prior: float) -> float:
        item = totals[team]
        return (item[goals_key] + SHRINKAGE_MATCHES * prior) / (item[games_key] + SHRINKAGE_MATCHES)

    rng = np.random.default_rng(seed)
    for _, home, away in fixtures:
        if home not in team_idx or away not in team_idx:
            continue
        h, a = totals[home], totals[away]
        # Independent Poisson goals with five-match shrinkage to league averages.
        lambda_home = shrunk(home, "h_gf", "h_n", avg_home) * shrunk(away, "a_ga", "a_n", avg_home) / max(avg_home, 0.1)
        lambda_away = shrunk(away, "a_gf", "a_n", avg_away) * shrunk(home, "h_ga", "h_n", avg_away) / max(avg_away, 0.1)
        hg = rng.poisson(max(0.05, min(lambda_home, 5.0)), size=n_sims)
        ag = rng.poisson(max(0.05, min(lambda_away, 5.0)), size=n_sims)
        hi, ai = team_idx[home], team_idx[away]
        points[:, hi] += np.where(hg > ag, 3, np.where(hg == ag, 1, 0))
        points[:, ai] += np.where(ag > hg, 3, np.where(hg == ag, 1, 0))
        wins[:, hi] += hg > ag
        wins[:, ai] += ag > hg
        goal_diff[:, hi] += hg - ag
        goal_diff[:, ai] += ag - hg
        goals_for[:, hi] += hg
        goals_for[:, ai] += ag

    # Brasileirão tie-break: points, wins, goal difference, goals scored, then team name.
    name_order = np.broadcast_to(np.arange(n_teams), (n_sims, n_teams))
    sorted_idx = np.lexsort((name_order, -goals_for, -goal_diff, -wins, -points), axis=1)
    relegated_idx = sorted_idx[:, max(0, n_teams - spots):]
    counts = np.zeros(n_teams, dtype=np.int32)
    np.add.at(counts, relegated_idx.ravel(), 1)
    return {team: float(counts[i] / n_sims) for i, team in enumerate(teams)}


def simulate(season_code: str | None = None, league_code: str | None = None) -> dict:
    season_code, league_code = season_code or season(), (league_code or league()).upper()
    n_sims, seed, spots = simulations(), int(__import__("os").getenv("RANDOM_SEED", "42")), relegation_spots()
    probabilities = poisson_outcomes(season_code, league_code, n_sims, seed, spots)
    estimated_at = datetime.now(timezone.utc)
    snapshot = hashlib.sha256(f"{season_code}|{league_code}|{estimated_at.isoformat()}|{seed}".encode()).hexdigest()[:16]
    conn = connect()
    try:
        conn.execute("""
            create table if not exists raw_relegation_estimates (
                estimate_id varchar, season varchar, league varchar, team varchar,
                estimated_at timestamptz, relegation_probability double, simulations integer,
                relegation_spots integer, random_seed integer
            )
        """)
        conn.executemany("insert into raw_relegation_estimates values (?, ?, ?, ?, ?, ?, ?, ?, ?)", [
            (f"{snapshot}-{hashlib.sha1(team.encode()).hexdigest()[:8]}", season_code, league_code,
             team, estimated_at, probability, n_sims, spots, seed)
            for team, probability in probabilities.items()
        ])
    finally:
        conn.close()
    result = {"season": season_code, "league": league_code, "snapshot": snapshot,
              "teams": len(probabilities), "simulations": n_sims}
    LOG.info("Simulation completed: %s", result)
    return result


if __name__ == "__main__":
    configure_logging()
    simulate()
