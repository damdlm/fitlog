/**
 * Módulo para registro de treinos
 * FitLog - Sistema de Controle de Treinos
 * 
 * Gerencia o cálculo de volumes, carregamento de histórico,
 * validações e interações na página de registro de treinos.
 */

const RegistrarTreino = (function() {
    'use strict';
    
    // ========================================================================
    // VARIÁVEIS PRIVADAS
    // ========================================================================
    
    let timeoutCalculo;
    let ultimosValores = {};
    let toastContainer = null;
    
    // ========================================================================
    // FUNÇÕES PRIVADAS
    // ========================================================================
    
    /**
     * Inicializa o container de toast se não existir
     */
    function _initToastContainer() {
        if (!toastContainer) {
            toastContainer = document.getElementById('toast-container');
            if (!toastContainer) {
                toastContainer = document.createElement('div');
                toastContainer.id = 'toast-container';
                toastContainer.className = 'toast-container position-fixed top-0 end-0 p-3';
                toastContainer.style.zIndex = '9999';
                document.body.appendChild(toastContainer);
            }
        }
    }
    
    /**
     * Mostra uma mensagem toast
     * 
     * @param {string} message - Mensagem a ser exibida
     * @param {string} type - Tipo (success, danger, warning, info)
     * @param {number} duration - Duração em ms
     */
    function _showToast(message, type = 'info', duration = 3000) {
        _initToastContainer();
        
        const toastId = 'toast-' + Date.now();
        const bgColor = {
            'success': '#28a745',
            'danger': '#dc3545',
            'warning': '#ffc107',
            'info': '#17a2b8'
        }[type] || '#6c757d';
        
        const toast = document.createElement('div');
        toast.id = toastId;
        toast.className = 'toast align-items-center text-white border-0 mb-2';
        toast.setAttribute('role', 'alert');
        toast.setAttribute('aria-live', 'assertive');
        toast.setAttribute('aria-atomic', 'true');
        toast.style.backgroundColor = bgColor;
        toast.style.opacity = '1';
        
        toast.innerHTML = `
            <div class="d-flex">
                <div class="toast-body">
                    <i class="bi bi-${type === 'success' ? 'check-circle' : 
                                      type === 'danger' ? 'exclamation-triangle' :
                                      type === 'warning' ? 'exclamation-circle' :
                                      'info-circle'} me-2"></i>
                    ${message}
                </div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" 
                        data-bs-dismiss="toast" aria-label="Close"></button>
            </div>
        `;
        
        toastContainer.appendChild(toast);
        
        // Inicializar toast do Bootstrap
        if (typeof bootstrap !== 'undefined' && bootstrap.Toast) {
            const bsToast = new bootstrap.Toast(toast, { 
                autohide: true, 
                delay: duration,
                animation: true
            });
            bsToast.show();
            
            toast.addEventListener('hidden.bs.toast', () => {
                toast.remove();
            });
        } else {
            // Fallback se Bootstrap não estiver disponível
            setTimeout(() => {
                toast.style.transition = 'opacity 0.5s';
                toast.style.opacity = '0';
                setTimeout(() => toast.remove(), 500);
            }, duration);
        }
    }
    
    /**
     * Calcula o volume total de um exercício
     * 
     * @param {number} exercicioId - ID do exercício
     * @returns {Object} Objeto com os valores calculados
     */
    function _calcularVolumeExercicio(exercicioId) {
        const exercicio = document.querySelector(`[data-exercicio-id="${exercicioId}"]`);
        if (!exercicio) return { carga: 0, reps: 0, series: 3, volume: 0 };
        
        const cargaInput = exercicio.querySelector('.carga-input');
        const repsInput = exercicio.querySelector('.reps-input');
        
        if (!cargaInput || !repsInput) return { carga: 0, reps: 0, series: 3, volume: 0 };
        
        const carga = parseFloat(cargaInput.value) || 0;
        const reps = parseInt(repsInput.value) || 0;
        
        const seriesSelect = document.getElementById(`series-select-${exercicioId}`);
        const series = parseInt(seriesSelect?.value) || 3;
        
        const volume = carga * reps * series;
        
        return { carga, reps, series, volume };
    }
    
    /**
     * Atualiza a interface com o volume calculado
     * 
     * @param {number} exercicioId - ID do exercício
     * @param {Object} dados - Dados calculados
     */
    function _atualizarInterfaceVolume(exercicioId, dados) {
        const volumeElement = document.getElementById(`volume-${exercicioId}`);
        if (volumeElement) {
            if (dados.volume > 0) {
                volumeElement.innerHTML = `<i class="bi bi-bar-chart"></i> ${dados.volume} kg`;
                volumeElement.style.background = '#2D2D2D';
            } else {
                volumeElement.innerHTML = `<i class="bi bi-bar-chart"></i> 0 kg`;
            }
        }
        
        // Atualizar detalhamento
        const detalheElement = document.getElementById(`volume-detalhe-${exercicioId}`);
        if (detalheElement) {
            if (dados.carga > 0 && dados.reps > 0) {
                detalheElement.innerHTML = `
                    <i class="bi bi-calculator"></i>
                    ${dados.carga} kg × ${dados.reps} reps × ${dados.series} séries = 
                    <strong>${dados.volume} kg</strong>
                `;
            } else {
                detalheElement.innerHTML = '';
            }
        }
        
        // Atualizar barra de progresso
        const progressBar = document.getElementById(`progress-${exercicioId}`);
        if (progressBar && dados.volume > 0) {
            // Estimar progresso baseado no volume máximo (ajustável)
            const volumeMax = ultimosValores[exercicioId]?.volumeMax || dados.volume * 1.2;
            if (!ultimosValores[exercicioId]) {
                ultimosValores[exercicioId] = { volumeMax: dados.volume * 1.2 };
            }
            const percentual = Math.min(100, (dados.volume / volumeMax) * 100);
            progressBar.style.width = percentual + '%';
        }
    }
    
    /**
     * Atualiza o resumo do treino
     */
    function _atualizarResumo() {
        let volumeTotal = 0;
        let exerciciosPreenchidos = 0;
        let totalExercicios = 0;
        
        document.querySelectorAll('.exercise-row').forEach(row => {
            const exId = row.dataset.exercicioId;
            if (!exId) return;
            
            totalExercicios++;
            const dados = _calcularVolumeExercicio(parseInt(exId));
            volumeTotal += dados.volume;
            
            if (dados.carga > 0 && dados.reps > 0) {
                exerciciosPreenchidos++;
            }
        });
        
        const resumoElement = document.getElementById('resumo-volume');
        if (resumoElement) {
            resumoElement.innerHTML = `<strong>${volumeTotal} kg</strong>`;
        }
        
        // Mostrar progresso de preenchimento
        const progressoDiv = document.getElementById('progresso-preenchimento');
        if (progressoDiv && totalExercicios > 0) {
            const percentual = (exerciciosPreenchidos / totalExercicios) * 100;
            progressoDiv.style.width = percentual + '%';
            progressoDiv.setAttribute('aria-valuenow', percentual);
        }
        
        return volumeTotal;
    }
    
    /**
     * Valida um campo individual
     * 
     * @param {HTMLElement} campo - Elemento do campo
     * @returns {boolean} True se válido
     */
    function _validarCampo(campo) {
        if (!campo || !campo.value) return true;
        
        const valor = campo.value.trim();
        if (valor === '') return true;
        
        // Validar se é número
        const numero = parseFloat(valor);
        if (isNaN(numero)) {
            campo.classList.add('is-invalid');
            return false;
        }
        
        // Validar se é positivo
        if (numero < 0) {
            campo.classList.add('is-invalid');
            return false;
        }
        
        // Validar limites
        if (campo.classList.contains('carga-input') && numero > 999) {
            campo.classList.add('is-invalid');
            return false;
        }
        
        if (campo.classList.contains('reps-input') && numero > 100) {
            campo.classList.add('is-invalid');
            return false;
        }
        
        campo.classList.remove('is-invalid');
        return true;
    }
    
    // ========================================================================
    // FUNÇÕES PÚBLICAS
    // ========================================================================
    
    /**
     * Inicializa o módulo
     */
    function init() {
        console.log('📝 Inicializando módulo de registro de treinos');
        
        // Configurar listeners para cálculo automático de volume
        document.querySelectorAll('.carga-input, .reps-input, select[name^="num_series"]').forEach(input => {
            // Input events
            input.addEventListener('input', function() {
                clearTimeout(timeoutCalculo);
                const row = this.closest('.exercise-row');
                if (row) {
                    const exId = row.dataset.exercicioId;
                    if (exId) {
                        timeoutCalculo = setTimeout(() => {
                            calcularVolume(parseInt(exId));
                        }, 300);
                    }
                }
            });
            
            // Change events
            input.addEventListener('change', function() {
                const row = this.closest('.exercise-row');
                if (row) {
                    const exId = row.dataset.exercicioId;
                    if (exId) calcularVolume(parseInt(exId));
                }
            });
            
            // Validação em tempo real
            input.addEventListener('blur', function() {
                _validarCampo(this);
            });
        });
        
        // Calcular volumes iniciais
        document.querySelectorAll('.exercise-row').forEach(row => {
            const exId = row.dataset.exercicioId;
            if (exId) {
                const exIdNum = parseInt(exId);
                setTimeout(() => calcularVolume(exIdNum), 50);
                
                // Armazenar valores iniciais
                const dados = _calcularVolumeExercicio(exIdNum);
                if (dados.volume > 0) {
                    ultimosValores[exIdNum] = {
                        volumeMax: dados.volume * 1.2
                    };
                }
            }
        });
        
        // Configurar validação do formulário
        const form = document.getElementById('registroForm');
        if (form) {
            form.addEventListener('submit', validarFormulario);
        }
        
        // Calcular resumo periodicamente
        setInterval(_atualizarResumo, 500);
        
        // Adicionar listener para teclas de atalho
        document.addEventListener('keydown', function(e) {
            // Ctrl+Enter para submeter
            if (e.ctrlKey && e.key === 'Enter') {
                e.preventDefault();
                const form = document.getElementById('registroForm');
                if (form) {
                    const btn = form.querySelector('button[type="submit"]');
                    if (btn) btn.click();
                }
            }
            
            // Ctrl+L para carregar último registro
            if (e.ctrlKey && e.key === 'l') {
                e.preventDefault();
                carregarUltimoRegistro();
            }
        });
        
        console.log('✅ Módulo de registro inicializado');
    }
    
    /**
     * Calcula o volume total de um exercício e atualiza a interface
     * 
     * @param {number} exercicioId - ID do exercício
     */
    function calcularVolume(exercicioId) {
        const dados = _calcularVolumeExercicio(exercicioId);
        _atualizarInterfaceVolume(exercicioId, dados);
        _atualizarResumo();
    }
    
    /**
     * Carrega o último registro de todos os exercícios
     */
    function carregarUltimoRegistro() {
        let carregados = 0;
        let totalExercicios = 0;
        
        document.querySelectorAll('.exercise-row').forEach(row => {
            const exId = row.dataset.exercicioId;
            if (!exId) return;
            
            totalExercicios++;
            
            // Pegar os dados do último registro armazenados no elemento
            const ultimaCarga = row.dataset.ultimaCarga;
            const ultimasReps = row.dataset.ultimasReps;
            const ultimasSeries = row.dataset.ultimasSeries;
            
            if (ultimaCarga && ultimasReps && 
                ultimaCarga !== 'undefined' && ultimasReps !== 'undefined') {
                
                // Atualizar campos
                const cargaInput = row.querySelector('.carga-input');
                const repsInput = row.querySelector('.reps-input');
                const seriesSelect = document.getElementById(`series-select-${exId}`);
                
                if (cargaInput) cargaInput.value = ultimaCarga;
                if (repsInput) repsInput.value = ultimasReps;
                if (seriesSelect && ultimasSeries && ultimasSeries !== 'undefined') {
                    seriesSelect.value = ultimasSeries;
                }
                
                // Disparar evento change para recalcular
                if (cargaInput) cargaInput.dispatchEvent(new Event('change'));
                
                carregados++;
            }
        });
        
        if (carregados > 0) {
            _showToast(
                `${carregados} de ${totalExercicios} exercício(s) carregado(s) com dados do último treino!`, 
                'success'
            );
        } else {
            _showToast('Nenhum dado anterior encontrado para carregar.', 'warning');
        }
    }
    
    /**
     * Carrega um valor específico para um exercício
     * 
     * @param {number} exercicioId - ID do exercício
     * @param {number} carga - Valor da carga
     * @param {number} reps - Número de repetições
     * @param {number} series - Número de séries
     */
    function carregarValorExercicio(exercicioId, carga, reps, series = 3) {
        const row = document.querySelector(`[data-exercicio-id="${exercicioId}"]`);
        if (!row) return;
        
        const cargaInput = row.querySelector('.carga-input');
        const repsInput = row.querySelector('.reps-input');
        const seriesSelect = document.getElementById(`series-select-${exercicioId}`);
        
        if (cargaInput) cargaInput.value = carga;
        if (repsInput) repsInput.value = reps;
        if (seriesSelect) seriesSelect.value = series;
        
        calcularVolume(exercicioId);
    }
    
    /**
     * Limpa todos os campos do formulário
     */
    function limparTodos() {
        if (!confirm('Tem certeza que deseja limpar todos os campos?')) return;
        
        document.querySelectorAll('.carga-input, .reps-input').forEach(input => {
            input.value = '';
            input.classList.remove('is-invalid');
        });
        
        document.querySelectorAll('select[name^="num_series"]').forEach(select => {
            select.value = '3';
        });
        
        document.querySelectorAll('.exercise-row').forEach(row => {
            const exId = row.dataset.exercicioId;
            if (exId) calcularVolume(parseInt(exId));
        });
        
        _showToast('Todos os campos foram limpos!', 'info');
    }
    
    /**
     * Valida o formulário antes de enviar
     * 
     * @param {Event} e - Evento de submit
     * @returns {boolean} True se válido
     */
    function validarFormulario(e) {
        let valido = true;
        let primeiroInvalido = null;
        let camposPreenchidos = 0;
        let totalExercicios = 0;
        
        document.querySelectorAll('.exercise-row').forEach(row => {
            totalExercicios++;
            const carga = row.querySelector('.carga-input')?.value;
            const reps = row.querySelector('.reps-input')?.value;
            
            // Se um está preenchido e o outro não
            if ((carga && !reps) || (!carga && reps)) {
                valido = false;
                row.classList.add('border', 'border-danger');
                if (!primeiroInvalido) primeiroInvalido = row;
            } else {
                row.classList.remove('border', 'border-danger');
            }
            
            // Validar valores individuais
            const cargaInput = row.querySelector('.carga-input');
            const repsInput = row.querySelector('.reps-input');
            
            if (cargaInput && !_validarCampo(cargaInput)) {
                valido = false;
                if (!primeiroInvalido) primeiroInvalido = row;
            }
            
            if (repsInput && !_validarCampo(repsInput)) {
                valido = false;
                if (!primeiroInvalido) primeiroInvalido = row;
            }
            
            // Contar campos preenchidos
            if (carga && reps && parseFloat(carga) > 0 && parseInt(reps) > 0) {
                camposPreenchidos++;
            }
        });
        
        if (!valido) {
            e.preventDefault();
            _showToast('Preencha todos os campos corretamente!', 'danger');
            
            if (primeiroInvalido) {
                primeiroInvalido.scrollIntoView({ 
                    behavior: 'smooth', 
                    block: 'center' 
                });
            }
            return false;
        }
        
        if (camposPreenchidos === 0) {
            e.preventDefault();
            _showToast('Preencha pelo menos um exercício!', 'warning');
            return false;
        }
        
        // Mostrar loading
        const loader = document.getElementById('global-loader');
        if (loader) {
            loader.style.display = 'flex';
            
            // Animar o loader
            const spinner = loader.querySelector('.spinner-border');
            if (spinner) {
                spinner.style.animation = 'spinner-border 1s linear infinite';
            }
        }
        
        _showToast(`Salvando ${camposPreenchidos} exercícios...`, 'info', 2000);
        return true;
    }
    
    /**
     * Exporta os dados atuais para JSON
     */
    function exportarJSON() {
        const dados = [];
        
        document.querySelectorAll('.exercise-row').forEach(row => {
            const exId = row.dataset.exercicioId;
            if (!exId) return;
            
            const carga = row.querySelector('.carga-input')?.value;
            const reps = row.querySelector('.reps-input')?.value;
            const seriesSelect = document.getElementById(`series-select-${exId}`);
            
            if (carga && reps) {
                dados.push({
                    exercicio_id: parseInt(exId),
                    carga: parseFloat(carga),
                    repeticoes: parseInt(reps),
                    series: parseInt(seriesSelect?.value || 3)
                });
            }
        });
        
        if (dados.length === 0) {
            _showToast('Nenhum dado para exportar!', 'warning');
            return;
        }
        
        const dataStr = JSON.stringify(dados, null, 2);
        const dataUri = 'data:application/json;charset=utf-8,'+ encodeURIComponent(dataStr);
        
        const exportFileDefaultName = `treino_${new Date().toISOString().split('T')[0]}.json`;
        
        const linkElement = document.createElement('a');
        linkElement.setAttribute('href', dataUri);
        linkElement.setAttribute('download', exportFileDefaultName);
        linkElement.click();
        
        _showToast(`${dados.length} exercícios exportados!`, 'success');
    }
    
    /**
     * Preenche todos os exercícios com um valor padrão
     * 
     * @param {number} cargaPadrao - Carga padrão
     * @param {number} repsPadrao - Repetições padrão
     */
    function preencherTodos(cargaPadrao = 0, repsPadrao = 0) {
        if (cargaPadrao <= 0 || repsPadrao <= 0) {
            cargaPadrao = parseFloat(prompt('Digite a carga padrão (kg):', '20')) || 0;
            repsPadrao = parseInt(prompt('Digite as repetições padrão:', '10')) || 0;
            
            if (cargaPadrao <= 0 || repsPadrao <= 0) {
                _showToast('Valores inválidos!', 'warning');
                return;
            }
        }
        
        document.querySelectorAll('.exercise-row').forEach(row => {
            const exId = row.dataset.exercicioId;
            if (!exId) return;
            
            const cargaInput = row.querySelector('.carga-input');
            const repsInput = row.querySelector('.reps-input');
            
            if (cargaInput) cargaInput.value = cargaPadrao;
            if (repsInput) repsInput.value = repsPadrao;
            
            calcularVolume(parseInt(exId));
        });
        
        _showToast(`Todos os exercícios preenchidos com ${cargaPadrao}kg x ${repsPadrao}reps!`, 'success');
    }
    
    // ========================================================================
    // API PÚBLICA
    // ========================================================================
    
    return {
        // Inicialização
        init: init,
        
        // Cálculos
        calcularVolume: calcularVolume,
        
        // Carregamento de dados
        carregarUltimoRegistro: carregarUltimoRegistro,
        carregarValorExercicio: carregarValorExercicio,
        
        // Utilitários
        limparTodos: limparTodos,
        exportarJSON: exportarJSON,
        preencherTodos: preencherTodos,
        
        // Validação
        validarFormulario: validarFormulario
    };
})();

