"""scripts/backup_bucket.py: backup somente leitura do bucket de mídia.
Cliente S3 falso em memória -- sem rede e sem boto3."""
import csv
import importlib.util
from pathlib import Path

import pytest

CAMINHO = Path(__file__).resolve().parents[2] / 'scripts' / 'backup_bucket.py'
spec = importlib.util.spec_from_file_location('backup_bucket', CAMINHO)
bb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bb)


class ClienteFalso:
    """Imita o mínimo do cliente boto3: paginação e download_file."""

    def __init__(self, objetos, falhar=None, truncar=None):
        self.objetos = objetos          # {chave: bytes}
        self.falhar = falhar or set()   # chaves que dão erro ao baixar
        self.truncar = truncar or set() # chaves que baixam incompletas
        self.baixadas = []
        self.so_leitura = True

    def get_paginator(self, nome):
        assert nome == 'list_objects_v2'
        objetos = self.objetos

        class Pag:
            def paginate(self, Bucket, Prefix=''):
                itens = [{'Key': k, 'Size': len(v), 'ETag': '"abc"', 'LastModified': '2026-10-01'}
                         for k, v in sorted(objetos.items()) if k.startswith(Prefix)]
                for i in range(0, max(len(itens), 1), 2):  # páginas de 2 itens
                    yield {'Contents': itens[i:i + 2]}
        return Pag()

    def download_file(self, Bucket, Key, Filename):
        self.baixadas.append(Key)
        if Key in self.falhar:
            raise RuntimeError('erro de rede simulado')
        dados = self.objetos[Key]
        Path(Filename).write_bytes(dados[:1] if Key in self.truncar else dados)


OBJ = {'videos/a.gif': b'GIF89a-aaa', 'videos/b.gif': b'GIF89a-bbbbbb', 'images/c.jpg': b'jpg', 'professores/1-1.jpg': b'foto'}


@pytest.fixture(autouse=True)
def _sem_espera(monkeypatch):
    monkeypatch.setattr(bb.time, 'sleep', lambda s: None)


def _rodar(cli, destino, *extra):
    return bb.main(['--destino', str(destino), *extra], cliente=cli, bucket='bkt')


class TestBackup:
    def test_baixa_tudo_confere_e_grava_manifesto(self, tmp_path, capsys):
        cli = ClienteFalso(OBJ)
        assert _rodar(cli, tmp_path / 'bk') == 0
        for chave, dados in OBJ.items():
            assert (tmp_path / 'bk' / chave).read_bytes() == dados
        linhas = list(csv.DictReader(open(tmp_path / 'bk' / 'MANIFESTO.csv', encoding='utf-8')))
        assert len(linhas) == 4 and {l['conferencia'] for l in linhas} == {'ok'}
        assert 'Backup completo e conferido' in capsys.readouterr().out

    def test_somente_listar_nao_baixa_nada(self, tmp_path, capsys):
        cli = ClienteFalso(OBJ)
        assert _rodar(cli, tmp_path / 'bk', '--somente-listar') == 0
        assert cli.baixadas == [] and not (tmp_path / 'bk').exists()
        assert '4 objetos' in capsys.readouterr().out

    def test_prefixo_limita_ao_que_foi_pedido(self, tmp_path):
        cli = ClienteFalso(OBJ)
        assert _rodar(cli, tmp_path / 'bk', '--prefixo', 'videos/') == 0
        assert sorted(cli.baixadas) == ['videos/a.gif', 'videos/b.gif']

    def test_retomavel_segunda_execucao_nao_rebaixa(self, tmp_path):
        cli = ClienteFalso(OBJ)
        _rodar(cli, tmp_path / 'bk')
        cli.baixadas.clear()
        assert _rodar(cli, tmp_path / 'bk') == 0
        assert cli.baixadas == []

    def test_baixa_so_o_que_falta(self, tmp_path):
        cli = ClienteFalso(OBJ)
        _rodar(cli, tmp_path / 'bk')
        (tmp_path / 'bk' / 'videos' / 'b.gif').unlink()
        (tmp_path / 'bk' / 'images' / 'c.jpg').write_bytes(b'x')  # tamanho errado
        cli.baixadas.clear()
        assert _rodar(cli, tmp_path / 'bk') == 0
        assert sorted(cli.baixadas) == ['images/c.jpg', 'videos/b.gif']

    def test_falha_de_download_sai_com_1_e_nao_deixa_arquivo_parcial(self, tmp_path, capsys):
        cli = ClienteFalso(OBJ, falhar={'videos/b.gif'})
        assert _rodar(cli, tmp_path / 'bk') == 1
        assert not list((tmp_path / 'bk').rglob('*.parcial'))
        saida = capsys.readouterr().out
        assert 'falhou' in saida and 'NÃO está completo' in saida

    def test_download_truncado_e_detectado_e_nao_vira_arquivo_final(self, tmp_path):
        cli = ClienteFalso(OBJ, truncar={'videos/a.gif'})
        assert _rodar(cli, tmp_path / 'bk') == 1
        assert not (tmp_path / 'bk' / 'videos' / 'a.gif').exists()

    def test_nao_altera_o_bucket(self, tmp_path):
        cli = ClienteFalso(OBJ)
        antes = dict(cli.objetos)
        _rodar(cli, tmp_path / 'bk')
        assert cli.objetos == antes


class TestSegurancaDoCaminho:
    @pytest.mark.parametrize('chave', ['../fora.txt', 'a/../../fora.txt', '/abs.txt', 'a\\b.txt', 'pasta/'])
    def test_chaves_inseguras_nunca_viram_caminho(self, tmp_path, chave):
        assert bb.destino_seguro(tmp_path, chave) is None

    def test_chave_normal_fica_dentro_da_pasta(self, tmp_path):
        alvo = bb.destino_seguro(tmp_path, 'videos/0001-x.gif')
        assert tmp_path.resolve() in alvo.parents

    def test_chave_insegura_no_bucket_e_ignorada_e_nada_e_gravado_fora(self, tmp_path):
        cli = ClienteFalso({'../fora.txt': b'mal', 'videos/ok.gif': b'ok'})
        destino = tmp_path / 'bk'
        assert _rodar(cli, destino) == 1
        assert not (tmp_path / 'fora.txt').exists()
        assert (destino / 'videos' / 'ok.gif').read_bytes() == b'ok'
