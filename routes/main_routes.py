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
