from flask import current_app
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime, timezone
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.ext.hybrid import hybrid_property
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

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
    data_associacao = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
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
    data_solicitacao = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    data_resposta = db.Column(db.DateTime(timezone=True))
    
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
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_login = db.Column(db.DateTime(timezone=True))
    
    # Relacionamentos
    treinos = db.relationship('Treino', backref='usuario', lazy=True, cascade='all, delete-orphan')
    versoes = db.relationship('VersaoGlobal', backref='usuario', lazy=True, cascade='all, delete-orphan')
    registros = db.relationship('RegistroTreino', backref='usuario', lazy=True, cascade='all, delete-orphan')
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def get_reset_token(self, expires_sec=1800):
        """
        Gera um token assinado (itsdangerous) para reset de senha.

        O token embute o id do usuario e o hash da senha atual (nao a
        senha em si). Isso tem duas vantagens sobre guardar um token
        em coluna no banco:
          - nao precisa de migracao/tabela nova;
          - o token se invalida sozinho assim que a senha muda (o hash
            embutido deixa de bater), entao nao da pra reusar um link
            de reset antigo depois que a senha ja foi trocada.

        expires_sec: validade do token em segundos (padrao 30 minutos).
        """
        s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
        return s.dumps(
            {'user_id': self.id, 'pw_hash': self.password_hash},
            salt='password-reset',
        )

    @staticmethod
    def verify_reset_token(token, max_age=1800):
        """
        Verifica um token de reset de senha.
        Retorna o User correspondente se o token for valido, ainda
        dentro da validade, e a senha nao tiver mudado desde a geracao.
        Retorna None em qualquer caso de token invalido/expirado/ja usado.
        """
        s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
        try:
            data = s.loads(token, salt='password-reset', max_age=max_age)
        except (BadSignature, SignatureExpired):
            return None

        user = User.query.get(data.get('user_id'))
        if user is None or user.password_hash != data.get('pw_hash'):
            return None
        return user
    
    def is_professor(self):
        return self.tipo_usuario == 'professor'
    
    def is_aluno(self):
        return self.tipo_usuario == 'aluno'

    def pode_gerenciar_treino_proprio(self):
        """
        Retorna True se o usuário pode ter seus próprios exercícios,
        treinos e versões -- alunos sempre podem, e professores também,
        já que um professor pode treinar por conta própria usando o
        mesmo sistema (reaproveita as telas/rotas do aluno, sempre
        filtradas por user_id=current_user.id).
        """
        return self.is_aluno() or self.is_professor()
    
    def get_alunos(self):
        """Retorna alunos ativos do professor em uma única query (sem N+1)."""
        if not self.is_professor():
            return []
        return (User.query
                .join(AlunoProfessor, AlunoProfessor.aluno_id == User.id)
                .filter(
                    AlunoProfessor.professor_id == self.id,
                    AlunoProfessor.ativo == True,
                    User.ativo == True,
                )
                .order_by(User.nome_completo)
                .all())
    
    def get_professor(self):
        """Retorna o professor do aluno em uma única query (sem N+1)."""
        if not self.is_aluno():
            return None
        return (User.query
                .join(AlunoProfessor, AlunoProfessor.professor_id == User.id)
                .filter(
                    AlunoProfessor.aluno_id == self.id,
                    AlunoProfessor.ativo == True,
                )
                .first())
    
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
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    
    versoes = db.relationship('TreinoVersao', backref='treino_ref', lazy=True, cascade='all, delete-orphan')
    registros = db.relationship('RegistroTreino', backref='treino_ref', lazy=True, cascade='all, delete-orphan')
    
    __table_args__ = (
        db.UniqueConstraint('user_id', 'codigo', name='unique_treino_por_usuario'),
        db.Index('idx_treino_user', 'user_id'),
        db.Index('idx_treino_codigo', 'codigo'),
    )


