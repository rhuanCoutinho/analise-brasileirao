select
    estimate_id,
    season,
    league,
    team,
    cast(estimated_at as timestamp) as estimated_at,
    cast(relegation_probability as double) as relegation_probability,
    cast(simulations as integer) as simulations,
    cast(relegation_spots as integer) as relegation_spots,
    random_seed
from {{ source('raw', 'raw_relegation_estimates') }}
