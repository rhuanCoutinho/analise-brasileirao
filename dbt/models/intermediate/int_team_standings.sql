with results as (
    select season, league, team,
        sum(played) as played, sum(wins) as wins, sum(draws) as draws, sum(losses) as losses,
        sum(goals_for) as goals_for, sum(goals_against) as goals_against, sum(points) as points
    from {{ ref('int_team_match_results') }}
    group by season, league, team
)
select e.season, e.league, e.team,
    coalesce(r.played, 0) as played,
    coalesce(r.wins, 0) as wins,
    coalesce(r.draws, 0) as draws,
    coalesce(r.losses, 0) as losses,
    coalesce(r.goals_for, 0) as goals_for,
    coalesce(r.goals_against, 0) as goals_against,
    coalesce(r.goals_for, 0) - coalesce(r.goals_against, 0) as goal_difference,
    coalesce(r.points, 0) as points
from {{ ref('int_team_season_entities') }} e
left join results r using (season, league, team)
