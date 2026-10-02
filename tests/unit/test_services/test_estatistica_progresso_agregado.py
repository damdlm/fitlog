"""Agregação do gráfico do dashboard por semana e por rodada de treino."""
from datetime import date, datetime, timedelta

from services.estatistica_service import EstatisticaService

HOJE = date(2026, 9, 28)  # segunda-feira
TREINOS = [{'codigo': c} for c in 'ABCD']
_LETRA = {1: 'A', 2: 'B', 3: 'C', 4: 'D'}


def _s(dias_atras, treino_id, volume, n_series=3, hora=8):
    d = HOJE - timedelta(days=dias_atras)
    return {
        'dia': d, 'inicio': datetime(d.year, d.month, d.day, hora),
        'treino': _LETRA[treino_id], 'volume': float(volume),
        'soma_carga': float(volume) / 10, 'n_series': n_series,
    }


def test_por_treino_rodada_reinicia_quando_treino_repete():
    # A, B, D e depois volta pro A -> rodada 1 = A+B+C(0)+D, rodada 2 = só o novo A
    sessoes = [_s(20, 1, 100), _s(18, 2, 200), _s(16, 4, 400), _s(10, 1, 150)]
    r = EstatisticaService.agregar_progresso(sessoes, TREINOS, 'treino', hoje=HOJE)
    assert r['volumes'] == [700.0, 150.0]
    assert r['detalhes'][0] == [
        {'codigo': 'A', 'volume': 100.0}, {'codigo': 'B', 'volume': 200.0},
        {'codigo': 'C', 'volume': 0.0}, {'codigo': 'D', 'volume': 400.0},
    ]
    assert r['detalhes'][1][0] == {'codigo': 'A', 'volume': 150.0}
    assert r['detalhes'][1][1]['volume'] == 0.0


def test_por_treino_filtro_individual_traz_zero_na_rodada_sem_o_treino():
    sessoes = [_s(20, 1, 100), _s(18, 2, 200), _s(10, 2, 250), _s(8, 1, 120)]
    # rodadas: [A,B] | [B, A]  -> C individual: 0 em todas
    r = EstatisticaService.agregar_progresso(sessoes, TREINOS, 'treino', treino='C', hoje=HOJE)
    assert r['volumes'] == [0.0, 0.0]
    r = EstatisticaService.agregar_progresso(sessoes, TREINOS, 'treino', treino='B', hoje=HOJE)
    assert r['volumes'] == [200.0, 250.0]
    assert r['detalhes'] == [[], []]


def test_por_semana_soma_so_o_que_foi_treinado_na_semana():
    # semana de 21/09: A(seg), B(qua), D(sex); semana de 28/09 (hoje): A, C
    sessoes = [_s(7, 1, 100), _s(5, 2, 200), _s(3, 4, 400), _s(0, 1, 110), _s(0, 3, 300, hora=10)]
    r = EstatisticaService.agregar_progresso(sessoes, TREINOS, 'semana', hoje=HOJE)
    assert r['volumes'][-2:] == [700.0, 410.0]
    assert r['semanas'][-1] == '28/09'
    assert r['semanas'][-2] == '21/09–27/09'


def test_por_semana_preenche_semanas_sem_treino_com_zero_e_respeita_janela():
    sessoes = [_s(0, 1, 100), _s(40, 1, 999)]  # 40 dias atrás fica fora
    r = EstatisticaService.agregar_progresso(sessoes, TREINOS, 'semana', hoje=HOJE)
    assert sum(r['volumes']) == 100.0
    assert r['volumes'][0] == 0.0
    # 30 dias tocam 6 semanas (seg-dom); a 1ª é só o domingo 30/08, vazia, e some
    assert len(r['semanas']) == len(r['volumes']) == 5
    assert r['semanas'][0] == '31/08–06/09'


