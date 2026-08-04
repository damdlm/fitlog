# Diagnóstico de performance — queries de leitura (Fase 3)

Este documento é só diagnóstico: não altera comportamento da aplicação.
Serve para decidir, com dados, o que vale otimizar numa fase futura —
nenhum item aqui foi corrigido automaticamente nesta fase.

**Nunca rode `EXPLAIN ANALYZE` direto em produção.** `ANALYZE` executa a
query de verdade (não é só o plano) — se a query fizer parte de um fluxo
de escrita, `ANALYZE` a executa também. Use uma cópia representativa dos
dados (staging, ou um dump restaurado localmente).

## Como usar EXPLAIN (ANALYZE, BUFFERS)

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT ...  -- a query real, com valores de exemplo no lugar dos parâmetros
```

O que observar no resultado:
- **Seq Scan** numa tabela grande (`registros_treino`, `historico_treino`)
  onde se esperava um índice → índice ausente ou não sendo usado.
- **Rows Removed by Filter** alto → filtro aplicado depois de já ter lido
  linhas demais; considerar índice composto na ordem certa.
- **Buffers: shared read** alto (vs. `shared hit`) → dados não estão no
  cache do Postgres; se for recorrente, pode indicar volume de dados que
  já pede paginação, não só índice.
- **Nested Loop** com muitas iterações → geralmente sinal de N+1 que
  escapou do ORM e foi parar no plano da própria query, ou de um join
  sem índice do lado certo.

## Queries prioritárias para investigar (em ordem)

Para cada uma, rode o `EXPLAIN (ANALYZE, BUFFERS)` da consulta SQL
equivalente ao que o service gera (pode ser obtido com
`str(query.statement.compile(compile_kwargs={"literal_binds": True}))`
num shell Python com contexto de app, ou habilitando o log de queries do
SQLAlchemy).

1. **Registros do usuário** — `RegistroService.get_all(user_id=..., load_series=True)`.
   Base de quase todas as telas (calendário, estatísticas, histórico).
2. **Histórico de treino** — join `registros_treino` ↔ `historico_treino`
   usado dentro do `load_series=True` acima.
3. **Calendário** — `GET /api/eventos`, especialmente com `ano`/`mes`
   informados (ver se o filtro está sendo aplicado em Python ou SQL).
4. **Estatísticas por músculo** — `EstatisticaService.calcular_por_musculo`.
5. **Progresso semanal** — `EstatisticaService.get_progresso_por_semana`
   (já usa `GROUP BY` agregado no SQL — bom candidato a estar OK).
6. **Últimos 30 dias** — rota de progresso usada no dashboard do aluno.
7. **Consultas professor → aluno** — qualquer rota que passe por
   `BaseService.get_target_user_id`, para confirmar que o índice de
   `aluno_professor` (`aluno_id`, `professor_id`) está sendo usado no
   `JOIN`/`EXISTS` de verificação de vínculo.

## Como medir do lado da aplicação (sem SQL manual)

Use `scripts/benchmark_queries.py` (criado nesta fase) para ter uma
medida relativa em milissegundos, sem precisar escrever SQL à mão:

```bash
python scripts/benchmark_queries.py --user-id 1
```

Ele só faz SELECT através dos services existentes, não imprime nenhum
dado sensível (senha, token, `DATABASE_URL`, API key), e não altera
nada no banco. Serve para comparar antes/depois de uma mudança, ou para
apontar qual das operações acima merece o `EXPLAIN ANALYZE` primeiro.

## Índices já existentes (não mexer sem medir)

Ver `models.py` — a lista completa está no `__table_args__` de cada
model. Resumo:

- `Treino`: `user_id`; `user_id + codigo`
- `VersaoGlobal`: `user_id + data_inicio + data_fim`
- `TreinoVersao`: `versao_id`; `treino_id`
- `RegistroTreino`: `user_id + data_registro`; `user_id + treino_id + periodo + semana`;
  `exercicio_usuario_id`; `exercicio_base_id`; `versao_id`; `periodo + semana`
- `HistoricoTreino`: `registro_id`

Se o `EXPLAIN` mostrar que algum desses não está sendo usado (Seq Scan
onde se esperava Index Scan), o mais provável é que o índice existe mas
a query não está filtrando pela mesma combinação de colunas — vale
investigar a query antes de assumir que falta índice novo.
