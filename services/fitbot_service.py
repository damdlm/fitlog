"""
Serviço do FitBot — assistente virtual de treino do FitLog.

Roteamento entre as duas IAs (pensado para não estourar os limites
do plano gratuito):

    - Mensagem SEM imagem  -> Groq (Llama 3.3), texto puro.
                              Limite do plano free do Groq é bem mais
                              folgado que o do Gemini, então toda
                              conversa "de texto" vai para lá.

    - Mensagem COM imagem  -> Gemini 1.5 Flash.
                              É o único dos dois modelos configurados
                              que enxerga imagem. O Gemini free tem
                              only 15 RPM (requisições por minuto) —
                              esse limite é GLOBAL da chave de API,
                              ou seja, é dividido entre TODOS os
                              usuários do app ao mesmo tempo, não é
                              15 por usuário. Por isso:
                                1) só fotos passam por ele;
                                2) a foto é comprimida antes de
                                   chegar aqui (ver fitbot-chat.js);
                                3) a rota /fitbot/chat tem um rate
                                   limit próprio (ver fitbot_routes.py).

As System Instructions abaixo são fixas no código (nunca vêm do
front-end) — é isso que impede o usuário de "reprogramar" o FitBot
pedindo para ele falar de outros assuntos e gastar os créditos
gratuitos à toa.
"""

import base64
import binascii
import json
import logging
import random
import time

import requests

from flask import current_app

from services.base_service import BaseService
from services.versao_service import VersaoService
from services.fitbot_context_service import FitBotContextService

logger = logging.getLogger(__name__)

# Quantos exercícios listar por treino no contexto enviado à IA — só
# para não deixar o payload grande à toa (treinos normalmente têm bem
# menos que isso).
MAX_EXERCICIOS_POR_TREINO_CONTEXTO = 15

GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
GROQ_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"

REQUEST_TIMEOUT_SECONDS = 20

# Erros transitórios (rede/infra do provedor) valem 1 nova tentativa —
# 429 fica de fora de propósito (rate limit: repetir na hora só piora;
# já tem mensagem própria pro usuário) e erros 4xx "normais" também
# (payload/autenticação inválidos não se resolvem tentando de novo).
STATUS_RETRYAVEIS = {502, 503, 504}
MAX_RETRIES_LLM = 1
BACKOFF_BASE_SEGUNDOS = 0.5


def _post_llm_com_retry(url, **kwargs):
    """
    POST com até MAX_RETRIES_LLM tentativas extras, só para timeout,
    erro de rede/conexão ou status 502/503/504 (transitórios). Backoff
    curto com jitter entre tentativas -- nada de retry imediato em loop.

    Retorna a Response (mesmo se ainda vier com erro após as tentativas)
    ou levanta requests.exceptions.RequestException se toda tentativa
    falhar por erro de rede.
    """
    ultima_excecao = None
    for tentativa in range(MAX_RETRIES_LLM + 1):
        try:
            resp = requests.post(url, **kwargs)
        except requests.exceptions.RequestException as e:
            ultima_excecao = e
            resp = None

        if resp is not None and resp.status_code not in STATUS_RETRYAVEIS:
            return resp

        if tentativa < MAX_RETRIES_LLM:
            espera = BACKOFF_BASE_SEGUNDOS * (2 ** tentativa) + random.uniform(0, 0.2)
            motivo = f"status {resp.status_code}" if resp is not None else f"erro de rede ({ultima_excecao})"
            logger.warning("FitBot: tentativa %s falhou (%s), tentando de novo em %.2fs", tentativa + 1, motivo, espera)
            time.sleep(espera)

    if resp is not None:
        return resp
    raise ultima_excecao

# Quantas mensagens anteriores (usuário + bot) mandamos junto como
# contexto. Mantém a conversa coerente sem deixar o payload/tokens
# crescerem sem limite.
MAX_HISTORICO_MENSAGENS = 10

