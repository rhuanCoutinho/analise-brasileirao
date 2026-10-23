select season, league, team as relegated_team, final_position, points
from {{ ref('int_brazil_historical_standings') }}
where final_position between 17 and 20