// ========================================================================
// EXPORTAÇÃO PARA USO GLOBAL
// ========================================================================

if (typeof window !== 'undefined') {
    window.RegistrarTreino = RegistrarTreino;
    
    // Adicionar ao objeto global para debug
    window.FitLog = window.FitLog || {};
    window.FitLog.RegistrarTreino = RegistrarTreino;
}

// ========================================================================
// INICIALIZAÇÃO AUTOMÁTICA (opcional - comentar se preferir init manual)
// ========================================================================

document.addEventListener('DOMContentLoaded', function() {
    // Verificar se estamos na página de registro
    if (document.getElementById('registroForm')) {
        // Pequeno delay para garantir que tudo foi carregado
        setTimeout(() => {
            RegistrarTreino.init();
        }, 100);
    }
});

// ========================================================================
// TEclas DE ATALHO GLOBAIS
// ========================================================================

document.addEventListener('keydown', function(e) {
    // Alt+L - Carregar último registro
    if (e.altKey && e.key === 'l') {
        e.preventDefault();
        if (typeof RegistrarTreino !== 'undefined') {
            RegistrarTreino.carregarUltimoRegistro();
        }
    }
    
    // Alt+C - Limpar todos
    if (e.altKey && e.key === 'c') {
        e.preventDefault();
        if (typeof RegistrarTreino !== 'undefined') {
            RegistrarTreino.limparTodos();
        }
    }
    
    // Alt+E - Exportar JSON
    if (e.altKey && e.key === 'e') {
        e.preventDefault();
        if (typeof RegistrarTreino !== 'undefined') {
            RegistrarTreino.exportarJSON();
        }
    }
});