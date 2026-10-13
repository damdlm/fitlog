"""scripts/conferir_midia_bucket.py: confere os GIFs dos exercícios no bucket
(somente leitura). Testa a leitura do JSON, a comparação com o bucket, a
listagem paginada e o modo http contra um servidor local."""
import csv
import importlib.util
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

CAMINHO = Path(__file__).resolve().parents[2] / 'scripts' / 'conferir_midia_bucket.py'
spec = importlib.util.spec_from_file_location('conferir_midia_bucket', CAMINHO)
cmb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cmb)


def _json(tmp_path, itens):
    arq = tmp_path / 'ex.json'
    arq.write_text(json.dumps(itens), encoding='utf-8')
    return str(arq)


ITENS = [
    {'id': '1', 'name': 'Ok', 'gif_url': 'videos/a.gif'},
    {'id': '2', 'name': 'Falta', 'gif_url': 'videos/b.gif'},
    {'id': '3', 'name': 'Sem gif', 'gif_url': ''},
    {'id': '4', 'name': 'Sem campo'},
    {'id': '5', 'name': 'Vazio', 'gif_url': 'videos/c.gif'},
]


class TestLeituraEComparacao:
    def test_carrega_so_quem_tem_gif_url(self, tmp_path):
        esperados = cmb.carregar_do_json(_json(tmp_path, ITENS))
        assert [e[2] for e in esperados] == ['videos/a.gif', 'videos/b.gif', 'videos/c.gif']

    def test_json_real_do_projeto_e_lido(self):
        esperados = cmb.carregar_do_json()
        assert len(esperados) > 1000 and all(c.startswith('videos/') for _, _, c in esperados)

    def test_comparar_ok_faltando_vazio_e_extras(self, tmp_path):
        esperados = cmb.carregar_do_json(_json(tmp_path, ITENS))
        existentes = {'videos/a.gif': 10, 'videos/c.gif': 0, 'professores/1-1.jpg': 5}
        linhas, extras = cmb.comparar(esperados, existentes)
        assert {l[2]: l[3] for l in linhas} == {'videos/a.gif': 'ok', 'videos/b.gif': 'faltando', 'videos/c.gif': 'vazio'}
        assert extras == ['professores/1-1.jpg']

    def test_chave_com_formato_suspeito_e_sinalizada(self):
        linhas, _ = cmb.comparar([('9', 'x', '/videos/a.gif'), ('8', 'y', 'videos/../a.gif')], {})
        assert all('formato suspeito' in l[4] for l in linhas)

    def test_listar_bucket_junta_todas_as_paginas(self):
        class Pag:
            def paginate(self, Bucket):
                yield {'Contents': [{'Key': 'a', 'Size': 1}]}
                yield {'Contents': [{'Key': 'b', 'Size': 2}]}
                yield {}
        class Cli:
            def get_paginator(self, nome):
                assert nome == 'list_objects_v2'
                return Pag()
        assert cmb.listar_bucket(Cli(), 'bkt') == {'a': 1, 'b': 2}


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        r = {
            '/exercicios-media/videos/a.gif': (206, 'image/gif'),
            '/exercicios-media/videos/c.gif': (200, 'text/html'),
            '/exercicios-media/videos/d.gif': (500, 'text/plain'),
        }.get(self.path, (429 if '/limite/' in self.path else 404, 'text/plain'))
        self.send_response(r[0])
        self.send_header('Content-Type', r[1])
        self.send_header('Content-Length', '1')
        self.end_headers()
        self.wfile.write(b'x')

    def log_message(self, *a):
        pass


@pytest.fixture
def servidor():
    srv = HTTPServer(('127.0.0.1', 0), _Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f'http://127.0.0.1:{srv.server_port}'
    srv.shutdown()


class TestModoHttp:
    def test_classifica_cada_resposta(self, servidor, monkeypatch):
        monkeypatch.setattr(cmb.time, 'sleep', lambda s: None)
        esperados = [('1', 'a', 'videos/a.gif'), ('2', 'b', 'videos/b.gif'),
                     ('3', 'c', 'videos/c.gif'), ('4', 'd', 'videos/d.gif')]
        linhas = cmb.conferir_http(esperados, servidor, simultaneas=2)
        sit = {l[2]: l[3] for l in linhas}
        assert sit == {'videos/a.gif': 'ok', 'videos/b.gif': 'faltando', 'videos/c.gif': 'erro', 'videos/d.gif': 'erro'}
        assert 'tipo inesperado' in dict((l[2], l[4]) for l in linhas)['videos/c.gif']
        assert '500' in dict((l[2], l[4]) for l in linhas)['videos/d.gif']

    def test_main_http_sai_com_1_quando_falta_arquivo_e_grava_csv(self, servidor, tmp_path, capsys):
        saida = tmp_path / 'rel.csv'
        codigo = cmb.main(['--modo', 'http', '--url', servidor, '--json', _json(tmp_path, ITENS[:2]),
                           '--saida', str(saida)])
        assert codigo == 1
        linhas = list(csv.DictReader(open(saida, encoding='utf-8')))
        assert {l['chave']: l['situacao'] for l in linhas} == {'videos/a.gif': 'ok', 'videos/b.gif': 'faltando'}
        assert 'faltando: 1' in capsys.readouterr().out

    def test_main_http_sai_com_0_quando_tudo_existe(self, servidor, tmp_path):
        codigo = cmb.main(['--modo', 'http', '--url', servidor, '--json', _json(tmp_path, ITENS[:1]),
                           '--saida', str(tmp_path / 'r.csv')])
        assert codigo == 0

    def test_modo_http_exige_url(self, tmp_path):
        with pytest.raises(SystemExit):
            cmb.main(['--modo', 'http', '--json', _json(tmp_path, ITENS)])


class TestLimiteDoSite:
    def test_429_interrompe_e_nao_conta_como_arquivo_faltando(self, servidor, tmp_path, capsys):
        itens = [{'id': str(i), 'name': f'x{i}', 'gif_url': f'limite/{i}.gif'} for i in range(30)]
        saida = tmp_path / 'r.csv'
        codigo = cmb.main(['--modo', 'http', '--url', servidor, '--simultaneas', '1',
                           '--json', _json(tmp_path, itens), '--saida', str(saida)])
        assert codigo == 3
        situacoes = {l['situacao'] for l in csv.DictReader(open(saida, encoding='utf-8'))}
        assert situacoes == {'limitado', 'nao-conferido'}
        assert 'NÃO é completo' in capsys.readouterr().out
