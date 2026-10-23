select
    season,
    league,
    max(case when final_position = 16 then team end) as last_safe_team,
    max(case when final_position = 16 then points end) as last_safe_points,
    max(case when final_position = 17 then team end) as last_relegated_team,
    max(case when final_position = 17 then points end) as last_relegated_points,
    cast(5 as integer) as seasons_in_window
from {{ ref('int_brazil_historical_standings') }}
group by season, league
