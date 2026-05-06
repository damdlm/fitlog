@api_bp.route("/debug-rotas", methods=["GET"])
@login_required
def api_debug_rotas():
    """
    Endpoint de debug para listar todas as rotas disponíveis
    """
    rotas = []
    
    for rule in current_app.url_map.iter_rules():
        if rule.endpoint != 'static':
            rotas.append({
                "endpoint": rule.endpoint,
                "methods": list(rule.methods - {"HEAD", "OPTIONS"}),
                "path": str(rule)
            })
    
    return jsonify(rotas)