from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, session
from flask_login import login_user, logout_user, login_required, current_user
from models import db, User
from extensions import limiter   # <-- importa de extensions, nunca de app
from datetime import datetime, timezone
from urllib.parse import urlparse, urljoin
import logging
from utils.validators import validar_email, validar_senha
from utils.email_utils import enviar_email
from services.base_service import CacheService
from services.billing_service import BillingService

auth_bp = Blueprint('auth', __name__)
logger = logging.getLogger(__name__)


def _safe_next_url(next_url):
    """
    Valida URL de redirecionamento pós-login -- previne Open Redirect
    (CORREÇÃO seção 11 do hardening de segurança).

    A checagem antiga (`startswith('/') and not startswith('//')`)
    tinha um bypass conhecido: `next=/\\evil.com` passa em ambas as
    condições, mas navegadores normalizam a contra-barra para `/`,
    virando `//evil.com` (URL protocol-relative) na hora de navegar --
    ou seja, um redirect externo escapando do check baseado em string.

    Agora usamos urllib.parse: resolvemos next_url contra o host atual
    (urljoin) e só aceitamos se o netloc resultante bater exatamente
    com o host da aplicação, além de rejeitar explicitamente qualquer
    contra-barra. Isso é O(1)/local -- sem custo de rede ou banco.
    """
    if not next_url or '\\' in next_url or not next_url.startswith('/'):
        return url_for('main.index')

    host_atual = urlparse(request.host_url).netloc
    destino = urlparse(urljoin(request.host_url, next_url))

    if destino.scheme in ('http', 'https') and destino.netloc == host_atual:
        return next_url
    return url_for('main.index')


def _build_trusted_url(endpoint, **values):
    """
    Gera uma URL absoluta para e-mails/links enviados ao usuário sem
    depender do header Host da requisição recebida (CORREÇÃO seção 12
    do hardening de segurança -- Trusted Hosts / Host Header Injection).

    Se APP_BASE_URL estiver configurada (recomendado em produção), o
    link é montado a partir dela. Caso contrário, cai no comportamento
    padrão do Flask (url_for com _external=True, que usa o Host
    recebido) com um aviso no log -- aceitável em dev/testes, mas em
    produção configure APP_BASE_URL para fechar esse vetor.
    """
    from flask import current_app

    base_url = current_app.config.get('APP_BASE_URL')
    caminho = url_for(endpoint, **values)  # relativo, não usa Host

    if base_url:
        return base_url.rstrip('/') + caminho

    logger.warning(
        "APP_BASE_URL não configurada -- link gerado a partir do Host "
        "da requisição (vulnerável a Host Header Injection se o proxy "
        "reverso não validar o Host antes de chegar aqui)."
    )
    return url_for(endpoint, _external=True, **values)


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
        session['sv'] = user.session_version
        logger.info(f"Login OK -- usuario ID {user.id} ({user.tipo_usuario})")
        flash(f'Bem-vindo, {user.nome_completo or user.username}!', 'boas-vindas')

        return redirect(_safe_next_url(request.args.get('next')))

    return render_template('auth/login.html')


@auth_bp.route('/reset-password-request', methods=['GET', 'POST'])
@limiter.limit("5 per hour")
def reset_password_request():
    """Solicitação de recuperação de senha: envia (ou loga, se SMTP não
    estiver configurado) um link de reset válido por 30 minutos."""
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        user = User.query.filter_by(email=email).first() if email else None

        # Mensagem sempre igual, exista ou não a conta com esse e-mail —
        # evita que alguém use este formulário para descobrir quais
        # e-mails estão cadastrados (user enumeration).
        if user and user.ativo:
            token = user.get_reset_token()
            db.session.commit()
            reset_url = _build_trusted_url('auth.reset_password', token=token)

            corpo_texto = (
                f"Olá, {user.nome_completo or user.username}!\n\n"
                f"Recebemos uma solicitação para redefinir sua senha no FitLog.\n"
                f"Clique no link abaixo para escolher uma nova senha "
                f"(válido por 30 minutos):\n\n{reset_url}\n\n"
                f"Se você não solicitou isso, pode ignorar este e-mail."
            )
            enviar_email(user.email, 'FitLog — Redefinição de senha', corpo_texto)
            logger.info(f"Solicitacao de reset de senha -- usuario ID {user.id}")
        else:
            logger.info(f"Solicitacao de reset de senha para e-mail nao encontrado/inativo -- IP: {request.remote_addr}")

        flash('Se este e-mail estiver cadastrado, enviamos um link de redefinição de senha.', 'info')
        return redirect(url_for('auth.login'))

    return render_template('auth/reset_password_request.html')


