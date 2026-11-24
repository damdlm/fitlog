"""Catálogo com as animações do Gif do Treino (migração a3c7e9b1d5f2):
dados congelados coerentes com data/exercises.json, caminhos aceitos pela
rota de mídia, músculos dentro do vocabulário do catálogo e do mapa
muscular, e a migração indo e voltando."""
import importlib.util
import json
from pathlib import Path

from app import _MEDIA_EXERCICIO_RE
from models import db, ExercicioSistema, musculo_principal_de
from services.mapa_muscular_service import regiao_do_musculo

RAIZ = Path(__file__).resolve().parents[3]
DADOS = json.loads((RAIZ / 'data' / 'catalogo_gifdotreino.json').read_text(encoding='utf-8'))
CATALOGO = json.loads((RAIZ / 'data' / 'exercises.json').read_text(encoding='utf-8'))
POR_ID = {e['id']: e for e in CATALOGO}


def _mig(arquivo='a3c7e9b1d5f2_catalogo_gifdotreino.py'):
    spec = importlib.util.spec_from_file_location('mig_' + arquivo[:12], RAIZ / 'migrations' / 'versions' / arquivo)
    mig = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig)
    return mig


# Correções da revisão visual (migração b5d8f2a4c6e1) sobre os dados congelados.
CORR = _mig('b5d8f2a4c6e1_corrige_catalogo_gifdotreino.py')
NOVOS = [dict(n, **{col: par[1] for col, par in CORR.CORRECOES.get(n['id_original'], {}).items()})
         for n in DADOS['novos'] if n['id_original'] not in CORR.DUPLICADOS]


class TestDados:
    def test_tamanhos(self):
        assert len(DADOS['trocas']) == 486 and len(DADOS['novos']) == 494
        assert set(DADOS['trocas']) == set(DADOS['antigos'])

    def test_trocas_batem_com_o_exercises_json(self):
        for fid, (gif, img) in DADOS['trocas'].items():
            assert POR_ID[fid]['gif_url'] == gif and POR_ID[fid]['image'] == img

    def test_novos_estao_no_exercises_json_sem_colidir(self):
        ids = [n['id_original'] for n in DADOS['novos']]
        assert len(ids) == len(set(ids)) and all(i.startswith('8') and len(i) == 4 for i in ids)
        assert len(CATALOGO) == len(POR_ID)  # nenhum id repetido no catálogo
        for n in NOVOS:
            e = POR_ID[n['id_original']]
            assert (e['name'], e['target'], e['equipment'], e['category'], e['gif_url']) == (
                n['nome'], n['alvo'], n['equipamento'], n['categoria'], n['gif_url'])
            assert e.get('record_mode') == {'tempo': 'time'}.get(n['modo_registro'])
        assert not set(CORR.DUPLICADOS) & set(POR_ID)

    def test_nomes_novos_nao_repetem_os_do_catalogo(self):
        # (o catálogo antigo já tinha um nome repetido: 0697 e 1766)
        antigos = {e['name'].strip().lower() for e in CATALOGO if not e['id'].startswith('8')}
        novos = [n['nome'].strip().lower() for n in NOVOS]
        assert len(novos) == len(set(novos)) and not (set(novos) & antigos)
        # nem com um apelido de exercício que já existia (a busca acharia dois)
        apelidos = {a.strip().lower() for e in CATALOGO if not e['id'].startswith('8') for a in (e.get('nicknames') or [])}
        assert not (set(novos) & apelidos)

    def test_caminhos_passam_na_rota_de_midia(self):
        caminhos = [c for par in DADOS['trocas'].values() for c in par]
        caminhos += [n['gif_url'] for n in DADOS['novos']] + [n['imagem'] for n in DADOS['novos']]
        for c in caminhos:
            assert _MEDIA_EXERCICIO_RE.match(c), c
            assert c.startswith(('videos/gdt/', 'images/gdt/')) and c.endswith(('.mp4', '.webp'))

    def test_musculos_no_vocabulario_do_catalogo(self):
        antigos = [e for e in CATALOGO if not e['id'].startswith('8')]
        alvos = {e['target'] for e in antigos}
        secundarios = {m for e in antigos for m in (e.get('secondary_muscles') or [])}
        categorias = {e['category'] for e in antigos}
        equipamentos = {e['equipment'] for e in antigos}
        for n in NOVOS:
            assert n['alvo'] in alvos and n['categoria'] in categorias and n['equipamento'] in equipamentos, n['nome']
            assert all(m in secundarios or regiao_do_musculo(m) for m in n['musculos_secundarios']), n['nome']
            assert n['instrucao_pt'] and n['passos_pt'], n['nome']

    def test_todo_novo_tem_regiao_no_mapa_muscular(self):
        for n in NOVOS:
            if n['alvo'] == 'Sistema cardiovascular':
                assert n['modo_registro'] == 'tempo'
                continue
            assert regiao_do_musculo(musculo_principal_de(n['alvo'], n['grupo_muscular'])), n['nome']


