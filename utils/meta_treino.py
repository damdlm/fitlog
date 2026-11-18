"""Meta de séries × repetições de um exercício da ficha (lote 6b, T4).

Formulário (modal "Editar treino", fichas do aluno e do professor): por
exercício marcado, três campos opcionais com a mesma chave da observação --
meta_series_<chave>, meta_reps_min_<chave>, meta_reps_max_<chave>.
"""

SERIES_MAX = 10
REPS_MAX = 100


def _inteiro(valor, minimo, maximo):
    try:
        n = int(str(valor).strip())
    except (TypeError, ValueError):
        return None
    return n if minimo <= n <= maximo else None


def normalizar_meta(series, reps_min, reps_max):
    """Valida e arruma uma meta. Devolve (series, reps_min, reps_max), com
    None no que não vale. Faixa invertida ("12 a 10") é desinvertida; só um
    lado preenchido vira número fixo (min = max)."""
    s = _inteiro(series, 1, SERIES_MAX)
    rmin = _inteiro(reps_min, 1, REPS_MAX)
    rmax = _inteiro(reps_max, 1, REPS_MAX)
    if rmin is None:
        rmin = rmax
    if rmax is None:
        rmax = rmin
    if rmin is not None and rmax is not None and rmin > rmax:
        rmin, rmax = rmax, rmin
    return s, rmin, rmax


def parse_meta_form(form, chaves):
    """{chave: (series, reps_min, reps_max)} para as chaves com alguma meta."""
    metas = {}
    for chave in chaves:
        meta = normalizar_meta(
            form.get(f'meta_series_{chave}'),
            form.get(f'meta_reps_min_{chave}'),
            form.get(f'meta_reps_max_{chave}'),
        )
        if any(v is not None for v in meta):
            metas[chave] = meta
    return metas


def formatar_reps(reps_min, reps_max):
    if reps_min is None:
        return ''
    if reps_max is None or reps_max == reps_min:
        return str(reps_min)
    return f'{reps_min}–{reps_max}'


def formatar_meta(series, reps_min, reps_max):
    """'4 × 10–12', '4 × 10', '4 séries', '10–12 reps' ou ''."""
    reps = formatar_reps(reps_min, reps_max)
    if series and reps:
        return f'{series} × {reps}'
    if series:
        return f'{series} série' + ('s' if series != 1 else '')
    if reps:
        return f'{reps} reps'
    return ''


def meta_para_json(series, reps_min, reps_max):
    """Formato usado no JavaScript do editor (CT_TREINO_METAS)."""
    return {'s': series, 'min': reps_min, 'max': reps_max}


def sugestao_progressao(ultimas_series, reps_min, reps_max):
    """Dica de progressão (R3): todas as séries da última sessão chegaram ao
    topo da meta de repetições, com carga > 0 -> sugere aumentar a carga.

    ultimas_series: lista de objetos/dicts com .carga e .repeticoes (a
    última sessão do exercício). Devolve o incremento sugerido em kg
    (2.5, ou 1.0 para cargas abaixo de 10 kg) ou None.
    """
    alvo = reps_max if reps_max is not None else reps_min
    if not alvo or not ultimas_series:
        return None

    def campo(s, nome):
        return s.get(nome) if isinstance(s, dict) else getattr(s, nome, None)

    cargas = [campo(s, 'carga') for s in ultimas_series]
    reps = [campo(s, 'repeticoes') for s in ultimas_series]
    if any(c is None or c <= 0 for c in cargas) or any(r is None for r in reps):
        return None
    if min(reps) < alvo:
        return None
    return 2.5 if max(cargas) >= 10 else 1.0
