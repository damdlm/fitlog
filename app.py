from flask import Flask, render_template, request, redirect, url_for, jsonify, flash
import json
from pathlib import Path
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'sua_chave_secreta_aqui'  # Necessário para flash messages

BASE = Path("storage")

# === CACHE PARA MELHOR PERFORMANCE ===
_ultima_carga_cache = {}

def load_json(file):
    path = BASE / file
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))

def save_json(file, data):
    path = BASE / file
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

def get_periodos_existentes():
    registros = load_json("registros.json")
    periodos = sorted(set(r["periodo"] for r in registros), reverse=True)
    return periodos

def clear_cache():
    """Limpa o cache (útil após novos registros)"""
    _ultima_carga_cache.clear()

def calcular_media_series(series):
    """Calcula média de carga e repetições das séries"""
    if not series:
        return 0, 0
    media_carga = sum(s["carga"] for s in series) / len(series)
    media_reps = sum(s["repeticoes"] for s in series) / len(series)
    return round(media_carga, 1), round(media_reps, 1)

def calcular_volume_total(series):
    """Calcula volume total somando todas as séries"""
    return sum(s["carga"] * s["repeticoes"] for s in series)

def get_ultimas_series(exercicio_id, limite=1):
    """Obtém as últimas séries de um exercício"""
    registros = load_json("registros.json")
    series_exercicio = []
    
    for r in reversed(registros):
        if r["exercicio_id"] == exercicio_id and "series" in r:
            series_exercicio.append({
                "periodo": r["periodo"],
                "semana": r["semana"],
                "series": r["series"]
            })
            if len(series_exercicio) >= limite:
                break
    
    return series_exercicio

def buscar_musculo_no_catalogo(nome_exercicio):
    """Busca o músculo primário de um exercício no catálogo completo"""
    catalogo_path = BASE / "exercises-ptbr-full-translation.json"
    
    if not catalogo_path.exists():
        return None
    
    try:
        with open(catalogo_path, 'r', encoding='utf-8') as f:
            catalogo = json.load(f)
        
        # Busca o exercício pelo nome (case insensitive)
        nome_busca = nome_exercicio.lower().strip()
        for ex in catalogo:
            if ex.get('name', '').lower().strip() == nome_busca:
                # Retorna o primeiro músculo primário encontrado
                primary_muscles = ex.get('primaryMuscles', [])
                if primary_muscles and len(primary_muscles) > 0:
                    return primary_muscles[0]
                break
            
        # Se não encontrar exatamente, tenta buscar por correspondência parcial
        for ex in catalogo:
            if nome_busca in ex.get('name', '').lower():
                primary_muscles = ex.get('primaryMuscles', [])
                if primary_muscles and len(primary_muscles) > 0:
                    return primary_muscles[0]
                break
                
    except Exception as e:
        print(f"Erro ao buscar no catálogo: {e}")
    
    return None

@app.route("/")
def index():
    treinos = load_json("treinos.json")
    registros = load_json("registros.json")
    
    # Estatísticas para o dashboard
    total_registros = len(registros)
    semanas_treinadas = len(set((r["periodo"], r["semana"]) for r in registros))
    
    ultima_semana = "N/A"
    if registros:
        ultimo = registros[-1]
        ultima_semana = f"{ultimo['periodo']} - Semana {ultimo['semana']}"
    
    return render_template("index.html", 
                         treinos=treinos,
                         total_registros=total_registros,
                         semanas_treinadas=semanas_treinadas,
                         ultima_semana=ultima_semana)

