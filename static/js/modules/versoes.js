/**
 * Módulo para gerenciamento de versões
 */
const VersoesManager = (function() {
    
    function init() {
        console.log('Inicializando módulo de versões');
    }
    
    function criarTreinoViaAPI() {
        const id = document.getElementById('novo_treino_id').value.toUpperCase().trim();
        const nome = document.getElementById('novo_treino_nome').value.trim();
        const descricao = document.getElementById('novo_treino_descricao').value.trim();
        
        if (!id || !nome || !descricao) {
            FitLogUtils.showToast('Preencha todos os campos', 'warning');
            return;
        }
        
        if (!id.match(/^[A-Z]$/)) {
            FitLogUtils.showToast('ID deve ser uma letra maiúscula', 'warning');
            return;
        }
        
        showLoading(true);
        
        fetch('/version/api/criar-treino', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({id: id, nome: nome, descricao: descricao})
        })
        .then(response => response.json())
        .then(data => {
            showLoading(false);
            if (data.success) {
                FitLogUtils.showToast(`Treino ${id} criado!`, 'success');
                setTimeout(() => location.reload(), 1500);
            } else {
                FitLogUtils.showToast(data.error || 'Erro ao criar treino', 'danger');
            }
        })
        .catch(error => {
            showLoading(false);
            console.error('Erro:', error);
            FitLogUtils.showToast('Erro de conexão', 'danger');
        });
    }
    
    return {
        init: init,
        criarTreinoViaAPI: criarTreinoViaAPI
    };
})();

// Exportar para uso global
window.VersoesManager = VersoesManager;