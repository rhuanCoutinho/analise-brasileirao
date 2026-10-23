select estimate_id
from {{ ref('mart_relegation_estimates') }}
where relegation_probability < 0 or relegation_probability > 1