@app.route("/registrar", methods=["GET", "POST"])
def registrar():
    treinos = load_json("treinos.json")
    exercicios = load_json("exercicios.json")
    registros = load_json("registros.json")

    treino = request.values.get("treino")
    periodo = request.values.get("periodo")
    semana = request.values.get("semana")

    exercicios_treino = [
        e for e in exercicios if e["treino"] == treino
    ] if treino else []

    registros_map = {}
    historico_series = {}
    
    if treino and periodo and semana:
        # Buscar registros existentes
        registros_map = {
            r["exercicio_id"]: r
            for r in registros
            if r["treino"] == treino
            and r["periodo"] == periodo
            and str(r["semana"]) == str(semana)
        }
        
        # Buscar últimas séries para cada exercício
        for ex in exercicios_treino:
            ultimas = get_ultimas_series(ex["id"], limite=1)
            if ultimas:
                historico_series[ex["id"]] = ultimas[0]["series"]

    if request.method == "POST" and "salvar" in request.form:
        novos = []
        clear_cache()

        for ex in exercicios_treino:
            num_series = int(request.form.get(f"num_series_{ex['id']}", 3))
            carga = request.form.get(f"carga_{ex['id']}")
            reps = request.form.get(f"reps_{ex['id']}")
            
            # Agora aceita zero como valor válido
            if carga is not None and reps is not None and carga != '' and reps != '':
                carga_float = float(carga)
                reps_int = int(reps)
                
                # Verifica se são números válidos (pode ser zero)
                if carga_float >= 0 and reps_int >= 0:
                    # Criar todas as séries com os mesmos valores
                    series = []
                    for i in range(num_series):
                        series.append({
                            "carga": carga_float,
                            "repeticoes": reps_int
                        })
                    
                    novos.append({
                        "treino": treino,
                        "periodo": periodo,
                        "semana": int(semana),
                        "exercicio_id": ex["id"],
                        "series": series,
                        "num_series": num_series,
                        "data_registro": datetime.now().isoformat()
                    })

        # Remover registros antigos da mesma semana
        registros = [
            r for r in registros
            if not (
                r["treino"] == treino and
                r["periodo"] == periodo and
                r["semana"] == int(semana)
            )
        ]

        registros.extend(novos)
        save_json("registros.json", registros)

        flash(f"Treino {treino} - Semana {semana} salvo com sucesso!", "success")
        return redirect(url_for("index"))

    return render_template(
        "registrar_semana.html",
        treinos=treinos,
        exercicios=exercicios_treino,
        registros=registros_map,
        historico_series=historico_series,
        periodos_existentes=get_periodos_existentes(),
        treino=treino,
        periodo=periodo,
        semana=semana
    )

@app.route("/estatisticas")
def estatisticas():
    registros = load_json("registros.json")
    exercicios = load_json("exercicios.json")
    treinos = load_json("treinos.json")
    
    # Derivar músculos dos exercícios
    musculos = sorted(set(e["musculo"] for e in exercicios))
    
    # Estatísticas por músculo
    musculo_stats = {}
    for r in registros:
        ex = next(e for e in exercicios if e["id"] == r["exercicio_id"])
        musculo = ex["musculo"]
        if musculo not in musculo_stats:
            musculo_stats[musculo] = {
                "carga_total": 0, 
                "volume_total": 0, 
                "qtd_exercicios": 0,
                "qtd_registros": 0,
                "total_series": 0
            }
        
        # Calcular volume total considerando todas as séries
        volume_exercicio = calcular_volume_total(r["series"])
        musculo_stats[musculo]["volume_total"] += volume_exercicio
        musculo_stats[musculo]["qtd_registros"] += 1
        musculo_stats[musculo]["total_series"] += len(r["series"])
        
    for e in exercicios:
        musculo = e["musculo"]
        if musculo in musculo_stats:
            musculo_stats[musculo]["qtd_exercicios"] += 1
    
    # Estatísticas por treino
    treino_stats = {}
    for t in treinos:
        treino_id = t["id"]
        exercicios_treino = [e for e in exercicios if e["treino"] == treino_id]
        registros_treino = [r for r in registros if r["treino"] == treino_id]
        
        volume_total = 0
        total_series = 0
        for r in registros_treino:
            volume_total += calcular_volume_total(r["series"])
            total_series += len(r["series"])
        
        treino_stats[treino_id] = {
            "descricao": t["descricao"],
            "qtd_exercicios": len(exercicios_treino),
            "qtd_registros": len(registros_treino),
            "volume_total": volume_total,
            "total_series": total_series
        }
    
    return render_template("estatisticas.html",
                         musculo_stats=musculo_stats,
                         treino_stats=treino_stats,
                         treinos=treinos,
                         musculos=musculos)

