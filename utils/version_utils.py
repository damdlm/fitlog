from .date_utils import converter_periodo_para_data
from .exercise_utils import get_series_from_registro

# ===== VERSÕES GLOBAIS =====

def get_versoes_globais():
    """Retorna todas as versões globais"""
    from .db_utils import get_versoes
    return get_versoes()

def get_versao_ativa(periodo):
    """
    Retorna a versão global que estava ativa em um determinado período
    """
    from .db_utils import get_versao_ativa as db_get_versao_ativa
    return db_get_versao_ativa(periodo)

def get_treinos_da_versao(versao_id):
    """Retorna todos os treinos de uma versão específica"""
    from .db_utils import get_versao
    
    versao = get_versao(versao_id)
    
    if not versao:
        return {}
    
    resultado = {}
    for tv in versao.treinos:
        # Aqui usamos o código do treino como chave, não o ID numérico
        treino = Treino.query.get(tv.treino_id)
        if treino:
            resultado[treino.codigo] = {
                "id": tv.treino_id,  # ID numérico
                "codigo": treino.codigo,  # Código (A, B, C...)
                "nome": tv.nome_treino,
                "descricao": tv.descricao_treino,
                "exercicios": [ve.exercicio_id for ve in tv.exercicios]
            }
    
    return resultado

def get_exercicios_do_treino(versao_id, treino_id):
    """Retorna os exercícios de um treino específico em uma versão"""
    from .db_utils import get_exercicios_da_versao
    return get_exercicios_da_versao(versao_id, treino_id)

def get_todos_exercicios_da_versao(versao_id):
    """Retorna todos os exercícios de todos os treinos em uma versão"""
    from .db_utils import get_todos_exercicios_da_versao as db_func
    return db_func(versao_id)

# ===== FUNÇÕES PARA GERENCIAR TREINOS DENTRO DAS VERSÕES =====

def adicionar_treino_na_versao(versao_id, treino_codigo, nome_treino, descricao_treino, exercicios_ids):
    """Adiciona um novo treino em uma versão existente"""
    from models import db, TreinoVersao, VersaoExercicio, Treino
    from .db_utils import get_versao
    
    versao = get_versao(versao_id)
    
    if not versao:
        return False
    
    # VERIFICAR SE O TREINO EXISTE PELO CÓDIGO
    treino_existente = Treino.query.filter_by(codigo=treino_codigo).first()
    if not treino_existente:
        print(f"❌ ERRO: Treino com código {treino_codigo} não existe na tabela treinos")
        return False
    
    # Verificar se o treino já existe na versão (pelo ID numérico)
    existe = False
    for tv in versao.treinos:
        if tv.treino_id == treino_existente.id:
            existe = True
            break
    
    if existe:
        print(f"❌ Treino {treino_codigo} já existe nesta versão")
        return False
    
    # Criar novo treino na versão
    treino_versao = TreinoVersao(
        versao_id=versao_id,
        treino_id=treino_existente.id,  # ID numérico
        nome_treino=nome_treino,
        descricao_treino=descricao_treino,
        ordem=len(versao.treinos)
    )
    db.session.add(treino_versao)
    db.session.flush()
    
    # Adicionar exercícios
    for ordem, ex_id in enumerate(exercicios_ids):
        ve = VersaoExercicio(
            treino_versao_id=treino_versao.id,
            exercicio_id=ex_id,
            ordem=ordem
        )
        db.session.add(ve)
    
    db.session.commit()
    return True

def verificar_versao_ativa(periodo=None):
    """
    Verifica se há uma versão ativa no período.
    Retorna (tem_ativa, versao, mensagem_erro)
    """
    from .db_utils import get_versao_ativa
    
    versao_ativa = get_versao_ativa(periodo)
    
    if not versao_ativa:
        if not periodo:
            return False, None, "Não há versão ativa no momento. Crie uma nova versão ou finalize a anterior."
        else:
            return False, None, f"Não há versão ativa para o período {periodo}."
    
    return True, versao_ativa, None

