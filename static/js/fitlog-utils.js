// fitlog-utils.js - Utilitários compartilhados

const FitLogUtils = (function() {
    'use strict';
    
    // =============================================
    // TOAST NOTIFICATIONS
    // =============================================
    function showToast(message, type = 'info', duration = 3000) {
        // Criar container se não existir
        let container = document.getElementById('toast-container');
        if (!container) {
            container = document.createElement('div');
            container.id = 'toast-container';
            container.style.cssText = `
                position: fixed;
                top: 20px;
                right: 20px;
                z-index: 9999;
            `;
            document.body.appendChild(container);
        }
        
        // Criar toast
        const toast = document.createElement('div');
        toast.className = `toast-notification toast-${type}`;
        toast.style.cssText = `
            min-width: 250px;
            margin-bottom: 10px;
            padding: 15px 20px;
            border-radius: 8px;
            color: white;
            font-weight: 500;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            animation: slideIn 0.3s ease;
            cursor: pointer;
        `;
        
        // Definir cor baseada no tipo
        const colors = {
            success: '#28a745',
            error: '#dc3545',
            warning: '#ffc107',
            info: '#17a2b8'
        };
        toast.style.backgroundColor = colors[type] || colors.info;
        
        // Adicionar ícone
        const icons = {
            success: 'bi-check-circle-fill',
            error: 'bi-exclamation-circle-fill',
            warning: 'bi-exclamation-triangle-fill',
            info: 'bi-info-circle-fill'
        };
        
        toast.innerHTML = `
            <div style="display: flex; align-items: center;">
                <i class="bi ${icons[type]}" style="font-size: 1.2rem; margin-right: 10px;"></i>
                <span>${message}</span>
            </div>
        `;
        
        container.appendChild(toast);
        
        // Remover após duração
        setTimeout(() => {
            toast.style.animation = 'slideOut 0.3s ease';
            setTimeout(() => {
                if (toast.parentNode) {
                    toast.parentNode.removeChild(toast);
                }
            }, 300);
        }, duration);
        
        // Fechar ao clicar
        toast.addEventListener('click', () => {
            toast.style.animation = 'slideOut 0.3s ease';
            setTimeout(() => {
                if (toast.parentNode) {
                    toast.parentNode.removeChild(toast);
                }
            }, 300);
        });
    }
    
    // =============================================
    // LOADING SPINNER
    // =============================================
    function showLoading(show = true, message = 'Processando...') {
        let loader = document.getElementById('global-loader');
        
        if (!loader) {
            loader = document.createElement('div');
            loader.id = 'global-loader';
            loader.style.cssText = `
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background: rgba(255, 255, 255, 0.9);
                z-index: 9999;
                display: none;
                justify-content: center;
                align-items: center;
                flex-direction: column;
            `;
            loader.innerHTML = `
                <div class="spinner-border text-primary" style="width: 4rem; height: 4rem;" role="status">
                    <span class="visually-hidden">Carregando...</span>
                </div>
                <div class="loader-text" style="margin-top: 20px; color: #F28C33; font-weight: 600; font-size: 1.2rem;">
                    ${message}
                </div>
            `;
            document.body.appendChild(loader);
        } else {
            // Atualizar mensagem se necessário
            const textElement = loader.querySelector('.loader-text');
            if (textElement) {
                textElement.textContent = message;
            }
        }
        
        loader.style.display = show ? 'flex' : 'none';
    }
    
    // =============================================
    // DEBOUNCE FUNCTION
    // =============================================
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
    
    // =============================================
    // THROTTLE FUNCTION
    // =============================================
    function throttle(func, limit) {
        let inThrottle;
        return function(...args) {
            if (!inThrottle) {
                func.apply(this, args);
                inThrottle = true;
                setTimeout(() => inThrottle = false, limit);
            }
        };
    }
    
    // =============================================
    // FORMATAÇÃO
    // =============================================
    function formatDate(date) {
        if (!date) return '';
        const d = new Date(date);
        return d.toLocaleDateString('pt-BR');
    }
    
    function formatNumber(num) {
        return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ".");
    }
    
    function formatWeight(weight) {
        return weight ? weight.toFixed(1).replace('.', ',') + ' kg' : '-';
    }
    
    // =============================================
    // VALIDAÇÕES
    // =============================================
    function validateEmail(email) {
        const re = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        return re.test(email);
    }
    
    function validatePhone(phone) {
        const re = /^\(?[1-9]{2}\)? ?(?:[2-8]|9[1-9])[0-9]{3}\-?[0-9]{4}$/;
        return re.test(phone);
    }
    
    // =============================================
    // CONFIRMAÇÕES
    // =============================================
    function confirmAction(message, callback) {
        if (confirm(message)) {
            callback();
        }
    }
    
    // =============================================
    // API CALLS
    // =============================================
    async function apiCall(url, method = 'GET', data = null) {
        const options = {
            method,
            headers: {
                'Content-Type': 'application/json',
                'X-Requested-With': 'XMLHttpRequest'
            }
        };
        
        if (data) {
            options.body = JSON.stringify(data);
        }
        
        // Adicionar CSRF token se existir
        const csrfToken = document.querySelector('input[name="csrf_token"]')?.value;
        if (csrfToken) {
            options.headers['X-CSRFToken'] = csrfToken;
        }
        
        try {
            const response = await fetch(url, options);
            return await response.json();
        } catch (error) {
            console.error('API Error:', error);
            throw error;
        }
    }
    
    // =============================================
    // COPIAR PARA ÁREA DE TRANSFERÊNCIA
    // =============================================
    function copyToClipboard(text) {
        return new Promise((resolve, reject) => {
            if (navigator.clipboard && window.isSecureContext) {
                navigator.clipboard.writeText(text).then(resolve).catch(reject);
            } else {
                // Fallback para navegadores antigos
                const textArea = document.createElement('textarea');
                textArea.value = text;
                textArea.style.position = 'fixed';
                textArea.style.left = '-999999px';
                textArea.style.top = '-999999px';
                document.body.appendChild(textArea);
                textArea.focus();
                textArea.select();
                
                try {
                    document.execCommand('copy') ? resolve() : reject();
                } catch (error) {
                    reject(error);
                } finally {
                    textArea.remove();
                }
            }
        });
    }
    
    // =============================================
    // EXPORTAR FUNÇÕES PÚBLICAS
    // =============================================
    return {
        showToast,
        showLoading,
        debounce,
        throttle,
        formatDate,
        formatNumber,
        formatWeight,
        validateEmail,
        validatePhone,
        confirmAction,
        apiCall,
        copyToClipboard
    };
})();

// Animações CSS para toasts
const style = document.createElement('style');
style.textContent = `
    @keyframes slideIn {
        from {
            transform: translateX(100%);
            opacity: 0;
        }
        to {
            transform: translateX(0);
            opacity: 1;
        }
    }
    
    @keyframes slideOut {
        from {
            transform: translateX(0);
            opacity: 1;
        }
        to {
            transform: translateX(100%);
            opacity: 0;
        }
    }
`;
document.head.appendChild(style);

// Disponibilizar globalmente
window.FitLogUtils = FitLogUtils;