@app.route("/visualizar/tabela")
def visualizar_tabela():
    treino_selecionado = request.args.get("treino", "")
    musculo_selecionado = request.args.get("musculo", "")
    ordenar = request.args.get("ordenar", "exercicio")
    semanas_filtro = request.args.get("semanas", "todas")
    
    registros = load_json("registros.json")
    exercicios = load_json("exercicios.json")
    treinos = load_json("treinos.json")
    
    # Derivar músculos dos exercícios
    musculos = sorted(set(e["musculo"] for e in exercicios))
    
    # Filtrar exercícios
    exercicios_filtrados = exercicios.copy()
    if treino_selecionado:
        exercicios_filtrados = [e for e in exercicios_filtrados if e["treino"] == treino_selecionado]
    if musculo_selecionado:
        exercicios_filtrados = [e for e in exercicios_filtrados if e["musculo"] == musculo_selecionado]
    
    if ordenar == "musculo":
        exercicios_filtrados.sort(key=lambda x: (x["musculo"], x["nome"]))
    else:
        exercicios_filtrados.sort(key=lambda x: (x["treino"], x["nome"]))
    
    registros_por_exercicio = {}
    for ex in exercicios_filtrados:
        registros_por_exercicio[ex["id"]] = {}
    
    for r in registros:
        if r["exercicio_id"] in registros_por_exercicio:
            key = f"{r['periodo']}_{r['semana']}"
            registros_por_exercicio[r["exercicio_id"]][key] = r
    
    semanas_set = set()
    for r in registros:
        semanas_set.add((r["periodo"], r["semana"], f"{r['periodo']}_{r['semana']}"))
    
    semanas = []
    for periodo, semana, key in semanas_set:
        semanas.append({
            "periodo": periodo,
            "semana": semana,
            "key": key
        })
    
    ordem_periodos = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", 
                      "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
    
    semanas.sort(key=lambda x: (ordem_periodos.index(x["periodo"]) if x["periodo"] in ordem_periodos else 999, x["semana"]))
    
    semanas_filtradas = []
    semanas_selecionadas_lista = []
    
    if semanas_filtro == "ultimas3":
        semanas_filtradas = semanas[-3:]
    elif semanas_filtro == "ultimas5":
        semanas_filtradas = semanas[-5:]
    elif semanas_filtro == "personalizado":
        for periodo, semana, key in semanas_set:
            if request.args.get(f"semana_{periodo}_{semana}"):
                semanas_filtradas.append({
                    "periodo": periodo,
                    "semana": semana,
                    "key": key
                })
                semanas_selecionadas_lista.append(key)
        if not semanas_filtradas:
            semanas_filtradas = semanas
    else:
        semanas_filtradas = semanas
    
    semanas_filtradas.sort(key=lambda x: (ordem_periodos.index(x["periodo"]) if x["periodo"] in ordem_periodos else 999, x["semana"]))
    
    periodos_disponiveis = []
    for periodo in set(s[0] for s in semanas_set):
        semanas_periodo = sorted([s[1] for s in semanas_set if s[0] == periodo])
        registros_por_semana = {}
        for semana in semanas_periodo:
            count = sum(1 for r in registros if r["periodo"] == periodo and r["semana"] == semana)
            registros_por_semana[semana] = count
        
        periodos_disponiveis.append({
            "periodo": periodo,
            "semanas": semanas_periodo,
            "registros_por_semana": registros_por_semana
        })
    
    periodos_disponiveis.sort(key=lambda x: ordem_periodos.index(x["periodo"]) if x["periodo"] in ordem_periodos else 999)
    
    return render_template("visualizar_tabela.html",
                         treinos=treinos,
                         treino_selecionado=treino_selecionado,
                         musculos=musculos,
                         musculo_selecionado=musculo_selecionado,
                         ordenar=ordenar,
                         exercicios=exercicios_filtrados,
                         semanas=semanas_filtradas,
                         registros_por_exercicio=registros_por_exercicio,
                         semanas_selecionadas=semanas_filtro,
                         semanas_selecionadas_lista=semanas_selecionadas_lista,
                         periodos_disponiveis=periodos_disponiveis)

