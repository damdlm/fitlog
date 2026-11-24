# FitLog — guia rápido para o Claude

App Flask (Python 3.12, SQLAlchemy, Alembic, Jinja, Bootstrap 5.3, Chart.js) para
alunos registrarem treinos e professores gerenciarem fichas. Produção no Railway
(www.fitlog.vip), Postgres + Redis. Responda e escreva em português do Brasil.

## Entrega e commits (regras do dono do projeto)

- O dono faz os commits. Entregue os arquivos alterados: até 4 arquivos soltos,
  com o caminho no repositório; mais que isso, um zip com as pastas.
- Sempre mande junto o texto do commit (em português, estilo
  `feat(area): ...` / `fix(area): ...`, com tópicos do que mudou).
- Nunca adicione linhas `Co-Authored-By` ou `Claude-Session` no commit.
- Depois que ele commitar: confira se os arquivos batem com a entrega, o CI
  (`gh run list -R damdlm/fitlog -L 1`) e o deploy no Railway antes de seguir.

## Arquivos: cuidados que já custaram retrabalho

- **Quebra de linha é mista, arquivo a arquivo** (CRLF em boa parte de
  `templates/`, `static/js`, `static/css`, `migrations/versions` e alguns
  testes; LF no resto). Preserve a do arquivo: no Python use
  `open(p, newline='')` para ler e gravar. Conferir: `grep -c $'\r$' arquivo`.
- Arquivos grandes — leia por trecho (`grep -n` + `Read` com offset/limit),
  nunca inteiros: `models.py`, `templates/aluno/estatisticas.html`,
  `templates/register/registrar_treino.html`, `routes/api_routes.py`,
  `routes/professor_routes.py`, `data/exercises.json` (1.300+ exercícios).
- Catálogo (`ExercicioSistema`): o músculo principal é `alvo`, traduzido por
  `musculo_principal` / `musculo_principal_de()` em `models.py`.
  `grupo_muscular` é só o PRIMEIRO SECUNDÁRIO no dataset (supino = "Tríceps").
- Datas: o "hoje" do app é o de Brasília
  (`EstatisticaService.hoje_brasil()`, `utils.format_utils.data_atual()`).
  `date.today()` / `datetime.utcnow()` no servidor são UTC e erram entre 21h e
  meia-noite. Em testes, crie fichas com `data_inicio` alguns dias no passado.
- Mídia dos exercícios (imagens/GIFs) é © Gym Visual — licença a confirmar.
  Código de terceiros fica em `static/vendor/` com LICENSE e entrada no
  `static/vendor/README.md` (ex.: `musclemap/`, MIT).

## Tema claro/escuro (CSS)

- Cores via variáveis `var(--fl-c-*, <cor do tema claro>)` — sempre com a cor
  clara como reserva, e a variável precisa existir em `static/css/tema-escuro.css`.
- Cor fixa (igual nos dois temas, ex.: laranja #F28C33) leva o comentário
  `/* tema: fixo */` na mesma linha. `tests/.../test_lote6e.py` confere isso.
- Modal aberto durante o "modo treino" (registrar_treino.html) precisa entrar
  na lista de z-index 2000 desse template (o overlay é 1900).

## Testes

- Rápido (durante o trabalho), só o que mexeu:
  `python -m pytest -q -x --no-cov -n auto -p no:cacheprovider <arquivos ou -k expr>`
- Completo (antes de entregar): `python -m pytest -q -n auto -p no:cacheprovider tests 2>&1 | tail -5`
  (~10 min com 2 CPUs; em série ~19). Filtre a saída: são ~1.700 warnings.
- CI (`.github/workflows/ci.yml`): flake8 `E9,F63,F7,F82` quebra o build;
  cobertura mínima 85% somando os 4 grupos (unit, security, integration, resto).
- Helpers de teste usados em vários arquivos:
  `tests/unit/test_services/test_exercicio_service_extra.py` (`_criar_usuario`
  com senha `SenhaForte123!`, `_criar_versao_com_treino`, `_criar_exercicio_base`).
  Recursos premium (estatísticas) precisam de `BillingService.iniciar_trial(u)`.
- Teste de migração: carregue o arquivo com `importlib` e rode
  `downgrade`/`upgrade` via `alembic.operations.Operations` (exemplo em
  `tests/integration/test_routes/test_mapa_muscular.py::test_migracao_peso`).

## Simular telas (Playwright)

Use `tests/ux/harness.py` — não reescreva login, banco, tutoriais, bloqueio de
rede nem coleta de erros. Base realista em cache (`tests/ux/seed.py`: usuários
`prof`, `ana`, `bruno`, `dani`, `novo`, `adm`; senha `senha forte 1`).

```python
from tests.ux.harness import Sessao
with Sessao('cel') as s:            # 'cel' | 'escuro' | 'desk'
    pg = s.entrar('ana')
    pg.goto(s.url('/aluno/estatisticas'))
    print(s.texto(pg, '#mapaMuscular .mm-painel'), s.erros(pg), s.largura(pg))
```

Prefira `s.texto()` a screenshot; tire foto (`s.foto`) só quando a mudança é
visual — imagem custa caro. Exemplo completo: `tests/ux/exemplo_mapa.py`.

## Produção (Railway)

- Projeto `8502e213-4d0c-4f64-a401-fc7508f23498`; serviço web
  `d9076ec9-e81e-4837-983b-de8566629f01`. Deploy sai da `main` depois do CI.
- Migrações: `alembic upgrade head` no Pre-Deploy do serviço web. Em produção o
  app NÃO faz `create_all()`. Toda coluna/tabela nova precisa de migração em
  `migrations/versions/` (encadeada no `down_revision` da última).
- Crons são serviços separados com o mesmo código (`flask <comando>`), ex.:
  `fitlog-cron-versoes-expiracao` roda `flask versoes-alertar-expiracao` às
  8h UTC e também aplica as fichas agendadas "quando a atual vencer".
- Conferir um deploy: status do deployment, logs com
  `alembic OR Traceback OR "Erro ao"`, e taxa de 5xx da última hora.
- Logs com nível "error" que começam com `INFO` são só o gunicorn/alembic
  escrevendo no stderr.
