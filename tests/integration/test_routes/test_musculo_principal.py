"""Músculo principal do catálogo: vem de `alvo` (traduzido para os nomes da
tabela musculos), não de `grupo_muscular`, que no dataset é o primeiro
músculo SECUNDÁRIO (supino reto: grupo "Tríceps", alvo "Peitorais")."""
import json
from datetime import datetime

from models import (db, User, ExercicioSistema, VersaoGlobal, TreinoVersao, RegistroTreino, HistoricoTreino,
                    ALVO_PARA_MUSCULO, musculo_principal_de)
from services.catalogo_service import CatalogoService
from services.estatistica_service import EstatisticaService
from utils.exercise_utils import buscar_musculo_no_catalogo


def _ex(id_original, nome, alvo, grupo):
    ex = ExercicioSistema(id_original=id_original, nome=nome, alvo=alvo, grupo_muscular=grupo)
    db.session.add(ex)
    db.session.commit()
    return ex


def test_regra():
    assert musculo_principal_de('Peitorais', 'Tríceps') == 'Peito'
    assert musculo_principal_de('Bíceps', 'Antebraços') == 'Bíceps'
    assert musculo_principal_de('Dorsais', 'Bíceps') == 'Grande dorsal'
    assert musculo_principal_de(None, 'Quadríceps') == 'Quadríceps'
    assert musculo_principal_de('', 'Peito') == 'Peito'
    assert ExercicioSistema(alvo='Deltoides', grupo_muscular='Trapézio').musculo_principal == 'Ombros'
    assert ExercicioSistema(alvo='Abdômen', grupo_muscular='Oblíquos').musculo_nome == 'Abdominais'


def test_todo_alvo_do_catalogo_vira_um_musculo_que_o_app_conhece():
    """A tabela musculos é montada com os valores de grupo_muscular mais
    as categorias adicionais (scripts/sync_musculos_de_exercicios_sistema.py)."""
    from scripts.sync_musculos_de_exercicios_sistema import CATEGORIAS_ADICIONAIS
    with open('data/exercises.json', encoding='utf-8') as f:
        catalogo = json.load(f)
    conhecidos = {e.get('muscle_group') for e in catalogo} | set(CATEGORIAS_ADICIONAIS)
    alvos = {e.get('target') for e in catalogo if e.get('target')}
    assert {musculo_principal_de(a, None) for a in alvos} <= conhecidos
    assert set(ALVO_PARA_MUSCULO.values()) <= conhecidos


def test_catalogo_busca_e_lista_pelo_principal(app):
    with app.app_context():
        _ex('mp1', 'Supino reto com barra', 'Peitorais', 'Tríceps')
        _ex('mp2', 'Rosca direta com barra', 'Bíceps', 'Antebraços')
        _ex('mp3', 'Agachamento antigo', None, 'Quadríceps')
        assert [e['nome'] for e in CatalogoService.buscar_exercicios(musculo='Peito')] == ['Supino reto com barra']
        assert CatalogoService.buscar_exercicios(musculo='Tríceps') == []
        assert [e['nome'] for e in CatalogoService.buscar_exercicios(musculo='Quadríceps')] == ['Agachamento antigo']
        assert CatalogoService.buscar_exercicios(termo='Supino')[0]['musculo'] == 'Peito'
        musculos = CatalogoService.get_musculos_disponiveis()
        assert {'Peito', 'Bíceps', 'Quadríceps'} <= set(musculos)
        assert 'Tríceps' not in musculos and 'Antebraços' not in musculos
        assert buscar_musculo_no_catalogo('Supino reto com barra') == 'Peito'


def test_volume_por_musculo_conta_no_principal(app):
    with app.app_context():
        u = User(username='mp_aluno', email='mp@teste.com', tipo_usuario='aluno', ativo=True)
        u.set_password('123456')
        db.session.add(u)
        db.session.commit()
        supino = _ex('mp4', 'Supino', 'Peitorais', 'Tríceps')
        v = VersaoGlobal(numero_versao=1, descricao='V', divisao='LIVRE', user_id=u.id,
                         data_inicio=datetime.now().date())
        db.session.add(v)
        db.session.flush()
        t = TreinoVersao(versao_id=v.id, codigo='A', nome_treino='A')
        db.session.add(t)
        db.session.flush()
        r = RegistroTreino(treino_versao_id=t.id, versao_id=v.id, periodo='Nov/2026', semana=1, user_id=u.id,
                           exercicio_base_id=supino.id, data_registro=datetime.now())
        db.session.add(r)
        db.session.flush()
        db.session.add(HistoricoTreino(registro_id=r.id, carga=60, repeticoes=10))
        db.session.commit()
        stats = EstatisticaService.calcular_por_musculo(user_id=u.id)
        assert stats['Peito']['volume_total'] == 600 and stats['Peito']['total_series'] == 1
        assert 'Tríceps' not in stats or stats['Tríceps']['volume_total'] == 0
