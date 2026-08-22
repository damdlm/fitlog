"""
Substitui o conteúdo da tabela `musculos` pelos valores distintos do
campo `grupo_muscular` de `exercicios_sistema` (28 valores hoje, ex:
"Peito", "Dorsais", "Isquiotibiais" -- mais granular que o taxonomy
antigo de ~10 músculos criado manualmente em data/default_workouts.py).

POR QUE NÃO É SÓ "DELETE + INSERT"
-----------------------------------
Qualquer tabela com FK pra `musculos.id` (sem ondelete definido, padrão
RESTRICT/NO ACTION) impede apagar um músculo ainda referenciado. O óbvio
é `exercicios_usuario.musculo_id` -- mas o banco de produção também tem
`exercicios_base` (tabela legada, descontinuada e sem model no
SQLAlchemy, então invisível pra quem só olha models.py) com a mesma FK.
Por isso este script NÃO usa uma lista fixa de tabelas: ele descobre
via introspecção do banco (SQLAlchemy Inspector) toda tabela+coluna que
referencia musculos.id, incluindo tabelas legadas -- e trata todas elas
igual, com UPDATE/COUNT via SQL bruto (não dá pra usar um Model do
SQLAlchemy pra uma tabela que não tem Model).

O que este script faz, em ordem:
1. Lê os valores distintos de `grupo_muscular` em exercicios_sistema
   (ignora nulos/vazios), agrupados por slug pra tolerar variações de
   texto (ex: "Peito" e "peito") que apontam pro mesmo músculo, e
   junta com CATEGORIAS_ADICIONAIS abaixo -- esse é o novo conjunto
   "alvo" (grupo_muscular + categorias aprovadas manualmente).
2. Cria os músculos do novo conjunto que ainda não existem (match por
   nome_exibicao e por slug -- se já existir, reaproveita em vez de
   duplicar).
3. Descobre todas as tabelas com FK pra musculos.id (introspecção).
4. Para cada músculo ANTIGO que não faz parte do novo conjunto:
   - Se estiver em MAPEAMENTO_ANTIGO_NOVO abaixo, remapeia (UPDATE) a
     referência em TODAS as tabelas dependentes pro músculo novo
     equivalente, e então apaga o músculo antigo (já sem referências).
   - Se NÃO estiver no mapeamento:
       - sem nenhuma referência em nenhuma tabela dependente -> apaga
         (é só lixo não usado);
       - com alguma referência -> MANTÉM e avisa no relatório final.
         Nunca apaga algo em uso sem saber pra onde mandar. Se depois
         de olhar o aviso você decidir que aquele nome deve continuar
         existindo como categoria própria (em vez de remapear pra uma
         existente), adicione ele em CATEGORIAS_ADICIONAIS e rode de
         novo -- ele passa a fazer parte do conjunto alvo e some do
         aviso.

MAPEAMENTO_ANTIGO_NOVO foi definido a partir do taxonomy atual
(data/default_workouts.py:MUSCLE_MAPPING) comparado com os 28 valores
reais de grupo_muscular -- ajuste antes de rodar se o seu banco tiver
nomes diferentes desses ~10 (rode primeiro com --dry-run pra
conferir).

Uso:
    railway run python scripts/sync_musculos_de_exercicios_sistema.py --dry-run
    railway run python scripts/sync_musculos_de_exercicios_sistema.py

Idempotente: pode ser executado várias vezes sem duplicar nada.
"""
import sys
import argparse
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text, inspect as sa_inspect       # noqa: E402
from app import create_app                                # noqa: E402
from models import db, Musculo, ExercicioSistema          # noqa: E402

# Nome antigo (como está hoje em `musculos.nome_exibicao`) -> nome novo
# (como aparece em exercicios_sistema.grupo_muscular). Só precisa de
# entrada aqui pros nomes antigos que NÃO batem exatamente com um
# nome do novo conjunto (os que já batem, ex: "Bíceps", "Ombros",
# "Tríceps", "Quadríceps", "Glúteos", "Panturrilhas", são reaproveitados
# automaticamente, sem precisar remapear nada).
MAPEAMENTO_ANTIGO_NOVO = {
    "Peitoral": "Peito",
    "Costas": "Dorsais",
    "Posterior de Coxa": "Isquiotibiais",
    "Abdômen": "Abdominais",
}