def editar_treino_na_versao(versao_id, treino_codigo, nome_treino=None, descricao_treino=None, exercicios_ids=None):
    """Edita um treino existente em uma versão usando o código do treino"""
    from models import db, VersaoExercicio, Treino
    from .db_utils import get_versao
    
    versao = get_versao(versao_id)
    
    if not versao:
        print(f"❌ Versão {versao_id} não encontrada")
        return False
    
    # Buscar o treino pelo código para obter o ID numérico
    treino = Treino.query.filter_by(codigo=treino_codigo).first()
    if not treino:
        print(f"❌ Treino com código {treino_codigo} não encontrado")
        return False
    
    # Encontrar o treino na versão usando o ID numérico
    treino_versao = None
    for tv in versao.treinos:
        if tv.treino_id == treino.id:
            treino_versao = tv
            break
    
    if not treino_versao:
        print(f"❌ Treino {treino_codigo} não encontrado nesta versão")
        return False
    
    # Atualizar dados
    if nome_treino is not None:
        treino_versao.nome_treino = nome_treino
    if descricao_treino is not None:
        treino_versao.descricao_treino = descricao_treino
    
    # Atualizar exercícios
    if exercicios_ids is not None:
        # Remover exercícios antigos
        VersaoExercicio.query.filter_by(treino_versao_id=treino_versao.id).delete()
        
        # Adicionar novos
        for ordem, ex_id in enumerate(exercicios_ids):
            ve = VersaoExercicio(
                treino_versao_id=treino_versao.id,
                exercicio_id=ex_id,
                ordem=ordem
            )
            db.session.add(ve)
    
    db.session.commit()
    return True

def remover_treino_da_versao(versao_id, treino_codigo):
    """Remove um treino de uma versão usando o código do treino"""
    from models import db, Treino
    from .db_utils import get_versao
    
    versao = get_versao(versao_id)
    
    if not versao:
        print(f"❌ Versão {versao_id} não encontrada")
        return False
    
    # Buscar o treino pelo código para obter o ID numérico
    treino = Treino.query.filter_by(codigo=treino_codigo).first()
    if not treino:
        print(f"❌ Treino com código {treino_codigo} não encontrado")
        return False
    
    # Encontrar o treino na versão usando o ID numérico
    treino_versao = None
    for tv in versao.treinos:
        if tv.treino_id == treino.id:
            treino_versao = tv
            break
    
    if not treino_versao:
        print(f"❌ Treino {treino_codigo} não encontrado nesta versão")
        return False
    
    db.session.delete(treino_versao)
    db.session.commit()
    return True

# ===== FUNÇÕES PARA GERENCIAR EXERCÍCIOS DENTRO DOS TREINOS =====

def adicionar_exercicio_ao_treino(versao_id, treino_codigo, exercicio_id):
    """Adiciona um exercício existente a um treino específico dentro de uma versão"""
    from models import db, VersaoExercicio, Treino
    from .db_utils import get_versao
    
    versao = get_versao(versao_id)
    
    if not versao:
        return False
    
    # Buscar o treino pelo código
    treino = Treino.query.filter_by(codigo=treino_codigo).first()
    if not treino:
        return False
    
    # Encontrar o treino na versão pelo ID numérico
    treino_versao = None
    for tv in versao.treinos:
        if tv.treino_id == treino.id:
            treino_versao = tv
            break
    
    if not treino_versao:
        return False
    
    # Verificar se o exercício já existe
    for ve in treino_versao.exercicios:
        if ve.exercicio_id == exercicio_id:
            return True  # Já existe
    
    # Adicionar no final
    nova_ordem = len(treino_versao.exercicios)
    ve = VersaoExercicio(
        treino_versao_id=treino_versao.id,
        exercicio_id=exercicio_id,
        ordem=nova_ordem
    )
    db.session.add(ve)
    db.session.commit()
    
    return True

def remover_exercicio_do_treino(versao_id, treino_codigo, exercicio_id):
    """Remove um exercício de um treino específico dentro de uma versão"""
    from models import db, VersaoExercicio, Treino
    from .db_utils import get_versao
    
    versao = get_versao(versao_id)
    
    if not versao:
        return False
    
    # Buscar o treino pelo código
    treino = Treino.query.filter_by(codigo=treino_codigo).first()
    if not treino:
        return False
    
    # Encontrar o treino na versão pelo ID numérico
    treino_versao = None
    for tv in versao.treinos:
        if tv.treino_id == treino.id:
            treino_versao = tv
            break
    
    if not treino_versao:
        return False
    
    # Encontrar e remover o exercício
    for ve in treino_versao.exercicios:
        if ve.exercicio_id == exercicio_id:
            db.session.delete(ve)
            db.session.commit()
            return True
    
    return False

