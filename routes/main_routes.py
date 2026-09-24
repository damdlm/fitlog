from flask import Blueprint, render_template
from flask_login import current_user
from services.treino_service import TreinoService

main_bp = Blueprint('main', __name__)


@main_bp.route("/")
def index():
    """Página inicial.

    Sem @login_required de propósito: '/' precisa ser pública e
    indexável (landing page) para quem não está logado, mas continua
    sendo o dashboard de sempre para quem já tem sessão -- por isso a
    ramificação é feita aqui dentro, em vez de criar uma rota nova
    (ex: /dashboard). Os dezenas de `redirect(url_for('main.index'))`
    espalhados pelo projeto (decorators, professor/aluno/billing/auth
    routes) só acontecem para usuário já autenticado, então continuam
    caindo direto no dashboard, sem nenhuma mudança de comportamento.
    """
    if not current_user.is_authenticated:
        return render_template("landing.html")

    treinos = TreinoService.get_da_versao_ativa()

    return render_template("index.html", treinos=treinos)


@main_bp.route("/precos")
def precos():
    """Página pública de preços. Sem @login_required de propósito,
    igual à landing -- precisa ser vista por quem ainda não tem conta.

    Os valores vêm direto do banco via PlanoService.listar_editaveis()
    (os mesmos 3 planos editáveis em /admin/telas-controladas), pra
    refletir automaticamente qualquer ajuste de preço feito pelo admin
    sem precisar mexer nesta página."""
    from services.plano_service import PlanoService
    planos = {p.codigo: p for p in PlanoService.listar_editaveis()}
    return render_template("precos.html", planos=planos)


@main_bp.route("/faq")
def faq():
    """Página pública de perguntas frequentes. Sem @login_required de
    propósito, igual à landing e a /precos -- precisa ser vista por
    quem ainda não tem conta, inclusive linkada a partir da tela
    pública de contato (templates/contato_publico.html)."""
    return render_template("faq.html")