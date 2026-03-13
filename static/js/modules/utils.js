/**
 * Utilitários gerais para a aplicação
 */
const FitLogUtils = (function() {
    
    /**
     * Formata um número com decimais
     */
    function formatNumber(num, decimals = 1) {
        if (num === null || num === undefined || isNaN(num)) return '-';
        return parseFloat(num).toFixed(decimals);
    }
    
    /**
     * Mostra uma mensagem toast
     */
    function showToast(message, type = 'info', duration = 3000) {
        let toastContainer = document.getElementById('toast-container');
        if (!toastContainer) {
            toastContainer = document.createElement('div');
            toastContainer.id = 'toast-container';
            toastContainer.style.position = 'fixed';
            toastContainer.style.top = '20px';
            toastContainer.style.right = '20px';
            toastContainer.style.zIndex = '9999';
            document.body.appendChild(toastContainer);
        }
        
        const toast = document.createElement('div');
        toast.className = `toast align-items-center text-white bg-${type} border-0`;
        toast.setAttribute('role', 'alert');
        toast.setAttribute('aria-live', 'assertive');
        toast.setAttribute('aria-atomic', 'true');
        
        toast.innerHTML = `
            <div class="d-flex">
                <div class="toast-body">
                    ${message}
                </div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
            </div>
        `;
        
        toastContainer.appendChild(toast);
        
        const bsToast = new bootstrap.Toast(toast, { autohide: true, delay: duration });
        bsToast.show();
        
        toast.addEventListener('hidden.bs.toast', () => {
            toast.remove();
        });
    }
    
    /**
     * Debounce para evitar múltiplas chamadas
     */
    function debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    }
    
    /**
     * Salva dados no localStorage
     */
    function saveToStorage(key, data) {
        try {
            localStorage.setItem(key, JSON.stringify(data));
            return true;
        } catch (e) {
            console.error('Erro ao salvar no storage:', e);
            return false;
        }
    }
    
    /**
     * Recupera dados do localStorage
     */
    function getFromStorage(key, defaultValue = null) {
        try {
            const data = localStorage.getItem(key);
            return data ? JSON.parse(data) : defaultValue;
        } catch (e) {
            console.error('Erro ao ler do storage:', e);
            return defaultValue;
        }
    }
    
    /**
     * Remove acentos de uma string
     */
    function removerAcentos(texto) {
        return texto.normalize('NFD').replace(/[\u0300-\u036f]/g, '');
    }
    
    return {
        formatNumber,
        showToast,
        debounce,
        saveToStorage,
        getFromStorage,
        removerAcentos
    };
})();

// Exportar para uso global
window.FitLogUtils = FitLogUtils;