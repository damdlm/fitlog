from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

# =====================================================
# TABELA DE ASSOCIAÇÃO ENTRE ALUNOS E PROFESSORES
# =====================================================

class AlunoProfessor(db.Model):
    """Tabela de associação entre alunos e professores"""
    __tablename__ = 'aluno_professor'
    
    id = db.Column(db.Integer, primary_key=True)
    aluno_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, unique=True)
    professor_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    data_associacao = db.Column(db.DateTime, default=datetime.now)
    ativo = db.Column(db.Boolean, default=True)
    
    # Relacionamentos
    aluno = db.relationship('User', foreign_keys=[aluno_id], backref='professor_associado')
    professor = db.relationship('User', foreign_keys=[professor_id], backref='alunos_associados')
    
    __table_args__ = (
        db.Index('idx_aluno_professor_aluno', 'aluno_id'),
        db.Index('idx_aluno_professor_professor', 'professor_id'),
    )


# =====================================================
# SOLICITAÇÕES DE VÍNCULO
# =====================================================

class SolicitacaoVinculo(db.Model):
    """Solicitações de vínculo entre alunos e professores"""
    __tablename__ = 'solicitacoes_vinculo'
    
    id = db.Column(db.Integer, primary_key=True)
    aluno_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    professor_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    status = db.Column(db.String(20), default='pendente')
    data_solicitacao = db.Column(db.DateTime, default=datetime.now)
    data_resposta = db.Column(db.DateTime)
    
    # Relacionamentos
    aluno = db.relationship('User', foreign_keys=[aluno_id], backref='solicitacoes_enviadas')
    professor = db.relationship('User', foreign_keys=[professor_id], backref='solicitacoes_recebidas')
    
    __table_args__ = (
        db.Index('idx_solicitacao_status', 'status'),
        db.Index('idx_solicitacao_professor', 'professor_id'),
    )


# =====================================================
# MODELO DE USUÁRIO
# =====================================================

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    
    tipo_usuario = db.Column(db.String(20), nullable=False, default='aluno')
    nome_completo = db.Column(db.String(200))
    telefone = db.Column(db.String(20))
    data_nascimento = db.Column(db.Date)
    ativo = db.Column(db.Boolean, default=True)
    
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.now)
    last_login = db.Column(db.DateTime)
    
    # Relacionamentos
    treinos = db.relationship('Treino', backref='usuario', lazy=True, cascade='all, delete-orphan')
    versoes = db.relationship('VersaoGlobal', backref='usuario', lazy=True, cascade='all, delete-orphan')
    registros = db.relationship('RegistroTreino', backref='usuario', lazy=True, cascade='all, delete-orphan')
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def is_professor(self):
        return self.tipo_usuario == 'professor'
    
    def is_aluno(self):
        return self.tipo_usuario == 'aluno'
    
    def get_alunos(self):
        if not self.is_professor():
            return []
        associations = AlunoProfessor.query.filter_by(professor_id=self.id, ativo=True).all()
        alunos = []
        for assoc in associations:
            aluno = User.query.get(assoc.aluno_id)
            if aluno and aluno.ativo:
                alunos.append(aluno)
        return alunos
    
    def get_professor(self):
        if not self.is_aluno():
            return None
        assoc = AlunoProfessor.query.filter_by(aluno_id=self.id, ativo=True).first()
        if assoc:
            return User.query.get(assoc.professor_id)
        return None
    
    def pode_acessar_dados_de(self, outro_usuario):
        if self.is_admin:
            return True
        if self.is_professor():
            assoc = AlunoProfessor.query.filter_by(
                aluno_id=outro_usuario.id,
                professor_id=self.id,
                ativo=True
            ).first()
            return assoc is not None
        return self.id == outro_usuario.id
    
    @property
    def solicitacoes_pendentes_count(self):
        if self.is_professor():
            return SolicitacaoVinculo.query.filter_by(
                professor_id=self.id,
                status='pendente'
            ).count()
        return 0
    
    def __repr__(self):
        return f'<User {self.username} ({self.tipo_usuario})>'


# =====================================================
# MODELOS DE DADOS
# =====================================================

class Treino(db.Model):
    __tablename__ = 'treinos'
    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(1), nullable=False)
    nome = db.Column(db.String(100), nullable=False)
    descricao = db.Column(db.String(100), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)
    
    # exercicios removido — use ExercicioCustomizado.query.filter_by(usuario_id=...) diretamente
    versoes = db.relationship('TreinoVersao', backref='treino_ref', lazy=True, cascade='all, delete-orphan')
    registros = db.relationship('RegistroTreino', backref='treino_ref', lazy=True, cascade='all, delete-orphan')
    
    __table_args__ = (
        db.UniqueConstraint('user_id', 'codigo', name='unique_treino_por_usuario'),
        db.Index('idx_treino_user', 'user_id'),
        db.Index('idx_treino_codigo', 'codigo'),
    )