@app.route("/api/progresso")
def api_progresso():
    registros = load_json("registros.json")
    treino = request.args.get("treino")
    
    # Ordem dos meses para ordenação correta
    ordem_meses = {
        "Janeiro": 1, "Fevereiro": 2, "Março": 3, "Abril": 4,
        "Maio": 5, "Junho": 6, "Julho": 7, "Agosto": 8,
        "Setembro": 9, "Outubro": 10, "Novembro": 11, "Dezembro": 12
    }
    
    semanas = {}
    for r in registros:
        if treino and r["treino"] != treino:
            continue
            
        key = f"{r['periodo']}_{r['semana']}"
        
        # Extrair mês e ano do período
        periodo_parts = r["periodo"].split('/')
        mes = periodo_parts[0].strip()
        ano = int(periodo_parts[1]) if len(periodo_parts) > 1 else 2024
        
        if key not in semanas:
            semanas[key] = {
                "periodo": r["periodo"],
                "semana": r["semana"],
                "volume_total": 0,
                "carga_media": 0,
                "qtd_exercicios": 0,
                "ano": ano,
                "mes_num": ordem_meses.get(mes, 0),
                "mes_nome": mes
            }
        
        volume_exercicio = calcular_volume_total(r["series"])
        semanas[key]["volume_total"] += volume_exercicio
        semanas[key]["qtd_exercicios"] += 1
    
    # Calcular carga média baseada na média das séries
    for key in semanas:
        if semanas[key]["qtd_exercicios"] > 0:
            semanas[key]["carga_media"] = round(semanas[key]["volume_total"] / semanas[key]["qtd_exercicios"], 1)
    
    # Ordenar por ano, mês e semana
    semanas_ordenadas = sorted(
        semanas.values(),
        key=lambda x: (x["ano"], x["mes_num"], x["semana"])
    )
    
    return jsonify({
        "semanas": [f"{s['periodo']} - S{s['semana']}" for s in semanas_ordenadas],
        "volumes": [s["volume_total"] for s in semanas_ordenadas],
        "cargas_medias": [s["carga_media"] for s in semanas_ordenadas]
    })

@app.route("/api/buscar-musculo")
def api_buscar_musculo():
    """API para buscar o músculo de um exercício no catálogo"""
    nome = request.args.get("nome", "").strip()
    
    if not nome:
        return jsonify({"encontrado": False, "mensagem": "Nome do exercício não fornecido"})
    
    musculo = buscar_musculo_no_catalogo(nome)
    
    if musculo:
        return jsonify({
            "encontrado": True, 
            "musculo": musculo,
            "mensagem": f"Músculo encontrado: {musculo}"
        })
    else:
        return jsonify({
            "encontrado": False, 
            "mensagem": "Músculo não encontrado no catálogo"
        })

@app.route("/api/buscar-exercicios")
def api_buscar_exercicios():
    """API para buscar exercícios no catálogo - retorna TODOS os exercícios ou filtra por termo"""
    termo = request.args.get("termo", "").strip().lower()
    catalogo_path = BASE / "exercises-ptbr-full-translation.json"
    
    if not catalogo_path.exists():
        print("Arquivo de catálogo não encontrado!")
        return jsonify([])
    
    try:
        with open(catalogo_path, 'r', encoding='utf-8') as f:
            catalogo = json.load(f)
        
        print(f"Total de exercícios no catálogo: {len(catalogo)}")
        
        resultados = []
        
        for ex in catalogo:
            nome = ex.get('name', '')
            primary_muscles = ex.get('primaryMuscles', [])
            musculo = primary_muscles[0] if primary_muscles else "Não especificado"
            
            # Se tem termo de busca, filtra
            if termo:
                if termo in nome.lower():
                    resultados.append({
                        "nome": nome,
                        "musculo": musculo
                    })
            else:
                # Se não tem termo, retorna todos (limitado a 200 para performance)
                resultados.append({
                    "nome": nome,
                    "musculo": musculo
                })
                if len(resultados) >= 200:
                    break
        
        print(f"Retornando {len(resultados)} resultados")
        return jsonify(resultados)
        
    except Exception as e:
        print(f"Erro ao buscar catálogo: {e}")
        import traceback
        traceback.print_exc()
        return jsonify([])

