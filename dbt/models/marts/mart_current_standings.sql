select
    season, league, team, played, wins, draws, losses,
    goals_for, goals_against, goal_difference, points,
    rank() over (partition by season, league order by points desc, wins desc, goal_difference desc, goals_for desc, team) as position,
    count(*) over (partition by season, league) as league_size,
    cast({{ var('relegation_spots', 3) }} as integer) as relegation_spots
from {{ ref('int_team_standings') }}
