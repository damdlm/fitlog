"""Lote 3 da análise de UX: telas mais leves.

T1: as fichas (Cadastrar Treinos / detalhe de versão) abrem sem os ~1.350
cartões do catálogo, que vêm de uma rota à parte quando o modal "Editar
treino" precisa deles. R8: a lista do "+ Exercício" do registro também vem
à parte, só quando o modal abre. X5: Chart.js, FullCalendar, html2canvas e
SortableJS servidos pelo próprio FitLog, sem CDN.
"""
import base64
import glob
import hashlib
import os
import re
from datetime import date

from models import db, ExercicioSistema
from tests.integration.test_routes.test_professor_routes_versoes import (
    _associar, _criar_exercicio, _criar_treino_versao, _criar_usuario, _criar_versao, _login,
)

DATA = date(2026, 1, 12)


def _catalogo_extra():
    db.session.add(ExercicioSistema(id_original='8881', nome='Extensão de perna na máquina',
                                    nicknames=['Cadeira extensora'], grupo_muscular='Quadríceps'))
    db.session.commit()


def _ficha(username, tipo='aluno'):
    u = _criar_usuario(username, tipo_usuario=tipo)
    v = _criar_versao(u.id)
    tv = _criar_treino_versao(v.id)
    ex = _criar_exercicio(u.id, nome='Supino do aluno')
    return u, v, tv, ex


class TestFichaSemCatalogoEmbutido:
    def test_cadastrar_treinos_abre_sem_os_cartoes(self, client, app):
        with app.app_context():
            _ficha('t1_cadastrar')
            _catalogo_extra()
        _login(client, 't1_cadastrar')
        html = client.get('/aluno/cadastrar-treinos').get_data(as_text=True)
        assert 'data-catalogo-url="/aluno/catalogo-exercicios/cards"' in html
        assert 'class="etv-card"' not in html
        assert 'data-etv-carregando' in html

    def test_ver_versao_abre_sem_os_cartoes(self, client, app):
        with app.app_context():
            _u, v, _tv, _ex = _ficha('t1_versao')
            vid = v.id
        _login(client, 't1_versao')
        html = client.get(f'/aluno/versao/{vid}').get_data(as_text=True)
        assert 'data-catalogo-url="/aluno/catalogo-exercicios/cards"' in html
        assert 'class="etv-card"' not in html

    def test_rota_dos_cartoes_traz_o_catalogo_do_aluno(self, client, app):
        with app.app_context():
            _ficha('t1_cards')
            _catalogo_extra()
        _login(client, 't1_cards')
        resp = client.get('/aluno/catalogo-exercicios/cards')
        assert resp.status_code == 200
        assert 'no-store' in resp.headers['Cache-Control']
        html = resp.get_data(as_text=True)
        assert '<html' not in html  # só o fragmento, sem layout
        assert 'data-nome-display="Supino do aluno"' in html
        assert 'data-nome-display="Extensão de perna na máquina"' in html
        assert 'cadeira extensora' in html  # apelido entra na busca
        assert 'name="exercicios[]"' in html and 'etv-tipo-badge' in html

    def test_rota_dos_cartoes_exige_login(self, client):
        resp = client.get('/aluno/catalogo-exercicios/cards')
        assert resp.status_code in (302, 401)


class TestCatalogoDoAlunoPeloProfessor:
    def test_professor_ve_cartoes_do_proprio_aluno_e_nao_de_outro(self, client, app):
        with app.app_context():
            prof = _criar_usuario('t1_prof', tipo_usuario='professor')
            aluno, v, _tv, _ex = _ficha('t1_aluno_dele')
            outro, _v2, _tv2, _ex2 = _ficha('t1_aluno_outro')
            _associar(aluno.id, prof.id)
            aid, oid, vid = aluno.id, outro.id, v.id
        _login(client, 't1_prof')
        html = client.get(f'/professor/aluno/{aid}/versao/{vid}').get_data(as_text=True)
        assert f'data-catalogo-url="/professor/aluno/{aid}/catalogo-exercicios/cards"' in html
        assert 'class="etv-card"' not in html
        cards = client.get(f'/professor/aluno/{aid}/catalogo-exercicios/cards')
        assert cards.status_code == 200 and 'Supino do aluno' in cards.get_data(as_text=True)
        negado = client.get(f'/professor/aluno/{oid}/catalogo-exercicios/cards')
        assert negado.status_code == 403 and negado.get_data(as_text=True) == ''


