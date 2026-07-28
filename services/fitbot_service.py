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
import logging

import requests

from flask import current_app

logger = logging.getLogger(__name__)

GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
GROQ_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"

REQUEST_TIMEOUT_SECONDS = 20

# Quantas mensagens anteriores (usuário + bot) mandamos junto como
# contexto. Mantém a conversa coerente sem deixar o payload/tokens
# crescerem sem limite.
MAX_HISTORICO_MENSAGENS = 10

SYSTEM_INSTRUCTION_TEXTO = (
    "Você é o Personal Trainer Virtual do aplicativo FitLog. Seu único "
    "objetivo é tirar dúvidas sobre musculação, aeróbico, execução de "
    "exercícios e dar dicas de motivação. Se o usuário perguntar algo "
    "fora desse tema, recuse educadamente. Sempre avise o usuário para "
    "consultar um profissional físico antes de começar um treino novo."
)

SYSTEM_INSTRUCTION_IMAGEM = (
    "Você é o FitBot, assistente de musculação. Quando o usuário enviar "
    "a foto de um equipamento ou acessório de treino, identifique o "
    "nome do aparelho, diga quais músculos ele trabalha (ex: peito, "
    "pernas, costas) e forneça um passo a passo curto e seguro de como "
    "executar o exercício. Sempre avise para ajustarem a carga com "
    "cuidado. Se a imagem não mostrar um equipamento de treino, recuse "
    "educadamente e explique que só analisa fotos de aparelhos/"
    "acessórios de musculação."
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
    def get_resposta(mensagem, imagem_base64=None, historico=None):
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

        Returns:
            dict: {"ok": bool, "resposta": str, "modo": "texto"|"imagem"}
        """
        historico = (historico or [])[-MAX_HISTORICO_MENSAGENS:]

        if imagem_base64:
            return FitBotService._responder_com_imagem(mensagem, imagem_base64)

        return FitBotService._responder_com_texto(mensagem, historico)

    # ------------------------------------------------------------------
    # Groq (Llama) — conversas de texto
    # ------------------------------------------------------------------
    @staticmethod
    def _responder_com_texto(mensagem, historico):
        api_key = current_app.config.get("GROQ_API_KEY")
        if not api_key:
            logger.warning("FitBot: GROQ_API_KEY não configurada.")
            return {"ok": False, "resposta": MENSAGEM_INDISPONIVEL, "modo": "texto"}

        modelo = current_app.config.get("GROQ_MODEL", "llama-3.3-70b-versatile")

        mensagens = [{"role": "system", "content": SYSTEM_INSTRUCTION_TEXTO}]
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
            resp = requests.post(
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

        modelo = current_app.config.get("GEMINI_MODEL", "gemini-1.5-flash")
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
            resp = requests.post(
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