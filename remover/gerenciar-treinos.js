/**
 * Funções para gerenciamento de treinos
 */
const GerenciarTreinos = (function() {
    
    function editarTreino(id, codigo, nome, descricao) {
        document.getElementById('edit_treino_id_original').value = id;
        document.getElementById('edit_treino_id').value = codigo;
        document.getElementById('edit_treino_nome').value = nome;
        document.getElementById('edit_treino_descricao').value = descricao;
        document.getElementById('edit_treino_alerta').style.display = 'none';
        
        const modal = new bootstrap.Modal(document.getElementById('modalEditarTreino'));
        modal.show();
    }
    
    function editarExercicio(id, nome, musculo, treino) {
        // Implementar conforme necessidade
        console.log('Editar exercício:', id, nome, musculo, treino);
        FitLogUtils.showToast('Funcionalidade em desenvolvimento', 'info');
    }
    
    function confirmarExclusaoTreino(id, descricao) {
        if (confirm(`Excluir treino ${descricao}?\nIsso também excluirá todos os exercícios e registros!`)) {
            window.location.href = `/admin/excluir/treino/${id}`;
        }
    }
    
    function confirmarExclusaoExercicio(id, nome) {
        if (confirm(`Excluir exercício "${nome}"?\nIsso também excluirá todos os registros!`)) {
            window.location.href = `/admin/excluir/exercicio/${id}`;
        }
    }
    
    // Validação de ID único
    document.getElementById('edit_treino_id')?.addEventListener('input', function() {
        const novoId = this.value.toUpperCase();
        const idOriginal = document.getElementById('edit_treino_id_original').value;
        const alertaDiv = document.getElementById('edit_treino_alerta');
        const mensagemSpan = document.getElementById('edit_treino_mensagem');
        
        if (novoId === document.getElementById('edit_treino_id_original').value) {
            alertaDiv.style.display = 'none';
            return;
        }
        
        fetch(`/api/verificar-treino?id=${encodeURIComponent(novoId)}`)
            .then(response => response.json())
            .then(data => {
                if (data.existe) {
                    mensagemSpan.textContent = `O ID "${novoId}" já está em uso.`;
                    alertaDiv.style.display = 'block';
                } else {
                    alertaDiv.style.display = 'none';
                }
            })
            .catch(error => {
                console.error('Erro ao verificar treino:', error);
            });
    });
    
    return {
        editarTreino: editarTreino,
        editarExercicio: editarExercicio,
        confirmarExclusaoTreino: confirmarExclusaoTreino,
        confirmarExclusaoExercicio: confirmarExclusaoExercicio
    };
})();

// Exportar para uso global
window.GerenciarTreinos = GerenciarTreinos;