def test_migracao_vai_e_volta(app):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    mig = _mig()
    assert mig.down_revision == 'e1f3a7b9c2d4'
    fid = next(iter(DADOS['trocas']))
    gif_antigo, img_antiga = DADOS['antigos'][fid]
    with app.app_context():
        db.session.add(ExercicioSistema(id_original=fid, nome='Antigo', gif_url=gif_antigo, imagem=img_antiga))
        db.session.commit()

        def rodar(f):
            with db.engine.begin() as conn:
                with Operations.context(MigrationContext.configure(conn)):
                    f()

        rodar(mig.upgrade)
        db.session.expire_all()
        ex = ExercicioSistema.query.filter_by(id_original=fid).one()
        assert (ex.gif_url, ex.imagem) == tuple(DADOS['trocas'][fid])
        assert ExercicioSistema.query.filter(ExercicioSistema.id_original.like('8%')).count() == 494
        novo = ExercicioSistema.query.filter_by(id_original='8001').one()
        assert novo.gif_url.endswith('.mp4') and novo.passos_pt and novo.atribuicao

        rodar(mig.upgrade)  # de novo: não duplica
        assert ExercicioSistema.query.filter(ExercicioSistema.id_original.like('8%')).count() == 494

        rodar(mig.downgrade)
        db.session.expire_all()
        ex = ExercicioSistema.query.filter_by(id_original=fid).one()
        assert (ex.gif_url, ex.imagem) == (gif_antigo, img_antiga)
        assert ExercicioSistema.query.filter(ExercicioSistema.id_original.like('8%')).count() == 0


def test_correcoes_vao_e_voltam(app):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    assert CORR.down_revision == 'a3c7e9b1d5f2'
    # toda correção parte do valor congelado da a3c7e9b1d5f2
    por_id = {n['id_original']: n for n in DADOS['novos']}
    for fid, campos in CORR.CORRECOES.items():
        for col, (antes, depois) in campos.items():
            assert por_id[fid].get(col) == antes and antes != depois, (fid, col)
    with app.app_context():
        db.session.add(ExercicioSistema(id_original='0042', nome='Agachamento frontal com barra',
                                        gif_url=CORR.MIDIA['0042'][0][0], imagem=CORR.MIDIA['0042'][0][1]))
        db.session.commit()

        def rodar(f):
            with db.engine.begin() as conn:
                with Operations.context(MigrationContext.configure(conn)):
                    f()

        rodar(_mig().upgrade)
        rodar(CORR.upgrade)
        db.session.expire_all()
        q = ExercicioSistema.query
        assert q.filter(ExercicioSistema.id_original.like('8%')).count() == 494 - len(CORR.DUPLICADOS)
        ex = q.filter_by(id_original='8114').one()
        assert (ex.nome, ex.equipamento, ex.nicknames) == ('Hang clean com barra', 'Barra', ['Barbell hang clean'])
        ex = q.filter_by(id_original='8039').one()
        assert (ex.alvo, ex.categoria, ex.modo_registro) == ('Deltoides', 'Ombros', 'carga')
        assert q.filter_by(id_original='0042').one().gif_url == CORR.MIDIA['0042'][1][0]

        rodar(CORR.downgrade)
        db.session.expire_all()
        ex = q.filter_by(id_original='8114').one()
        assert (ex.nome, ex.equipamento) == ('Barbell hang clean', 'Peso corporal')
        assert q.filter_by(id_original='8039').one().modo_registro == 'tempo'
        assert q.filter_by(id_original='0042').one().gif_url == CORR.MIDIA['0042'][0][0]