@app.route("/api/verificar-treino")
def api_verificar_treino():
    """Verifica se um ID de treino já existe"""
    treino_id = request.args.get("id", "").upper()
    treinos = load_json("treinos.json")
    
    existe = any(t["id"] == treino_id for t in treinos)
    
    return jsonify({"existe": existe})

@app.route("/gerenciar")
def gerenciar():
    treinos = load_json("treinos.json")
    exercicios = load_json("exercicios.json")
    registros = load_json("registros.json")
    
    # Derivar músculos dos exercícios
    musculos = sorted(set(e["musculo"] for e in exercicios))
    
    exercicios_por_treino = {}
    for ex in exercicios:
        treino_id = ex["treino"]
        if treino_id not in exercicios_por_treino:
            exercicios_por_treino[treino_id] = 0
        exercicios_por_treino[treino_id] += 1
    
    ultimas_cargas = {}
    for ex in exercicios:
        registros_ex = [r for r in registros if r["exercicio_id"] == ex["id"]]
        if registros_ex:
            # Pega a carga da última série do último registro
            ultimo_registro = registros_ex[-1]
            if "series" in ultimo_registro and ultimo_registro["series"]:
                ultimas_cargas[ex["id"]] = ultimo_registro["series"][0]["carga"]
    
    return render_template("gerenciar_treinos.html",
                         treinos=treinos,
                         exercicios=exercicios,
                         musculos=musculos,
                         exercicios_por_treino=exercicios_por_treino,
                         ultimas_cargas=ultimas_cargas)

@app.route("/salvar/treino", methods=["POST"])
def salvar_treino():
    treinos = load_json("treinos.json")
    
    novo_treino = {
        "id": request.form["id"].upper(),
        "descricao": request.form["descricao"]
    }
    
    if any(t["id"] == novo_treino["id"] for t in treinos):
        flash(f"Treino {novo_treino['id']} já existe!", "danger")
    else:
        treinos.append(novo_treino)
        treinos.sort(key=lambda x: x["id"])
        save_json("treinos.json", treinos)
        flash(f"Treino {novo_treino['id']} criado com sucesso!", "success")
    
    return redirect(url_for("gerenciar"))

@app.route("/editar/treino", methods=["POST"])
def editar_treino():
    treinos = load_json("treinos.json")
    
    treino_id_original = request.form["id_original"]
    novo_id = request.form["id"].upper()
    nova_descricao = request.form["descricao"]
    
    # Verifica se o novo ID já existe (e não é o mesmo treino)
    if novo_id != treino_id_original and any(t["id"] == novo_id for t in treinos):
        flash(f"Treino {novo_id} já existe!", "danger")
        return redirect(url_for("gerenciar"))
    
    # Atualiza o treino
    for treino in treinos:
        if treino["id"] == treino_id_original:
            treino["id"] = novo_id
            treino["descricao"] = nova_descricao
            break
    
    # Atualiza também os exercícios que pertenciam a este treino
    exercicios = load_json("exercicios.json")
    for ex in exercicios:
        if ex["treino"] == treino_id_original:
            ex["treino"] = novo_id
    
    save_json("treinos.json", treinos)
    save_json("exercicios.json", exercicios)
    
    flash(f"Treino {treino_id_original} atualizado para {novo_id} com sucesso!", "success")
    return redirect(url_for("gerenciar"))