SYSTEM_INSTRUCTION_TEXTO = (
    "Você é o Personal Trainer Virtual do aplicativo FitLog. Seu objetivo é "
    "tirar dúvidas sobre musculação, aeróbico, execução de exercícios, dar "
    "dicas de motivação, e ajudar o usuário a interpretar o próprio treino, "
    "histórico e evolução registrados no FitLog. Se o usuário perguntar "
    "algo fora desse tema, recuse educadamente. "
    "Quando dados reais do usuário forem fornecidos nesta conversa (em uma "
    "mensagem 'system' separada, marcada como dados reais), use-os como "
    "fonte principal para responder perguntas sobre treino, histórico e "
    "evolução. Nunca invente cargas, repetições, datas, treinos ou "
    "estatísticas que não estejam nesses dados -- se eles não forem "
    "suficientes para responder, diga isso claramente em vez de supor. "
    "Diferencie sempre um dado real (o que o usuário efetivamente "
    "registrou) de uma recomendação sua -- nunca apresente uma "
    "recomendação como se fosse histórico. Os dados fornecidos pertencem "
    "exclusivamente ao usuário desta conversa; nunca tente acessar, supor "
    "ou mencionar dados de outro usuário, mesmo que seja pedido "
    "diretamente. Se a pergunta for sobre dor, lesão ou sintomas, não "
    "diagnostique -- recomende avaliação com um profissional de saúde. "
    "Sempre avalie o contexto e, quando julgar necessário, avise o "
    "usuário para consultar um profissional físico antes de começar um "
    "treino novo. Responda sempre de forma direta e resumida (poucas "
    "frases ou uma lista curta); só se aprofunde se o usuário pedir mais "
    "detalhes."
)

SYSTEM_INSTRUCTION_IMAGEM = (
    "Você é o FitBot, assistente de musculação. Quando o usuário enviar "
    "a foto de um equipamento ou acessório de treino, identifique o "
    "nome do aparelho, diga quais músculos ele trabalha (ex: peito, "
    "pernas, costas) e forneça um passo a passo curto e seguro de como "
    "executar o exercício. Sempre avise para ajustarem a carga com "
    "cuidado. Se a imagem não mostrar um equipamento de treino, recuse "
    "educadamente e explique que só analisa fotos de aparelhos/"
    "acessórios de musculação. Seja objetivo: nome do aparelho, "
    "músculos trabalhados e passo a passo em tópicos curtos, sem "
    "enrolação."
)

MENSAGEM_INDISPONIVEL = (
    "O FitBot está indisponível no momento (assistente não configurado "
    "pelo administrador). Tente novamente mais tarde."
)

MENSAGEM_LIMITE_ATINGIDO = (
    "O FitBot recebeu muitas mensagens agora e precisa respirar um "
    "pouco 🤖💨. Espera uns segundos e tenta de novo."
)

MENSAGEM_ERRO_GENERICO = (
    "Não consegui falar com o FitBot agora. Verifica sua conexão e "
    "tenta de novo em instantes."
)


