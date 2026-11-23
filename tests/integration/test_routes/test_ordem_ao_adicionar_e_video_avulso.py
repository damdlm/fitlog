"""Correções de nov/2026 (2).

1) Ficha: ao adicionar um exercício no modal "Editar treino", a sequência
   salva do treino se perdia em dois casos -- buscar o exercício e salvar
   sem limpar a busca (a busca joga os resultados pro topo da grade e o
   formulário era enviado na ordem da grade) e criar um exercício novo no
   próprio modal (o card entrava no topo). Agora a ordem enviada é sempre:
   os que já estavam, na ordem salva, e depois os marcados agora, na ordem
   em que foram marcados.
2) Registrar treino: na lista do "+ Exercício" (avulso), botão pequeno para
   ver o vídeo do exercício sem escolhê-lo.
"""
from datetime import date
from pathlib import Path

from models import db, ExercicioSistema, VersaoExercicio
from tests.integration.test_routes.test_lote3_carregamento import _ficha
from tests.integration.test_routes.test_professor_routes_versoes import _login

RAIZ = Path(__file__).resolve().parents[3]


def _ler(caminho):
    return (RAIZ / caminho).read_text(encoding='utf-8').replace('\r\n', '\n')


class TestOrdemAoAdicionarNoModal:
    def test_ordem_de_envio_salvos_primeiro_e_novos_na_ordem_de_marcacao(self):
        js = _ler('static/js/editar-treino-versao.js')
        corpo = js[js.index('function ordemDeEnvio()'):js.index('function cardsNaOrdemDeEnvio()')]
        assert corpo.index('(ultimaOrdemIds || []).forEach(incluir);') \
            < corpo.index('marcadosAgora.forEach(incluir);') \
            < corpo.index('marcados.forEach(incluir);')

    def test_marcacao_registrada_e_zerada_ao_abrir_o_modal(self):
        js = _ler('static/js/editar-treino-versao.js')
        troca = js[js.index('function onCheckboxChange(checkbox) {'):][:400]
        assert 'if (checkbox.checked && i === -1) marcadosAgora.push(checkbox.value);' in troca
        assert 'else if (!checkbox.checked && i !== -1) marcadosAgora.splice(i, 1);' in troca
        abrir = js[js.index("grid?.addEventListener('etv:reordenar'"):][:300]
        assert 'marcadosAgora = [];' in abrir

    def test_envio_poe_os_marcados_na_ordem_de_envio(self):
        js = _ler('static/js/editar-treino-versao.js')
        envio = js[js.index("form.addEventListener('submit', function (e) {"):][:1200]
        # depois da validação de "nenhum marcado"
        assert envio.index('if (marcados === 0) {') < envio.index('const cards = cardsNaOrdemDeEnvio();')
        assert 'if (cards.length) grid.prepend(...cards);' in envio

    def test_exercicio_criado_no_modal_aparece_depois_dos_marcados(self):
        js = _ler('static/js/editar-treino-versao.js')
        criar = js[js.index('cb.checked = true;\n                            onCheckboxChange(cb);'):][:500]
        assert 'if (!ordenadoPorBusca) reordenarSelecionados();' in criar

    def test_servidor_grava_na_ordem_dos_campos_enviados(self, client, app):
        # contrato do servidor que o JS acima usa: a ordem dos exercicios[]
        with app.app_context():
            u, v, tv, ex = _ficha('ord_envio')
            b1 = ExercicioSistema(id_original='9101', nome='Remada A', grupo_muscular='Costas')
            b2 = ExercicioSistema(id_original='9102', nome='Remada B', grupo_muscular='Costas')
            db.session.add_all([b1, b2])
            db.session.commit()
            from services.versao_service import VersaoService
            enviados = [f'b_{b2.id}', f'u_{ex.id}', f'b_{b1.id}']
            VersaoService.adicionar_exercicios_a_treino_versao(
                tv.id, [ex.id], [b1.id, b2.id],
                ordem_chaves=VersaoService.chaves_na_ordem_enviada(enviados))
            db.session.commit()
            gravados = VersaoExercicio.query.filter_by(treino_versao_id=tv.id).order_by(VersaoExercicio.ordem).all()
            chaves = [f'b_{g.exercicio_base_id}' if g.exercicio_base_id else f'u_{g.exercicio_usuario_id}' for g in gravados]
            assert chaves == enviados


class TestVideoNoMaisExercicio:
    def _lista(self, client, app, username):
        with app.app_context():
            _u, _v, tv, ex = _ficha(username)
            db.session.add(VersaoExercicio(treino_versao_id=tv.id, exercicio_usuario_id=ex.id, ordem=0))
            db.session.add(ExercicioSistema(id_original='9201', nome='Rosca com vídeo', grupo_muscular='Bíceps',
                                            gif_url='videos/9201-teste.mp4'))
            db.session.add(ExercicioSistema(id_original='9202', nome='Rosca sem vídeo', grupo_muscular='Bíceps'))
            db.session.commit()
        _login(client, username)
        return client.get('/registrar/catalogo-avulso').get_data(as_text=True)

    def test_item_vira_role_button_e_leva_o_caminho_do_video(self, client, app):
        corpo = self._lista(client, app, 'vid_avulso')
        itens = [linha for linha in corpo.splitlines() if 'avulso-picker-item' in linha]
        com = next(i for i in itens if 'data-nome="rosca com vídeo"' in i)
        sem = next(i for i in itens if 'data-nome="rosca sem vídeo"' in i)
        assert '<div class="avulso-picker-item" role="button" tabindex="0"' in com
        assert 'data-gif="videos/9201-teste.mp4"' in com
        assert 'data-gif' not in sem
        # o botão é criado no navegador (lista mais leve)
        assert 'avulso-picker-video' not in corpo
        assert '<button type="button" class="avulso-picker-item"' not in corpo

    def test_tela_cria_o_botao_e_abre_o_video_sem_escolher(self, client, app):
        with app.app_context():
            _u, _v, tv, ex = _ficha('vid_tela')
            db.session.add(VersaoExercicio(treino_versao_id=tv.id, exercicio_usuario_id=ex.id, ordem=0))
            db.session.commit()
            tid = tv.id
        _login(client, 'vid_tela')
        html = client.get(f'/registrar/registrar-treino?data={date(2024, 2, 1).isoformat()}&treino={tid}') \
            .get_data(as_text=True).replace('\r\n', '\n')
        assert 'function criarBotoesVideoAvulso(lista) {' in html
        assert "lista.innerHTML = html;\n                    criarBotoesVideoAvulso(lista);" in html
        clique = html[html.index("const btnVideo = evt.target.closest('.avulso-picker-video');"):][:300]
        assert 'abrirVideoSobreAvulso(btnVideo);\n                return;' in clique
        # por cima do modal do avulso (z-index 2000 nesta tela)
        assert "midiaEl.style.zIndex = '2010';" in html
        assert "fundos[fundos.length - 1].style.zIndex = '2005';" in html
        # teclado: Enter/Espaço no item escolhem, como no <button> de antes
        assert "(evt.key === 'Enter' || evt.key === ' ') && evt.target.classList.contains('avulso-picker-item')" in html