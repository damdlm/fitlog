from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from models import db, User
from services.seed_service import SeedService
from extensions import limiter   # <-- importa de extensions, nunca de app
from datetime import datetime, timezone
import logging
from utils.validators import validar_email, validar_senha

auth_bp = Blueprint('auth', __name__)
logger = logging.getLogger(__name__)


def _safe_next_url(next_url):
    """
    Valida URL de redirecionamento pós-login — previne Open Redirect.
    Aceita apenas caminhos relativos (ex: /dashboard).
    Rejeita URLs externas (http://...) e protocol-relative (//evil.com).
    """
    if next_url and next_url.startswith('/') and not next_url.startswith('//'):
        return next_url
    return url_for('main.index')


@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit("10 per minute")
def login():
    """Página de login."""
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        remember = bool(request.form.get('remember'))

        user = User.query.filter_by(username=username).first()

        if not user or not user.check_password(password):
            # Não revela se foi o usuário ou a senha que errou (evita user enumeration)
            logger.warning(f"Login invalido -- IP: {request.remote_addr}")
            flash('Usuário ou senha inválidos', 'danger')
            return redirect(url_for('auth.login'))

        if not user.ativo:
            logger.warning(f"Login bloqueado: usuario inativo ID {user.id}")
            flash('Usuário inativo. Contate o administrador.', 'danger')
            return redirect(url_for('auth.login'))

        user.last_login = datetime.now(timezone.utc)
        db.session.commit()

        login_user(user, remember=remember)
        logger.info(f"Login OK -- usuario ID {user.id} ({user.tipo_usuario})")
        flash(f'Bem-vindo, {user.nome_completo or user.username}!', 'success')

        return redirect(_safe_next_url(request.args.get('next')))

    return render_template('auth/login.html')


@auth_bp.route('/register', methods=['GET', 'POST'])
@limiter.limit("5 per hour")
def register():
    """Página de registro."""
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        tipo_usuario = request.form.get('tipo_usuario', 'aluno')
        nome_completo = request.form.get('nome_completo', '').strip()
        telefone = request.form.get('telefone', '').strip()

        if not username or not email or not password:
            flash('Todos os campos são obrigatórios', 'danger')
            return redirect(url_for('auth.register'))

        if len(username) < 3:
            flash('Usuário deve ter pelo menos 3 caracteres', 'danger')
            return redirect(url_for('auth.register'))

        ok_senha, msg_senha = validar_senha(password)
        if not ok_senha:
            flash(msg_senha, 'danger')
            return redirect(url_for('auth.register'))

        if password != confirm_password:
            flash('As senhas não coincidem', 'danger')
            return redirect(url_for('auth.register'))

        ok_email, msg_email = validar_email(email)
        if not ok_email:
            flash(msg_email, 'danger')
            return redirect(url_for('auth.register'))

        if User.query.filter_by(username=username).first():
            flash('Nome de usuário já existe', 'danger')
            return redirect(url_for('auth.register'))

        if User.query.filter_by(email=email).first():
            flash('E-mail já cadastrado', 'danger')
            return redirect(url_for('auth.register'))

        user = User(
            username=username,
            email=email,
            tipo_usuario=tipo_usuario,
            nome_completo=nome_completo or None,
            telefone=telefone or None,
            ativo=True,
        )
        user.set_password(password)

        if User.query.count() == 0:
            user.is_admin = True
            user.tipo_usuario = 'professor'

        db.session.add(user)
        db.session.flush()

        if user.tipo_usuario == 'aluno':
            treinos_criados = SeedService.create_minimal_workouts(user.id)
            if treinos_criados:
                flash(f'Conta criada com {len(treinos_criados)} treinos básicos!', 'success')
            else:
                flash('Conta criada, mas houve erro ao configurar treinos básicos.', 'warning')
        else:
            flash('Conta de professor criada com sucesso!', 'success')

        db.session.commit()
        logger.info(f"Novo usuario: {username} ({tipo_usuario})")
        return redirect(url_for('auth.login'))

    return render_template('auth/register.html')


@auth_bp.route('/logout')
@login_required
def logout():
    logger.info(f"Logout -- usuario {current_user.username}")
    logout_user()
    flash('Você saiu do sistema', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/profile')
@login_required
def profile():
    return render_template('auth/profile.html', user=current_user)


@auth_bp.route('/profile/update', methods=['POST'])
@login_required
def update_profile():
    try:
        nome_completo = request.form.get('nome_completo', '').strip()
        email = request.form.get('email', '').strip()
        telefone = request.form.get('telefone', '').strip()

        if not email:
            flash('E-mail é obrigatório', 'danger')
            return redirect(url_for('auth.profile'))

        if email != current_user.email:
            if User.query.filter_by(email=email).first():
                flash('Este e-mail já está em uso', 'danger')
                return redirect(url_for('auth.profile'))

        current_user.nome_completo = nome_completo or None
        current_user.email = email
        current_user.telefone = telefone or None
        db.session.commit()

        flash('Perfil atualizado com sucesso!', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f"Erro ao atualizar perfil: {e}")
        flash('Erro ao atualizar perfil. Tente novamente.', 'danger')

    return redirect(url_for('auth.profile'))


@auth_bp.route('/change-password', methods=['POST'])
@login_required
def change_password():
    current_password = request.form.get('current_password', '')
    new_password = request.form.get('new_password', '')
    confirm_password = request.form.get('confirm_password', '')

    if not current_password or not new_password or not confirm_password:
        flash('Todos os campos são obrigatórios', 'danger')
        return redirect(url_for('auth.profile'))

    if new_password != confirm_password:
        flash('As senhas não coincidem', 'danger')
        return redirect(url_for('auth.profile'))

    ok_nova, msg_nova = validar_senha(new_password)
    if not ok_nova:
        flash(msg_nova, 'danger')
        return redirect(url_for('auth.profile'))

    if not current_user.check_password(current_password):
        flash('Senha atual incorreta', 'danger')
        return redirect(url_for('auth.profile'))

    current_user.set_password(new_password)
    db.session.commit()
    logger.info(f"Senha alterada -- usuario {current_user.username}")
    flash('Senha alterada com sucesso!', 'success')
    return redirect(url_for('auth.profile'))
