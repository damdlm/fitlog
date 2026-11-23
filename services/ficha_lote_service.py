"""Mesma ficha para vários alunos (lote 4).

O professor escolhe UMA ficha de origem, marca os alunos e diz como
aplicar:

  - 'agora':    encerra a ficha ativa do aluno hoje e cria a nova já
                ativa (mesmo efeito de finalizar + clonar, numa transação)
  - 'vencer':   a nova ficha entra sozinha quando a ficha atual vencer
                (validade_meses). Fica em FichaEnviada até o cron diário
                (comando "versoes-alertar-expiracao") aplicar.
  - 'sugestao': o aluno recebe a ficha para ver e decide se aceita.

Origens possíveis (valor do campo "fonte" do formulário):
  - 'p:<id>'    ficha do próprio professor
  - 'a:<id>'    ficha (ativa) de um aluno dele
  - 'm:<slug>'  ficha pronta (data/fichas_prontas.py)

O resultado volta aluno por aluno, inclusive os ignorados com o motivo.
A origem é lida na hora de aplicar (não há "foto" da ficha): se o
professor ajustar a ficha de origem antes de ela entrar, entra a versão
ajustada; se a origem for excluída, o envio é cancelado com o motivo.
"""
import logging
from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import joinedload

from models import (db, User, AlunoProfessor, VersaoGlobal, TreinoVersao, VersaoExercicio,
                    ExercicioUsuario, FichaEnviada)
from utils.format_utils import data_atual
from .versao_service import VersaoService

logger = logging.getLogger(__name__)

MODOS = ('agora', 'vencer', 'sugestao')
MAX_ALUNOS_POR_ENVIO = 100
DIAS_SUGESTAO_SEM_RESPOSTA = 3


def _nome(u):
    return u.nome_completo or u.username


def _url(endpoint, reserva, **kw):
    """url_for quando há requisição; o caminho fixo no cron (CLI)."""
    from flask import url_for
    try:
        return url_for(endpoint, **kw)
    except RuntimeError:
        return reserva