class VersaoGlobal(db.Model):
    __tablename__ = 'versoes_globais'
    id = db.Column(db.Integer, primary_key=True)
    numero_versao = db.Column(db.Integer, nullable=False)
    descricao = db.Column(db.String(200), nullable=False)
    divisao = db.Column(db.String(10), nullable=False, default='ABC')
    data_inicio = db.Column(db.Date, nullable=False)
    data_fim = db.Column(db.Date)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    
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
    treino_versao_id = db.Column(db.Integer, db.ForeignKey('treinos_versao.id', ondelete='CASCADE'), nullable=False)

    # Duas FKs: uma para exercícios do usuário, outra para exercícios do catálogo
    # (exercicio_base_id aponta hoje para exercicios_sistema — nome mantido por
    # compatibilidade com código/templates existentes que já usam esse nome)
    exercicio_usuario_id = db.Column(db.Integer, db.ForeignKey('exercicios_usuario.id', ondelete='CASCADE'))
    exercicio_base_id = db.Column(db.Integer, db.ForeignKey('exercicios_sistema.id', ondelete='CASCADE'))

    ordem = db.Column(db.Integer, default=0)

    # Relacionamentos
    treino_versao = db.relationship('TreinoVersao', back_populates='exercicios')
    exercicio_usuario = db.relationship('ExercicioUsuario', foreign_keys=[exercicio_usuario_id])
    exercicio_base = db.relationship('ExercicioSistema', foreign_keys=[exercicio_base_id])

    # Validação: exatamente uma das FKs deve ser preenchida
    __table_args__ = (
        db.CheckConstraint(
            '(exercicio_usuario_id IS NOT NULL AND exercicio_base_id IS NULL) OR '
            '(exercicio_usuario_id IS NULL AND exercicio_base_id IS NOT NULL)',
            name='check_exactly_one_exercicio'
        ),
        db.UniqueConstraint('treino_versao_id', 'exercicio_usuario_id', name='unique_exercicio_usuario_na_versao'),
        db.UniqueConstraint('treino_versao_id', 'exercicio_base_id', name='unique_exercicio_base_na_versao'),
        db.Index('idx_versao_exercicio_treino', 'treino_versao_id'),
    )

    @hybrid_property
    def exercicio(self):
        """Retorna o objeto exercício (seja do usuário ou base)"""
        return self.exercicio_usuario or self.exercicio_base

    # ============================================================
    # NOVAS PROPERTIES PARA COMPATIBILIDADE
    # ============================================================

    @property
    def exercicio_id(self):
        """Retorna o ID do exercício, independente da origem."""
        return self.exercicio_usuario_id or self.exercicio_base_id

    @property
    def tipo_exercicio(self):
        """Retorna 'usuario' ou 'base'."""
        return 'usuario' if self.exercicio_usuario_id else 'base'

class RegistroTreino(db.Model):
    __tablename__ = 'registros_treino'

    id = db.Column(db.Integer, primary_key=True)

    treino_id = db.Column(db.Integer, db.ForeignKey('treinos.id'), nullable=False)
    versao_id = db.Column(db.Integer, db.ForeignKey('versoes_globais.id'), nullable=False)

    periodo = db.Column(db.String(50), nullable=False)
    semana = db.Column(db.Integer, nullable=False)

    # Duas FKs: uma para exercícios do usuário, outra para exercícios base
    exercicio_usuario_id = db.Column(
        db.Integer,
        db.ForeignKey('exercicios_usuario.id', ondelete='CASCADE'),
        nullable=True
    )

    exercicio_base_id = db.Column(
        db.Integer,
        db.ForeignKey('exercicios_sistema.id', ondelete='CASCADE'),
        nullable=True
    )

    data_registro = db.Column(db.DateTime, nullable=False)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False
    )

    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    series = db.relationship(
        'HistoricoTreino',
        backref='registro_ref',
        lazy=True, 
        cascade='all, delete-orphan'
    )

    exercicio = db.relationship(
        'ExercicioUsuario',
        foreign_keys=[exercicio_usuario_id],
        backref='registros'
    )

    exercicio_base = db.relationship(
        'ExercicioSistema',
        foreign_keys=[exercicio_base_id],
        backref='registros'
    )

    __table_args__ = (
        db.CheckConstraint(
            '(exercicio_usuario_id IS NOT NULL AND exercicio_base_id IS NULL) OR '
            '(exercicio_usuario_id IS NULL AND exercicio_base_id IS NOT NULL)',
            name='check_registro_exactly_one_exercicio'
        ),
        db.Index('idx_registro_user_data', 'user_id', 'data_registro'),
        db.Index('idx_registro_busca', 'user_id', 'treino_id', 'periodo', 'semana'),
        db.Index('idx_registro_exercicio_usuario', 'exercicio_usuario_id'),
        db.Index('idx_registro_exercicio_base', 'exercicio_base_id'),
        db.Index('idx_registro_versao', 'versao_id'),
        db.Index('idx_registro_periodo_semana', 'periodo', 'semana'),
    )

    @hybrid_property
    def exercicio_id(self):
        return self.exercicio_usuario_id or self.exercicio_base_id

    @exercicio_id.expression
    def exercicio_id(cls):
        return db.func.coalesce(cls.exercicio_usuario_id, cls.exercicio_base_id)


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


