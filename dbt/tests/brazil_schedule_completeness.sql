with played as (
    select count(*) as games
    from {{ ref('stg_matches') }}
    where season = '2026' and league = 'BRA' and match_status = 'finished'
),
teams as (
    select count(*) as teams
    from {{ ref('int_team_season_entities') }}
    where season = '2026' and league = 'BRA'
),
remaining as (
    select count(*) as games
    from {{ ref('int_remaining_fixtures') }}
    where season = '2026' and league = 'BRA'
)
select *
from played cross join teams cross join remaining
where teams.teams <> 20
   or played.games + remaining.games <> 380
   or remaining.games <> 380 - played.games
