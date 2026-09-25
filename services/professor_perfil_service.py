"""Serviço da página pública do professor -- perfil (bio, CREF,
especialidades, foto, Instagram) e o slug estável da URL. A avaliação
por estrelas fica em AvaliacaoProfessorService (services/avaliacao_professor_service.py)."""
import logging
import os
import time

from models import db, User
from services.storage_service import StorageService
from utils.slug_utils import slugify
from .base_service import BaseService

logger = logging.getLogger(__name__)

# Vocabulário fixo de especialidades (checkboxes na tela de edição) --
# valores livres não são aceitos, pra manter a página pública
# consistente entre professores.
ESPECIALIDADES_VALIDAS = {
    'emagrecimento': 'Emagrecimento',
    'hipertrofia': 'Hipertrofia',
    'reabilitacao': 'Reabilitação',
    'terceira_idade': 'Terceira idade',
}

EXTENSOES_FOTO_PERMITIDAS = {'.jpg', '.jpeg', '.png', '.webp'}
FOTO_TAMANHO_MAXIMO_BYTES = 4 * 1024 * 1024  # 4MB

TAGLINE_TAMANHO_MAXIMO = 200
BIO_TAMANHO_MAXIMO = 1000
CREF_TAMANHO_MAXIMO = 30
INSTAGRAM_TAMANHO_MAXIMO = 120


class ProfessorPerfilService(BaseService):

    @staticmethod
    def garantir_slug(professor: User) -> str:
        """Gera e grava o slug na primeira vez que a página pública é
        acessada/editada (nunca muda depois, pra não quebrar link já
        compartilhado -- ver comentário no campo em models.py)."""
        if professor.professor_slug:
            return professor.professor_slug

        base = slugify(professor.nome_completo or professor.username) or f'professor-{professor.id}'
        candidato = base
        sufixo = 2
        # Colisão é rara (dois professores com nome igual), mas trata
        # mesmo assim -- tenta "-2", "-3"... até achar um livre.
        while User.query.filter_by(professor_slug=candidato).first() is not None:
            candidato = f'{base}-{sufixo}'
            sufixo += 1

        professor.professor_slug = candidato
        db.session.commit()
        return candidato

    @staticmethod
    def get_por_slug(slug: str):
        """Busca o professor pela slug pública. Só retorna professores
        ativos -- se a conta foi desativada, a página pública some
        (404), nunca vaza dado de conta inativa."""
        if not slug:
            return None
        professor = User.query.filter_by(professor_slug=slug, tipo_usuario='professor', ativo=True).first()
        return professor

    @staticmethod
    def atualizar_perfil(professor: User, form) -> tuple[bool, str]:
        """Atualiza os campos editáveis da página pública a partir de
        `request.form` (MultiDict) da rota de edição -- validação de
        tamanho/vocabulário acontece aqui. Retorna (ok, mensagem)."""
        if not professor.is_professor():
            return False, 'Apenas professores têm página pública.'

        tagline = (form.get('tagline') or '').strip()
        bio = (form.get('bio') or '').strip()
        cref = (form.get('cref') or '').strip()
        instagram = (form.get('instagram') or '').strip().lstrip('@')
        # Cola de link completo (ex: "https://instagram.com/fulano") --
        # o professor só precisa digitar o handle, mas aceitamos colado.
        if 'instagram.com/' in instagram:
            instagram = instagram.split('instagram.com/')[-1].split('/')[0].split('?')[0]

        if len(tagline) > TAGLINE_TAMANHO_MAXIMO:
            return False, f'A frase de impacto pode ter no máximo {TAGLINE_TAMANHO_MAXIMO} caracteres.'
        if len(bio) > BIO_TAMANHO_MAXIMO:
            return False, f'O texto "Sobre mim" pode ter no máximo {BIO_TAMANHO_MAXIMO} caracteres.'
        if len(cref) > CREF_TAMANHO_MAXIMO:
            return False, 'CREF inválido.'
        if len(instagram) > INSTAGRAM_TAMANHO_MAXIMO:
            return False, 'Instagram inválido.'

        especialidades = [e for e in form.getlist('especialidades') if e in ESPECIALIDADES_VALIDAS]

        try:
            professor.professor_tagline = tagline or None
            professor.professor_bio = bio or None
            professor.professor_cref = cref or None
            professor.professor_instagram = instagram or None
            professor.professor_especialidades = especialidades or None
            # Checkbox desmarcado não vem no POST -- ausência = False
            # (mesmo padrão de auth_routes.update_profile).
            professor.professor_mostrar_avaliacoes = 'mostrar_avaliacoes' in form
            ProfessorPerfilService.garantir_slug(professor)
            db.session.commit()
            return True, 'Página atualizada com sucesso!'
        except Exception:
            db.session.rollback()
            logger.exception('Erro ao atualizar perfil público do professor %s', professor.id)
            return False, 'Erro ao salvar. Tente novamente.'

    @staticmethod
    def salvar_foto(professor: User, arquivo) -> tuple[bool, str]:
        """Recebe um FileStorage (request.files['foto']), valida e
        sobe pro bucket S3-compatível (services/storage_service.py) --
        mesmo bucket "fitlog-media" já usado pela mídia dos exercícios,
        numa pasta separada ("professores/"). Cada upload usa uma chave
        nova (com timestamp) para poder cachear a URL como imutável no
        navegador, e a chave antiga é removida do bucket em seguida."""
        if not professor.is_professor():
            return False, 'Apenas professores têm página pública.'
        if not arquivo or not arquivo.filename:
            return False, 'Nenhum arquivo selecionado.'

        ext = os.path.splitext(arquivo.filename)[1].lower()
        if ext not in EXTENSOES_FOTO_PERMITIDAS:
            return False, 'Formato inválido -- use JPG, PNG ou WEBP.'

        arquivo.seek(0, os.SEEK_END)
        tamanho = arquivo.tell()
        arquivo.seek(0)
        if tamanho > FOTO_TAMANHO_MAXIMO_BYTES:
            return False, 'Arquivo muito grande -- o limite é 4MB.'

        content_type = arquivo.mimetype or 'application/octet-stream'
        chave_antiga = professor.professor_foto_chave
        chave_nova = f'professores/{professor.id}-{int(time.time())}{ext}'

        if not StorageService.is_configured():
            logger.warning(
                'ProfessorPerfilService.salvar_foto: bucket S3 não configurado neste '
                'ambiente -- upload de foto indisponível (funciona normalmente em produção).'
            )
            return False, 'Upload de foto indisponível neste ambiente no momento.'

        if not StorageService.upload_fileobj(arquivo, chave_nova, content_type=content_type):
            return False, 'Falha ao enviar a foto. Tente novamente.'

        try:
            professor.professor_foto_chave = chave_nova
            ProfessorPerfilService.garantir_slug(professor)
            db.session.commit()
        except Exception:
            db.session.rollback()
            logger.exception('Erro ao salvar chave da foto do professor %s', professor.id)
            StorageService.delete_object(chave_nova)
            return False, 'Erro ao salvar. Tente novamente.'

        if chave_antiga:
            StorageService.delete_object(chave_antiga)

        return True, 'Foto atualizada com sucesso!'

    @staticmethod
    def especialidades_selecionadas(professor: User) -> list[str]:
        """Nomes de exibição das especialidades marcadas, na ordem
        fixa do vocabulário (não na ordem que foram salvas)."""
        selecionadas = set(professor.professor_especialidades or [])
        return [label for chave, label in ESPECIALIDADES_VALIDAS.items() if chave in selecionadas]