def test_por_semana_ponta_parcial_com_treino_e_mantida():
    sessoes = [_s(29, 1, 100)]  # domingo 30/08, semana cortada mas com treino
    r = EstatisticaService.agregar_progresso(sessoes, TREINOS, 'semana', hoje=HOJE)
    assert r['semanas'][0] == '30/08'
    assert r['volumes'][0] == 100.0


def test_sem_sessoes_retorna_vazio():
    for modo in ('semana', 'treino'):
        r = EstatisticaService.agregar_progresso([], TREINOS, modo, hoje=HOJE)
        assert r['semanas'] == [] and r['volumes'] == []


def test_carga_media_e_media_das_series_do_ponto():
    sessoes = [_s(1, 1, 100, n_series=2), _s(1, 2, 300, n_series=2)]
    r = EstatisticaService.agregar_progresso(sessoes, TREINOS, 'treino', hoje=HOJE)
    assert r['cargas_medias'] == [round((10 + 30) / 4, 2)]


def test_treino_com_mesma_letra_de_versoes_diferentes_conta_como_o_mesmo():
    # v1 (A, B) encerrada e v2 (A) ativa: os dois "A" são o mesmo treino,
    # então o 2º A abre a rodada 2 e nada some do gráfico
    sessoes = [_s(20, 1, 100), _s(18, 2, 200), _s(5, 1, 150)]
    r = EstatisticaService.agregar_progresso(sessoes, TREINOS, 'treino', hoje=HOJE)
    assert r['volumes'] == [300.0, 150.0]
    r = EstatisticaService.agregar_progresso(sessoes, TREINOS, 'semana', hoje=HOJE)
    assert sum(r['volumes']) == 450.0


def test_hoje_brasil_nao_adianta_o_dia_a_noite(monkeypatch):
    from datetime import timezone
    import services.estatistica_service as mod

    class _Agora(datetime):
        @classmethod
        def now(cls, tz=None):
            base = datetime(2026, 9, 29, 1, 30, tzinfo=timezone.utc)  # 22h30 de 28/09 no Brasil
            return base.astimezone(tz) if tz else base

    monkeypatch.setattr(mod, 'datetime', _Agora)
    assert EstatisticaService.hoje_brasil() == date(2026, 9, 28)

def test_sessoes_por_treino_traz_detalhe_pro_modal_ao_clicar_na_barra():
    """sessoes_por_treino alimenta o modal que abre ao clicar numa barra
    do gráfico: pra cada treino que apareceu naquele ponto, precisa de
    volume, carga média, nº de séries e os dias em que foi feito --
    mesmo filtrando por um treino específico, pois o front pode mostrar
    o modal de qualquer uma das barras renderizadas."""
    sessoes = [_s(20, 1, 100, n_series=2), _s(18, 2, 200, n_series=2)]
    r = EstatisticaService.agregar_progresso(sessoes, TREINOS, 'treino', hoje=HOJE)
    spt = r['sessoes_por_treino'][0]
    assert spt['A'] == {
        'volume': 100.0, 'carga_media': 5.0, 'n_series': 2,
        'dias': [(HOJE - timedelta(days=20)).isoformat()],
    }
    assert spt['B']['volume'] == 200.0
    assert spt['B']['n_series'] == 2

    # mesmo com filtro de um treino só, sessoes_por_treino continua
    # trazendo todos os treinos daquele ponto (não só o filtrado)
    r_filtrado = EstatisticaService.agregar_progresso(sessoes, TREINOS, 'treino', treino='A', hoje=HOJE)
    assert set(r_filtrado['sessoes_por_treino'][0].keys()) == {'A', 'B'}


def test_sessoes_por_treino_junta_dias_diferentes_do_mesmo_treino():
    sessoes = [_s(20, 1, 100), _s(18, 1, 100)]  # A feito 2x na mesma rodada (?) -- junta os dias
    r = EstatisticaService.agregar_progresso(sessoes, TREINOS, 'semana', hoje=HOJE)
    ponto = next(p for p in r['sessoes_por_treino'] if p)
    assert len(ponto['A']['dias']) == 2