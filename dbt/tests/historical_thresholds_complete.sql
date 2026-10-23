with season_summary as (
    select count(*) as seasons,
        count(last_safe_points) as safe_cutoffs,
        count(last_relegated_points) as relegation_cutoffs
    from {{ ref('mart_historical_relegation_thresholds') }}
    where league = 'BRA' and season in ('2021', '2022', '2023', '2024', '2025')
),
relegated_counts as (
    select season, count(*) as relegated_teams
    from {{ ref('mart_historical_relegated_teams') }}
    where league = 'BRA' and season in ('2021', '2022', '2023', '2024', '2025')
    group by season
)
select * from season_summary
where seasons <> 5 or safe_cutoffs <> 5 or relegation_cutoffs <> 5
union all
select count(*) as seasons, sum(case when relegated_teams = 4 then 1 else 0 end) as safe_cutoffs,
       sum(case when relegated_teams = 4 then 1 else 0 end) as relegation_cutoffs
from relegated_counts
having count(*) <> 5 or sum(case when relegated_teams = 4 then 1 else 0 end) <> 5
