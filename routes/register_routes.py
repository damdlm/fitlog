from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from datetime import datetime, timezone
from services.versao_service import VersaoService
from services.exercicio_service import ExercicioService
from services.registro_service import RegistroService
from services.notificacao_service import NotificacaoService
from utils.date_utils import data_para_periodo, data_para_semana, formatar_data_br, validar_data
from utils.format_utils import data_atual_iso, _agora_brasil
import logging

register_bp = Blueprint('register', __name__)
logger = logging.getLogger(__name__)

@register_bp.route("/registrar-treino", methods=["GET"])
@login_required
def registrar_treino():
    """
    Página de registro de treino - Nova versão com seleção por data
    Agora os treinos são filtrados pela versão ativa na data selecionada
    """
    data_selecionada_str = request.args.get("data") or data_atual_iso()
    treino_selecionado = request.args.get("treino")
    
    exercicios = []
    registros_map = {}
    historico_series = {}
    versao_info = None
    erro_versao = None
    treinos_disponiveis = []
    exercicios_catalogo = []
    
    # Validar a data e converter para objeto date
    data_valida, data_obj = validar_data(data_selecionada_str)
    if not data_valida:
        flash(data_obj, "danger")
        data_obj = _agora_brasil().date()
        data_selecionada_str = data_obj.strftime("%Y-%m-%d")
    else:
        data_obj = data_obj
    
    # Buscar versão ativa na data
    versao_ativa = VersaoService.get_ativa_por_data(data_obj)
    
    if not versao_ativa:
        erro_versao = f"Não há versão ativa para {data_obj.strftime('%d/%m/%Y')}"
        logger.warning(f"Tentativa de registro sem versão ativa para data {data_obj}")
    else:
        # Buscar treinos disponíveis nesta versão
        treinos_disponiveis = VersaoService.get_treinos_para_registro(versao_ativa.id)
        
        versao_info = {
            'id': versao_ativa.id,
            'numero': versao_ativa.numero_versao,
            'descricao': versao_ativa.descricao,
            'divisao': versao_ativa.divisao
        }
        
        # Se um treino foi selecionado, carregar seus exercícios
        if treino_selecionado:
            # Verificar se o treino selecionado está na versão ativa
            treino_valido = False
            treino_codigo = None
            for t in treinos_disponiveis:
                if str(t['id']) == str(treino_selecionado):
                    treino_valido = True
                    treino_codigo = t['codigo']  # ← PEGA O CÓDIGO (A, B, C...)
                    break
            
            if not treino_valido:
                flash(f"Treino não encontrado na versão ativa para esta data!", "warning")
                treino_selecionado = None
            else:
                # Buscar exercícios do treino nesta versão usando o CÓDIGO
                exercicios = VersaoService.get_exercicios(versao_ativa.id, treino_codigo)
                for ex in exercicios:
                    ex.avulso = False
                
                logger.info(f"Buscando exercícios para versão {versao_ativa.id}, treino {treino_codigo}")
                logger.info(f"Encontrados {len(exercicios)} exercícios")
                
                # Buscar registros existentes para esta data
                registros = RegistroService.get_by_data(
                    treino_id=treino_selecionado,  # ← USA ID (correto para registros)
                    versao_id=versao_ativa.id,
                    data=data_obj
                )
                # ⚠️ Chave prefixada (ex: "u_5", "b_5") em vez do ID puro: exercicios_usuario
                # e exercicios_base têm sequências de ID independentes, então o mesmo número
                # pode existir nas duas tabelas — usar só o ID causava colisão entre exercícios
                # diferentes (dados de um "vazando"/sobrescrevendo o outro).
                registros_map = {}
                for r in registros:
                    if r.exercicio_usuario_id is not None:
                        registros_map[f"u_{r.exercicio_usuario_id}"] = r
                    elif r.exercicio_base_id is not None:
                        registros_map[f"b_{r.exercicio_base_id}"] = r

                # Exercícios AVULSOS: lançados nesta sessão específica (ver
                # botão "Adicionar exercício" / ExercicioService.buscar_por_chaves)
                # sem fazer parte da lista oficial do treino -- ficam só no
                # registro deste dia, nunca em VersaoExercicio. Duas origens:
                # 1) já têm registro salvo (chave em registros_map, mas fora
                #    da lista oficial); 2) acabou de ser adicionado agora
                #    (?avulso=u_5 na URL, ver o botão no template -- ainda
                #    sem registro, entra zerado igual um exercício novo).
                chaves_oficiais = {f"{ex.prefixo}{ex.id}" for ex in exercicios}
                chaves_avulsas = {c for c in registros_map if c not in chaves_oficiais}
                for chave_url in request.args.getlist("avulso"):
                    if chave_url not in chaves_oficiais:
                        chaves_avulsas.add(chave_url)
                if chaves_avulsas:
                    avulsos_map = ExercicioService.buscar_por_chaves(list(chaves_avulsas), current_user.id)
                    exercicios = exercicios + list(avulsos_map.values())
                
                # Buscar histórico da ÚLTIMA sessão completa (carga, reps E
                # número real de séries -- não uma janela fixa que pode
                # misturar sessões diferentes, ver get_ultima_sessao_series).
                # Em lote: antes, 1 chamada (2 queries) por exercício —
                # medido em 26 queries pra 8 exercícios. Agora 1 chamada
                # pra todos de uma vez.
                historico_series = ExercicioService.get_ultima_sessao_series_em_lote(
                    exercicios,
                    versao_id=versao_ativa.id
                )

                # Catálogo completo (próprios + globais) pro seletor do botão
                # "Adicionar exercício" -- mesma função já usada em
                # cadastrar_treinos.html pro mesmo tipo de busca/seleção.
                exercicios_catalogo = ExercicioService.get_exercicios_completos(user_id=current_user.id)
    
    return render_template(
        "register/registrar_treino.html",
        treinos_disponiveis=treinos_disponiveis,
        treino_selecionado=treino_selecionado,
        data_selecionada=data_obj,  # ← AGORA É OBJETO DATE
        data_selecionada_str=data_selecionada_str,  # ← STRING PARA INPUT
        exercicios=exercicios,
        registros=registros_map,
        historico_series=historico_series,
        versao_info=versao_info,
        erro_versao=erro_versao,
        exercicios_catalogo=exercicios_catalogo
    )


