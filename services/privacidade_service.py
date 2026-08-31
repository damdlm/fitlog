"""Serviço de privacidade / LGPD.

Reúne as três operações que a Central de Privacidade (Meu Perfil ->
aba Privacidade) expõe ao usuário, e a gravação de consentimento usada
pelo FitBot e pelo fluxo de vínculo aluno-professor:

  - registrar_consentimento(...)   -- grava uma manifestação de vontade
  - tem_consentimento_fitbot(user) -- consulta rápida usada no gate do chat
  - exportar_dados(user)           -- portabilidade (Art. 18, V da LGPD)
  - anonimizar_conta(user)         -- "exclusão"/esquecimento (Art. 18, VI)

Nenhuma dessas operações mexe no formulário de cadastro nem cria campo
obrigatório novo -- tudo é self-service, acessado de dentro do perfil já
existente.
"""

import logging
from datetime import datetime, timezone

from models import (
    db,
    User,
    ConsentimentoLGPD,
    AlunoProfessor,
    SolicitacaoVinculo,
    VersaoGlobal,
    ExercicioUsuario,
    RegistroTreino,
)

logger = logging.getLogger(__name__)

TIPO_FITBOT = 'fitbot_ia'
TIPO_COMPARTILHAMENTO_PROFESSOR = 'compartilhamento_professor'


