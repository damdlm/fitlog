"""
Mede o tempo das operações de leitura mais importantes do FitLog.

Uso:
    python scripts/benchmark_queries.py --user-id 1
    railway run python scripts/benchmark_queries.py --user-id 1   # contra staging

Só executa SELECT (via os services já existentes) — não altera nenhum
dado no banco. Não imprime senhas, tokens, DATABASE_URL nem API keys;
só nomes de operação e tempos em milissegundos.

Este script é um apoio de diagnóstico da Fase 3 (ver
docs/PERFORMANCE_DIAGNOSTICO.md). Ele não corrige nada sozinho — serve
para decidir, com números, o que vale a pena otimizar depois.
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app  # noqa: E402


def _medir(nome, fn, repeticoes=5):
    tempos = []
    resultado = None
    for _ in range(repeticoes):
        inicio = time.perf_counter()
        resultado = fn()
        tempos.append((time.perf_counter() - inicio) * 1000)
    tempos.sort()
    mediana = tempos[len(tempos) // 2]
    tamanho = None
    try:
        tamanho = len(resultado)
    except TypeError:
        pass
    tamanho_str = f", {tamanho} registro(s)" if tamanho is not None else ""
    print(f"  {nome:<40} mediana={mediana:8.2f}ms  min={min(tempos):8.2f}ms  max={max(tempos):8.2f}ms{tamanho_str}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-id", type=int, required=True, help="ID do usuário a usar como base para as consultas")
    parser.add_argument("--repeticoes", type=int, default=5, help="Quantas vezes repetir cada consulta (padrão: 5)")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        from services.estatistica_service import EstatisticaService
        from services.registro_service import RegistroService
        from services.treino_service import TreinoService

        user_id = args.user_id
        n = args.repeticoes

        print(f"\nBenchmark de queries de leitura — user_id={user_id}, {n} repetições cada\n")

        _medir("EstatisticaService.calcular_por_treino",
               lambda: EstatisticaService.calcular_por_treino(user_id=user_id), n)

        _medir("EstatisticaService.calcular_por_musculo",
               lambda: EstatisticaService.calcular_por_musculo(user_id=user_id), n)

        _medir("EstatisticaService.get_progresso_por_semana",
               lambda: EstatisticaService.get_progresso_por_semana(user_id=user_id), n)

        _medir("RegistroService.get_all (load_series=True)",
               lambda: RegistroService.get_all(user_id=user_id, load_series=True), n)

        _medir("TreinoService.get_all",
               lambda: TreinoService.get_all(user_id=user_id), n)

        print("\nPara ver o plano de execução de alguma dessas queries no Postgres,")
        print("use EXPLAIN (ANALYZE, BUFFERS) — ver docs/PERFORMANCE_DIAGNOSTICO.md.\n")


if __name__ == "__main__":
    main()
