/**
 * Módulo de proteção CSRF para requisições AJAX
 * 
 * Este módulo intercepta fetch e XMLHttpRequest para adicionar
 * automaticamente o token CSRF em requisições POST/PUT/DELETE.
 */
const CSRFProtection = (function() {
    'use strict';
    
    let token = null;
    
    /**
     * Inicializa o módulo e obtém o token CSRF
     */
    function init() {
        const metaToken = document.querySelector('meta[name="csrf-token"]')?.content;
        if (!metaToken) {
            console.warn('⚠️ Token CSRF não encontrado no meta tag');
            return false;
        }
        
        token = metaToken;
        console.log('✅ CSRF Protection inicializado');
        
        // Interceptar fetch
        interceptFetch();
        
        // Interceptar XMLHttpRequest
        interceptXHR();
        
        return true;
    }
    
    /**
     * Intercepta chamadas fetch para adicionar token CSRF
     */
    function interceptFetch() {
        const originalFetch = window.fetch;
        
        window.fetch = function(url, options = {}) {
            options = options || {};
            options.headers = options.headers || {};
            
            // Adicionar token em requisições POST/PUT/DELETE/PATCH
            const method = (options.method || 'GET').toUpperCase();
            if (['POST', 'PUT', 'DELETE', 'PATCH'].includes(method)) {
                options.headers['X-CSRFToken'] = token;
                
                // Log em desenvolvimento
                if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
                    console.debug(`🔒 CSRF token adicionado para ${method} ${url}`);
                }
            }
            
            return originalFetch.call(this, url, options);
        };
    }
    
    /**
     * Intercepta XMLHttpRequest para adicionar token CSRF
     */
    function interceptXHR() {
        const originalOpen = XMLHttpRequest.prototype.open;
        const originalSend = XMLHttpRequest.prototype.send;
        
        // Interceptar open para armazenar método e URL
        XMLHttpRequest.prototype.open = function(method, url, async = true, user = null, password = null) {
            this._method = method;
            this._url = url;
            return originalOpen.call(this, method, url, async, user, password);
        };
        
        // Interceptar send para adicionar token
        XMLHttpRequest.prototype.send = function(body) {
            if (this._method && ['POST', 'PUT', 'DELETE', 'PATCH'].includes(this._method.toUpperCase())) {
                this.setRequestHeader('X-CSRFToken', token);
                
                // Log em desenvolvimento
                if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
                    console.debug(`🔒 CSRF token adicionado para XHR ${this._method} ${this._url}`);
                }
            }
            return originalSend.call(this, body);
        };
    }
    
    /**
     * Retorna o token CSRF atual
     */
    function getToken() {
        return token;
    }
    
    // API pública
    return {
        init: init,
        getToken: getToken
    };
})();

// Inicializar automaticamente quando o DOM estiver pronto
document.addEventListener('DOMContentLoaded', () => {
    CSRFProtection.init();
});

// Exportar para uso global
if (typeof window !== 'undefined') {
    window.CSRFProtection = CSRFProtection;
}