class FichaLoteService:

    # ------------------------------------------------------------------
    # Dados para a tela
    # ------------------------------------------------------------------

    @staticmethod
    def alunos_do_professor(professor_id):
        return (User.query
                .join(AlunoProfessor, AlunoProfessor.aluno_id == User.id)
                .filter(AlunoProfessor.professor_id == professor_id,
                        AlunoProfessor.ativo == True,  # noqa: E712
                        User.ativo == True)  # noqa: E712
                .order_by(User.nome_completo)
                .all())

    @staticmethod
    def dados_tela(professor_id):
        """Fontes (agrupadas) e alunos com a ficha atual, numa ida ao banco
        por tabela."""
        alunos = FichaLoteService.alunos_do_professor(professor_id)
        ids = [a.id for a in alunos]
        ativas = {}
        if ids:
            for v in (VersaoGlobal.query.filter(VersaoGlobal.user_id.in_(ids), VersaoGlobal.data_fim.is_(None))
                      .order_by(VersaoGlobal.data_inicio.desc()).all()):
                ativas.setdefault(v.user_id, v)
        pendentes = {}
        if ids:
            for e in FichaEnviada.query.filter(FichaEnviada.professor_id == professor_id,
                                               FichaEnviada.aluno_id.in_(ids),
                                               FichaEnviada.status == 'pendente').all():
                pendentes[e.aluno_id] = e

        lista_alunos = []
        for a in alunos:
            v = ativas.get(a.id)
            lista_alunos.append({
                'id': a.id, 'nome': _nome(a),
                'ficha': v.descricao if v else None,
                'versao': v.numero_versao if v else None,
                'vence_em': v.data_expiracao if v else None,
                'dias_para_vencer': v.dias_para_expirar if v else None,
                'pendente': pendentes.get(a.id),
            })

        minhas = VersaoGlobal.query.filter_by(user_id=professor_id) \
            .order_by(VersaoGlobal.data_fim.is_(None).desc(), VersaoGlobal.data_inicio.desc()).all()
        fontes = {
            'minhas': [{'valor': f'p:{v.id}', 'nome': v.descricao,
                        'detalhe': f"v{v.numero_versao}" + (' · ativa' if v.data_fim is None else '')}
                       for v in minhas],
            'alunos': [{'valor': f'a:{ativas[a.id].id}', 'nome': ativas[a.id].descricao,
                        'detalhe': f"de {_nome(a)}"}
                       for a in alunos if a.id in ativas],
            'prontas': [{'valor': f"m:{f['slug']}", 'nome': f['nome'], 'detalhe': f['detalhe']}
                        for f in VersaoService.fichas_prontas_para_tela()],
        }
        return {'alunos': lista_alunos, 'fontes': fontes}

    @staticmethod
    def resolver_fonte(professor_id, fonte):
        """('versao', VersaoGlobal) ou ('modelo', slug). ValueError se a
        fonte não existir ou não for do professor / de um aluno dele."""
        tipo, _, valor = (fonte or '').partition(':')
        if tipo == 'm':
            from data.fichas_prontas import FICHAS_POR_SLUG
            if valor in FICHAS_POR_SLUG:
                return 'modelo', valor
        elif tipo in ('p', 'a') and valor.isdigit():
            v = db.session.get(VersaoGlobal, int(valor))
            if v and tipo == 'p' and v.user_id == professor_id:
                return 'versao', v
            if v and tipo == 'a' and AlunoProfessor.query.filter_by(
                    aluno_id=v.user_id, professor_id=professor_id, ativo=True).first():
                return 'versao', v
        raise ValueError('Escolha uma ficha da lista.')

    @staticmethod
    def descricao_da_fonte(tipo, origem):
        if tipo == 'modelo':
            from data.fichas_prontas import FICHAS_POR_SLUG
            return FICHAS_POR_SLUG[origem]['nome']
        return origem.descricao

    # ------------------------------------------------------------------
    # Aplicar
    # ------------------------------------------------------------------

    @staticmethod
    def aplicar(professor, fonte, aluno_ids, modo, validade='__manter__'):
        """Aplica a ficha nos alunos. Devolve uma lista, um item por aluno
        pedido: {'aluno_id', 'nome', 'status', 'texto'} com status
        'aplicada' | 'agendada' | 'sugerida' | 'ignorado'."""
        if modo not in MODOS:
            raise ValueError('Escolha como aplicar a ficha.')
        tipo, origem = FichaLoteService.resolver_fonte(professor.id, fonte)
        if validade == '__manter__':
            validade = origem.validade_meses if tipo == 'versao' else None
        else:
            validade = VersaoService._validar_validade_meses(validade)

        ids = []
        for i in aluno_ids or []:
            try:
                i = int(i)
            except (TypeError, ValueError):
                continue
            if i not in ids:
                ids.append(i)
        if not ids:
            raise ValueError('Marque pelo menos um aluno.')
        if len(ids) > MAX_ALUNOS_POR_ENVIO:
            raise ValueError(f'Escolha no máximo {MAX_ALUNOS_POR_ENVIO} alunos por vez.')

        meus = {a.id: a for a in FichaLoteService.alunos_do_professor(professor.id)}
        descricao = FichaLoteService.descricao_da_fonte(tipo, origem)[:200]
        resultados = []
        for aluno_id in ids:
            aluno = meus.get(aluno_id)
            if not aluno:
                resultados.append({'aluno_id': aluno_id, 'nome': f'Aluno #{aluno_id}', 'status': 'ignorado',
                                   'texto': 'não está na sua lista de alunos ativos'})
                continue
            item = {'aluno_id': aluno_id, 'nome': _nome(aluno)}
            try:
                item.update(FichaLoteService._aplicar_um(professor, aluno, tipo, origem, descricao, modo, validade))
            except ValueError as e:
                db.session.rollback()
                item.update(status='ignorado', texto=str(e))
            except Exception:
                db.session.rollback()
                logger.exception(f'Erro ao aplicar ficha ({fonte}) no aluno {aluno_id}')
                item.update(status='ignorado', texto='não foi possível copiar a ficha agora')
            resultados.append(item)
        logger.info(f'Professor {professor.id} aplicou {fonte} ({modo}) em {len(ids)} aluno(s)')
        return resultados

    @staticmethod
    def _aplicar_um(professor, aluno, tipo, origem, descricao, modo, validade):
        ativa = VersaoService.get_ativa(user_id=aluno.id)
        if tipo == 'versao' and ativa and ativa.id == origem.id:
            raise ValueError('esta já é a ficha atual dele')

        anterior = FichaLoteService._cancelar_pendente(professor.id, aluno.id)
        obs = ' · substituiu o envio anterior' if anterior else ''

        if modo == 'vencer' and ativa:
            dias = ativa.dias_para_expirar
            if dias is None:
                raise ValueError('a ficha atual não tem data de vencimento; '
                                 'use "Substituir agora" ou "Enviar como sugestão"')
            if dias > 0:
                FichaLoteService._registrar_envio(professor, aluno, tipo, origem, descricao, modo, validade,
                                                  versao_alvo_id=ativa.id)
                db.session.commit()
                FichaLoteService._notificar(
                    aluno, professor, 'Sua próxima ficha já está pronta',
                    f'{_nome(professor)} preparou a ficha "{descricao}". Ela entra no lugar da atual '
                    f'em {ativa.data_expiracao.strftime("%d/%m/%Y")}, quando a atual vencer.', None)
                return {'status': 'agendada',
                        'texto': f'entra em {ativa.data_expiracao.strftime("%d/%m/%Y")}, quando a atual vencer' + obs}
            obs = ' · a ficha atual já tinha vencido' + obs

        if modo == 'sugestao':
            envio = FichaLoteService._registrar_envio(professor, aluno, tipo, origem, descricao, modo, validade,
                                                      versao_alvo_id=ativa.id if ativa else None)
            db.session.commit()
            FichaLoteService._notificar(
                aluno, professor, 'Seu professor sugeriu uma nova ficha',
                f'{_nome(professor)} sugeriu a ficha "{descricao}". Veja os treinos e diga se quer trocar.',
                _url('aluno.ficha_sugerida', f'/aluno/ficha-sugerida/{envio.id}', envio_id=envio.id))
            return {'status': 'sugerida', 'texto': 'o aluno escolhe se aceita' + obs}

        nova = FichaLoteService._trocar_ficha(professor.id, aluno.id, tipo, origem, descricao, validade)
        if not ativa and modo == 'vencer':
            obs = ' · não tinha ficha ativa' + obs
        FichaLoteService._notificar_troca(aluno, professor, nova)
        return {'status': 'aplicada', 'texto': f'já é a ficha ativa (v{nova.numero_versao})' + obs}

    @staticmethod
    def _cancelar_pendente(professor_id, aluno_id):
        """Um aluno tem no máximo um envio pendente por professor: o novo
        substitui o anterior."""
        pend = FichaEnviada.query.filter_by(professor_id=professor_id, aluno_id=aluno_id,
                                            status='pendente').all()
        for e in pend:
            e.status = 'cancelada'
            e.motivo = 'substituída por outro envio'
            e.respondida_em = datetime.now(timezone.utc)
        return bool(pend)

    @staticmethod
    def _registrar_envio(professor, aluno, tipo, origem, descricao, modo, validade, versao_alvo_id=None):
        envio = FichaEnviada(
            professor_id=professor.id, aluno_id=aluno.id,
            origem_versao_id=origem.id if tipo == 'versao' else None,
            origem_modelo=origem if tipo == 'modelo' else None,
            descricao=descricao, validade_meses=validade, modo=modo,
            versao_alvo_id=versao_alvo_id, status='pendente',
        )
        db.session.add(envio)
        db.session.flush()
        return envio

    # ------------------------------------------------------------------
    # Copiar a ficha
    # ------------------------------------------------------------------

    @staticmethod
    def _trocar_ficha(professor_id, aluno_id, tipo, origem, descricao, validade):
        """Encerra a ficha ativa (data_fim = hoje) e cria a nova, tudo
        numa transação. Devolve a nova VersaoGlobal."""
        hoje = data_atual()
        for v in VersaoGlobal.query.filter_by(user_id=aluno_id, data_fim=None).all():
            v.data_fim = hoje
        db.session.flush()

        if tipo == 'modelo':
            # criar_de_modelo faz o próprio commit; a ficha anterior já
            # está encerrada na mesma sessão.
            nova = VersaoService.criar_de_modelo(origem, user_id=aluno_id)
            if validade:
                nova.validade_meses = validade
                db.session.commit()
            return nova

        ultima = db.session.query(func.max(VersaoGlobal.numero_versao)).filter_by(user_id=aluno_id).scalar() or 0
        nova = VersaoGlobal(numero_versao=ultima + 1, descricao=descricao, divisao='LIVRE',
                            data_inicio=hoje, data_fim=None, user_id=aluno_id, validade_meses=validade)
        db.session.add(nova)
        db.session.flush()

        cache = {}
        treinos = (TreinoVersao.query.filter_by(versao_id=origem.id)
                   .options(joinedload(TreinoVersao.exercicios))
                   .order_by(TreinoVersao.ordem).all())
        for tv in treinos:
            novo_tv = TreinoVersao(versao_id=nova.id, codigo=tv.codigo, nome_treino=tv.nome_treino,
                                   descricao_treino=tv.descricao_treino, ordem=tv.ordem)
            db.session.add(novo_tv)
            db.session.flush()
            for ve in tv.exercicios:
                eu_id = None
                if ve.exercicio_usuario_id is not None:
                    eu_id = FichaLoteService._exercicio_para_aluno(ve.exercicio_usuario_id, professor_id,
                                                                    aluno_id, cache)
                    if eu_id is None:
                        continue
                db.session.add(VersaoExercicio(
                    treino_versao_id=novo_tv.id, exercicio_usuario_id=eu_id,
                    exercicio_base_id=ve.exercicio_base_id, ordem=ve.ordem, observacao=ve.observacao,
                    meta_series=ve.meta_series, meta_reps_min=ve.meta_reps_min, meta_reps_max=ve.meta_reps_max,
                ))
        db.session.commit()
        return nova

    @staticmethod
    def _exercicio_para_aluno(exercicio_id, professor_id, aluno_id, cache):
        """Exercício personalizado da ficha de origem -> exercício do aluno
        de destino. Do próprio aluno: o mesmo. Do professor (ou cópia de um
        do professor, quando a origem é a ficha de outro aluno): a cópia
        do aluno (VersaoService._resolver_exercicio_do_aluno). Criado por
        outro aluno: um com o mesmo nome, ou uma cópia nova."""
        if exercicio_id in cache:
            return cache[exercicio_id]
        ex = db.session.get(ExercicioUsuario, exercicio_id)
        if not ex:
            resultado = None
        elif ex.usuario_id == aluno_id:
            resultado = ex.id
        elif ex.usuario_id == professor_id:
            resultado = VersaoService._resolver_exercicio_do_aluno(ex.id, professor_id, aluno_id, {})
        elif ex.copiado_de_professor_id == professor_id and ex.copiado_de_exercicio_id:
            resultado = VersaoService._resolver_exercicio_do_aluno(ex.copiado_de_exercicio_id, professor_id,
                                                                   aluno_id, {})
        else:
            igual = ExercicioUsuario.query.filter(ExercicioUsuario.usuario_id == aluno_id,
                                                  func.lower(ExercicioUsuario.nome) == ex.nome.lower()).first()
            if not igual:
                igual = ExercicioUsuario(usuario_id=aluno_id, nome=ex.nome, descricao=ex.descricao,
                                         musculo_id=ex.musculo_id, observacoes=ex.observacoes,
                                         modo_registro=ex.modo_registro)
                db.session.add(igual)
                db.session.flush()
            resultado = igual.id
        cache[exercicio_id] = resultado
        return resultado

    # ------------------------------------------------------------------
    # Envios pendentes: aplicar, aceitar, recusar, cancelar
    # ------------------------------------------------------------------

    @staticmethod
    def _origem_do_envio(envio):
        if envio.origem_modelo:
            from data.fichas_prontas import FICHAS_POR_SLUG
            if envio.origem_modelo in FICHAS_POR_SLUG:
                return 'modelo', envio.origem_modelo
            return None, None
        v = db.session.get(VersaoGlobal, envio.origem_versao_id) if envio.origem_versao_id else None
        return ('versao', v) if v else (None, None)

    @staticmethod
    def _efetivar(envio):
        """Troca a ficha do aluno pela do envio. ValueError se a origem
        sumiu."""
        tipo, origem = FichaLoteService._origem_do_envio(envio)
        if not tipo:
            raise ValueError('a ficha de origem foi excluída')
        nova = FichaLoteService._trocar_ficha(envio.professor_id, envio.aluno_id, tipo, origem,
                                              envio.descricao, envio.validade_meses)
        envio.status = 'aplicada'
        envio.versao_criada_id = nova.id
        envio.respondida_em = datetime.now(timezone.utc)
        db.session.commit()
        return nova

    @staticmethod
    def aplicar_agendadas():
        """Cron diário: aplica os envios 'vencer' cuja ficha atual venceu.
        Se o aluno trocou de ficha antes (a ativa não é mais a esperada),
        o envio é cancelado com o motivo. Devolve (aplicadas, canceladas)."""
        aplicadas = canceladas = 0
        for envio in FichaEnviada.query.filter_by(modo='vencer', status='pendente').all():
            vinculo = AlunoProfessor.query.filter_by(aluno_id=envio.aluno_id, professor_id=envio.professor_id,
                                                     ativo=True).first()
            ativa = VersaoService.get_ativa(user_id=envio.aluno_id)
            motivo = None
            if not vinculo:
                motivo = 'o aluno não está mais vinculado'
            elif ativa and ativa.id != envio.versao_alvo_id:
                motivo = 'o aluno trocou de ficha antes do vencimento'
            elif ativa and (ativa.dias_para_expirar is None or ativa.dias_para_expirar > 0):
                continue
            try:
                if motivo:
                    raise ValueError(motivo)
                nova = FichaLoteService._efetivar(envio)
                FichaLoteService._notificar_troca(envio.aluno, envio.professor, nova)
                aplicadas += 1
            except ValueError as e:
                db.session.rollback()
                envio.status, envio.motivo = 'cancelada', str(e)
                envio.respondida_em = datetime.now(timezone.utc)
                db.session.commit()
                canceladas += 1
            except Exception:
                db.session.rollback()
                logger.exception(f'Erro ao aplicar a ficha agendada {envio.id}')
        return aplicadas, canceladas

    @staticmethod
    def sugestao_do_aluno(envio_id, aluno_id):
        return FichaEnviada.query.filter_by(id=envio_id, aluno_id=aluno_id, modo='sugestao').first()

    @staticmethod
    def sugestoes_pendentes_do_aluno(aluno_id):
        return (FichaEnviada.query.filter_by(aluno_id=aluno_id, modo='sugestao', status='pendente')
                .order_by(FichaEnviada.criada_em.desc()).all())

    @staticmethod
    def responder_sugestao(envio_id, aluno, aceitar):
        envio = FichaLoteService.sugestao_do_aluno(envio_id, aluno.id)
        if not envio or envio.status != 'pendente':
            raise ValueError('Esta sugestão não está mais disponível.')
        if aceitar:
            nova = FichaLoteService._efetivar(envio)
            FichaLoteService._notificar_professor(envio, f'{_nome(aluno)} aceitou a ficha sugerida',
                                                  f'"{envio.descricao}" agora é a ficha ativa de {_nome(aluno)}.')
            return nova
        envio.status = 'recusada'
        envio.respondida_em = datetime.now(timezone.utc)
        db.session.commit()
        FichaLoteService._notificar_professor(envio, f'{_nome(aluno)} preferiu manter a ficha atual',
                                              f'A sugestão "{envio.descricao}" foi recusada.')
        return None

    @staticmethod
    def pendentes_do_professor(professor_id):
        return (FichaEnviada.query.options(joinedload(FichaEnviada.aluno))
                .filter_by(professor_id=professor_id, status='pendente')
                .order_by(FichaEnviada.criada_em.desc()).all())

    @staticmethod
    def cancelar(envio_id, professor_id):
        envio = FichaEnviada.query.filter_by(id=envio_id, professor_id=professor_id, status='pendente').first()
        if not envio:
            return False
        envio.status, envio.motivo = 'cancelada', 'cancelada pelo professor'
        envio.respondida_em = datetime.now(timezone.utc)
        db.session.commit()
        return True

    @staticmethod
    def sugestoes_sem_resposta(professor_id, aluno_ids, dias=DIAS_SUGESTAO_SEM_RESPOSTA):
        """Para o alerta do painel: sugestões pendentes há `dias`+ dias."""
        if not aluno_ids:
            return []
        from datetime import timedelta
        limite = datetime.now(timezone.utc) - timedelta(days=dias)
        return (FichaEnviada.query
                .filter(FichaEnviada.professor_id == professor_id, FichaEnviada.aluno_id.in_(aluno_ids),
                        FichaEnviada.modo == 'sugestao', FichaEnviada.status == 'pendente',
                        FichaEnviada.criada_em <= limite)
                .all())

    # ------------------------------------------------------------------
    # Prévia (tela do aluno)
    # ------------------------------------------------------------------

    @staticmethod
    def previa(envio):
        """Treinos e exercícios da ficha enviada, para o aluno ver antes de
        decidir. None se a origem sumiu."""
        from utils.meta_treino import formatar_meta
        tipo, origem = FichaLoteService._origem_do_envio(envio)
        if tipo == 'modelo':
            for f in VersaoService.fichas_prontas_para_tela():
                if f['slug'] == origem:
                    return f['treinos']
            return None
        if tipo != 'versao':
            return None
        treinos = []
        for tv in (TreinoVersao.query.filter_by(versao_id=origem.id)
                   .options(joinedload(TreinoVersao.exercicios))
                   .order_by(TreinoVersao.ordem).all()):
            itens = []
            for ve in sorted(tv.exercicios, key=lambda x: x.ordem or 0):
                nome = (ve.exercicio_usuario.nome if ve.exercicio_usuario_id and ve.exercicio_usuario
                        else ve.exercicio_base.nome if ve.exercicio_base else None)
                if nome:
                    itens.append({'nome': nome, 'meta': formatar_meta(ve.meta_series, ve.meta_reps_min,
                                                                      ve.meta_reps_max)})
            treinos.append({'codigo': tv.codigo, 'nome': tv.nome_treino, 'exercicios': itens})
        return treinos

    # ------------------------------------------------------------------
    # Notificações
    # ------------------------------------------------------------------

    @staticmethod
    def _notificar(aluno, professor, titulo, mensagem, url):
        from services.notificacao_service import NotificacaoService
        try:
            NotificacaoService.notificar_aluno(aluno.id, professor, tipo='treino_adicionado', titulo=titulo,
                                               mensagem=mensagem, url=url)
        except Exception:
            logger.exception(f'Falha ao notificar o aluno {aluno.id}')

    @staticmethod
    def _notificar_troca(aluno, professor, nova):
        url = _url('aluno.ver_versao', f'/aluno/versao/{nova.id}', versao_id=nova.id)
        FichaLoteService._notificar(aluno, professor, 'Você tem uma nova ficha',
                                    f'{_nome(professor)} trocou sua ficha por "{nova.descricao}". '
                                    'Já dá para registrar o próximo treino nela.', url)

    @staticmethod
    def _notificar_professor(envio, titulo, mensagem):
        from services.notificacao_service import NotificacaoService
        try:
            NotificacaoService.criar_ou_agrupar(destinatario_id=envio.professor_id, remetente_id=envio.aluno_id,
                                                tipo='treino_adicionado', titulo=titulo, mensagem=mensagem,
                                                url=f'/professor/aluno/{envio.aluno_id}/versoes')
        except Exception:
            logger.exception(f'Falha ao notificar o professor {envio.professor_id}')
