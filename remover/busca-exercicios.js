/**
 * Módulo de busca de exercícios no catálogo
 */
const BuscaExercicios = (function() {
    'use strict';
    
    let buscaTimeout;
    let todosResultados = [];
    let resultadosExibidos = 50;
    let callbacks = {};
    
    /**
     * Inicializa o módulo
     */
    function init(config) {
        const input = document.getElementById(config.inputId);
        if (!input) {
            console.error(`Input com id ${config.inputId} não encontrado`);
            return;
        }
        
        callbacks = config;
        
        input.addEventListener('input', function() {
            clearTimeout(buscaTimeout);
            const termo = this.value.trim();
            
            if (termo.length < 2) {
                const resultsDiv = document.getElementById(config.resultsDiv);
                if (resultsDiv) resultsDiv.style.display = 'none';
                return;
            }
            
            const listaDiv = document.getElementById(config.listId);
            if (!listaDiv) return;
            
            listaDiv.innerHTML = '<div class="list-group-item text-center"><div class="spinner-border spinner-border-sm"></div> Carregando...</div>';
            
            const resultsDiv = document.getElementById(config.resultsDiv);
            if (resultsDiv) resultsDiv.style.display = 'block';
            
            buscaTimeout = setTimeout(() => {
                fetch(`/api/buscar-exercicios?termo=${encodeURIComponent(termo)}`)
                    .then(response => {
                        if (!response.ok) throw new Error('Erro na requisição');
                        return response.json();
                    })
                    .then(data => {
                        todosResultados = data;
                        resultadosExibidos = 50;
                        _exibirResultados(config);
                    })
                    .catch(error => {
                        console.error('Erro na busca:', error);
                        listaDiv.innerHTML = '<div class="list-group-item text-danger">Erro ao carregar resultados</div>';
                        
                        if (config.onError) {
                            config.onError(error);
                        }
                    });
            }, 300);
        });
    }
    
    /**
     * Exibe resultados paginados
     */
    function _exibirResultados(config) {
        const listaDiv = document.getElementById(config.listId);
        if (!listaDiv) return;
        
        listaDiv.innerHTML = '';
        
        const resultadosParaExibir = todosResultados.slice(0, resultadosExibidos);
        
        if (resultadosParaExibir.length === 0) {
            listaDiv.innerHTML = '<div class="list-group-item text-muted">Nenhum exercício encontrado</div>';
            return;
        }
        
        resultadosParaExibir.forEach(ex => {
            const item = document.createElement('a');
            item.href = '#';
            item.className = 'list-group-item list-group-item-action';
            item.innerHTML = `<strong>${ex.nome}</strong><br><small class="text-muted">Músculo: ${ex.musculo}</small>`;
            item.onclick = (e) => {
                e.preventDefault();
                if (config.onSelect) {
                    config.onSelect(ex);
                }
            };
            listaDiv.appendChild(item);
        });
        
        if (todosResultados.length > resultadosExibidos) {
            const contador = document.createElement('div');
            contador.className = 'list-group-item text-muted text-center';
            contador.innerHTML = `<small>${todosResultados.length - resultadosExibidos} restantes. <a href="#" onclick="BuscaExercicios.carregarMais('${config.listId}'); return false;">Carregar mais</a></small>`;
            listaDiv.appendChild(contador);
        }
    }
    
    /**
     * Carrega mais resultados
     */
    function carregarMais(listId) {
        resultadosExibidos += 50;
        
        const config = {
            listId: listId,
            resultsDiv: listId.replace('lista', 'resultados'),
            inputId: listId.replace('lista', 'busca'),
            onSelect: callbacks.onSelect
        };
        
        _exibirResultados(config);
    }
    
    /**
     * Limpa resultados
     */
    function limpar() {
        todosResultados = [];
        resultadosExibidos = 50;
    }
    
    return {
        init: init,
        carregarMais: carregarMais,
        limpar: limpar
    };
})();

// Exportar para uso global
if (typeof window !== 'undefined') {
    window.BuscaExercicios = BuscaExercicios;
}