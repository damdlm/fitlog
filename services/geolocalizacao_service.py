"""Geolocalização do professor a partir do CEP (services/billing_service.py já
usa User.endereco_cep para o checkout Asaas; aqui é reaproveitado só para
posicionar o professor no mapa de busca do aluno -- ver routes/aluno/mapa.py
e routes/api_routes.py).

A geocodificação roda uma única vez por CEP (cacheada via CacheService, o
mesmo wrapper Redis/SimpleCache usado no resto do projeto -- ver
services/base_service.py) e só é refeita quando o professor troca o CEP.
"""
import logging
import re
import time
from datetime import datetime, timezone
from typing import Optional, Tuple

import requests
from sqlalchemy import func

from models import User, db
from .base_service import BaseService, CacheService

logger = logging.getLogger(__name__)

TIMEOUT_SEGUNDOS = 4  # nunca deixar o cadastro/edição do perfil travado
USER_AGENT = {"User-Agent": "FitLog/1.0 (contato@fitlog.vip)"}  # exigido pelo Nominatim
CACHE_TTL_SEGUNDOS = 60 * 60 * 24 * 30  # 30 dias -- coordenadas de um CEP não mudam
CACHE_PREFIXO = "geocep:"

ZOOM_MINIMO_PONTOS_INDIVIDUAIS = 11  # abaixo disso, o mapa mostra clusters
LIMITE_PROFESSORES_POR_RESPOSTA = 300
LIMITE_CLUSTERS_POR_RESPOSTA = 500

Coordenadas = Tuple[float, float]


