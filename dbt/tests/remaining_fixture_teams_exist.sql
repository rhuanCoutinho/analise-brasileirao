select f.match_id, f.team
from {{ ref('mart_remaining_fixtures') }} f
left join {{ ref('mart_current_standings') }} s using (season, league, team)
where s.team is null