# Musculo e Exercicio (tabelas legadas) foram removidos.
# Use Musculo e ExercicioCustomizado para novos exercícios do usuário.


class VersaoGlobal(db.Model):
    __tablename__ = 'versoes_globais'
    id = db.Column(db.Integer, primary_key=True)
    numero_versao = db.Column(db.Integer, nullable=False)
    descricao = db.Column(db.String(200), nullable=False)
    divisao = db.Column(db.String(10), nullable=False, default='ABC')
    data_inicio = db.Column(db.Date, nullable=False)
    data_fim = db.Column(db.Date)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)
    
    treinos = db.relationship('TreinoVersao', backref='versao_ref', lazy=True, cascade='all, delete-orphan')
    registros = db.relationship('RegistroTreino', backref='versao_ref', lazy=True, cascade='all, delete-orphan')
    
    __table_args__ = (
        db.UniqueConstraint('user_id', 'numero_versao', name='unique_versao_por_usuario'),
        db.Index('idx_versao_user_data', 'user_id', 'data_inicio', 'data_fim'),
    )


class TreinoVersao(db.Model):
    __tablename__ = 'treinos_versao'
    id = db.Column(db.Integer, primary_key=True)
    versao_id = db.Column(db.Integer, db.ForeignKey('versoes_globais.id', ondelete='CASCADE'), nullable=False)
    treino_id = db.Column(db.Integer, db.ForeignKey('treinos.id', ondelete='CASCADE'), nullable=False)
    nome_treino = db.Column(db.String(100), nullable=False)
    descricao_treino = db.Column(db.String(200))
    ordem = db.Column(db.Integer, default=0)
    
    exercicios = db.relationship('VersaoExercicio', back_populates='treino_versao', lazy=True, cascade='all, delete-orphan')
    
    __table_args__ = (
        db.UniqueConstraint('versao_id', 'treino_id', name='unique_treino_na_versao'),
        db.Index('idx_treino_versao_versao', 'versao_id'),
        db.Index('idx_treino_versao_treino', 'treino_id'),
    )

class VersaoExercicio(db.Model):
    __tablename__ = 'versao_exercicios'

    id = db.Column(db.Integer, primary_key=True)

    treino_versao_id = db.Column(
        db.Integer,
        db.ForeignKey('treinos_versao.id', ondelete='CASCADE'),
        nullable=False
    )

    exercicio_id = db.Column(
        db.Integer,
        db.ForeignKey('exercicios_usuario.id', ondelete='CASCADE'),
        nullable=False
    )

    exercicio_base_id = db.Column(
        db.Integer,
        db.ForeignKey('exercicios_base.id', ondelete='CASCADE')
    )

    exercicio_custom_id = db.Column(
        db.Integer,
        db.ForeignKey('exercicios_usuario.id', ondelete='CASCADE')
    )

    ordem = db.Column(db.Integer, default=0)

    # RELACIONAMENTOS
    treino_versao = db.relationship(
        'TreinoVersao',
        back_populates='exercicios'
    )

    exercicio = db.relationship(
        'ExercicioUsuario',
        foreign_keys=[exercicio_id],
        backref='versoes_exercicio'
    )

    exercicio_base = db.relationship(
        'ExercicioBase',
        foreign_keys=[exercicio_base_id]
    )

    exercicio_custom = db.relationship(
        'ExercicioUsuario',
        foreign_keys=[exercicio_custom_id]
    )

    __table_args__ = (
        db.UniqueConstraint(
            'treino_versao_id',
            'exercicio_id',
            name='unique_exercicio_na_versao'
        ),
        db.Index('idx_versao_exercicio_treino', 'treino_versao_id'),
        db.Index('idx_versao_exercicio_exercicio', 'exercicio_id'),
    )


