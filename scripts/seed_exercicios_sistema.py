"""
Carrega data/exercises.json na tabela exercicios_sistema.

Uso:
    railway run python scripts/seed_exercicios_sistema.py

O comando `railway run` injeta a DATABASE_URL da produção como variável de
ambiente só para essa execução — o script nunca precisa saber a senha do
banco, e ela nunca fica hardcoded em nenhum arquivo.

Idempotente: pode ser executado várias vezes. Registros existentes
(identificados por id_original) são atualizados; novos são inseridos.

Registros que existiam no banco mas não estão mais presentes no JSON
(ex: duplicados removidos na curadoria) são APAGADOS de exercicios_sistema.
Isso é um hard-delete: exercicios_sistema.id é referenciado com
ondelete='CASCADE' por versao_exercicios.exercicio_base_id e
registros_treino.exercicio_base_id, então remover um exercício aqui também
remove, em cascata, qualquer treino montado ou histórico de treino de aluno
que já use esse exercício. O script imprime, antes de apagar, quantos
registros dependentes serão afetados em cada tabela, para que isso fique
visível no log de execução.
"""
import json
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert

# Permite rodar o script tanto de dentro de scripts/ quanto da raiz do projeto
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app          # noqa: E402
from models import db, ExercicioSistema, VersaoExercicio, RegistroTreino  # noqa: E402

JSON_PATH = Path(__file__).resolve().parent.parent / "data" / "exercises.json"
BATCH_SIZE = 500


def parse_registro(item: dict) -> dict:
    """Converte um objeto do JSON no dict de colunas da tabela."""
    instrucoes = item.get("instructions") or {}
    passos = item.get("instruction_steps") or {}

    data_criacao_original = None
    if item.get("created_at"):
        try:
            data_criacao_original = datetime.fromisoformat(item["created_at"])
        except ValueError:
            data_criacao_original = None

    return {
        "id_original": item["id"],
        "nome": item.get("name", ""),
        "categoria": item.get("category"),
        "parte_corpo": item.get("body_part"),
        "equipamento": item.get("equipment"),
        "instrucao_pt": instrucoes.get("pt"),
        "passos_pt": passos.get("pt"),
        "grupo_muscular": item.get("muscle_group"),
        "musculos_secundarios": item.get("secondary_muscles"),
        "nicknames": item.get("nicknames") or [],
        "alvo": item.get("target"),
        "imagem": item.get("image"),
        "gif_url": item.get("gif_url"),
        "media_id": item.get("media_id"),
        "data_criacao_original": data_criacao_original,
        "atribuicao": item.get("attribution"),
    }


def carregar():
    if not JSON_PATH.exists():
        print(f"Arquivo não encontrado: {JSON_PATH}")
        sys.exit(1)

    with open(JSON_PATH, encoding="utf-8") as f:
        registros = json.load(f)

    print(f"{len(registros)} registros encontrados em {JSON_PATH.name}")

    app = create_app()
    with app.app_context():
        total_processados = 0

        for inicio in range(0, len(registros), BATCH_SIZE):
            lote = registros[inicio:inicio + BATCH_SIZE]
            valores = [parse_registro(item) for item in lote]

            stmt = insert(ExercicioSistema).values(valores)
            stmt = stmt.on_conflict_do_update(
                index_elements=["id_original"],
                set_={
                    "nome": stmt.excluded.nome,
                    "categoria": stmt.excluded.categoria,
                    "parte_corpo": stmt.excluded.parte_corpo,
                    "equipamento": stmt.excluded.equipamento,
                    "instrucao_pt": stmt.excluded.instrucao_pt,
                    "passos_pt": stmt.excluded.passos_pt,
                    "grupo_muscular": stmt.excluded.grupo_muscular,
                    "musculos_secundarios": stmt.excluded.musculos_secundarios,
                    "nicknames": stmt.excluded.nicknames,
                    "alvo": stmt.excluded.alvo,
                    "imagem": stmt.excluded.imagem,
                    "gif_url": stmt.excluded.gif_url,
                    "media_id": stmt.excluded.media_id,
                    "data_criacao_original": stmt.excluded.data_criacao_original,
                    "atribuicao": stmt.excluded.atribuicao,
                },
            )
            db.session.execute(stmt)
            db.session.commit()

            total_processados += len(lote)
            print(f"  {total_processados}/{len(registros)} processados...")

        print("Carga (insert/update) concluída com sucesso.")

        remover_orfaos(registros)


def remover_orfaos(registros: list[dict]):
    """
    Apaga de exercicios_sistema os registros cujo id_original não está mais
    presente no JSON atual (ex: duplicados removidos na curadoria).

    HARD DELETE: por causa do ondelete='CASCADE' nas FKs de
    versao_exercicios.exercicio_base_id e registros_treino.exercicio_base_id,
    isso também apaga treinos montados e histórico de treino de qualquer
    aluno que já tenha usado esses exercícios. Antes de apagar, o script
    conta e imprime quantas linhas dependentes serão afetadas em cada
    tabela, para deixar isso visível no log.
    """
    ids_do_json = {item["id"] for item in registros}

    orfaos = ExercicioSistema.query.filter(
        ExercicioSistema.id_original.notin_(ids_do_json)
    ).all()

    if not orfaos:
        print("Nenhum exercício órfão (removido do JSON) encontrado no banco.")
        return

    print(f"\n{len(orfaos)} exercício(s) presentes no banco mas ausentes do JSON novo:")
    ids_internos = [ex.id for ex in orfaos]

    for ex in orfaos:
        n_versoes = db.session.scalar(
            select(func.count()).select_from(VersaoExercicio)
            .where(VersaoExercicio.exercicio_base_id == ex.id)
        )
        n_registros = db.session.scalar(
            select(func.count()).select_from(RegistroTreino)
            .where(RegistroTreino.exercicio_base_id == ex.id)
        )
        aviso = ""
        if n_versoes or n_registros:
            aviso = (
                f"  ATENÇÃO: será apagado em cascata de "
                f"{n_versoes} treino(s) montado(s) e {n_registros} registro(s) de histórico"
            )
        print(f"  - {ex.id_original} | {ex.nome}{aviso}")

    ExercicioSistema.query.filter(
        ExercicioSistema.id.in_(ids_internos)
    ).delete(synchronize_session=False)
    db.session.commit()

    print(f"\n{len(orfaos)} exercício(s) removido(s) de exercicios_sistema.")


if __name__ == "__main__":
    carregar()