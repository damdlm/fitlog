# /app/models/vinculo.py
from app import db
from datetime import datetime

class Vinculo(db.Model):
    __tablename__ = 'vinculos'
    
    id = db.Column(db.Integer, primary_key=True)
    professor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    aluno_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # Status
    ativo = db.Column(db.Boolean, default=True)
    data_solicitacao = db.Column(db.DateTime, default=datetime.utcnow)
    data_aprovacao = db.Column(db.DateTime)
    data_encerramento = db.Column(db.DateTime)
    
    # Relacionamentos
    professor = db.relationship('User', foreign_keys=[professor_id], backref='vinculos_como_professor')
    aluno = db.relationship('User', foreign_keys=[aluno_id], backref='vinculos_como_aluno')
    
    def aprovar(self):
        self.ativo = True
        self.data_aprovacao = datetime.utcnow()
        db.session.commit()
    
    def encerrar(self):
        self.ativo = False
        self.data_encerramento = datetime.utcnow()
        db.session.commit()
    
    def __repr__(self):
        return f'<Vinculo Prof:{self.professor_id} Aluno:{self.aluno_id}>'