# Categorias que NÃO existem em exercicios_sistema.grupo_muscular, mas
# devem ser tratadas como parte oficial do catálogo novo mesmo assim
# (mantidas/criadas via INSERT, nunca removidas ou remapeadas). Use
# isso pros músculos antigos que o relatório de "MANTIDOS por
# segurança" apontar e que você decidiu que continuam válidos como
# categoria própria, em vez de remapear pra um músculo existente.
CATEGORIAS_ADICIONAIS = [
    "Abdutores",
    "Adutores",
    "Pescoço",
]


def _slug(nome_exibicao: str) -> str:
    return nome_exibicao.strip().lower()


def _tabelas_dependentes_de_musculos():
    """Descobre, via introspecção do banco, toda tabela+coluna com FK
    pra musculos.id -- inclusive tabelas legadas sem model no
    SQLAlchemy (ex: exercicios_base), que uma busca no código-fonte
    (models.py, services/) não enxergaria.

    Importante: a introspecção usa db.session.connection() -- a MESMA
    conexão/transação já aberta pela sessão -- e não db.engine (que
    pega uma conexão nova do pool). Especialmente em SQLite (onde só
    existe uma transação por conexão), inspecionar via uma conexão
    separada faz o Inspector encerrar/fazer rollback da SUA própria
    transação ao terminar, e como é a MESMA conexão física por baixo,
    isso derruba silenciosamente qualquer INSERT/UPDATE que a sessão
    já tinha dado flush() mas ainda não tinha commitado -- os
    músculos recém-criados na etapa 2 desapareciam antes do
    remapeamento rodar. Em Postgres cada conexão é isolada de verdade,
    então esse sintoma específico não apareceria lá -- mas usar a
    conexão da sessão é a forma correta em qualquer banco."""
    insp = sa_inspect(db.session.connection())
    dependentes = []
    for nome_tabela in insp.get_table_names():
        if nome_tabela == "musculos":
            continue
        for fk in insp.get_foreign_keys(nome_tabela):
            if fk.get("referred_table") == "musculos":
                for coluna in fk.get("constrained_columns") or []:
                    dependentes.append((nome_tabela, coluna))
    return dependentes


def _contar_uso(dependentes, musculo_id):
    total = 0
    for tabela, coluna in dependentes:
        total += db.session.execute(
            text(f'SELECT COUNT(*) FROM "{tabela}" WHERE "{coluna}" = :id'),
            {"id": musculo_id}
        ).scalar()
    return total


def _remapear(dependentes, antigo_id, novo_id):
    total = 0
    for tabela, coluna in dependentes:
        resultado = db.session.execute(
            text(f'UPDATE "{tabela}" SET "{coluna}" = :novo WHERE "{coluna}" = :antigo'),
            {"novo": novo_id, "antigo": antigo_id}
        )
        total += resultado.rowcount
    return total