class GeolocalizacaoService(BaseService):

    # ------------------------------------------------------------
    # Geocodificação de CEP
    # ------------------------------------------------------------

    @staticmethod
    def normalizar_cep(cep: Optional[str]) -> Optional[str]:
        digitos = re.sub(r"\D", "", cep or "")
        return digitos if len(digitos) == 8 else None

    @staticmethod
    def _brasilapi(cep: str):
        """Retorna (coordenadas | None, endereço | None)."""
        resposta = requests.get(f"https://brasilapi.com.br/api/cep/v2/{cep}", timeout=TIMEOUT_SEGUNDOS)
        if resposta.status_code != 200:
            return None, None
        dados = resposta.json()
        coords = (dados.get("location") or {}).get("coordinates") or {}
        try:
            return (float(coords["latitude"]), float(coords["longitude"])), dados
        except (KeyError, TypeError, ValueError):
            return None, dados  # sem coordenadas, mas dá pro fallback usar o endereço

    @staticmethod
    def _nominatim(params: dict) -> Optional[Coordenadas]:
        resposta = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={**params, "country": "Brazil", "format": "json", "limit": 1},
            headers=USER_AGENT,
            timeout=TIMEOUT_SEGUNDOS,
        )
        if resposta.status_code == 200 and resposta.json():
            item = resposta.json()[0]
            return float(item["lat"]), float(item["lon"])
        return None

    @classmethod
    def geocodificar_cep(cls, cep: Optional[str]) -> Optional[dict]:
        """Retorna {"lat", "lng", "cidade", "uf"} ou None. Cacheado por
        CACHE_TTL_SEGUNDOS -- cidade/UF vêm da mesma chamada à BrasilAPI
        que resolve as coordenadas, sem custo extra de rede."""
        cep = cls.normalizar_cep(cep)
        if not cep:
            return None

        chave_cache = f"{CACHE_PREFIXO}{cep}"
        em_cache = CacheService.get(chave_cache)
        if em_cache == "nao_encontrado":
            return None
        if isinstance(em_cache, dict):
            return em_cache
        # else: sem cache, ou formato antigo (só lat/lng, de antes da
        # cidade/UF existirem) -- recalcula e já grava no formato novo.

        resultado = None
        try:
            coords, endereco = cls._brasilapi(cep)
            cidade = (endereco or {}).get("city")
            uf = (endereco or {}).get("state")
            if not coords and endereco:
                # Fallback 1: rua + cidade; fallback 2: só a cidade
                rua = endereco.get("street")
                base = {"city": cidade, "state": uf}
                coords = (rua and cls._nominatim({**base, "street": rua})) or cls._nominatim(base)
            if coords:
                resultado = {"lat": coords[0], "lng": coords[1], "cidade": cidade, "uf": uf}
        except requests.RequestException:
            logger.warning("Falha ao geocodificar CEP %s", cep)
            return None  # erro transitório: não grava no cache, tenta de novo depois

        CacheService.set(chave_cache, resultado if resultado else "nao_encontrado", CACHE_TTL_SEGUNDOS)
        return resultado

    @classmethod
    def atualizar_geolocalizacao_professor(cls, professor: User) -> bool:
        """Geocodifica professor.endereco_cep e grava lat/lng + cidade/UF.
        Chame sempre que o CEP do professor mudar (ver
        services/professor_perfil_service.py:atualizar_perfil). Retorna
        True se o professor ficou com coordenadas."""
        resultado = cls.geocodificar_cep(professor.endereco_cep)
        if resultado:
            professor.professor_latitude = resultado["lat"]
            professor.professor_longitude = resultado["lng"]
            professor.professor_cidade = resultado["cidade"]
            professor.professor_uf = resultado["uf"]
            professor.professor_geo_atualizado_em = datetime.now(timezone.utc)
        else:
            professor.professor_latitude = professor.professor_longitude = None
            professor.professor_cidade = professor.professor_uf = None
        db.session.commit()
        return resultado is not None

    @classmethod
    def geocodificar_pendentes(cls, limite: int = 50) -> int:
        """Para o comando CLI `flask geocodificar-professores`: processa
        professores visíveis no mapa com CEP mas ainda sem coordenadas."""
        pendentes = User.query.filter(
            User.tipo_usuario == "professor",
            User.professor_visivel_no_mapa.is_(True),
            User.endereco_cep.isnot(None),
            User.professor_latitude.is_(None),
        ).limit(limite).all()

        total = 0
        for professor in pendentes:
            if cls.atualizar_geolocalizacao_professor(professor):
                total += 1
            time.sleep(1.1)  # respeita o limite de 1 req/s do Nominatim
        return total

    # ------------------------------------------------------------
    # Busca para o mapa do aluno (área visível + clusters)
    # ------------------------------------------------------------

    @staticmethod
    def _filtro_area(sul, oeste, norte, leste):
        return (
            User.tipo_usuario == "professor",
            User.ativo.is_(True),
            User.professor_visivel_no_mapa.is_(True),
            User.professor_latitude.isnot(None),
            User.professor_latitude.between(sul, norte),
            User.professor_longitude.between(oeste, leste),
        )

    @classmethod
    def clusters_na_area(cls, sul, oeste, norte, leste, zoom):
        """Agrupa em células de grade (tamanho decresce com o zoom) --
        usado quando o zoom está afastado, pra não devolver milhares de
        pontos de uma vez. Inclui o id de um dos professores da célula
        (min) -- quando total==1, esse id é o do único professor ali, e
        a rota usa isso pra mostrar o pino azul clicável em vez de uma
        bolha de cluster (ver routes/api_routes.py:api_professores_mapa)."""
        passo = 360.0 / (2 ** zoom) / 4.0
        celula_lat = func.floor(User.professor_latitude / passo)
        celula_lng = func.floor(User.professor_longitude / passo)

        linhas = (
            db.session.query(
                func.count(User.id),
                func.avg(User.professor_latitude),
                func.avg(User.professor_longitude),
                func.min(User.id),
            )
            .filter(*cls._filtro_area(sul, oeste, norte, leste))
            .group_by(celula_lat, celula_lng)
            .limit(LIMITE_CLUSTERS_POR_RESPOSTA)
            .all()
        )
        return [
            {"total": total, "lat": lat, "lng": lng, "id_se_unico": id_min}
            for total, lat, lng, id_min in linhas
        ]

    @classmethod
    def professores_por_id(cls, ids):
        if not ids:
            return []
        return User.query.filter(User.id.in_(ids)).all()

    @classmethod
    def professores_na_area(cls, sul, oeste, norte, leste):
        return (
            User.query.filter(*cls._filtro_area(sul, oeste, norte, leste))
            .limit(LIMITE_PROFESSORES_POR_RESPOSTA)
            .all()
        )

    # ------------------------------------------------------------
    # Busca textual por cidade (reservado para uma busca no mapa que
    # não dependa de bounding box -- ex: campo "Digite sua cidade").
    # Ainda sem rota/UI própria; os métodos abaixo já ficam prontos.
    # ------------------------------------------------------------

    @classmethod
    def buscar_por_cidade(cls, cidade: str, uf: Optional[str] = None, limite: int = 100):
        """Professores visíveis no mapa numa cidade (case-insensitive).
        Cidade sozinha é ambígua no Brasil (várias cidades repetem nome
        em UFs diferentes) -- passe uf sempre que o front souber."""
        filtros = [
            User.tipo_usuario == "professor",
            User.ativo.is_(True),
            User.professor_visivel_no_mapa.is_(True),
            func.lower(User.professor_cidade) == cidade.strip().lower(),
        ]
        if uf:
            filtros.append(func.upper(User.professor_uf) == uf.strip().upper())
        return User.query.filter(*filtros).limit(limite).all()

    @classmethod
    def cidades_com_professores(cls):
        """Lista (cidade, uf, total) para popular um autocomplete de
        busca por cidade, ordenada pelas cidades com mais professores."""
        return (
            db.session.query(User.professor_cidade, User.professor_uf, func.count(User.id))
            .filter(
                User.tipo_usuario == "professor",
                User.ativo.is_(True),
                User.professor_visivel_no_mapa.is_(True),
                User.professor_cidade.isnot(None),
            )
            .group_by(User.professor_cidade, User.professor_uf)
            .order_by(func.count(User.id).desc())
            .all()
        )