class PrivacidadeService:

    # ------------------------------------------------------------
    # Consentimento
    # ------------------------------------------------------------
    @staticmethod
    def registrar_consentimento(usuario_id, tipo, concedido=True, contexto=None):
        """Grava uma nova manifestação de vontade. Nunca sobrescreve a
        anterior -- cada chamada é uma linha nova, preservando o
        histórico completo para fins de auditoria."""
        try:
            registro = ConsentimentoLGPD(
                usuario_id=usuario_id,
                tipo=tipo,
                concedido=bool(concedido),
                contexto=contexto,
                criado_em=datetime.now(timezone.utc),
            )
            db.session.add(registro)
            db.session.commit()
            return registro
        except Exception:
            db.session.rollback()
            logger.exception(
                "Erro ao registrar consentimento LGPD (usuario_id=%s, tipo=%s)",
                usuario_id, tipo,
            )
            return None

    @staticmethod
    def tem_consentimento_fitbot(usuario_id):
        return ConsentimentoLGPD.tem_consentimento_ativo(usuario_id, TIPO_FITBOT)

    # ------------------------------------------------------------
    # Portabilidade (Art. 18, V)
    # ------------------------------------------------------------
    @staticmethod
    def exportar_dados(user):
        """Monta um dicionário com todos os dados pessoais do usuário
        para download (JSON) -- pensado pra ser completo o bastante
        pra portabilidade real, sem expor dado de outro usuário (ex:
        nome do professor aparece, mas não os dados de treino dele)."""
        professor = user.get_professor() if user.is_aluno() else None

        versoes = []
        if user.pode_gerenciar_treino_proprio():
            for v in VersaoGlobal.query.filter_by(user_id=user.id).all():
                treinos = []
                for tv in v.treinos:
                    treinos.append({
                        'nome': tv.nome_treino,
                        'descricao': tv.descricao_treino,
                    })
                versoes.append({
                    'numero_versao': v.numero_versao,
                    'descricao': v.descricao,
                    'divisao': v.divisao,
                    'data_inicio': v.data_inicio.isoformat() if v.data_inicio else None,
                    'data_fim': v.data_fim.isoformat() if v.data_fim else None,
                    'treinos': treinos,
                })

        registros = []
        for r in RegistroTreino.query.filter_by(user_id=user.id).all():
            series = [
                {'carga': float(s.carga), 'repeticoes': s.repeticoes}
                for s in r.series
            ]
            registros.append({
                'periodo': r.periodo,
                'semana': r.semana,
                'data_registro': r.data_registro.isoformat() if r.data_registro else None,
                'series': series,
            })

        exercicios_criados = [
            {'nome': e.nome, 'descricao': e.descricao, 'observacoes': e.observacoes}
            for e in ExercicioUsuario.query.filter_by(usuario_id=user.id).all()
        ]

        consentimentos = [
            {
                'tipo': c.tipo,
                'concedido': c.concedido,
                'contexto': c.contexto,
                'data': c.criado_em.isoformat() if c.criado_em else None,
            }
            for c in ConsentimentoLGPD.query.filter_by(usuario_id=user.id)
                .order_by(ConsentimentoLGPD.criado_em).all()
        ]

        return {
            'dados_pessoais': {
                'username': user.username,
                'nome_completo': user.nome_completo,
                'email': user.email,
                'telefone': user.telefone,
                'data_nascimento': user.data_nascimento.isoformat() if user.data_nascimento else None,
                'tipo_usuario': user.tipo_usuario,
                'criado_em': user.created_at.isoformat() if user.created_at else None,
                'ultimo_login': user.last_login.isoformat() if user.last_login else None,
            },
            'vinculo_professor': (
                {'nome': professor.nome_completo or professor.username}
                if professor else None
            ),
            'versoes_de_treino': versoes,
            'registros_de_treino': registros,
            'exercicios_criados': exercicios_criados,
            'consentimentos_lgpd': consentimentos,
            'gerado_em': datetime.now(timezone.utc).isoformat(),
        }

    # ------------------------------------------------------------
    # Exclusão / esquecimento (Art. 18, VI)
    # ------------------------------------------------------------
    @staticmethod
    def anonimizar_conta(user):
        """Remove os dados de identificação do usuário e desativa a
        conta, mantendo intactos os registros de treino (sem nenhum
        dado pessoal neles: carga/repetições não identificam ninguém
        sozinhos) para não quebrar histórico consultado por um
        professor vinculado, nem estatísticas agregadas.

        Não é um DELETE físico: SQLAlchemy já teria cascade delete
        disponível (ver User.versoes/registros), mas apagar a linha
        de fato reabriria o username/e-mail para reuso imediato e
        destruiria o próprio registro de que a exclusão aconteceu --
        pior para auditoria do que anonimizar mantendo o vínculo.
        """
        try:
            marcador = f"usuario-removido-{user.id}"

            user.nome_completo = "Usuário removido"
            user.email = f"{marcador}@removido.fitlog"
            user.telefone = None
            user.data_nascimento = None
            user.cpf_cnpj = None
            user.endereco_cep = None
            user.endereco_numero = None
            user.ativo = False
            # Impede login: hash inválido, nunca bate com nenhuma senha real.
            user.password_hash = "!anonimizado!"
            user.session_version = (user.session_version or 0) + 1

            # Encerra qualquer vínculo ativo (como aluno ou como professor)
            # -- ninguém deve continuar tendo acesso aos dados de uma conta
            # que pediu para ser esquecida.
            AlunoProfessor.query.filter(
                db.or_(
                    AlunoProfessor.aluno_id == user.id,
                    AlunoProfessor.professor_id == user.id,
                ),
                AlunoProfessor.ativo == True,
            ).update({'ativo': False}, synchronize_session=False)

            SolicitacaoVinculo.query.filter(
                db.or_(
                    SolicitacaoVinculo.aluno_id == user.id,
                    SolicitacaoVinculo.professor_id == user.id,
                ),
                SolicitacaoVinculo.status == 'pendente',
            ).update({'status': 'cancelado'}, synchronize_session=False)

            db.session.commit()

            PrivacidadeService.registrar_consentimento(
                user.id, 'exclusao_conta', concedido=True,
                contexto="conta anonimizada a pedido do titular",
            )

            logger.info("Conta anonimizada a pedido do titular -- usuario ID %s", user.id)
            return True
        except Exception:
            db.session.rollback()
            logger.exception("Erro ao anonimizar conta (usuario_id=%s)", user.id)
            return False
