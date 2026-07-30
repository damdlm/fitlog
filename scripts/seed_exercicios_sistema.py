"""
Carrega data/exercises.json na tabela exercicios_sistema.

Uso:
    railway run python scripts/seed_exercicios_sistema.py

O comando `railway run` injeta a DATABASE_URL da produção como variável de
ambiente só para essa execução — o script nunca precisa saber a senha do
banco, e ela nunca fica hardcoded em nenhum arquivo.

Idempotente: pode ser executado várias vezes. Registros existentes
(identificados por id_original) são atualizados; novos são inseridos.
"""
import json
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy.dialects.postgresql import insert

# Permite rodar o script tanto de dentro de scripts/ quanto da raiz do projeto
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app          # noqa: E402
from models import db, ExercicioSistema  # noqa: E402

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

        print("Carga concluída com sucesso.")


if __name__ == "__main__":
    carregar()