@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
@limiter.limit("10 per hour")
def reset_password(token):
    """Redefinição de senha a partir de um token válido enviado por e-mail."""
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    user = User.verify_reset_token(token)
    if user is None:
        flash('Este link de redefinição é inválido ou expirou. Solicite um novo.', 'danger')
        return redirect(url_for('auth.reset_password_request'))

    if not user.ativo:
        # Defesa extra: reset_password_request já não emite token novo pra
        # conta inativa, mas um token emitido pouco antes de uma exclusão/
        # anonimização de conta (routes/privacidade_routes.py:excluir_conta)
        # já é invalidado lá -- este check aqui é só um cinto e suspensório.
        flash('Este link de redefinição não é mais válido.', 'danger')
        return redirect(url_for('auth.reset_password_request'))

    if request.method == 'POST':
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        ok_senha, msg_senha = validar_senha(password)
        if not ok_senha:
            flash(msg_senha, 'danger')
            return render_template('auth/reset_password.html', token=token)

        if password != confirm_password:
            flash('As senhas não coincidem', 'danger')
            return render_template('auth/reset_password.html', token=token)

        user.set_password(password)
        User.invalidate_reset_token(token)
        db.session.commit()
        logger.info(f"Senha redefinida via token -- usuario ID {user.id}")
        flash('Senha redefinida com sucesso! Faça login com a nova senha.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/reset_password.html', token=token)


@auth_bp.route('/check-email')
@limiter.limit("20 per minute")
def check_email():
    """
    Verifica se um e-mail já está cadastrado -- usado tanto no cadastro
    (bloquear e-mail duplicado) quanto na tela de recuperação de senha
    (avisar que o e-mail não tem conta). NOTA: usar isso na recuperação
    de senha remove a proteção contra enumeração de usuários que o
    fluxo de reset tinha antes -- decisão explícita do dono do projeto.
    """
    email = request.args.get('email', '').strip()
    if not email:
        return jsonify({'exists': False})
    existe = User.query.filter_by(email=email).first() is not None
    return jsonify({'exists': existe})


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
        if tipo_usuario not in ('aluno', 'professor'):
            # O formulário só envia 'aluno' ou 'professor' (radio buttons),
            # mas um POST manual poderia mandar qualquer string. Sem essa
            # checagem, um tipo_usuario inválido deixa o usuário sem acesso
            # a nenhuma área (is_professor() e is_aluno() ficam False).
            flash('Tipo de usuário inválido', 'danger')
            return redirect(url_for('auth.register'))
        nome_completo = request.form.get('nome_completo', '').strip()
        telefone = request.form.get('telefone', '').strip()

        if not username or not email or not password:
            flash('Todos os campos são obrigatórios', 'danger')
            return redirect(url_for('auth.register'))

        if not request.form.get('aceite_termos'):
            flash('É preciso ler e aceitar os Termos de Uso e a Política de Privacidade para criar uma conta.', 'danger')
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

        # Cadastro é UMA transação só: User + trial + aceite de Termos/
        # Política. Se qualquer etapa falhar, nada é confirmado -- sem
        # isso, era possível ficar com um usuário criado (e já com
        # commit feito) sem o aceite correspondente registrado, caso a
        # gravação do aceite falhasse por algum motivo depois. Ver
        # services/privacidade_service.py:registrar_aceite_cadastro e
        # services/billing_service.py:iniciar_trial (ambos com
        # commit=False aqui, para participar deste único commit).
        from services.privacidade_service import PrivacidadeService
        try:
            user = User(
                username=username,
                email=email,
                tipo_usuario=tipo_usuario,
                nome_completo=nome_completo or None,
                telefone=telefone or None,
                ativo=True,
            )
            user.set_password(password)

            db.session.add(user)
            db.session.flush()

            # Trial de 30 dias do Plano Fit começa junto com o cadastro
            # -- vale tanto para aluno quanto para professor (que também
            # treina por conta própria no mesmo sistema, reaproveitando
            # as telas de aluno) -- ver services/billing_service.py:
            # iniciar_trial.
            BillingService.iniciar_trial(user, commit=False)

            # Registro formal e versionado do aceite -- o checkbox único
            # do formulário vira dois registros (Termos + Política),
            # dentro desta mesma transação.
            PrivacidadeService.registrar_aceite_cadastro(user.id, commit=False)

            db.session.commit()
        except Exception:
            db.session.rollback()
            # Só informação técnica no log -- nunca senha, token ou
            # outro dado pessoal desnecessário (username/e-mail aqui já
            # são os mesmos que o próprio usuário acabou de digitar no
            # formulário que falhou, não um vazamento de dado de
            # terceiro).
            logger.exception(
                "Erro ao criar conta -- cadastro revertido por completo (tipo_usuario=%s)",
                tipo_usuario,
            )
            flash('Não foi possível criar sua conta agora. Tente novamente.', 'danger')
            return redirect(url_for('auth.register'))

        if user.tipo_usuario == 'aluno':
            flash('Conta criada com sucesso!', 'success')
        else:
            flash('Conta de professor criada com sucesso!', 'success')

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

        if current_user.tipo_usuario == 'aluno':
            # Checkbox desmarcado não vem no POST -- ausência = False.
            novo_valor = 'aparecer_no_ranking' in request.form
            if novo_valor != current_user.aparecer_no_ranking:
                current_user.aparecer_no_ranking = novo_valor
                # Opt-out de privacidade precisa valer na hora -- não dá
                # pra esperar o TTL de 5min do cache do ranking geral.
                CacheService.invalidate("ranking:geral:30d")

        db.session.commit()

        flash('Perfil atualizado com sucesso!', 'success')
    except Exception:
        db.session.rollback()
        logger.exception("Erro ao atualizar perfil")
        flash('Erro ao atualizar perfil. Tente novamente.', 'danger')

    return redirect(url_for('auth.profile'))


@auth_bp.route('/change-password', methods=['POST'])
@login_required
@limiter.limit("10 per hour")
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