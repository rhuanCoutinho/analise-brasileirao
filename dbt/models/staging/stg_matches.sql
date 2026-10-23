select
    match_id,
    season,
    league,
    cast(match_date as date) as match_date,
    trim(home_team) as home_team,
    trim(away_team) as away_team,
    cast(home_goals as integer) as home_goals,
    cast(away_goals as integer) as away_goals,
    case when home_goals is not null and away_goals is not null then 'finished' else 'scheduled' end as match_status,
    source_url,
    ingested_at
from {{ source('raw', 'raw_matches') }}
where home_team is not null and away_team is not null