class TestListaDoMaisExercicio:
    def test_registro_abre_sem_a_lista_e_a_rota_traz_todos(self, client, app):
        with app.app_context():
            _u, v, tv, ex = _ficha('r8_registro')
            from models import VersaoExercicio
            db.session.add(VersaoExercicio(treino_versao_id=tv.id, exercicio_usuario_id=ex.id, ordem=0))
            db.session.commit()
            _catalogo_extra()
            tid = tv.id
        _login(client, 'r8_registro')
        html = client.get(f'/registrar/registrar-treino?data=2024-02-01&treino={tid}').get_data(as_text=True)
        assert 'data-url="/registrar/catalogo-avulso"' in html
        assert 'class="avulso-picker-item"' not in html
        lista = client.get('/registrar/catalogo-avulso')
        assert lista.status_code == 200 and 'no-store' in lista.headers['Cache-Control']
        corpo = lista.get_data(as_text=True)
        # o navegador esconde os que já estão no treino (is-no-treino)
        assert corpo.count('class="avulso-picker-item"') >= 2
        assert 'Extensão de perna na máquina' in corpo and 'Supino do aluno' in corpo


class TestBibliotecasLocais:
    # mesmos hashes que as páginas usavam no atributo integrity do CDN
    ESPERADOS = {
        'chartjs/chart.umd.min.js': 'jb8JQMbMoBUzgWatfe6COACi2ljcDdZQ2OxczGA3bGNeWe+6DChMTBJemed7ZnvJ',
        'fullcalendar/main.min.js': '5/vsv56401Wf+RP3yE5/aIKW4wutk4nLY3HjueTXN0rA+DmweMtrYaN6RSjdv31b',
        'fullcalendar/main.min.css': '39yVKLsD9lMelmY+ij49KZgE+Mfk6hjdUPNE8yKHqdMPceLXzhlCJAK81xlD5jDj',
        'fullcalendar/locales/pt-br.js': 'nYTm93SVXbkFBAZDYl7rIdivGWF6TuP6m3X7taeRDE3L5VaeNv4OW34We0UTtUyr',
        'html2canvas/html2canvas.min.js': 'ZZ1pncU3bQe8y31yfZdMFdSpttDoPmOZg2wguVK9almUodir1PghgT0eY7Mrty8H',
        'sortablejs/Sortable.min.js': 'DgmC6Xe2bSN2WjTDXzWYbUbxyhNP+NNkGDR/g78pCXV7E7rcVTGxVg0uIVCUUcBc',
    }

    def test_arquivos_iguais_aos_do_cdn(self):
        for caminho, esperado in self.ESPERADOS.items():
            with open(os.path.join('static', 'vendor', caminho), 'rb') as f:
                assert base64.b64encode(hashlib.sha384(f.read()).digest()).decode() == esperado, caminho

    def test_nenhuma_tela_carrega_script_de_cdn(self):
        for p in glob.glob('templates/**/*.html', recursive=True):
            with open(p, encoding='utf-8') as f:
                html = f.read()
            assert not re.search(r'(src|href)=["\']https://(cdn\.jsdelivr\.net|cdnjs\.cloudflare\.com)', html), p
            assert 'document.write(' not in html, p

    def test_calendario_usa_os_arquivos_locais(self, client, app):
        with app.app_context():
            _criar_usuario('x5_calendario')
        _login(client, 'x5_calendario')
        html = client.get('/calendar/calendario').get_data(as_text=True)
        for arq in ('vendor/fullcalendar/main.min.js', 'vendor/fullcalendar/main.min.css',
                    'vendor/fullcalendar/locales/pt-br.js', 'vendor/chartjs/chart.umd.min.js'):
            assert f'/static/{arq}?v=' in html, arq
