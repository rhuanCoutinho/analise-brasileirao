select season, league, home_team as team from {{ ref('stg_matches') }}
union
select season, league, away_team as team from {{ ref('stg_matches') }}