@register_bp.route("/registrar-treino", methods=["POST"])
@login_required
def salvar_registro():
    """
    Salva o treino do dia
    """
    treino_id = request.form.get("treino")
    data_registro = request.form.get("data")
    # Presente só quando o formulário vem do modal de edição do calendário
    # (ver templates/calendar/calendario.html) -- é a data com que a sessão
    # já estava salva antes da edição, usada abaixo para descartar a sessão
    # antiga caso o usuário tenha mudado a data. Também é o sinal de que
    # "salvar" deve devolver a pessoa pro calendário (ver _redirect_apos_salvar
    # logo abaixo), em vez do fluxo normal de registro.
    data_original = request.form.get("data_original")
    veio_do_calendario = bool(data_original)

    def _redirect_apos_salvar(sucesso, data_para_exibir=None):
        """
        Pra onde ir depois de tentar salvar -- sucesso ou erro. Quando o
        formulário veio do modal de edição do calendário, sempre volta pra
        lá (?data=... reaproveita o deep-link que a página já tem pra
        abrir o evento daquele dia, ver dataParaAbrirAutomaticamente em
        calendario.html) em vez do fluxo normal de registro (tela de
        registrar treino / dashboard).
        """
        if veio_do_calendario:
            data_alvo = data_para_exibir or data_original
            return redirect(url_for("calendar.calendario", data=data_alvo))
        if sucesso:
            return redirect(url_for("main.index"))
        return redirect(url_for("register.registrar_treino",
                                 treino=treino_id,
                                 data=data_registro))

    # Tempo total do treino (cronômetro do topo), em segundos
    tempo_treino_raw = request.form.get("tempo_treino")
    try:
        tempo_treino = int(float(tempo_treino_raw)) if tempo_treino_raw else None
        if tempo_treino is not None and tempo_treino < 0:
            tempo_treino = None
    except (ValueError, TypeError):
        tempo_treino = None
    
    # Validações básicas
    if not treino_id or not data_registro:
        flash("Treino e data são obrigatórios", "danger")
        return _redirect_apos_salvar(sucesso=False)
    
    # Validar data
    data_valida, data_obj = validar_data(data_registro)
    if not data_valida:
        flash(data_obj, "danger")
        return _redirect_apos_salvar(sucesso=False)
    
    # Descobrir versão ativa na data
    versao_ativa = VersaoService.get_ativa_por_data(data_obj)
    
    if not versao_ativa:
        flash(f"Não há versão ativa para {data_obj.strftime('%d/%m/%Y')}", "danger")
        return _redirect_apos_salvar(sucesso=False, data_para_exibir=data_obj.isoformat())
    
    if versao_ativa.data_fim and versao_ativa.data_fim < data_obj:
        flash(f"A versão {versao_ativa.numero_versao} foi finalizada em {versao_ativa.data_fim.strftime('%d/%m/%Y')}", "danger")
        return _redirect_apos_salvar(sucesso=False, data_para_exibir=data_obj.isoformat())
    
    # Verificar se o treino pertence à versão ativa
    treinos_disponiveis = VersaoService.get_treinos_para_registro(versao_ativa.id)
    treino_valido = False
    treino_codigo = None
    treino_nome = None
    for t in treinos_disponiveis:
        if str(t['id']) == str(treino_id):
            treino_valido = True
            treino_codigo = t['codigo']
            treino_nome = t['nome']
            break
    
    if not treino_valido:
        flash(f"Treino não encontrado na versão ativa!", "danger")
        return _redirect_apos_salvar(sucesso=False, data_para_exibir=data_obj.isoformat())
    
    # Calcular período e semana a partir da data
    periodo = data_para_periodo(data_obj)
    semana = data_para_semana(data_obj)
    
    # Buscar exercícios do treino nesta versão usando o CÓDIGO
    exercicios = VersaoService.get_exercicios(versao_ativa.id, treino_codigo)

    def _extrair_dados_exercicio(chave, tipo, exercicio_id):
        """Lê carga/repetições/séries (uniforme ou individual por série) de
        um único exercício do formulário, pelo prefixo da chave ("u_5",
        "b_12"). Mesma lógica tanto pros exercícios oficiais do treino
        quanto pros avulsos (ver avulso_exercicios[] mais abaixo) -- só
        muda de onde vem o (tipo, exercicio_id)."""
        carga = request.form.get(f"carga_{chave}")
        reps = request.form.get(f"reps_{chave}")
        if not (carga and reps and carga.strip() and reps.strip()):
            return None
        try:
            carga_float = float(carga)
            reps_int = int(reps)
            num_series = int(request.form.get(f"num_series_{chave}", 3))
            if not (carga_float >= 0 and reps_int >= 0 and 1 <= num_series <= 10):
                return None

            dado = {
                'carga': carga_float,
                'repeticoes': reps_int,
                'num_series': num_series,
                'tipo': tipo,
                'exercicio_id': exercicio_id,
                'data_registro': data_obj
            }

            # Séries com valores individuais (lançadas pelo modal da
            # seta, na tela de registro): cada série pode ter carga e
            # repetições diferentes, em vez do mesmo valor repetido
            # `num_series` vezes. Só ativa se a flag vier "individual"
            # E pelo menos a 1ª série tiver valor válido -- senão cai
            # no comportamento uniforme de sempre.
            if request.form.get(f"modo_series_{chave}") == "individual":
                series_individuais = []
                for i in range(1, num_series + 1):
                    carga_serie = request.form.get(f"carga_{chave}_{i}")
                    reps_serie = request.form.get(f"reps_{chave}_{i}")
                    try:
                        c = float(carga_serie) if carga_serie and carga_serie.strip() else carga_float
                        r = int(reps_serie) if reps_serie and reps_serie.strip() else reps_int
                        if c < 0 or r < 0:
                            c, r = carga_float, reps_int
                    except (ValueError, TypeError):
                        c, r = carga_float, reps_int
                    series_individuais.append({'carga': c, 'repeticoes': r})
                if series_individuais:
                    dado['series_individuais'] = series_individuais

            return dado
        except (ValueError, TypeError):
            return None

    # Processar dados dos exercícios
    dados_exercicios = {}
    
    for ex in exercicios:
        chave = f"{ex.prefixo}{ex.id}"  # ex: "u_5" ou "b_5" — evita colisão entre as duas tabelas
        dado = _extrair_dados_exercicio(chave, ex.tipo, ex.id)
        if dado:
            dados_exercicios[chave] = dado

    # Exercícios AVULSOS: lançados só nesta sessão (botão "Adicionar
    # exercício" na tela de registro, ver .btn-adicionar-exercicio-avulso),
    # sem fazer parte da lista oficial do treino (nunca tocam
    # VersaoExercicio). O formulário manda uma chave por avulso em
    # avulso_exercicios[] -- os campos carga_/reps_/num_series_/
    # modo_series_ seguem exatamente a mesma convenção dos oficiais.
    # IDOR: chave "u_*" só é aceita se o exercício realmente pertencer a
    # este usuário -- sem isso, dava pra registrar um treino apontando pro
    # exercício customizado de qualquer outra pessoa só sabendo o ID.
    chaves_avulsas_form = request.form.getlist("avulso_exercicios[]")
    if chaves_avulsas_form:
        avulsos_validos = ExercicioService.buscar_por_chaves(chaves_avulsas_form, current_user.id)
        for chave in chaves_avulsas_form:
            ex_avulso = avulsos_validos.get(chave)
            if not ex_avulso:
                continue  # chave inexistente, ou "u_*" que não pertence a este usuário
            dado = _extrair_dados_exercicio(chave, ex_avulso.tipo, ex_avulso.id)
            if dado:
                dados_exercicios[chave] = dado
    
    if dados_exercicios:
        # Se a data foi alterada (edição pelo calendário), a sessão é
        # identificada no banco por período/semana -- valores derivados da
        # data, não pela data em si (ver RegistroService.salvar_registros).
        # Sem isto, mudar a data criaria uma sessão nova na data nova e
        # deixaria a sessão antiga órfã, duplicada, na data de origem.
        # Como treino_id (TreinoVersao) pertence a uma única versão fixa, e
        # o treino já foi validado acima contra a versão ativa da data NOVA,
        # sabemos que versao_ativa.id também é a versão da sessão antiga.
        if data_original and data_original != data_registro:
            data_original_valida, data_original_obj = validar_data(data_original)
            if data_original_valida:
                RegistroService.excluir_por_treino_data(
                    treino_id=treino_id,
                    versao_id=versao_ativa.id,
                    data=data_original_obj,
                )

        if RegistroService.salvar_registros(
            treino_id=treino_id,
            versao_id=versao_ativa.id,
            periodo=periodo,
            semana=semana,
            dados_exercicios=dados_exercicios,
            tempo_treino=tempo_treino
        ):
            logger.info(f"Treino {treino_id} salvo para {data_registro} (versão {versao_ativa.numero_versao})")
            flash(f"✅ Treino salvo para {data_obj.strftime('%d/%m/%Y')}!", "success")
            NotificacaoService.notificar_professor(
                current_user,
                tipo='treino_finalizado',
                titulo='Aluno finalizou um treino',
                mensagem=(
                    f'{current_user.nome_completo or current_user.username} finalizou o treino '
                    f'"{treino_nome or treino_codigo}" em {data_obj.strftime("%d/%m/%Y")}.'
                ),
                url=url_for('professor.calendario_aluno', aluno_id=current_user.id, data=data_obj.isoformat()),
                chave_agrupamento=f'registro:{treino_id}:{data_obj.isoformat()}',
            )
            return _redirect_apos_salvar(sucesso=True, data_para_exibir=data_obj.isoformat())
        else:
            flash("❌ Erro ao salvar registros!", "danger")
    else:
        flash("⚠️ Nenhum dado válido para salvar!", "warning")
    
    return _redirect_apos_salvar(sucesso=False, data_para_exibir=data_obj.isoformat())