def sincronizar(dry_run: bool):
    app = create_app()
    with app.app_context():
        # 1) Conjunto alvo, a partir de exercicios_sistema -- agrupado por
        #    slug (não só por string exata), pra tolerar variações de texto
        #    (ex: "Peito" e "peito", ou espaço extra) que já existiam na
        #    coluna grupo_muscular e apontam pro mesmo músculo. Sem isso, a
        #    segunda variante tentava criar um Musculo com o mesmo slug e
        #    estourava a constraint UNIQUE de musculos.nome.
        linhas = db.session.query(ExercicioSistema.grupo_muscular).distinct().all()
        brutos = [(nome or "").strip() for (nome,) in linhas if nome and nome.strip()]
        brutos += CATEGORIAS_ADICIONAIS

        por_slug = defaultdict(list)
        for nome in brutos:
            por_slug[_slug(nome)].append(nome)

        musculos_existentes = Musculo.query.all()
        existentes_por_slug = {m.nome: m for m in musculos_existentes}
        musculos_por_nome = {m.nome_exibicao: m for m in musculos_existentes}

        def _escolher_canonico(variantes, slug):
            # Se já existe um músculo com esse slug, usa o nome_exibicao
            # dele como canônico (não renomeia algo que já está estável).
            existente = existentes_por_slug.get(slug)
            if existente:
                return existente.nome_exibicao
            # Senão, prefere a variante com inicial maiúscula; entre
            # empatadas, ordem alfabética decide.
            com_maiuscula = sorted(v for v in variantes if v[:1].isupper())
            return com_maiuscula[0] if com_maiuscula else sorted(variantes)[0]

        variantes_por_slug = {slug: vs for slug, vs in por_slug.items() if len(vs) > 1}
        novo_conjunto = sorted(_escolher_canonico(vs, slug) for slug, vs in por_slug.items())

        print(f"{len(novo_conjunto)} categorias no conjunto alvo "
              f"({len(brutos) - len(CATEGORIAS_ADICIONAIS)} de exercicios_sistema.grupo_muscular "
              f"+ {len(CATEGORIAS_ADICIONAIS)} em CATEGORIAS_ADICIONAIS).")
        if variantes_por_slug:
            print(f"\nAviso: {len(variantes_por_slug)} slug(s) com mais de uma variante de texto "
                  f"em exercicios_sistema.grupo_muscular (tratadas como um único músculo):")
            for slug, vs in variantes_por_slug.items():
                print(f"  {slug}: {vs}")

        # 2) Cria os que faltam -- checando por slug também (não só por
        #    nome_exibicao), como segunda camada de proteção contra a
        #    mesma classe de colisão.
        criados = []
        for nome in novo_conjunto:
            slug = _slug(nome)
            if nome in musculos_por_nome or slug in existentes_por_slug:
                continue
            novo = Musculo(nome=slug, nome_exibicao=nome)
            db.session.add(novo)
            db.session.flush()
            musculos_por_nome[nome] = novo
            existentes_por_slug[slug] = novo
            criados.append(nome)

        # 3) Descobre todas as tabelas com FK pra musculos.id -- inclusive
        #    legadas sem model (ex: exercicios_base).
        dependentes = _tabelas_dependentes_de_musculos()
        print(f"\nTabelas com FK para musculos.id: "
              f"{', '.join(f'{t}.{c}' for t, c in dependentes) or '(nenhuma)'}")

        # 4) Trata os músculos antigos que não estão no novo conjunto.
        remapeados = []      # (nome_antigo, nome_novo, qtd_referencias)
        removidos_sem_uso = []
        mantidos_sem_mapeamento = []  # (nome_antigo, qtd_referencias)

        antigos = [m for m in musculos_por_nome.values() if m.nome_exibicao not in novo_conjunto]
        for antigo in antigos:
            nome_antigo = antigo.nome_exibicao
            destino_nome = MAPEAMENTO_ANTIGO_NOVO.get(nome_antigo)

            if destino_nome and destino_nome in musculos_por_nome:
                destino = musculos_por_nome[destino_nome]
                qtd = _remapear(dependentes, antigo.id, destino.id)
                db.session.delete(antigo)
                remapeados.append((nome_antigo, destino_nome, qtd))
                continue

            qtd_em_uso = _contar_uso(dependentes, antigo.id)
            if qtd_em_uso == 0:
                db.session.delete(antigo)
                removidos_sem_uso.append(nome_antigo)
            else:
                mantidos_sem_mapeamento.append((nome_antigo, qtd_em_uso))

        # ---- Relatório ----
        print(f"\nMúsculos criados ({len(criados)}):")
        for nome in criados:
            print(f"  + {nome}")

        print(f"\nMúsculos remapeados e removidos ({len(remapeados)}):")
        for antigo, novo, qtd in remapeados:
            print(f"  {antigo} -> {novo}  ({qtd} referência(s) atualizadas)")

        print(f"\nMúsculos antigos sem uso, removidos ({len(removidos_sem_uso)}):")
        for nome in removidos_sem_uso:
            print(f"  - {nome}")

        if mantidos_sem_mapeamento:
            print(f"\nATENÇÃO -- músculos antigos MANTIDOS por segurança "
                  f"({len(mantidos_sem_mapeamento)}), pois ainda têm referências "
                  f"em alguma tabela e não têm mapeamento definido em "
                  f"MAPEAMENTO_ANTIGO_NOVO:")
            for nome, qtd in mantidos_sem_mapeamento:
                print(f"  ! {nome}  ({qtd} referência(s))")
            print("  Adicione uma entrada pra esses nomes em MAPEAMENTO_ANTIGO_NOVO "
                  "e rode de novo, ou trate manualmente.")

        if dry_run:
            db.session.rollback()
            print("\n[--dry-run] Nada foi salvo no banco.")
        else:
            db.session.commit()
            print("\nSincronização concluída e salva.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                         help="Mostra o que seria feito, sem salvar no banco.")
    args = parser.parse_args()
    sincronizar(dry_run=args.dry_run)