@app.route("/salvar/exercicio", methods=["POST"])
def salvar_exercicio():
    exercicios = load_json("exercicios.json")
    
    novo_id = max([e["id"] for e in exercicios], default=0) + 1
    
    nome_exercicio = request.form["nome"]
    musculo = request.form["musculo"]
    treino = request.form["treino"]
    
    # Se o músculo não foi selecionado (valor vazio), tenta buscar no catálogo
    if not musculo or musculo == "":
        musculo_encontrado = buscar_musculo_no_catalogo(nome_exercicio)
        if musculo_encontrado:
            musculo = musculo_encontrado
            flash(f"Músculo '{musculo}' encontrado automaticamente no catálogo!", "info")
        else:
            musculo = "Outros"
            flash("Músculo não encontrado no catálogo. Usando 'Outros'.", "warning")
    
    novo_exercicio = {
        "id": novo_id,
        "nome": nome_exercicio,
        "musculo": musculo,
        "treino": treino
    }
    
    exercicios.append(novo_exercicio)
    exercicios.sort(key=lambda x: x["nome"])  # Ordena por nome
    save_json("exercicios.json", exercicios)
    
    flash(f"Exercício '{novo_exercicio['nome']}' criado com sucesso!", "success")
    return redirect(url_for("gerenciar"))

@app.route("/salvar/musculo", methods=["POST"])
def salvar_musculo():
    exercicios = load_json("exercicios.json")
    musculos = sorted(set(e["musculo"] for e in exercicios))
    
    novo_musculo = request.form["musculo"]
    
    if novo_musculo not in musculos:
        flash(f"Músculo '{novo_musculo}' adicionado com sucesso!", "success")
    else:
        flash(f"Músculo '{novo_musculo}' já existe!", "warning")
    
    return redirect(url_for("gerenciar"))

@app.route("/editar/exercicio", methods=["POST"])
def editar_exercicio():
    exercicios = load_json("exercicios.json")
    
    exercicio_id = int(request.form["id"])
    nome_exercicio = request.form["nome"]
    musculo = request.form["musculo"]
    treino = request.form["treino"]
    
    # Se o músculo não foi selecionado (valor vazio), tenta buscar no catálogo
    if not musculo or musculo == "":
        musculo_encontrado = buscar_musculo_no_catalogo(nome_exercicio)
        if musculo_encontrado:
            musculo = musculo_encontrado
            flash(f"Músculo atualizado para '{musculo}' com base no catálogo!", "info")
        else:
            # Mantém o músculo original se não encontrar
            exercicio_original = next((e for e in exercicios if e["id"] == exercicio_id), None)
            if exercicio_original:
                musculo = exercicio_original["musculo"]
            else:
                musculo = "Outros"
    
    for ex in exercicios:
        if ex["id"] == exercicio_id:
            ex["nome"] = nome_exercicio
            ex["musculo"] = musculo
            ex["treino"] = treino
            break
    
    save_json("exercicios.json", exercicios)
    flash("Exercício atualizado com sucesso!", "success")
    return redirect(url_for("gerenciar"))

@app.route("/excluir/treino/<treino_id>")
def excluir_treino(treino_id):
    treinos = load_json("treinos.json")
    exercicios = load_json("exercicios.json")
    registros = load_json("registros.json")
    
    treinos = [t for t in treinos if t["id"] != treino_id]
    
    exercicios_treino = [e for e in exercicios if e["treino"] == treino_id]
    ids_exercicios = [e["id"] for e in exercicios_treino]
    
    exercicios = [e for e in exercicios if e["treino"] != treino_id]
    registros = [r for r in registros if r["exercicio_id"] not in ids_exercicios]
    
    save_json("treinos.json", treinos)
    save_json("exercicios.json", exercicios)
    save_json("registros.json", registros)
    
    clear_cache()
    flash(f"Treino {treino_id} e todos os seus dados foram excluídos!", "success")
    return redirect(url_for("gerenciar"))

