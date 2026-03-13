"""Schemas para serialização de treinos"""

from marshmallow import Schema, fields, validate, post_load
from models import Treino

class TreinoSchema(Schema):
    """Schema completo para treinos"""
    
    id = fields.Int(dump_only=True)
    codigo = fields.Str(required=True, validate=validate.Length(equal=1))
    nome = fields.Str(required=True, validate=validate.Length(min=1, max=100))
    descricao = fields.Str(allow_none=True)
    user_id = fields.Int(dump_only=True)
    created_at = fields.DateTime(dump_only=True)
    
    # Relacionamentos
    exercicios = fields.Nested('ExercicioSimplificadoSchema', many=True, dump_only=True)
    qtd_exercicios = fields.Method("get_qtd_exercicios")
    
    def get_qtd_exercicios(self, obj):
        """Retorna quantidade de exercícios"""
        return len(obj.exercicios) if obj.exercicios else 0
    
    @post_load
    def make_treino(self, data, **kwargs):
        """Cria objeto Treino a partir dos dados"""
        return Treino(**data)

class TreinoSimplificadoSchema(Schema):
    """Schema simplificado para listagens"""
    
    id = fields.Int()
    codigo = fields.Str()
    nome = fields.Str()
    descricao = fields.Str()
    qtd_exercicios = fields.Int()