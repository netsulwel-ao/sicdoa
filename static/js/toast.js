/**
 * ═══════════════════════════════════════════════════════════════════════════
 * ToastManager — CDOA Sistema
 * Sistema de notificações profissional sem dependências externas.
 *
 * Uso JS:
 *   window.toast.success('Guardado com sucesso!');
 *   window.toast.error('Ocorreu um erro.', { title: 'Erro', duration: 6000 });
 *   window.toast.warning('Atenção!');
 *   window.toast.info('Informação disponível.');
 *   window.toast.show({ type: 'success', message: '...', title: '...' });
 *
 * Uso Python (Django messages framework):
 *   from django.contrib import messages
 *   messages.success(request, 'Guardado com sucesso!')
 *   messages.error(request, 'Ocorreu um erro.')
 *   messages.warning(request, 'Atenção!')
 *   messages.info(request, 'Informação.')
 *   # O template lê automaticamente via data-django-messages
 * ═══════════════════════════════════════════════════════════════════════════
 */

(function (global) {
  'use strict';

  /* ── Configuração ─────────────────────────────────────────────────────── */
  var CONFIG = {
    duration:  5000,   // ms até fechar automaticamente (0 = não fecha)
    maxToasts: 5,      // máximo de toasts visíveis em simultâneo
    containerId: 'toast-container',
  };

  /* ── Mapa de tipos ────────────────────────────────────────────────────── */
  var TYPES = {
    success: {
      title:  'Sucesso',
      icon:   'fa-check-circle',
      cls:    'toast-success',
    },
    error: {
      title:  'Erro',
      icon:   'fa-times-circle',
      cls:    'toast-error',
    },
    warning: {
      title:  'Atenção',
      icon:   'fa-exclamation-triangle',
      cls:    'toast-warning',
    },
    info: {
      title:  'Informação',
      icon:   'fa-info-circle',
      cls:    'toast-info',
    },
  };

  /* ── Utilitário: escape HTML ──────────────────────────────────────────── */
  function escHtml(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  /* ── Classe ToastManager ──────────────────────────────────────────────── */
  function ToastManager() {
    this._queue   = [];   // toasts activos
    this._counter = 0;    // id único
    this._container = null;
  }

  /* Garante que o container existe no DOM */
  ToastManager.prototype._getContainer = function () {
    if (!this._container) {
      var el = document.getElementById(CONFIG.containerId);
      if (!el) {
        el = document.createElement('div');
        el.id = CONFIG.containerId;
        document.body.appendChild(el);
      }
      this._container = el;
    }
    return this._container;
  };

  /**
   * show(options)
   * @param {object} options
   *   type     {string}  'success' | 'error' | 'warning' | 'info'
   *   message  {string}  Texto principal (obrigatório)
   *   title    {string}  Título (opcional — usa o padrão do tipo)
   *   duration {number}  ms (0 = permanente)
   */
  ToastManager.prototype.show = function (options) {
    var opts = options || {};
    var type = TYPES[opts.type] ? opts.type : 'info';
    var meta = TYPES[type];
    var duration = (opts.duration !== undefined) ? opts.duration : CONFIG.duration;
    var id = 'toast-' + (++this._counter);

    /* Limite de toasts visíveis */
    if (this._queue.length >= CONFIG.maxToasts) {
      this.close(this._queue[0].id);
    }

    var container = this._getContainer();

    /* ── Construir o card ─────────────────────────────────────────────── */
    var card = document.createElement('div');
    card.id        = id;
    card.className = 'toast-card ' + meta.cls;
    card.setAttribute('role', 'alert');
    card.setAttribute('aria-live', 'assertive');
    card.setAttribute('aria-atomic', 'true');

    var progressHtml = duration > 0
      ? '<div class="toast-progress-track">'
        + '<div class="toast-progress" style="animation-duration:' + duration + 'ms"></div>'
        + '</div>'
      : '';

    card.innerHTML =
      '<div class="toast-icon-wrap">'
        + '<i class="fas ' + escHtml(meta.icon) + '"></i>'
      + '</div>'
      + '<div class="toast-body">'
        + '<p class="toast-title">' + escHtml(opts.title || meta.title) + '</p>'
        + '<p class="toast-message">' + escHtml(opts.message || '') + '</p>'
      + '</div>'
      + '<button class="toast-close" aria-label="Fechar notificação">'
        + '<i class="fas fa-times"></i>'
      + '</button>'
      + progressHtml;

    container.appendChild(card);

    /* Registo interno */
    var entry = { id: id, card: card, timer: null };
    this._queue.push(entry);

    /* Botão fechar */
    var self = this;
    card.querySelector('.toast-close').addEventListener('click', function () {
      self.close(id);
    });

    /* Pausar progresso ao hover */
    if (duration > 0) {
      var progressEl = card.querySelector('.toast-progress');
      card.addEventListener('mouseenter', function () {
        if (progressEl) progressEl.style.animationPlayState = 'paused';
        clearTimeout(entry.timer);
      });
      card.addEventListener('mouseleave', function () {
        if (progressEl) {
          progressEl.style.animationPlayState = 'running';
          /* Recalcular tempo restante pela largura actual */
          var remaining = progressEl.getBoundingClientRect().width
            / card.getBoundingClientRect().width * duration;
          entry.timer = setTimeout(function () { self.close(id); }, remaining);
        }
      });

      /* Auto-fechar */
      entry.timer = setTimeout(function () { self.close(id); }, duration);
    }

    return id;
  };

  /**
   * close(id) — fecha um toast pelo id com animação de saída
   */
  ToastManager.prototype.close = function (id) {
    var idx = -1;
    for (var i = 0; i < this._queue.length; i++) {
      if (this._queue[i].id === id) { idx = i; break; }
    }
    if (idx === -1) return;

    var entry = this._queue[idx];
    clearTimeout(entry.timer);
    this._queue.splice(idx, 1);

    var card = entry.card;
    card.classList.add('toast-leaving');
    card.addEventListener('animationend', function () {
      if (card.parentNode) card.parentNode.removeChild(card);
    }, { once: true });
  };

  /* ── Atalhos por tipo ─────────────────────────────────────────────────── */
  ToastManager.prototype.success = function (message, opts) {
    return this.show(Object.assign({}, opts || {}, { type: 'success', message: message }));
  };
  ToastManager.prototype.error = function (message, opts) {
    return this.show(Object.assign({}, opts || {}, { type: 'error', message: message }));
  };
  ToastManager.prototype.warning = function (message, opts) {
    return this.show(Object.assign({}, opts || {}, { type: 'warning', message: message }));
  };
  ToastManager.prototype.info = function (message, opts) {
    return this.show(Object.assign({}, opts || {}, { type: 'info', message: message }));
  };

  /**
   * confirm(message, onConfirm, opts)
   * Mostra um toast de confirmação com dois botões.
   */
  ToastManager.prototype.confirm = function (message, onConfirm, opts) {
    var options  = opts || {};
    var self     = this;
    var type     = options.type || 'warning';
    var meta     = TYPES[type] || TYPES.warning;
    var id       = 'toast-' + (++this._counter);
    var confirmText = options.confirmText || 'Confirmar';
    var cancelText  = options.cancelText  || 'Cancelar';

    if (this._queue.length >= CONFIG.maxToasts) {
      this.close(this._queue[0].id);
    }

    var container = this._getContainer();
    var card = document.createElement('div');
    card.id        = id;
    card.className = 'toast-card ' + meta.cls;
    card.setAttribute('role', 'alertdialog');
    card.setAttribute('aria-modal', 'true');

    card.innerHTML =
      '<div class="toast-icon-wrap">'
        + '<i class="fas ' + escHtml(meta.icon) + '"></i>'
      + '</div>'
      + '<div class="toast-body">'
        + '<p class="toast-title">' + escHtml(options.title || meta.title) + '</p>'
        + '<p class="toast-message">' + escHtml(message) + '</p>'
        + '<div style="display:flex;gap:0.5rem;margin-top:0.625rem;">'
          + '<button class="toast-btn-confirm" style="'
              + 'flex:1;padding:0.375rem 0.75rem;border:none;border-radius:0.5rem;'
              + 'font-family:inherit;font-size:0.75rem;font-weight:700;cursor:pointer;'
              + 'background:#137fec;color:#fff;transition:opacity .15s;">'
            + escHtml(confirmText)
          + '</button>'
          + '<button class="toast-btn-cancel" style="'
              + 'flex:1;padding:0.375rem 0.75rem;border:1px solid #d1d5db;border-radius:0.5rem;'
              + 'font-family:inherit;font-size:0.75rem;font-weight:600;cursor:pointer;'
              + 'background:#fff;color:#374151;transition:background .15s;">'
            + escHtml(cancelText)
          + '</button>'
        + '</div>'
      + '</div>';

    container.appendChild(card);
    var entry = { id: id, card: card, timer: null };
    this._queue.push(entry);

    card.querySelector('.toast-btn-confirm').addEventListener('click', function () {
      self.close(id);
      if (typeof onConfirm === 'function') onConfirm();
    });
    card.querySelector('.toast-btn-cancel').addEventListener('click', function () {
      self.close(id);
      if (typeof options.onCancel === 'function') options.onCancel();
    });

    return id;
  };

  /**
   * fromDjangoMessages()
   * Lê o elemento #django-messages e exibe cada mensagem como toast.
   * Formato esperado no HTML:
   *   <script id="django-messages" type="application/json">
   *     [{"level": "success", "message": "Guardado!"}]
   *   </script>
   */
  ToastManager.prototype.fromDjangoMessages = function () {
    var el = document.getElementById('django-messages');
    if (!el) return;
    var messages;
    try { messages = JSON.parse(el.textContent || el.innerHTML); }
    catch (e) { return; }
    if (!Array.isArray(messages)) return;

    var self = this;
    /* Escalonar ligeiramente para não aparecerem todos ao mesmo tempo */
    messages.forEach(function (msg, i) {
      setTimeout(function () {
        var type = msg.level || 'info';
        /* Django usa 'success', 'error', 'warning', 'info', 'debug' */
        if (type === 'debug') type = 'info';
        self.show({ type: type, message: msg.message, title: msg.title });
      }, i * 120);
    });
  };

  /* ── Compatibilidade retroactiva com o sistema antigo ─────────────────── */
  function legacyBridge(manager) {
    /* Funções antigas usadas em vários templates */
    global.showToastSuccess = function (m, o) { return manager.success(m, o); };
    global.showToastError   = function (m, o) { return manager.error(m, o); };
    global.showToastWarning = function (m, o) { return manager.warning(m, o); };
    global.showToastInfo    = function (m, o) { return manager.info(m, o); };
    global.showToast        = function (m, t, o) { return manager.show(Object.assign({}, o || {}, { type: t, message: m })); };
    global.showToastConfirm = function (msg, onConfirm, onCancel, opts) {
      return manager.confirm(msg, onConfirm, Object.assign({}, opts || {}, { onCancel: onCancel }));
    };

    /* Atalhos ainda mais curtos */
    global.showSuccess = function (m) { return manager.success(m); };
    global.showError   = function (m) { return manager.error(m); };
    global.showWarning = function (m) { return manager.warning(m); };
    global.showInfo    = function (m) { return manager.info(m); };

    /* Leitura de data-attributes (sistema antigo do base_rh.html) */
    global.showDjangoNotifications = function () {
      var map = {
        'data-success-message': 'success',
        'data-error-message':   'error',
        'data-info-message':    'info',
        'data-warning-message': 'warning',
      };
      Object.keys(map).forEach(function (attr) {
        document.querySelectorAll('[' + attr + ']').forEach(function (el) {
          manager.show({ type: map[attr], message: el.getAttribute(attr) });
          el.removeAttribute(attr);
        });
      });
    };
  }

  /* ── Bootstrap ────────────────────────────────────────────────────────── */
  var manager = new ToastManager();

  /* API pública */
  global.toast = manager;

  /* Ponte de compatibilidade */
  legacyBridge(manager);

  /* Inicializar ao carregar o DOM */
  document.addEventListener('DOMContentLoaded', function () {
    manager.fromDjangoMessages();   /* mensagens via JSON */
    global.showDjangoNotifications(); /* mensagens via data-attributes */
  });

}(window));
