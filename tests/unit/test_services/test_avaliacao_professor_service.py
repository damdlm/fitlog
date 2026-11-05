"""
Testes de AvaliacaoProfessorService (nota de 1 a 5 do aluno ao SEU professor).

Regra de segurança central: o professor avaliado é SEMPRE o vinculado ao
aluno -- um professor_id arbitrário vindo do request nunca pode receber nota.
"""

import pytest

from models import db, User, AlunoProfessor, AvaliacaoProfessor
from services.avaliacao_professor_service import AvaliacaoProfessorService as Svc


def _user(username, tipo='aluno'):
    u = User(username=username, email=f'{username}@teste.com', tipo_usuario=tipo)
    u.set_password('SenhaForte123!')
    db.session.add(u)
    db.session.commit()
    return u


def _vincular(aluno, professor, ativo=True):
    db.session.add(AlunoProfessor(aluno_id=aluno.id, professor_id=professor.id, ativo=ativo))
    db.session.commit()


@pytest.fixture
def par(app):
    aluno, prof = _user('aluno_av'), _user('prof_av', 'professor')
    _vincular(aluno, prof)
    return aluno, prof


class TestAvaliar:

    @pytest.mark.parametrize('nota', [1, 2, 3, 4, 5, '1', '5', ' 4 '])
    def test_aceita_notas_de_1_a_5(self, par, nota):
        aluno, prof = par

        ok, msg = Svc.avaliar(aluno, prof.id, nota)

        assert ok is True
        assert 'obrigado' in msg
        assert AvaliacaoProfessor.query.one().nota == int(str(nota).strip())

    @pytest.mark.parametrize('nota', [0, 6, -1, 100, '0', '6'])
    def test_recusa_nota_fora_do_intervalo(self, par, nota):
        aluno, prof = par

        ok, msg = Svc.avaliar(aluno, prof.id, nota)

        assert (ok, msg) == (False, 'A nota deve ser de 1 a 5.')
        assert AvaliacaoProfessor.query.count() == 0

    @pytest.mark.parametrize('nota', [None, '', 'abc', '4.5', '4,5', [], {}])
    def test_recusa_nota_que_nao_e_inteiro(self, par, nota):
        aluno, prof = par

        ok, msg = Svc.avaliar(aluno, prof.id, nota)

        assert (ok, msg) == (False, 'Nota inválida.')
        assert AvaliacaoProfessor.query.count() == 0

    def test_avaliar_de_novo_atualiza_em_vez_de_duplicar(self, par):
        aluno, prof = par
        Svc.avaliar(aluno, prof.id, 3)

        ok, _ = Svc.avaliar(aluno, prof.id, 5)

        assert ok is True
        linhas = AvaliacaoProfessor.query.all()
        assert len(linhas) == 1 and linhas[0].nota == 5

    def test_professor_id_aceito_como_texto(self, par):
        aluno, prof = par
        assert Svc.avaliar(aluno, str(prof.id), 4)[0] is True

    def test_so_aluno_pode_avaliar(self, app):
        prof = _user('prof_sozinho', 'professor')
        outro = _user('outro_prof', 'professor')

        ok, msg = Svc.avaliar(prof, outro.id, 5)

        assert (ok, msg) == (False, 'Apenas alunos podem avaliar professores.')

    def test_aluno_sem_professor_vinculado_nao_avalia(self, app):
        aluno, prof = _user('aluno_sem'), _user('prof_qq', 'professor')

        ok, msg = Svc.avaliar(aluno, prof.id, 5)

        assert (ok, msg) == (False, 'Você só pode avaliar o seu próprio professor.')
        assert AvaliacaoProfessor.query.count() == 0

    def test_idor_nao_avalia_professor_que_nao_e_o_seu(self, par):
        aluno, _ = par
        estranho = _user('prof_estranho', 'professor')

        ok, msg = Svc.avaliar(aluno, estranho.id, 1)

        assert (ok, msg) == (False, 'Você só pode avaliar o seu próprio professor.')
        assert AvaliacaoProfessor.query.count() == 0

    def test_vinculo_inativo_nao_conta(self, app):
        aluno, prof = _user('aluno_ex'), _user('prof_ex', 'professor')
        _vincular(aluno, prof, ativo=False)

        ok, _ = Svc.avaliar(aluno, prof.id, 5)

        assert ok is False

    def test_professor_id_nao_numerico_levanta_em_vez_de_passar(self, par):
        """int(professor_id) é feito sem proteção: a ROTA nunca passa isso
        (usa current_user.get_professor().id); este teste só documenta."""
        aluno, _ = par
        with pytest.raises(ValueError):
            Svc.avaliar(aluno, 'abc', 5)

    def test_falha_no_banco_faz_rollback_e_devolve_mensagem_amigavel(self, par, monkeypatch):
        aluno, prof = par

        def _boom():
            raise RuntimeError('banco fora do ar')

        monkeypatch.setattr(db.session, 'commit', _boom)

        ok, msg = Svc.avaliar(aluno, prof.id, 5)

        assert (ok, msg) == (False, 'Erro ao salvar sua avaliação. Tente novamente.')
        monkeypatch.undo()
        assert AvaliacaoProfessor.query.count() == 0


class TestNotaDoAluno:

    def test_retorna_a_nota_dada(self, par):
        aluno, prof = par
        Svc.avaliar(aluno, prof.id, 4)
        assert Svc.nota_do_aluno(aluno.id, prof.id) == 4

    def test_sem_avaliacao_retorna_none(self, par):
        aluno, prof = par
        assert Svc.nota_do_aluno(aluno.id, prof.id) is None

    def test_nao_mistura_notas_de_outros_alunos(self, par):
        aluno, prof = par
        outro = _user('aluno_outro')
        _vincular(outro, prof)
        Svc.avaliar(outro, prof.id, 1)

        assert Svc.nota_do_aluno(aluno.id, prof.id) is None


class TestResumo:

    def test_sem_avaliacoes_retorna_zeros(self, par):
        _, prof = par
        assert Svc.resumo(prof.id) == {'media': 0.0, 'total': 0}

    def test_media_arredondada_em_uma_casa_e_total(self, par):
        _, prof = par
        for i, nota in enumerate([4, 5, 5]):
            aluno = _user(f'a{i}')
            _vincular(aluno, prof)
            Svc.avaliar(aluno, prof.id, nota)

        assert Svc.resumo(prof.id) == {'media': 4.7, 'total': 3}

    def test_so_conta_avaliacoes_do_proprio_professor(self, par):
        aluno, prof = par
        Svc.avaliar(aluno, prof.id, 2)
        outro_prof, outro_aluno = _user('prof_b', 'professor'), _user('aluno_b')
        _vincular(outro_aluno, outro_prof)
        Svc.avaliar(outro_aluno, outro_prof.id, 5)

        assert Svc.resumo(prof.id) == {'media': 2.0, 'total': 1}
        assert Svc.resumo(outro_prof.id) == {'media': 5.0, 'total': 1}
