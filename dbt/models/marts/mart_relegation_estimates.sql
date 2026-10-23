select
    e.estimate_id, e.season, e.league, e.team, e.estimated_at,
    e.relegation_probability, e.simulations, e.relegation_spots, e.random_seed,
    s.position, s.points, s.played, s.goal_difference,
    row_number() over (partition by e.season, e.league, e.team order by e.estimated_at desc) as snapshot_rank
from {{ ref('stg_relegation_estimates') }} e
left join {{ ref('mart_current_standings') }} s using (season, league, team)
