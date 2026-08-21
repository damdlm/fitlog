"""
Substitui o conteúdo da tabela `musculos` pelos valores distintos do
campo `grupo_muscular` de `exercicios_sistema` (28 valores hoje, ex:
"Peito", "Dorsais", "Isquiotibiais" -- mais granular que o taxonomy
antigo de ~10 músculos criado manualmente em data/default_workouts.py).

POR QUE NÃO É SÓ "DELETE + INSERT"
-----------------------------------
`exercicios_usuario.musculo_id` referencia `musculos.id` via FK sem
ondelete definido (padrão RESTRICT/NO ACTION) -- apagar um músculo
ainda referenciado por algum exercício de usuário falha no banco (ou,
se a constraint não estivesse lá, deixaria o exercício "orfão", sem
músculo, silenciosamente).

O que este script faz, em ordem:
1. Lê os valores distintos de `grupo_muscular` em exercicios_sistema
   (ignora nulos/vazios) -- esse é o novo conjunto "alvo".
2. Cria os músculos do novo conjunto que ainda não existem (match por
   nome_exibicao -- se já existir um músculo com esse nome, reaproveita
   em vez de duplicar).
3. Para cada músculo ANTIGO que não faz parte do novo conjunto:
   - Se estiver em MAPEAMENTO_ANTIGO_NOVO abaixo, remapeia todo
     ExercicioUsuario.musculo_id que apontava pra ele para o músculo
     novo equivalente, e então apaga o músculo antigo (já sem
     referências).
   - Se NÃO estiver no mapeamento:
       - sem nenhum ExercicioUsuario apontando pra ele -> apaga (é só
         lixo não usado);
       - com algum ExercicioUsuario apontando pra ele -> MANTÉM e avisa
         no relatório final. Nunca apaga algo em uso sem saber pra
         onde mandar.

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

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app                              # noqa: E402
from models import db, Musculo, ExercicioSistema, ExercicioUsuario  # noqa: E402

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


def _slug(nome_exibicao: str) -> str:
    return nome_exibicao.strip().lower()


def sincronizar(dry_run: bool):
    app = create_app()
    with app.app_context():
        # 1) Conjunto alvo, a partir de exercicios_sistema.
        linhas = db.session.query(ExercicioSistema.grupo_muscular).distinct().all()
        novo_conjunto = sorted({
            (nome or "").strip() for (nome,) in linhas if nome and nome.strip()
        })
        print(f"{len(novo_conjunto)} grupos musculares distintos encontrados em exercicios_sistema.")

        musculos_por_nome = {m.nome_exibicao: m for m in Musculo.query.all()}

        # 2) Cria os que faltam.
        criados = []
        for nome in novo_conjunto:
            if nome not in musculos_por_nome:
                novo = Musculo(nome=_slug(nome), nome_exibicao=nome)
                db.session.add(novo)
                db.session.flush()
                musculos_por_nome[nome] = novo
                criados.append(nome)

        # 3) Trata os músculos antigos que não estão no novo conjunto.
        remapeados = []      # (nome_antigo, nome_novo, qtd_exercicios)
        removidos_sem_uso = []
        mantidos_sem_mapeamento = []  # (nome_antigo, qtd_exercicios)

        antigos = [m for m in musculos_por_nome.values() if m.nome_exibicao not in novo_conjunto]
        for antigo in antigos:
            nome_antigo = antigo.nome_exibicao
            destino_nome = MAPEAMENTO_ANTIGO_NOVO.get(nome_antigo)

            if destino_nome and destino_nome in musculos_por_nome:
                destino = musculos_por_nome[destino_nome]
                qtd = ExercicioUsuario.query.filter_by(musculo_id=antigo.id).update(
                    {"musculo_id": destino.id}
                )
                db.session.delete(antigo)
                remapeados.append((nome_antigo, destino_nome, qtd))
                continue

            qtd_em_uso = ExercicioUsuario.query.filter_by(musculo_id=antigo.id).count()
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
            print(f"  {antigo} -> {novo}  ({qtd} exercício(s) de usuário atualizados)")

        print(f"\nMúsculos antigos sem uso, removidos ({len(removidos_sem_uso)}):")
        for nome in removidos_sem_uso:
            print(f"  - {nome}")

        if mantidos_sem_mapeamento:
            print(f"\nATENÇÃO -- músculos antigos MANTIDOS por segurança "
                  f"({len(mantidos_sem_mapeamento)}), pois ainda têm exercícios de "
                  f"usuário apontando pra eles e não têm mapeamento definido em "
                  f"MAPEAMENTO_ANTIGO_NOVO:")
            for nome, qtd in mantidos_sem_mapeamento:
                print(f"  ! {nome}  ({qtd} exercício(s) de usuário)")
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