-- The Brazil source CSV contains completed results only. The Brasileirao is a
-- 20-team double round-robin, so infer unplayed home/away pairs from the 380-game
-- format. Dates are intentionally NULL: the source file does not publish them.
with source_fixtures as (
    select match_id, season, league, match_date, home_team, away_team
    from {{ ref('stg_matches') }}
    where match_status = 'scheduled' and league <> 'BRA'
),
brazil_teams as (
    select season, league, team from {{ ref('int_team_season_entities') }}
    where league = 'BRA' and season = '2026'
),
brazil_remaining as (
    select
        'inferred-' || md5(home.team || '|' || away.team || '|' || home.season) as match_id,
        home.season,
        home.league,
        cast(null as date) as match_date,
        home.team as home_team,
        away.team as away_team
    from brazil_teams home
    cross join brazil_teams away
    where home.team <> away.team
      and not exists (
          select 1 from {{ ref('stg_matches') }} played
          where played.season = home.season
            and played.league = home.league
            and played.match_status = 'finished'
            and played.home_team = home.team
            and played.away_team = away.team
      )
)
select * from source_fixtures
union all
select * from brazil_remaining
