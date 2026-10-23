select
    match_id, season, league, match_date, home_team as team,
    1 as played,
    case when home_goals > away_goals then 1 else 0 end as wins,
    case when home_goals = away_goals then 1 else 0 end as draws,
    case when home_goals < away_goals then 1 else 0 end as losses,
    home_goals as goals_for, away_goals as goals_against,
    case when home_goals > away_goals then 3 when home_goals = away_goals then 1 else 0 end as points
from {{ ref('stg_matches') }}
where match_status = 'finished'
union all
select
    match_id, season, league, match_date, away_team as team,
    1 as played,
    case when away_goals > home_goals then 1 else 0 end as wins,
    case when away_goals = home_goals then 1 else 0 end as draws,
    case when away_goals < home_goals then 1 else 0 end as losses,
    away_goals as goals_for, home_goals as goals_against,
    case when away_goals > home_goals then 3 when away_goals = home_goals then 1 else 0 end as points
from {{ ref('stg_matches') }}
where match_status = 'finished'