@register_bp.route("/api/treinos-por-data")
@login_required
def api_treinos_por_data():
    """
    API para buscar treinos disponíveis em uma data específica
    Retorna os treinos da versão ativa na data
    """
    data_str = request.args.get("data")
    
    if not data_str:
        return jsonify({"success": False, "error": "Data não fornecida"}), 400
    
    try:
        data_obj = datetime.strptime(data_str, '%Y-%m-%d').date()
        versao_ativa = VersaoService.get_ativa_por_data(data_obj)
        
        if not versao_ativa:
            return jsonify({
                "success": False, 
                "error": f"Não há versão ativa para {data_obj.strftime('%d/%m/%Y')}"
            }), 404
        
        # Buscar treinos disponíveis nesta versão
        treinos_disponiveis = VersaoService.get_treinos_para_registro(versao_ativa.id)
        
        return jsonify({
            "success": True,
            "versao": {
                "id": versao_ativa.id,
                "numero": versao_ativa.numero_versao,
                "descricao": versao_ativa.descricao,
                "divisao": versao_ativa.divisao
            },
            "treinos": treinos_disponiveis
        })
        
    except Exception as e:
        logger.exception("Erro na API treinos-por-data")
        # CORREÇÃO seção 13 (hardening de segurança): idem -- não
        # devolver str(e) ao cliente.
        return jsonify({"success": False, "error": "Não foi possível concluir a operação."}), 500