class RegistroTreino(db.Model):
    __tablename__ = 'registros_treino'

    id = db.Column(db.Integer, primary_key=True)

    treino_id = db.Column(db.Integer, db.ForeignKey('treinos.id'), nullable=False)
    versao_id = db.Column(db.Integer, db.ForeignKey('versoes_globais.id'), nullable=False)

    periodo = db.Column(db.String(50), nullable=False)
    semana = db.Column(db.Integer, nullable=False)

    exercicio_id = db.Column(
        db.Integer,
        db.ForeignKey('exercicios_usuario.id'),
        nullable=False
    )

    data_registro = db.Column(db.DateTime, nullable=False)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False
    )

    created_at = db.Column(db.DateTime, default=datetime.now)

    series = db.relationship(
        'HistoricoTreino',
        backref='registro_ref',
        lazy='dynamic',
        cascade='all, delete-orphan'
    )

    exercicio = db.relationship(
        'ExercicioUsuario',
        foreign_keys=[exercicio_id],
        backref='registros'
    )

    __table_args__ = (
        db.Index('idx_registro_user_data', 'user_id', 'data_registro'),
        db.Index('idx_registro_busca', 'user_id', 'treino_id', 'periodo', 'semana'),
        db.Index('idx_registro_exercicio', 'exercicio_id'),
        db.Index('idx_registro_versao', 'versao_id'),
        db.Index('idx_registro_periodo_semana', 'periodo', 'semana'),
    )


class HistoricoTreino(db.Model):
    __tablename__ = 'historico_treino'
    id = db.Column(db.Integer, primary_key=True)
    registro_id = db.Column(db.Integer, db.ForeignKey('registros_treino.id', ondelete='CASCADE'), nullable=False)
    carga = db.Column(db.Numeric(5,1), nullable=False)
    repeticoes = db.Column(db.Integer, nullable=False)
    ordem = db.Column(db.Integer, default=0)
    
    __table_args__ = (
        db.Index('idx_historico_registro', 'registro_id'),
        db.Index('idx_historico_carga', 'carga'),
    )


# =====================================================
# MODELOS BASE COMPARTILHADOS
# =====================================================

class Musculo(db.Model):
    __tablename__ = 'musculos'
    
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(50), unique=True, nullable=False)
    nome_exibicao = db.Column(db.String(50), nullable=False)
    descricao = db.Column(db.Text)
    
   # exercicios_base = db.relationship('ExercicioBase', backref='musculo_ref', lazy=True)


class ExercicioBase(db.Model):
    """
    Catálogo global de exercícios — gerenciado apenas pelo admin.
    Populado a partir do arquivo exercises-ptbr-full-translation.json.
    Imagens servidas de static/exercises/<imagem_inicial|imagem_execucao>
    """
    __tablename__ = 'exercicios_base'

    id               = db.Column(db.Integer, primary_key=True)
    id_original      = db.Column(db.String(200), unique=True)        # ex: "3_4_Sit-Up"
    nome             = db.Column(db.String(200), nullable=False)
    musculo_id       = db.Column(db.Integer, db.ForeignKey('musculos.id'))
    musculo_nome     = db.Column(db.String(100))                     # nome original do JSON
    musculos_secundarios = db.Column(db.ARRAY(db.Text))
    equipamento      = db.Column(db.String(100))
    nivel            = db.Column(db.String(50))
    forca            = db.Column(db.String(50))
    mecanica         = db.Column(db.String(50))
    categoria        = db.Column(db.String(50))
    instrucoes       = db.Column(db.ARRAY(db.Text))
    imagem_inicial   = db.Column(db.String(300))                     # relativo a static/exercises/
    imagem_execucao  = db.Column(db.String(300))
    created_at       = db.Column(db.DateTime, default=datetime.now)

    musculo_ref = db.relationship('Musculo', foreign_keys=[musculo_id], backref='exercicios_base')

    __table_args__ = (
        db.Index('idx_exercicio_base_nome',    'nome'),
        db.Index('idx_exercicio_base_musculo', 'musculo_id'),
        db.Index('idx_exercicio_base_nivel',   'nivel'),
        db.Index('idx_exercicio_base_id_orig', 'id_original'),
    )


class ExercicioUsuario(db.Model):
    """
    Exercicios de professores e alunos.
    Visibilidade: o proprio usuario + alunos/professor vinculados.
    Ao quebrar vinculo: exercicios usados em registros sao copiados automaticamente.
    """
    __tablename__ = 'exercicios_usuario'

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    nome = db.Column(db.String(200), nullable=False)
    descricao = db.Column(db.Text)
    musculo_id = db.Column(db.Integer, db.ForeignKey('musculos.id'))
    observacoes = db.Column(db.Text)
    copiado_de_professor_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now)

    musculo_ref = db.relationship('Musculo', foreign_keys=[musculo_id], backref='exercicios_usuario')
    usuario = db.relationship('User', foreign_keys=[usuario_id], backref='exercicios')
    copiado_de = db.relationship('User', foreign_keys=[copiado_de_professor_id])

    __table_args__ = (
        db.Index('idx_exercicio_usuario_usuario', 'usuario_id'),
        db.Index('idx_exercicio_usuario_musculo', 'musculo_id'),
    )


# Alias para compatibilidade com codigo existente
ExercicioCustomizado = ExercicioUsuario