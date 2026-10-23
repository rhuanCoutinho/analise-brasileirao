select
    match_id,
    season,
    league,
    cast(match_date as date) as match_date,
    trim(home_team) as home_team,
    trim(away_team) as away_team,
    cast(home_goals as integer) as home_goals,
    cast(away_goals as integer) as away_goals
from {{ source('raw', 'raw_brazil_historical_matches') }}
where league = 'BRA'
  and season in ('2021', '2022', '2023', '2024', '2025')
  and home_goals is not null and away_goals is not null
