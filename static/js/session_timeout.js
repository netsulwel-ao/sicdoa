/**
 * Sistema de timeout de sessão com alertas visuais
 * Mostra tempo restante e avisa antes de expirar
 */

class SessionManager {
    constructor() {
        this.tempoRestante = 0;
        this.warningShown = false;
        this.timeoutWarning = null;
        this.timeoutRedirect = null;
        this.init();
    }

    init() {
        // Obter tempo restante da sessão do template
        const tempoRestanteElement = document.getElementById('tempo-restante-sessao');
        if (tempoRestanteElement) {
            this.tempoRestante = parseInt(tempoRestanteElement.textContent);
            this.startTimer();
        }
    }

    startTimer() {
        if (this.tempoRestante <= 0) return;

        // Limpar timers existentes
        this.clearTimers();

        // Mostrar aviso 5 minutos antes de expirar
        const warningTime = (this.tempoRestante - 5) * 60 * 1000;
        if (warningTime > 0) {
            this.timeoutWarning = setTimeout(() => {
                this.showWarning();
            }, warningTime);
        }

        // Redirecionar para login quando expirar
        const redirectTime = this.tempoRestante * 60 * 1000;
        this.timeoutRedirect = setTimeout(() => {
            this.redirectToLogin();
        }, redirectTime);

        // Atualizar display do tempo
        this.updateDisplay();
        this.displayInterval = setInterval(() => {
            this.tempoRestante--;
            this.updateDisplay();
            
            if (this.tempoRestante <= 0) {
                this.redirectToLogin();
            }
        }, 60000); // Atualizar a cada minuto
    }

    updateDisplay() {
        const displayElement = document.getElementById('session-timer-display');
        if (displayElement && this.tempoRestante > 0) {
            const minutos = this.tempoRestante;
            const horas = Math.floor(minutos / 60);
            const minsRestantes = minutos % 60;
            
            let tempoTexto = '';
            if (horas > 0) {
                tempoTexto = `${horas}h ${minsRestantes}min`;
            } else {
                tempoTexto = `${minutos} minutos`;
            }
            
            displayElement.textContent = tempoTexto;
            
            // Mudar cor quando estiver perto de expirar
            if (this.tempoRestante <= 5) {
                displayElement.className = 'text-red-600 font-medium';
            } else if (this.tempoRestante <= 10) {
                displayElement.className = 'text-yellow-600 font-medium';
            } else {
                displayElement.className = 'text-green-600 font-medium';
            }
        }
    }

    showWarning() {
        if (this.warningShown) return;
        this.warningShown = true;

        // Criar modal de aviso
        const modal = document.createElement('div');
        modal.className = 'fixed inset-0 bg-gray-600 bg-opacity-50 overflow-y-auto h-full w-full z-50';
        modal.innerHTML = `
            <div class="relative top-20 mx-auto p-5 border w-96 shadow-lg rounded-lg bg-white">
                <div class="mt-3 text-center">
                    <div class="flex items-center justify-center w-12 h-12 mx-auto bg-yellow-100 rounded-full">
                        <i class="fas fa-exclamation-triangle text-yellow-600 text-2xl"></i>
                    </div>
                    <h3 class="text-lg leading-6 font-medium text-gray-900 mt-4">Sessão Expirando</h3>
                    <div class="mt-2 px-7 py-3">
                        <p class="text-sm text-gray-500">
                            Sua sessão expirará em <span class="font-medium text-yellow-600">5 minutos</span>. 
                            Salve seu trabalho e faça login novamente para continuar.
                        </p>
                    </div>
                    <div class="items-center px-4 py-3">
                        <button id="extend-session-btn" class="px-4 py-2 bg-blue-600 text-white text-base font-medium rounded-lg w-full shadow-sm hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500">
                            Estender Sessão
                        </button>
                        <button id="close-warning-btn" class="mt-2 px-4 py-2 bg-gray-200 text-gray-800 text-base font-medium rounded-lg w-full shadow-sm hover:bg-gray-300 focus:outline-none focus:ring-2 focus:ring-gray-500">
                            Entendido
                        </button>
                    </div>
                </div>
            </div>
        `;

        document.body.appendChild(modal);

        // Adicionar event listeners
        document.getElementById('extend-session-btn').addEventListener('click', () => {
            this.extendSession();
            document.body.removeChild(modal);
        });

        document.getElementById('close-warning-btn').addEventListener('click', () => {
            document.body.removeChild(modal);
        });
    }

    extendSession() {
        // Fazer requisição para estender sessão
        fetch('/extend-session/', {
            method: 'POST',
            headers: {
                'X-CSRFToken': this.getCookie('csrftoken'),
                'Content-Type': 'application/json',
            },
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                this.tempoRestante = data.tempo_restante;
                this.warningShown = false;
                this.startTimer();
                this.showNotification('Sessão estendida por 30 minutos', 'success');
            }
        })
        .catch(error => {
            console.error('Erro ao estender sessão:', error);
            this.showNotification('Erro ao estender sessão', 'error');
        });
    }

    showNotification(message, type = 'info') {
        // Criar notificação
        const notification = document.createElement('div');
        const bgColor = type === 'success' ? 'bg-green-500' : type === 'error' ? 'bg-red-500' : 'bg-blue-500';
        
        notification.className = `fixed top-4 right-4 ${bgColor} text-white px-6 py-3 rounded-lg shadow-lg z-50 transform transition-all duration-300 translate-x-full`;
        notification.innerHTML = `
            <div class="flex items-center">
                <i class="fas mr-2">${type === 'success' ? 'fa-check-circle' : type === 'error' ? 'fa-times-circle' : 'fa-info-circle'}</i>
                <span>${message}</span>
            </div>
        `;

        document.body.appendChild(notification);

        // Animar entrada
        setTimeout(() => {
            notification.classList.remove('translate-x-full');
        }, 100);

        // Remover após 3 segundos
        setTimeout(() => {
            notification.classList.add('translate-x-full');
            setTimeout(() => {
                document.body.removeChild(notification);
            }, 300);
        }, 3000);
    }

    redirectToLogin() {
        this.clearTimers();
        this.showNotification('Sessão expirada. Redirecionando para login...', 'warning');
        setTimeout(() => {
            window.location.href = '/login/';
        }, 2000);
    }

    clearTimers() {
        if (this.timeoutWarning) {
            clearTimeout(this.timeoutWarning);
        }
        if (this.timeoutRedirect) {
            clearTimeout(this.timeoutRedirect);
        }
        if (this.displayInterval) {
            clearInterval(this.displayInterval);
        }
    }

    getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }
}

// Inicializar quando o DOM estiver pronto
document.addEventListener('DOMContentLoaded', function() {
    new SessionManager();
});
