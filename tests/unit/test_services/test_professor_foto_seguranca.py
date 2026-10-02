"""Hardening do upload/serving da foto do professor (P1-01)."""
import io
from unittest.mock import patch

from werkzeug.datastructures import FileStorage

from services.professor_perfil_service import ProfessorPerfilService, _detectar_imagem
from services.storage_service import StorageService

JPEG = b'\xff\xd8\xff\xe0' + b'\x00' * 32
PNG = b'\x89PNG\r\n\x1a\n' + b'\x00' * 32
WEBP = b'RIFF\x00\x00\x00\x00WEBP' + b'\x00' * 32
HTML = b'<script>alert(document.domain)</script>'


class _Prof:
    id = 7
    professor_foto_chave = None

    def is_professor(self):
        return True


def _enviar(app, conteudo, nome='foto.jpg', mimetype='text/html'):
    capturado = {}

    def fake_upload(fileobj, chave, content_type=None):
        capturado.update(chave=chave, content_type=content_type, corpo=fileobj.read())
        return True

    arq = FileStorage(stream=io.BytesIO(conteudo), filename=nome, content_type=mimetype)
    with patch.object(StorageService, 'is_configured', return_value=True), \
         patch.object(StorageService, 'upload_fileobj', side_effect=fake_upload), \
         patch.object(ProfessorPerfilService, 'garantir_slug'):
        resultado = ProfessorPerfilService.salvar_foto(_Prof(), arq)
    return resultado, capturado


class TestDeteccaoDeFormato:
    def test_reconhece_jpeg_png_e_webp(self):
        assert _detectar_imagem(JPEG[:12]) == ('.jpg', 'image/jpeg')
        assert _detectar_imagem(PNG[:12]) == ('.png', 'image/png')
        assert _detectar_imagem(WEBP[:12]) == ('.webp', 'image/webp')

    def test_html_e_svg_nao_sao_imagens_aceitas(self):
        assert _detectar_imagem(HTML[:12]) is None
        assert _detectar_imagem(b'<svg xmlns=') is None


class TestSalvarFoto:
    def test_html_renomeado_para_jpg_e_recusado_e_nao_vai_para_o_bucket(self, app):
        with app.app_context():
            (ok, _msg), capturado = _enviar(app, HTML, 'x.jpg', 'text/html')
        assert ok is False
        assert capturado == {}

    def test_jpeg_valido_e_aceito_com_content_type_pelo_conteudo(self, app):
        with app.app_context():
            (ok, _msg), capturado = _enviar(app, JPEG, 'foto.jpg', 'text/html')
        assert ok is True
        assert capturado['content_type'] == 'image/jpeg'  # ignora o 'text/html' do cliente
        assert capturado['chave'].endswith('.jpg')

    def test_extensao_enganosa_e_corrigida_pelo_formato_real(self, app):
        with app.app_context():
            (ok, _msg), capturado = _enviar(app, PNG, 'foto.jpg', 'image/jpeg')
        assert ok is True
        assert capturado['content_type'] == 'image/png'
        assert capturado['chave'].endswith('.png')


class TestServirFoto:
    def _get(self, client, content_type):
        obj = dict(body=io.BytesIO(HTML), content_type=content_type,
                   content_length=len(HTML), content_range=None, is_partial=False)
        with patch.object(StorageService, 'get_object_stream', return_value=obj):
            return client.get('/professores-media/professores/7-1.jpg')

    def test_objeto_legado_com_content_type_html_vira_download(self, client):
        resp = self._get(client, 'text/html')
        assert resp.status_code == 200
        assert resp.headers['Content-Type'].startswith('application/octet-stream')
        assert resp.headers['Content-Disposition'] == 'attachment'
        assert resp.headers['X-Content-Type-Options'] == 'nosniff'

    def test_imagem_legitima_continua_inline(self, client):
        resp = self._get(client, 'image/jpeg')
        assert resp.headers['Content-Type'].startswith('image/jpeg')
        assert 'Content-Disposition' not in resp.headers