@app.route("/excluir/exercicio/<int:exercicio_id>")
def excluir_exercicio(exercicio_id):
    exercicios = load_json("exercicios.json")
    registros = load_json("registros.json")
    
    exercicio = next((e for e in exercicios if e["id"] == exercicio_id), None)
    nome = exercicio["nome"] if exercicio else "Exercício"
    
    exercicios = [e for e in exercicios if e["id"] != exercicio_id]
    registros = [r for r in registros if r["exercicio_id"] != exercicio_id]
    
    save_json("exercicios.json", exercicios)
    save_json("registros.json", registros)
    
    clear_cache()
    flash(f"'{nome}' e todos os seus registros foram excluídos!", "success")
    return redirect(url_for("gerenciar"))

@app.route("/copiar/treino/<treino_origem>")
def copiar_treino(treino_origem):
    treinos = load_json("treinos.json")
    exercicios = load_json("exercicios.json")
    
    ids_existentes = [t["id"] for t in treinos]
    novo_id = None
    
    for letra in ['F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N', 'O', 'P', 'Q', 'R', 'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z']:
        if letra not in ids_existentes:
            novo_id = letra
            break
    
    if not novo_id:
        flash("Não há IDs disponíveis para novo treino!", "danger")
        return redirect(url_for("gerenciar"))
    
    treino = next((t for t in treinos if t["id"] == treino_origem), None)
    if not treino:
        flash("Treino origem não encontrado!", "danger")
        return redirect(url_for("gerenciar"))
    
    novo_treino = {
        "id": novo_id,
        "descricao": f"{treino['descricao']} (cópia)"
    }
    treinos.append(novo_treino)
    
    exercicios_treino = [e for e in exercicios if e["treino"] == treino_origem]
    novo_id_exercicio = max([e["id"] for e in exercicios], default=0) + 1
    
    for ex in exercicios_treino:
        novo_exercicio = {
            "id": novo_id_exercicio,
            "nome": ex["nome"],
            "musculo": ex["musculo"],
            "treino": novo_id
        }
        exercicios.append(novo_exercicio)
        novo_id_exercicio += 1
    
    save_json("treinos.json", treinos)
    save_json("exercicios.json", exercicios)
    
    flash(f"Treino {treino_origem} copiado para {novo_id} com sucesso!", "success")
    return redirect(url_for("gerenciar"))

@app.route("/api/evolucao/<int:exercicio_id>")
def api_evolucao_exercicio(exercicio_id):
    registros = load_json("registros.json")
    exercicios = load_json("exercicios.json")
    
    exercicio = next((e for e in exercicios if e["id"] == exercicio_id), None)
    if not exercicio:
        return jsonify({"error": "Exercício não encontrado"}), 404
    
    registros_exercicio = [
        r for r in registros if r["exercicio_id"] == exercicio_id
    ]
    
    registros_exercicio.sort(key=lambda x: (x["periodo"], x["semana"]))
    
    # Calcular métricas por sessão
    dados = []
    for r in registros_exercicio:
        media_carga, media_reps = calcular_media_series(r["series"])
        volume_total = calcular_volume_total(r["series"])
        
        dados.append({
            "sessao": f"{r['periodo']} - S{r['semana']}",
            "series": r["series"],
            "media_carga": media_carga,
            "media_reps": media_reps,
            "volume_total": volume_total,
            "num_series": len(r["series"])
        })
    
    return jsonify({
        "exercicio": exercicio["nome"],
        "dados": dados
    })

@app.route("/admin/migrar-series")
def migrar_series():
    """Rota administrativa para migrar registros antigos para o novo formato com séries"""
    registros = load_json("registros.json")
    migrados = 0
    
    for r in registros:
        if "series" not in r and "carga" in r and "repeticoes" in r:
            # Converter registro antigo para novo formato
            r["series"] = [{
                "carga": r["carga"],
                "repeticoes": r["repeticoes"]
            }]
            r["num_series"] = 1
            # Manter campos antigos para compatibilidade
            migrados += 1
    
    if migrados > 0:
        save_json("registros.json", registros)
        flash(f"{migrados} registros migrados para o novo formato com séries!", "success")
    else:
        flash("Nenhum registro precisou ser migrado!", "info")
    
    return redirect(url_for("index"))

if __name__ == "__main__":
    app.run(debug=True)