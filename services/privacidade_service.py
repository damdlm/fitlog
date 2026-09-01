"""Serviço de privacidade / LGPD.

Reúne:

  - registrar_consentimento(...)   -- grava uma manifestação de vontade
  - tem_consentimento_fitbot(user) -- consulta rápida usada no gate do chat
  - precisa_aceitar_algum(user_id) -- true se falta aceitar Termos e/ou
                                       Política na versão vigente
  - registrar_aceite_pendentes(...) -- grava o aceite dos documentos
                                       que ainda estavam pendentes
  - exportar_dados(user)           -- portabilidade (Art. 18, V da LGPD)
  - anonimizar_conta(user)         -- "exclusão"/esquecimento (Art. 18, VI)

Nenhuma dessas operações mexe no formulário de cadastro nem cria campo
obrigatório novo -- tudo é self-service, acessado de dentro do perfil já
existente, e o aceite de Termos/Política é um único checkbox no
cadastro (ver templates/auth/register.html), nunca um formulário
jurídico separado.
"""

import logging
import secrets
from datetime import datetime, timezone

from models import (
    db,
    User,
    ConsentimentoLGPD,
    PasswordResetToken,
    AlunoProfessor,
    SolicitacaoVinculo,
    VersaoGlobal,
    ExercicioUsuario,
    RegistroTreino,
)
from services.base_service import CacheService

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Consentimentos pontuais (exigem consentimento como base legal --
# Art. 7º, I). `versao` fica None nesses.
# ------------------------------------------------------------------
TIPO_FITBOT = 'fitbot_ia'
TIPO_COMPARTILHAMENTO_PROFESSOR = 'compartilhamento_professor'

# ------------------------------------------------------------------
# Documentos versionados -- aceite formal, não é "consentimento
# genérico" (ver docstring de ConsentimentoLGPD em models.py).
#
# Formato da versão: data de publicação (YYYY-MM-DD). Ao editar
# materialmente os Termos ou a Política, muda a constante aqui --
# isso, sozinho, já faz `precisa_aceitar_algum` voltar a apontar
# pendência pra base inteira de usuários existentes, sem precisar de
# migration nem de tocar em nenhum registro antigo.
# ------------------------------------------------------------------
TIPO_TERMOS_USO = 'terms_of_use'
TIPO_POLITICA_PRIVACIDADE = 'privacy_policy'

VERSAO_TERMOS_USO = '2026-08-31'
VERSAO_POLITICA_PRIVACIDADE = '2026-08-31'

DOCUMENTOS_VERSIONADOS = (
    (TIPO_TERMOS_USO, VERSAO_TERMOS_USO),
    (TIPO_POLITICA_PRIVACIDADE, VERSAO_POLITICA_PRIVACIDADE),
)


class PrivacidadeService:

    # ------------------------------------------------------------
    # Consentimento

    # ------------------------------------------------------------
    @staticmethod
    def registrar_consentimento(usuario_id, tipo, concedido=True, contexto=None, versao=None, commit=True):
        """Grava uma nova manifestação de vontade. Nunca sobrescreve a
        anterior -- cada chamada é uma linha nova, preservando o
        histórico completo para fins de auditoria.

        commit=False só adiciona o registro à sessão (sem confirmar
        nem tratar erro aqui) -- usado quando o aceite precisa fazer
        parte de uma transação maior controlada por quem chama (ver
        registrar_aceite_cadastro / routes/auth_routes.py:register).
        Nesse modo, uma falha propaga a exceção para o chamador, que é
        quem decide o rollback."""
        registro = ConsentimentoLGPD(
            usuario_id=usuario_id,
            tipo=tipo,
            versao=versao,
            concedido=bool(concedido),
            contexto=contexto,
            criado_em=datetime.now(timezone.utc),
        )
        db.session.add(registro)

        if not commit:
            return registro

        try:
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
    # Aceite versionado de Termos de Uso / Política de Privacidade
    # ------------------------------------------------------------
    @staticmethod
    def documentos_pendentes(usuario_id):
        """Lista os `tipo` (dentre TIPO_TERMOS_USO/TIPO_POLITICA_PRIVACIDADE)
        cuja versão vigente o usuário ainda não aceitou. Lista vazia =
        nada pendente (cadastro novo já aceitou os dois de uma vez; ver
        routes/auth_routes.py:register)."""
        return [
            tipo for tipo, versao in DOCUMENTOS_VERSIONADOS
            if not ConsentimentoLGPD.tem_versao_aceita(usuario_id, tipo, versao)
        ]

    @staticmethod
    def precisa_aceitar_algum(usuario_id):
        return len(PrivacidadeService.documentos_pendentes(usuario_id)) > 0

    @staticmethod
    def chave_versoes_atuais():
        """String que muda sempre que VERSAO_TERMOS_USO/VERSAO_POLITICA_
        PRIVACIDADE mudar -- usada para cachear na sessão que o usuário
        já está em dia, sem bater no banco a cada request (ver
        app.py:_exigir_aceite_lgpd_atual)."""
        return f"{VERSAO_TERMOS_USO}|{VERSAO_POLITICA_PRIVACIDADE}"

    @staticmethod
    def registrar_aceite_cadastro(usuario_id, commit=True):
        """Chamado uma única vez, no exato momento em que a conta é
        criada (routes/auth_routes.py:register) -- o aceite do
        checkbox único vira DOIS registros (Termos + Política), cada um
        já na versão vigente no momento do cadastro.

        commit=False mantém os dois registros só na sessão, sem
        confirmar -- é o modo usado pelo cadastro, onde User +
        Assinatura + estes dois aceites precisam ser uma única
        transação (ver routes/auth_routes.py:register). Uma falha aqui
        propaga a exceção para o chamador fazer o rollback de tudo."""
        for tipo, versao in DOCUMENTOS_VERSIONADOS:
            PrivacidadeService.registrar_consentimento(
                usuario_id, tipo, concedido=True, versao=versao, contexto='cadastro',
                commit=commit,
            )

    @staticmethod
    def registrar_aceite_pendentes(usuario_id):
        """Chamado pela tela de reaceite (routes/privacidade_routes.py:
        aceite) -- só grava os documentos que ainda estavam pendentes
        pra esse usuário, nunca reescreve um aceite já existente."""
        pendentes = PrivacidadeService.documentos_pendentes(usuario_id)
        versoes_por_tipo = dict(DOCUMENTOS_VERSIONADOS)
        for tipo in pendentes:
            PrivacidadeService.registrar_consentimento(
                usuario_id, tipo, concedido=True,
                versao=versoes_por_tipo[tipo], contexto='reaceite',
            )
        return pendentes

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
                'versao': c.versao,
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
        """Remove os dados de identificação do usuário, desativa a
        conta e APAGA o histórico de treino individual (versões,
        treinos, registros, séries e exercícios próprios) -- decisão
        de produto (Alternativa A): depois da exclusão, nem o professor
        vinculado nem mais ninguém deve continuar enxergando o
        histórico de treino do titular através do FitLog.

        Antes, esse histórico era mantido "intacto" (só a identidade do
        usuário era trocada) sob a justificativa de não quebrar o que
        um professor já tinha consultado -- mas isso não é anonimização
        de verdade: os registros continuavam 100% ligados ao mesmo
        user_id, então bastava reabrir o vínculo (ou ter acesso direto
        ao banco) para reidentificar tudo. Ou seja, na melhor das
        hipóteses era pseudonimização, nunca anonimização, e por isso
        não podia ficar acessível a ninguém além do titular. Como não
        há nenhuma finalidade legítima documentada para reter esse
        detalhe granular depois que a conta é excluída (estatísticas
        agregadas como o ranking já filtram por User.ativo e não
        dependem dele), a categoria correta é A. EXCLUIR, não B.
        ANONIMIZAR/DESVINCULAR -- daí o DELETE físico abaixo, em vez de
        só apagar o vínculo com a conta.

        O que É mantido, e por quê:
          - ConsentimentoLGPD (incl. o registro desta própria exclusão):
            continua ligado a usuario_id -- é retenção com finalidade
            legítima documentada (categoria C: prova de que o titular
            de fato consentiu/pediu a exclusão, exigida pela própria
            LGPD para fins de comprovação), não uma sobra esquecida.
            Sozinho, sem os dados pessoais do User (já removidos), não
            permite reconstruir a identidade do titular.
          - A linha do User em si (não é DELETE): evita reabrir o
            username/e-mail para reuso imediato e preserva o próprio
            registro de que a exclusão aconteceu -- pior para auditoria
            apagar a linha do que anonimizar mantendo o vínculo.

        Auditoria de identificação indireta (além dos campos óbvios
        nome/e-mail/telefone) que este método também cobre:
          - username: pode ter sido escolhido pelo próprio usuário com
            seu nome real -- é trocado por um marcador, igual ao e-mail.
            (A tela "Melhores Alunos" e a listagem de alunos do
            professor já filtram por User.ativo/AlunoProfessor.ativo,
            então um usuário anonimizado nem chega a aparecer lá --
            mas o username em si também precisa parar de ser o nome
            real, caso apareça em algum lugar administrativo.)
          - vínculo aluno-professor: desativado nos dois sentidos (como
            aluno OU como professor), senão o outro lado continua
            enxergando os dados de treino de quem pediu exclusão.
          - login: hash de senha substituído por um hash de verdade
            (não um texto fixo -- um texto fixo passado pra
            check_password_hash quebra com ValueError em vez de
            simplesmente recusar o login) gerado a partir de uma senha
            aleatória que ninguém conhece.
          - sessões ativas: invalidadas via bump de session_version
            (mesmo mecanismo usado após troca de senha, ver
            User.set_password / app.py:load_user).
          - tokens de reset de senha ainda válidos: marcados como
            usados -- sem isso, um link de "esqueci minha senha"
            emitido pouco antes da exclusão continuaria funcionando e
            reabriria a conta anonimizada.
          - histórico de treino (versões, treinos, séries, exercícios
            próprios): apagado -- ver explicação da Alternativa A no
            topo deste docstring.
          - cache do FitBot para este usuário: invalidado logo após o
            commit, para não esperar o TTL (ver services/
            fitbot_context_service.py).
        """
        try:
            marcador = f"usuario-removido-{user.id}"

            user.username = marcador
            user.nome_completo = "Usuário removido"
            user.email = f"{marcador}@removido.fitlog"
            user.telefone = None
            user.data_nascimento = None
            user.cpf_cnpj = None
            user.endereco_cep = None
            user.endereco_numero = None
            user.ativo = False
            # Senha aleatória e descartada na hora -- ninguém a conhece,
            # e vira um hash de verdade (não uma string fixa) via
            # set_password, que também já cuida de invalidar sessões
            # antigas (bump de session_version).
            user.set_password(secrets.token_urlsafe(32))

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

            # Invalida qualquer token de reset de senha ainda não usado
            # (o link de e-mail continuaria funcionando até expirar,
            # senão -- ver reset_password_request, que só bloqueia a
            # EMISSÃO de token novo para conta inativa, não os já emitidos).
            PasswordResetToken.query.filter(
                PasswordResetToken.user_id == user.id,
                PasswordResetToken.used_at.is_(None),
            ).update({'used_at': datetime.now(timezone.utc)}, synchronize_session=False)

            # Apaga o histórico de treino individual -- Alternativa A
            # (ver docstring do método). Query.delete() é um DELETE em
            # massa que não passa pelos eventos do ORM (o cascade
            # Python 'all, delete-orphan' de VersaoGlobal.treinos/
            # registros não é acionado aqui) -- mas TODAS as FKs no
            # caminho (TreinoVersao.versao_id, VersaoExercicio.
            # treino_versao_id, RegistroTreino.treino_versao_id,
            # HistoricoTreino.registro_id) já são ondelete='CASCADE' no
            # nível do banco (ver models.py), então apagar as versões
            # é suficiente para o próprio Postgres/SQLite levar tudo
            # junto. ExercicioUsuario (exercícios próprios) é apagado
            # à parte pelo mesmo motivo (ondelete='CASCADE' a partir de
            # users.id, mas aqui filtrando direto por usuario_id).
            VersaoGlobal.query.filter_by(user_id=user.id).delete(synchronize_session=False)
            ExercicioUsuario.query.filter_by(usuario_id=user.id).delete(synchronize_session=False)

            db.session.commit()

            PrivacidadeService.registrar_consentimento(
                user.id, 'exclusao_conta', concedido=True,
                contexto="conta anonimizada a pedido do titular",
            )

            # Não espera o TTL do cache de contexto do FitBot -- ver
            # services/fitbot_context_service.py (chave
            # fitbot_context:{user_id}:...).
            CacheService.invalidate_pattern(f"fitbot_context:{user.id}:")

            logger.info("Conta anonimizada a pedido do titular -- usuario ID %s", user.id)
            return True
        except Exception:
            db.session.rollback()
            logger.exception("Erro ao anonimizar conta (usuario_id=%s)", user.id)
            return False