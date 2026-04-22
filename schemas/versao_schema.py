"""Schemas para serialização de versões"""

from marshmallow import Schema, fields, validate, post_load, pre_load
from models import VersaoGlobal
from datetime import datetime

class VersaoSchema(Schema):
    """Schema completo para versões"""
    
    id = fields.Int(dump_only=True)
    numero_versao = fields.Int(dump_only=True)
    descricao = fields.Str(required=True, validate=validate.Length(min=1, max=200))
    data_inicio = fields.Date(required=True)
    data_fim = fields.Date(allow_none=True)
    user_id = fields.Int(dump_only=True)
    created_at = fields.DateTime(dump_only=True)
    
    # Campos calculados
    data_inicio_formatada = fields.Method("formatar_data_inicio")
    data_fim_formatada = fields.Method("formatar_data_fim")
    qtd_treinos = fields.Method("get_qtd_treinos")
    qtd_exercicios = fields.Method("get_qtd_exercicios")
    is_ativa = fields.Method("get_is_ativa")
    periodo = fields.Method("get_periodo")
    
    def formatar_data_inicio(self, obj):
        """Formata data de início"""
        if obj.data_inicio:
            return obj.data_inicio.strftime("%d/%m/%Y")
        return ""
    
    def formatar_data_fim(self, obj):
        """Formata data de fim"""
        if obj.data_fim:
            return obj.data_fim.strftime("%d/%m/%Y")
        return ""
    
    def get_qtd_treinos(self, obj):
        """Retorna quantidade de treinos"""
        return len(obj.treinos) if obj.treinos else 0
    
    def get_qtd_exercicios(self, obj):
        """Retorna quantidade de exercícios"""
        total = 0
        for tv in obj.treinos:
            total += len(tv.exercicios) if tv.exercicios else 0
        return total
    
    def get_is_ativa(self, obj):
        """Verifica se a versão está ativa"""
        return obj.data_fim is None
    
    def get_periodo(self, obj):
        """Retorna período formatado"""
        inicio = obj.data_inicio.strftime("%d/%m/%Y") if obj.data_inicio else "?"
        fim = obj.data_fim.strftime("%d/%m/%Y") if obj.data_fim else "Atual"
        return f"{inicio} até {fim}"
    
    @pre_load
    def process_data(self, data, **kwargs):
        """Processa dados antes da carga"""
        # Converter strings vazias para None
        if 'data_fim' in data and not data['data_fim']:
            data['data_fim'] = None
        return data
    
    @post_load
    def make_versao(self, data, **kwargs):
        """Cria objeto VersaoGlobal a partir dos dados"""
        return VersaoGlobal(**data)

class VersaoSimplificadoSchema(Schema):
    """Schema simplificado para listagens"""
    
    id = fields.Int()
    numero_versao = fields.Int()
    descricao = fields.Str()
    data_inicio = fields.Date()
    data_fim = fields.Date()
    is_ativa = fields.Boolean()
    data_inicio_formatada = fields.Str()
    data_fim_formatada = fields.Str()

class VersaoDetalhadaSchema(VersaoSchema):
    """Schema detalhado incluindo treinos e exercícios"""
    
    treinos = fields.Dict(keys=fields.Str(), values=fields.Dict(), dump_only=True)
    
    @post_load
    def make_versao(self, data, **kwargs):
        return VersaoGlobal(**data)