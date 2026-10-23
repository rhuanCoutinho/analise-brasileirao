from __future__ import annotations

import csv
import hashlib
import io
import logging
import time
from datetime import date, datetime, timezone
from pathlib import Path

import requests

from src.config import ROOT, league, season
from src.logging_config import configure_logging
from src.warehouse import connect

LOG = logging.getLogger("ingestion")
BASE_URL = "https://www.football-data.co.uk/mmz4281"
BRAZIL_URL = "https://www.football-data.co.uk/new/BRA.csv"
REQUIRED = {"Date", "HomeTeam", "AwayTeam"}


def _parse_date(raw: str) -> date | None:
    raw = raw.strip()
    if not raw:
        return None
    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            pass
    return None


def download_csv(season_code: str, league_code: str, *, attempts: int = 3) -> tuple[str, str]:
    # Brazil is published as one all-seasons file rather than a season/division file.
    url = BRAZIL_URL if league_code == "BRA" else f"{BASE_URL}/{season_code}/{league_code}.csv"
    cache_file = ROOT / "data" / "raw" / f"{season_code}_{league_code}.csv"
    local_brazil_file = ROOT / "BRA.csv"
    if league_code == "BRA" and local_brazil_file.exists():
        LOG.info("Using local Brazil data file: %s", local_brazil_file)
        return local_brazil_file.read_text(encoding="utf-8-sig"), local_brazil_file.as_uri()
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            response = requests.get(url, timeout=(5, 30), headers={"User-Agent": "relegation-dashboard/1.0"})
            response.raise_for_status()
            try:
                text = response.content.decode("utf-8-sig")
            except UnicodeDecodeError:
                text = response.content.decode("latin-1")
            if not text.strip():
                raise ValueError("Source returned an empty CSV")
            return text, url
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            if attempt < attempts - 1:
                time.sleep(2**attempt)
    if cache_file.exists():
        LOG.warning("Source unavailable; reusing cached CSV %s (last modified %s)",
                    cache_file, datetime.fromtimestamp(cache_file.stat().st_mtime, timezone.utc).isoformat())
        return cache_file.read_text(encoding="utf-8"), url
    raise RuntimeError(f"Could not download {url}: {last_error}") from last_error


def normalize_rows(text: str, season_code: str | None, league_code: str, source_url: str) -> list[tuple]:
    reader = csv.DictReader(io.StringIO(text))
    fields = set(reader.fieldnames or [])
    home_key = "HomeTeam" if "HomeTeam" in fields else "Home"
    away_key = "AwayTeam" if "AwayTeam" in fields else "Away"
    home_goals_key = "FTHG" if "FTHG" in fields else "HG"
    away_goals_key = "FTAG" if "FTAG" in fields else "AG"
    required = {"Date", home_key, away_key}
    if not required.issubset(fields):
        raise ValueError(f"Unexpected CSV schema; missing {sorted(required - fields)}")
    output = []
    for row in reader:
        home, away = (row.get(home_key) or "").strip(), (row.get(away_key) or "").strip()
        match_date = _parse_date(row.get("Date") or "")
        if not home or not away or match_date is None:
            continue
        row_season = season_code or str(match_date.year)
        if league_code == "BRA":
            source_season = (row.get("Season") or "").strip()
            row_season = source_season or str(match_date.year)
            if season_code is not None and row_season != season_code:
                continue
            source_league = (row.get("League") or "").strip().casefold()
            if source_league and source_league != "serie a":
                continue
        def score(key: str) -> int | None:
            value = (row.get(key) or "").strip()
            try:
                return int(float(value)) if value else None
            except ValueError:
                return None

        home_goals, away_goals = score(home_goals_key), score(away_goals_key)
        if (home_goals is None) != (away_goals is None):
            home_goals = away_goals = None
        key = f"{row_season}|{league_code}|{match_date.isoformat()}|{home}|{away}"
        match_id = hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]
        output.append((match_id, row_season, league_code, match_date, home, away,
                       home_goals, away_goals, source_url))
    if not output:
        raise ValueError(f"CSV contained no usable fixtures or results for season {season_code}")
    return output


