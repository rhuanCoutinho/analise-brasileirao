with team_results as (
    select season, league, home_team as team,
        1 as played,
        case when home_goals > away_goals then 1 else 0 end as wins,
        case when home_goals = away_goals then 1 else 0 end as draws,
        case when home_goals < away_goals then 1 else 0 end as losses,
        home_goals as goals_for, away_goals as goals_against,
        case when home_goals > away_goals then 3 when home_goals = away_goals then 1 else 0 end as points
    from {{ ref('stg_brazil_historical_matches') }}
    union all
    select season, league, away_team as team,
        1 as played,
        case when away_goals > home_goals then 1 else 0 end as wins,
        case when away_goals = home_goals then 1 else 0 end as draws,
        case when away_goals < home_goals then 1 else 0 end as losses,
        away_goals as goals_for, home_goals as goals_against,
        case when away_goals > home_goals then 3 when away_goals = home_goals then 1 else 0 end as points
    from {{ ref('stg_brazil_historical_matches') }}
),
aggregated as (
    select season, league, team,
        sum(played) as played, sum(wins) as wins, sum(draws) as draws, sum(losses) as losses,
        sum(goals_for) as goals_for, sum(goals_against) as goals_against,
        sum(goals_for) - sum(goals_against) as goal_difference, sum(points) as points
    from team_results
    group by season, league, team
)
select *, row_number() over (
    partition by season order by points desc, wins desc, goal_difference desc, goals_for desc, team
) as final_position
from aggregated
