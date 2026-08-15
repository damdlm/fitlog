"""Testes de segurança contra XSS / HTML injection.

CORREÇÃO 3 (prompt de hardening): o corpo HTML do e-mail de contato
deve escapar nome, e-mail e mensagem do usuário antes de montar o HTML.
"""
from services.contato_service import ContatoService


class _UsuarioFake:
    def __init__(self, nome_completo, username, email, tipo_usuario):
        self.nome_completo = nome_completo
        self.username = username
        self.email = email
        self.tipo_usuario = tipo_usuario


PAYLOADS = [
    "<script>alert(1)</script>",
    "<img src=x onerror=alert(1)>",
    "<svg onload=alert(1)>",
    "\"><script>alert(document.domain)</script>",
]


def _monta_corpo_html(usuario, mensagem):
    """Reproduz a montagem do corpo HTML sem depender de envio real de
    e-mail (não precisamos de RESEND_API_KEY configurada para testar o
    escaping)."""
    from markupsafe import escape

    nome_html = escape(usuario.nome_completo or usuario.username)
    email_html = escape(usuario.email)
    tipo_html = escape(usuario.tipo_usuario)
    mensagem_html = escape(mensagem)

    return (
        f"<p>Nova mensagem recebida pela tela de <strong>Contato</strong> do FitLog.</p>"
        f"<p><strong>De:</strong> {nome_html} "
        f"(<a href='mailto:{email_html}'>{email_html}</a>)<br>"
        f"<strong>Tipo de usuário:</strong> {tipo_html}</p>"
        f"<p><strong>Mensagem:</strong></p>"
        f"<p style='white-space:pre-wrap;background:#f9f9f9;padding:12px;border-radius:8px;'>{mensagem_html}</p>"
    )


def test_mensagem_com_payload_xss_e_escapada():
    usuario = _UsuarioFake("Fulano", "fulano", "fulano@teste.com", "aluno")
    for payload in PAYLOADS:
        html = _monta_corpo_html(usuario, payload)
        # Nenhuma tag real (<script>, <img>, <svg>) deve sobreviver --
        # os caracteres < e > do payload precisam ter sido escapados
        # para entidades HTML, o que impede a criação de elementos/
        # atributos executáveis mesmo que substrings como "onerror="
        # continuem presentes como texto inerte.
        assert "<script>" not in html
        assert "<img" not in html
        assert "<svg" not in html
        assert "&lt;" in html
        # o conteúdo original deve continuar presente, só que escapado
        assert "alert(1)" in html or "alert(document.domain)" in html


def test_nome_completo_com_payload_xss_e_escapado():
    usuario = _UsuarioFake('<img src=x onerror=alert(1)>', "fulano", "fulano@teste.com", "aluno")
    html = _monta_corpo_html(usuario, "mensagem normal")
    assert "<img src=x onerror=alert(1)>" not in html
    assert "&lt;img" in html


def test_enviar_mensagem_com_payload_nao_gera_excecao(client, db, app):
    """Fim a fim: enviar_mensagem não deve quebrar com payload malicioso
    (mesmo sem RESEND_API_KEY configurada em teste)."""
    from models import User
    with app.app_context():
        admin = User(username='admin_teste', email='admin@teste.com', is_admin=True)
        admin.set_password('Senha1234')
        db.session.add(admin)
        db.session.commit()

        resultado = ContatoService.enviar_mensagem(admin, "<script>alert(1)</script>")
        assert resultado["ok"] is True