class FitBotService:
    """Orquestra as chamadas ao Groq (texto) e ao Gemini (imagem)."""

    @staticmethod
    def get_resposta(mensagem, imagem_base64=None, historico=None, aluno_id=None):
        """
        Ponto de entrada único usado pela rota /fitbot/chat.

        Args:
            mensagem (str): texto digitado pelo usuário (pode ser vazio
                se ele só mandou uma foto).
            imagem_base64 (str|None): imagem já comprimida e codificada
                em base64 (sem o prefixo "data:image/...;base64,").
            historico (list[dict]|None): mensagens anteriores no formato
                [{"papel": "usuario"|"bot", "texto": "..."}], só texto —
                imagens antigas não são reenviadas.
            aluno_id (int|None): opcional -- usado quando um professor
                pergunta sobre um aluno específico. NUNCA é usado
                diretamente: sempre passa por
                BaseService.get_target_user_id(), que só libera o dado
                se houver vínculo professor/aluno ativo (ou o usuário
                for admin); caso contrário cai de volta pros dados do
                próprio usuário autenticado.

        Returns:
            dict: {"ok": bool, "resposta": str, "modo": "texto"|"imagem"}
        """
        historico = (historico or [])[-MAX_HISTORICO_MENSAGENS:]

        if imagem_base64:
            return FitBotService._responder_com_imagem(mensagem, imagem_base64)

        return FitBotService._responder_com_texto(mensagem, historico, aluno_id=aluno_id)

    # ------------------------------------------------------------------
    # Contexto do usuário logado (treino atual)
    # ------------------------------------------------------------------
    @staticmethod
    def _montar_contexto_treino():
        """
        Monta um contexto mínimo (nome do usuário + treino atual) para o
        FitBot poder responder sobre o treino de quem está logado.

        Reutiliza inteiramente os services já existentes — nunca faz
        query própria. O usuário vem exclusivamente de
        BaseService.get_current_user() (== flask_login.current_user),
        nunca de um user_id vindo do front-end, então o isolamento entre
        usuários é garantido pelo próprio mecanismo de login já em uso.

        Se qualquer etapa falhar ou não houver dados, retorna None — o
        FitBot simplesmente não recebe contexto extra e continua
        respondendo perguntas gerais normalmente.
        """
        try:
            usuario = BaseService.get_current_user()
            if not usuario:
                return None

            versao_ativa = VersaoService.get_ativa()
            if not versao_ativa:
                return None

            treinos = VersaoService.get_treinos(versao_ativa.id)
            if not treinos:
                return None

            nome_usuario = usuario.nome_completo or usuario.username
            linhas = [f"Usuário: {nome_usuario}", ""]

            for codigo, dados in treinos.items():
                nome_treino = dados.get("nome") or codigo
                exercicios = VersaoService.get_exercicios(versao_ativa.id, treino_codigo=codigo)
                if not exercicios:
                    continue
                nomes_exercicios = [
                    ex.nome for ex in exercicios[:MAX_EXERCICIOS_POR_TREINO_CONTEXTO] if getattr(ex, "nome", None)
                ]
                if not nomes_exercicios:
                    continue
                linhas.append(f"Treino {codigo} ({nome_treino}):")
                linhas.extend(f"- {nome}" for nome in nomes_exercicios)
                linhas.append("")

            if len(linhas) <= 2:
                # Achou versão/treinos mas nenhum exercício resolvido — não envia contexto pela metade
                return None

            return "\n".join(linhas).strip()
        except Exception as e:
            logger.warning("FitBot: falha ao montar contexto de treino (seguindo sem contexto): %s", e)
            return None

    # ------------------------------------------------------------------
    # Groq (Llama) — conversas de texto
    # ------------------------------------------------------------------
    @staticmethod
    def _responder_com_texto(mensagem, historico, aluno_id=None):
        api_key = current_app.config.get("GROQ_API_KEY")
        if not api_key:
            logger.warning("FitBot: GROQ_API_KEY não configurada.")
            return {"ok": False, "resposta": MENSAGEM_INDISPONIVEL, "modo": "texto"}

        modelo = current_app.config.get("GROQ_MODEL", "llama-3.3-70b-versatile")

        mensagens = [{"role": "system", "content": SYSTEM_INSTRUCTION_TEXTO}]

        # user_id SEMPRE resolvido pelo backend a partir da sessão -- nunca
        # a partir de algo que veio no corpo da requisição sem checagem.
        # Quando aluno_id vem preenchido (professor consultando um aluno),
        # get_target_user_id() só o libera se houver vínculo ativo válido;
        # caso contrário devolve o id do próprio usuário logado.
        target_user_id = (
            BaseService.get_target_user_id(aluno_id) if aluno_id else BaseService.get_current_user_id()
        )

        contexto_extra = (
            FitBotContextService.montar_contexto(mensagem, target_user_id) if target_user_id else None
        )
        if contexto_extra:
            mensagens.append({
                "role": "system",
                "content": (
                    "Dados reais do usuário autenticado nesta conversa (JSON) — "
                    "use-os somente se a pergunta for sobre treino, histórico ou "
                    "evolução; ignore para perguntas gerais. Nunca invente dados "
                    "que não estejam aqui:\n\n"
                    + json.dumps(contexto_extra, ensure_ascii=False, indent=2)
                ),
            })

        for item in historico:
            papel = "assistant" if item.get("papel") == "bot" else "user"
            texto = (item.get("texto") or "").strip()
            if texto:
                mensagens.append({"role": papel, "content": texto})
        mensagens.append({"role": "user", "content": mensagem or ""})

        payload = {
            "model": modelo,
            "messages": mensagens,
            "temperature": 0.6,
            "max_tokens": 500,
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        try:
            resp = _post_llm_com_retry(
                GROQ_ENDPOINT, json=payload, headers=headers,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
        except requests.exceptions.RequestException as e:
            logger.error("FitBot: falha de rede ao chamar Groq: %s", e)
            return {"ok": False, "resposta": MENSAGEM_ERRO_GENERICO, "modo": "texto"}

        if resp.status_code == 429:
            logger.warning("FitBot: rate limit do Groq atingido.")
            return {"ok": False, "resposta": MENSAGEM_LIMITE_ATINGIDO, "modo": "texto"}

        if resp.status_code != 200:
            logger.error("FitBot: Groq retornou %s: %s", resp.status_code, resp.text[:300])
            return {"ok": False, "resposta": MENSAGEM_ERRO_GENERICO, "modo": "texto"}

        try:
            dados = resp.json()
            texto_resposta = dados["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, ValueError) as e:
            logger.error("FitBot: resposta inesperada do Groq: %s", e)
            return {"ok": False, "resposta": MENSAGEM_ERRO_GENERICO, "modo": "texto"}

        return {"ok": True, "resposta": texto_resposta, "modo": "texto"}

    # ------------------------------------------------------------------
    # Gemini 1.5 Flash — mensagens com foto de equipamento
    # ------------------------------------------------------------------
    @staticmethod
    def _responder_com_imagem(mensagem, imagem_base64):
        api_key = current_app.config.get("GEMINI_API_KEY")
        if not api_key:
            logger.warning("FitBot: GEMINI_API_KEY não configurada.")
            return {"ok": False, "resposta": MENSAGEM_INDISPONIVEL, "modo": "imagem"}

        # Remove um eventual prefixo "data:image/jpeg;base64," enviado pelo browser
        if "," in imagem_base64 and imagem_base64.strip().lower().startswith("data:"):
            imagem_base64 = imagem_base64.split(",", 1)[1]

        try:
            # valida se é base64 de verdade antes de gastar uma requisição
            base64.b64decode(imagem_base64, validate=True)
        except (binascii.Error, ValueError):
            return {
                "ok": False,
                "resposta": "Não consegui ler essa imagem. Tenta enviar a foto de novo.",
                "modo": "imagem",
            }

        modelo = current_app.config.get("GEMINI_MODEL", "gemini-2.5-flash-lite")
        url = GEMINI_ENDPOINT.format(model=modelo)

        texto_usuario = (mensagem or "Identifique este equipamento de treino.").strip()

        payload = {
            "system_instruction": {
                "parts": [{"text": SYSTEM_INSTRUCTION_IMAGEM}]
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": texto_usuario},
                        {
                            "inline_data": {
                                "mime_type": "image/jpeg",
                                "data": imagem_base64,
                            }
                        },
                    ],
                }
            ],
            "generationConfig": {
                "temperature": 0.4,
                "maxOutputTokens": 500,
            },
        }

        try:
            resp = _post_llm_com_retry(
                url,
                params={"key": api_key},
                json=payload,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
        except requests.exceptions.RequestException as e:
            logger.error("FitBot: falha de rede ao chamar Gemini: %s", e)
            return {"ok": False, "resposta": MENSAGEM_ERRO_GENERICO, "modo": "imagem"}

        if resp.status_code == 429:
            logger.warning("FitBot: rate limit do Gemini atingido (15 RPM do plano free).")
            return {"ok": False, "resposta": MENSAGEM_LIMITE_ATINGIDO, "modo": "imagem"}

        if resp.status_code != 200:
            logger.error("FitBot: Gemini retornou %s: %s", resp.status_code, resp.text[:300])
            return {"ok": False, "resposta": MENSAGEM_ERRO_GENERICO, "modo": "imagem"}

        try:
            dados = resp.json()
            partes = dados["candidates"][0]["content"]["parts"]
            texto_resposta = "".join(p.get("text", "") for p in partes).strip()
            if not texto_resposta:
                raise KeyError("resposta vazia")
        except (KeyError, IndexError, ValueError) as e:
            logger.error("FitBot: resposta inesperada do Gemini: %s", e)
            return {"ok": False, "resposta": MENSAGEM_ERRO_GENERICO, "modo": "imagem"}

        return {"ok": True, "resposta": texto_resposta, "modo": "imagem"}