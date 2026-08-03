# Estratégia de schema do banco

O FitLog usa uma estratégia **híbrida** para o schema do banco — importante
entender isso antes de mexer em `models.py` ou em `migrations/`.

## 1. Banco novo (dev local, ambiente novo) → `db.create_all()`

Ao subir a aplicação pela primeira vez contra um banco vazio, o
SQLAlchemy cria todas as tabelas a partir do estado atual de
`models.py` via `db.create_all()` (chamado no boot da app / nos
fixtures de teste em `tests/conftest.py`). Não existe uma migração
Alembic "baseline" com o schema inteiro — isso é proposital, pra não
manter dois lugares descrevendo a mesma coisa (os models já são a
fonte da verdade do schema inicial).

## 2. Banco existente (produção) → migrações incrementais do Alembic

Uma vez que o banco de produção já existe e tem dados, `db.create_all()`
não altera tabelas existentes (ele só cria o que não existe). Qualquer
mudança de schema em um banco que já está rodando — nova coluna, nova
tabela, alteração de tipo — **precisa** de uma migração Alembic:

```bash
# depois de alterar models.py
alembic revision --autogenerate -m "descricao da mudanca"
# revisar o arquivo gerado em migrations/versions/ antes de commitar
alembic upgrade head
```

Por isso `migrations/versions/` hoje tem só migrações incrementais
(ex: `a1b2c3d4e5f6_add_tempo_treino_to_historico_treino.py`, que
adiciona uma coluna) em vez de uma migração completa do zero — elas
assumem que o schema-base já foi criado por `create_all()` em algum
momento.

## Regra prática ao alterar `models.py`

- **Só mexendo em dev local, sem produção rodando ainda?** Não precisa
  gerar migração — `create_all()` já resolve.
- **Mudança que vai rodar contra um banco de produção existente
  (Railway)?** Sempre gere e commite a migração Alembic correspondente,
  e rode `alembic upgrade head` como parte do deploy.

## Verificando estado atual

```bash
alembic current       # revisão aplicada no banco
alembic history       # todas as revisões conhecidas
```