def reordenar_exercicios_do_treino(versao_id, treino_codigo, nova_ordem):
    """Reordena os exercícios de um treino (lista de IDs na nova ordem)"""
    from models import db, Treino
    from .db_utils import get_versao
    
    versao = get_versao(versao_id)
    
    if not versao:
        return False
    
    # Buscar o treino pelo código
    treino = Treino.query.filter_by(codigo=treino_codigo).first()
    if not treino:
        return False
    
    # Encontrar o treino na versão pelo ID numérico
    treino_versao = None
    for tv in versao.treinos:
        if tv.treino_id == treino.id:
            treino_versao = tv
            break
    
    if not treino_versao:
        return False
    
    # Atualizar ordem
    for ordem, ex_id in enumerate(nova_ordem):
        for ve in treino_versao.exercicios:
            if ve.exercicio_id == ex_id:
                ve.ordem = ordem
                break
    
    db.session.commit()
    return True

# ===== FUNÇÕES PARA VERIFICAR ONDE UM EXERCÍCIO É USADO =====

def verificar_exercicio_em_versoes(exercicio_id):
    """
    Verifica em quais versões e treinos um exercício está presente
    """
    from models import VersaoExercicio, Treino
    
    resultados = []
    
    # Buscar todas as ocorrências do exercício
    ocorrencias = VersaoExercicio.query.filter_by(exercicio_id=exercicio_id).all()
    
    for ve in ocorrencias:
        treino_versao = ve.treino_versao_ref
        versao = treino_versao.versao_ref
        treino = Treino.query.get(treino_versao.treino_id)
        
        if treino:
            resultados.append({
                "versao_id": versao.id,
                "versao": versao.numero_versao,
                "versao_descricao": versao.descricao,
                "treino_id": treino.codigo,  # Usar o código
                "treino_nome": treino_versao.nome_treino,
                "treino_descricao": treino_versao.descricao_treino,
                "data_inicio": versao.data_inicio.isoformat() if versao.data_inicio else None,
                "data_fim": versao.data_fim.isoformat() if versao.data_fim else None
            })
    
    return resultados

# ===== FUNÇÕES DE MIGRAÇÃO =====

def migrar_versoes_para_novo_formato():
    """
    Função para migrar versões antigas para o novo formato com treinos detalhados
    """
    from .file_utils import load_json, save_json
    
    versoes = load_json("versoes_treino.json")
    
    # Se não houver versões, retorna lista vazia
    if not versoes:
        return []
    
    # Verifica se já está no novo formato
    for v in versoes:
        if 'treinos' in v and v['treinos']:
            primeiro_treino = next(iter(v['treinos'].values())) if v['treinos'] else None
            if primeiro_treino and isinstance(primeiro_treino, dict) and 'exercicios' in primeiro_treino:
                print("Arquivo já está no novo formato")
                return versoes
    
    # Converte para o novo formato
    novas_versoes = []
    for v in versoes:
        if 'treinos' in v and isinstance(v['treinos'], dict):
            novos_treinos = {}
            for treino_id, exercicios_ids in v['treinos'].items():
                # Se for lista, converte para dicionário
                if isinstance(exercicios_ids, list):
                    novos_treinos[treino_id] = {
                        "nome": f"Treino {treino_id}",
                        "descricao": f"Treino {treino_id}",
                        "exercicios": exercicios_ids
                    }
                # Se já for dicionário, mantém
                elif isinstance(exercicios_ids, dict):
                    novos_treinos[treino_id] = exercicios_ids
            v['treinos'] = novos_treinos
        novas_versoes.append(v)
    
    return novas_versoes

# ===== FUNÇÕES DE COMPATIBILIDADE =====

def get_versoes_treino_antigo(treino_id=None):
    """Compatibilidade: retorna lista vazia"""
    return []

def get_versao_ativa_antiga(treino_id, periodo):
    """Compatibilidade: retorna None"""
    return None

def get_exercicios_por_versao_antiga(versao_id):
    """Compatibilidade: retorna lista vazia"""
    return []

def get_versoes_treino(treino_id=None):
    """Compatibilidade: redireciona para get_versoes_globais"""
    return get_versoes_globais()

def get_exercicios_por_versao(versao_id):
    """Compatibilidade: redireciona para get_todos_exercicios_da_versao"""
    return get_todos_exercicios_da_versao(versao_id)

def get_ultimas_series(exercicio_id, versao_global_id=None, versao_id=None, limite=1):
    """
    Obtém as últimas séries de um exercício
    """
    from .db_utils import get_ultimas_series as db_get_ultimas_series
    return db_get_ultimas_series(exercicio_id, versao_id or versao_global_id, limite)