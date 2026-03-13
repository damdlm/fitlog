"""Schemas para serialização de exercícios"""

from marshmallow import Schema, fields, validate, post_load
from models import Exercicio

class ExercicioSchema(Schema):
    """Schema completo para exercícios"""
    
    id = fields.Int(dump_only=True)
    nome = fields.Str(required=True, validate=validate.Length(min=1, max=200))
    descricao = fields.Str(allow_none=True)
    musculo_id = fields.Int(allow_none=True)
    treino_id = fields.Int(allow_none=True)
    user_id = fields.Int(dump_only=True)
    created_at = fields.DateTime(dump_only=True)
    
    # Relacionamentos
    musculo = fields.Nested('MusculoSchema', dump_only=True)
    treino = fields.Nested('TreinoSimplificadoSchema', dump_only=True)
    ultima_carga = fields.Method("get_ultima_carga")
    
    def get_ultima_carga(self, obj):
        """Retorna última carga do exercício"""
        from services.exercicio_service import ExercicioService
        return ExercicioService.get_ultima_carga(obj.id)
    
    @post_load
    def make_exercicio(self, data, **kwargs):
        """Cria objeto Exercicio a partir dos dados"""
        return Exercicio(**data)

class ExercicioSimplificadoSchema(Schema):
    """Schema simplificado para listagens"""
    
    id = fields.Int()
    nome = fields.Str()
    musculo = fields.Str(attribute='musculo_ref.nome_exibicao')
    treino_id = fields.Int()

class MusculoSchema(Schema):
    """Schema para músculos"""
    
    id = fields.Int()
    nome = fields.Str()
    nome_exibicao = fields.Str()