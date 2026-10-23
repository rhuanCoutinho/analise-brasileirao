-- Deve retornar zero linhas: tabela coerente com as partidas encerradas.
with expected as (
    select season, league, team,
        count(*) as played,
        sum(case when goals_for > goals_against then 1 else 0 end) as wins,
        sum(case when goals_for = goals_against then 1 else 0 end) as draws,
        sum(case when goals_for < goals_against then 1 else 0 end) as losses,
        sum(case when goals_for > goals_against then 3 when goals_for = goals_against then 1 else 0 end) as points
    from {{ ref('int_team_match_results') }}
    group by season, league, team
)
select s.season, s.league, s.team
from {{ ref('mart_current_standings') }} s
left join expected e using (season, league, team)
where s.played != coalesce(e.played, 0)
   or s.played != s.wins + s.draws + s.losses
   or s.points != 3 * s.wins + s.draws
   or s.wins != coalesce(e.wins, 0)
   or s.draws != coalesce(e.draws, 0)
   or s.losses != coalesce(e.losses, 0)