def ingest(season_code: str | None = None, league_code: str | None = None) -> dict:
    season_code, league_code = season_code or season(), (league_code or league()).upper()
    started = datetime.now(timezone.utc)
    run_id = hashlib.sha256(f"{started.isoformat()}|{season_code}|{league_code}".encode()).hexdigest()[:20]
    try:
        content, url = download_csv(season_code, league_code)
        if league_code == "BRA":
            all_brazil_rows = normalize_rows(content, None, league_code, url)
            rows = [row for row in all_brazil_rows if row[1] == season_code]
            historical_rows = [row for row in all_brazil_rows if row[1] in {"2021", "2022", "2023", "2024", "2025"}]
            if not rows:
                raise ValueError(f"CSV contains no Brasileirão Série A results for {season_code}")
        else:
            rows = normalize_rows(content, season_code, league_code, url)
            historical_rows = []
        cache_dir = ROOT / "data" / "raw"
        cache_dir.mkdir(parents=True, exist_ok=True)
        (cache_dir / f"{season_code}_{league_code}.csv").write_text(content, encoding="utf-8")
        conn = connect()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS raw_matches (
                    match_id VARCHAR, season VARCHAR, league VARCHAR, match_date DATE,
                    home_team VARCHAR, away_team VARCHAR, home_goals INTEGER, away_goals INTEGER,
                    source_url VARCHAR, ingested_at TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS etl_runs (
                    run_id VARCHAR, season VARCHAR, league VARCHAR, started_at TIMESTAMPTZ,
                    finished_at TIMESTAMPTZ, status VARCHAR, rows_loaded INTEGER, error VARCHAR
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS raw_brazil_historical_matches (
                    match_id VARCHAR, season VARCHAR, league VARCHAR, match_date DATE,
                    home_team VARCHAR, away_team VARCHAR, home_goals INTEGER, away_goals INTEGER,
                    source_url VARCHAR, ingested_at TIMESTAMP
                )
            """)
            conn.execute("BEGIN TRANSACTION")
            conn.execute("DELETE FROM raw_matches WHERE season = ? AND league = ?", [season_code, league_code])
            ingested_at = datetime.now(timezone.utc).replace(tzinfo=None)
            conn.executemany("INSERT INTO raw_matches VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                             [(*row, ingested_at) for row in rows])
            conn.execute("DELETE FROM raw_brazil_historical_matches WHERE league = 'BRA' AND season IN ('2021', '2022', '2023', '2024', '2025')")
            conn.executemany("INSERT INTO raw_brazil_historical_matches VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                             [(*row, ingested_at) for row in historical_rows])
            conn.execute("INSERT INTO etl_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                         [run_id, season_code, league_code, started, datetime.now(timezone.utc), "success",
                          len(rows) + len(historical_rows), None])
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()
        result = {"run_id": run_id, "season": season_code, "league": league_code,
                  "rows": len(rows), "historical_rows": len(historical_rows), "status": "success"}
        LOG.info("Ingestion completed: %s", result)
        return result
    except Exception as exc:
        LOG.exception("Ingestion failed for season=%s league=%s", season_code, league_code)
        conn = connect()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS etl_runs (
                    run_id VARCHAR, season VARCHAR, league VARCHAR, started_at TIMESTAMPTZ,
                    finished_at TIMESTAMPTZ, status VARCHAR, rows_loaded INTEGER, error VARCHAR
                )
            """)
            conn.execute("INSERT INTO etl_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                         [run_id, season_code, league_code, started, datetime.now(timezone.utc), "failed", 0, str(exc)[:1000]])
        finally:
            conn.close()
        raise


if __name__ == "__main__":
    configure_logging()
    ingest()