# NOTA: ExercicioBase (tabela exercicios_base) foi descontinuado — o catálogo
# global de exercícios agora vem de ExercicioSistema (tabela exercicios_sistema,
# importada de data/exercises.json). A tabela exercicios_base ainda existe no
# banco (não foi apagada), mas o app não lê/escreve mais nela.


class ExercicioUsuario(db.Model):
    """
    Exercicios de professores e alunos.
    """
    __tablename__ = 'exercicios_usuario'

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    nome = db.Column(db.String(200), nullable=False)
    descricao = db.Column(db.Text)
    musculo_id = db.Column(db.Integer, db.ForeignKey('musculos.id'))
    observacoes = db.Column(db.Text)
    copiado_de_professor_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    musculo_ref = db.relationship('Musculo', foreign_keys=[musculo_id], backref='exercicios_usuario')
    usuario = db.relationship('User', foreign_keys=[usuario_id], backref='exercicios')
    copiado_de = db.relationship('User', foreign_keys=[copiado_de_professor_id])

    __table_args__ = (
        db.Index('idx_exercicio_usuario_usuario', 'usuario_id'),
        db.Index('idx_exercicio_usuario_musculo', 'musculo_id'),
    )

class ExercicioSistema(db.Model):
    """
    Catálogo de exercícios importado de data/exercises.json.
    Fonte separada do catálogo administrado manualmente (ExercicioBase) —
    dataset externo (Gymvisual) usado como base ampliada de exercícios.
    """
    __tablename__ = 'exercicios_sistema'

    id = db.Column(db.Integer, primary_key=True)
    id_original = db.Column(db.String(50), unique=True, nullable=False)  # "id" do JSON, ex: "0001"
    nome = db.Column(db.String(200), nullable=False)
    categoria = db.Column(db.String(100))
    parte_corpo = db.Column(db.String(100))
    equipamento = db.Column(db.String(100))
    instrucao_pt = db.Column(db.Text)
    passos_pt = db.Column(db.JSON)               # lista de strings (instruction_steps.pt)
    grupo_muscular = db.Column(db.String(100))
    musculos_secundarios = db.Column(db.JSON)     # lista de strings
    alvo = db.Column(db.String(100))
    imagem = db.Column(db.String(300))
    gif_url = db.Column(db.String(300))
    media_id = db.Column(db.String(50))
    data_criacao_original = db.Column(db.DateTime(timezone=True))  # "created_at" do JSON
    atribuicao = db.Column(db.String(300))
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.Index('idx_exercicios_sistema_categoria', 'categoria'),
        db.Index('idx_exercicios_sistema_grupo_muscular', 'grupo_muscular'),
    )

    # ============================================================
    # PROPERTIES DE COMPATIBILIDADE COM O ANTIGO ExercicioBase
    # ============================================================
    # exercicios_sistema não tem FK para musculos (grupo_muscular já vem
    # como texto pronto do dataset) nem os campos nivel/forca/mecanica.
    # Essas properties existem só pra reduzir a área de código/templates
    # que precisa mudar — NÃO são colunas reais nem aceitam joinedload().

    @property
    def musculo_nome(self):
        """Compat: em ExercicioBase isso era coluna real; aqui é o próprio grupo_muscular."""
        return self.grupo_muscular

    @property
    def musculo_ref(self):
        """Compat: exercicios_sistema não tem FK para musculos — sempre None."""
        return None

    @property
    def instrucoes(self):
        """Compat: junta instrucao_pt (texto) e passos_pt (lista) em uma lista única."""
        passos = list(self.passos_pt) if self.passos_pt else []
        if self.instrucao_pt and self.instrucao_pt not in passos:
            return [self.instrucao_pt] + passos
        return passos

    @property
    def imagem_inicial(self):
        """Compat: exercicios_sistema guarda uma imagem só (imagem/gif_url)."""
        return self.imagem

    @property
    def imagem_execucao(self):
        """Compat: usa o gif (se houver) como imagem de execução, senão a mesma imagem."""
        return self.gif_url or self.imagem

    # nivel, forca e mecanica não existem no dataset de exercicios_sistema
    nivel = None
    forca = None
    mecanica = None

# Alias para compatibilidade com codigo existente
ExercicioCustomizado = ExercicioUsuario