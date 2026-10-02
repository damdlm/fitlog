"""Mapa de professores (/aluno/mapa): o popup do pino só tem "Visualizar"
e o "Solicitar vínculo" fica no rodapé do modal da página do professor.

Cobre: payload da API (foto/iniciais pro avatar), presença do rodapé
(aluno com professor vê o botão e recebe o aviso no clique) e ausência dele
nas outras telas que reaproveitam o mesmo modal."""
from datetime import datetime, timezone

import pytest

from models import AlunoProfessor, User, db
from services.professor_perfil_service import ProfessorPerfilService


def _criar_usuario(username, tipo, nome=None):
    user = User(
        username=username,
        email=f'{username}@teste.com',
        tipo_usuario=tipo,
        nome_completo=nome,
    )
    user.set_password('123456')
    db.session.add(user)
    db.session.commit()
    return user


def _login(client, username):
    return client.post('/auth/login', data={'username': username, 'password': '123456'})


@pytest.fixture
def professor_no_mapa(app):
    prof = _criar_usuario('profmapa', 'professor', 'Felipe Luis')
    prof.professor_visivel_no_mapa = True
    prof.professor_latitude = -26.48
    prof.professor_longitude = -49.07
    prof.professor_cidade = 'Jaraguá do Sul'
    prof.professor_uf = 'SC'
    ProfessorPerfilService.garantir_slug(prof)
    db.session.commit()
    return prof


class TestPayloadApi:

    def test_pino_traz_foto_e_iniciais(self, app, client, professor_no_mapa):
        _criar_usuario('alunomapa', 'aluno')
        _login(client, 'alunomapa')

        resp = client.get('/api/professores/mapa', query_string={
            'sul': -27, 'oeste': -50, 'norte': -26, 'leste': -48, 'zoom': 19,
        })

        assert resp.status_code == 200
        itens = resp.get_json()['itens']
        profs = [p for item in itens if item['tipo'] != 'cluster' for p in item['professores']]
        assert len(profs) == 1
        prof = profs[0]
        assert prof['id'] == professor_no_mapa.id
        assert prof['slug'] == professor_no_mapa.professor_slug
        assert prof['iniciais'] == 'FL'
        assert prof['foto'] is None  # sem upload: o front cai pro círculo de iniciais


class TestRodapeSolicitarVinculo:

    def test_aluno_sem_professor_ve_botao_no_rodape_do_modal(self, app, client):
        _criar_usuario('alunolivre', 'aluno')
        _login(client, 'alunolivre')

        html = client.get('/aluno/mapa').get_data(as_text=True)

        assert 'id="ppVerPaginaModal"' in html
        assert 'id="ppSolicitarForm"' in html
        # URL-modelo termina em /0: o JS troca pelo id do professor clicado
        assert 'data-action-template="/aluno/enviar-solicitacao/0"' in html
        assert 'Solicitar vínculo' in html
        assert 'name="csrf_token"' in html

    def test_aluno_sem_professor_envia_direto(self, app, client):
        _criar_usuario('alunolivre2', 'aluno')
        _login(client, 'alunolivre2')

        html = client.get('/aluno/mapa').get_data(as_text=True)

        assert 'data-ja-tem-professor="0"' in html

    def test_aluno_com_professor_ve_o_botao_e_o_aviso_vem_no_clique(
            self, app, client, professor_no_mapa):
        aluno = _criar_usuario('alunovinculado', 'aluno')
        db.session.add(AlunoProfessor(
            aluno_id=aluno.id, professor_id=professor_no_mapa.id, ativo=True,
        ))
        db.session.commit()
        _login(client, 'alunovinculado')

        html = client.get('/aluno/mapa').get_data(as_text=True)

        # O botão continua lá; a validação acontece no clique (JS).
        assert 'id="ppSolicitarForm"' in html
        assert 'data-ja-tem-professor="1"' in html
        assert 'id="ppSolicitarAviso"' in html
        assert 'Você já tem um professor vinculado' in html

    def test_servidor_continua_barrando_aluno_com_professor(
            self, app, client, professor_no_mapa):
        """Proteção contra POST direto, sem passar pelo aviso do modal."""
        outro = _criar_usuario('profoutro', 'professor', 'Outro Prof')
        aluno = _criar_usuario('alunobarrado', 'aluno')
        db.session.add(AlunoProfessor(
            aluno_id=aluno.id, professor_id=professor_no_mapa.id, ativo=True,
        ))
        db.session.commit()
        _login(client, 'alunobarrado')

        resp = client.post(
            f'/aluno/enviar-solicitacao/{outro.id}', follow_redirects=True,
        )

        assert resp.status_code == 200
        assert 'Você já tem um professor vinculado' in resp.get_data(as_text=True)
        from models import SolicitacaoVinculo
        assert SolicitacaoVinculo.query.filter_by(aluno_id=aluno.id).count() == 0

    def test_popup_do_mapa_nao_tem_mais_solicitar_vinculo(self, app, client):
        """O JS do mapa não monta mais formulário de solicitação."""
        _criar_usuario('alunojs', 'aluno')
        _login(client, 'alunojs')

        js = client.get('/static/js/mapa_professores.js').get_data(as_text=True)

        assert 'Visualizar' in js
        assert 'Solicitar vínculo' not in js
        assert 'enviar-solicitacao' not in js
        assert 'Ver perfil' not in js

    def test_outras_telas_com_o_modal_nao_ganham_rodape(self, app, client):
        """Tela de edição da página do professor reaproveita o mesmo
        partial e não deve exibir o botão de solicitar vínculo."""
        prof = _criar_usuario('profeditar', 'professor', 'Ana Souza')
        ProfessorPerfilService.garantir_slug(prof)
        db.session.commit()
        _login(client, 'profeditar')

        resp = client.get('/professor/pagina/editar')

        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert 'id="ppVerPaginaModal"' in html
        assert 'id="ppSolicitarForm"' not in html

    def test_botao_de_fechar_do_modal_e_acessivel(self, app, client):
        """Botão de fechar redondo com ícone SVG, rótulo e dismiss do Bootstrap."""
        _criar_usuario('alunofechar', 'aluno')
        _login(client, 'alunofechar')

        html = client.get('/aluno/mapa').get_data(as_text=True)

        assert 'class="epp-preview-close"' in html
        assert 'data-bs-dismiss="modal" aria-label="Fechar"' in html
        assert 'btn-close' not in html.split('epp-preview-close')[1].split('</button>')[0]