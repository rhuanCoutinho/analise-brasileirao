select f.match_id, f.season, f.league, f.match_date, f.home_team, f.away_team, t.team,
    case when f.home_team = t.team then 'home' else 'away' end as venue
from {{ ref('int_remaining_fixtures') }} f
cross join (select season, league, team from {{ ref('int_team_season_entities') }}) t
where f.season = t.season and f.league = t.league
  and t.team in (f.home_team, f.away_team)
