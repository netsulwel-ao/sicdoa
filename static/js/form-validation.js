/**
 * form-validation.js
 * Validação client-side universal para todos os formulários do projecto.
 * Intercepta submissões, valida campos required e mostra erros inline.
 */

(function () {
  'use strict';

  // ── Estilos de erro ──────────────────────────────────────────────────────
  const ERR_BORDER = '2px solid #ef4444';
  const ERR_BG     = '#fef2f2';

  function _showFieldError(field, msg) {
    field.style.border = ERR_BORDER;
    field.style.backgroundColor = ERR_BG;
    field.setAttribute('aria-invalid', 'true');

    // Remover erro anterior
    const prev = field.parentElement.querySelector('.fv-error');
    if (prev) prev.remove();

    const err = document.createElement('p');
    err.className = 'fv-error';
    err.style.cssText = 'color:#ef4444;font-size:0.72rem;margin-top:3px;display:flex;align-items:center;gap:3px;';
    err.innerHTML = `<i class="fas fa-times-circle" style="font-size:13px;"></i>${msg}`;
    field.parentElement.appendChild(err);
  }

  function _clearFieldError(field) {
    field.style.border = '';
    field.style.backgroundColor = '';
    field.removeAttribute('aria-invalid');
    const prev = field.parentElement.querySelector('.fv-error');
    if (prev) prev.remove();
  }

  function _isEmpty(field) {
    if (field.type === 'checkbox') return !field.checked;
    if (field.tagName === 'SELECT') return !field.value || field.value === '';
    return !field.value || field.value.trim() === '';
  }

  // ── Validadores específicos ───────────────────────────────────────────────
  const VALIDATORS = {
    email: (v) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v) || 'Email inválido',
    password: (v) => v.length >= 6 || 'Mínimo de 6 caracteres',
  };

  function _validateField(field) {
    _clearFieldError(field);

    // Campo obrigatório vazio
    if (field.required && _isEmpty(field)) {
      const label = field.closest('.form-field, .form-group, div')
        ?.querySelector('label')?.textContent?.replace('*', '').trim()
        || field.placeholder || field.name || 'Campo';
      _showFieldError(field, `${label} é obrigatório`);
      return false;
    }

    // Validadores por tipo/name
    if (!_isEmpty(field)) {
      const type = field.type?.toLowerCase();
      const name = field.name?.toLowerCase();

      if (type === 'email' || name?.includes('email')) {
        const res = VALIDATORS.email(field.value);
        if (res !== true) { _showFieldError(field, res); return false; }
      }

      if (type === 'password' && field.required) {
        const res = VALIDATORS.password(field.value);
        if (res !== true) { _showFieldError(field, res); return false; }
      }

      // Confirmação de senha
      if (name?.includes('confirmar') || name?.includes('confirm')) {
        const form = field.closest('form');
        const senhaField = form?.querySelector('[name*="nova_senha"], [name*="new_password"], [name*="password"]:not([name*="confirm"]):not([name*="atual"]):not([name*="current"])');
        if (senhaField && field.value !== senhaField.value) {
          _showFieldError(field, 'As senhas não coincidem');
          return false;
        }
      }
    }

    return true;
  }

  // ── Validar formulário completo ───────────────────────────────────────────
  function _validateForm(form) {
    const fields = form.querySelectorAll('input, select, textarea');
    let valid = true;
    let firstInvalid = null;

    fields.forEach(field => {
      // Ignorar campos hidden, disabled, readonly e os do Select2 (hidden)
      if (field.type === 'hidden' || field.disabled || field.readOnly) return;
      if (field.style.display === 'none' || field.offsetParent === null) return;
      // Ignorar campos dentro de containers colapsados/ocultos
      if (field.closest('[style*="display: none"]') || field.closest('.hidden')) return;

      if (!_validateField(field)) {
        valid = false;
        if (!firstInvalid) firstInvalid = field;
      }
    });

    if (firstInvalid) {
      firstInvalid.focus();
      firstInvalid.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }

    return valid;
  }

  // ── Limpar erros ao editar ────────────────────────────────────────────────
  function _attachClearListeners(form) {
    form.querySelectorAll('input, select, textarea').forEach(field => {
      ['input', 'change'].forEach(evt => {
        field.addEventListener(evt, () => _clearFieldError(field), { passive: true });
      });
    });
  }

  // ── Interceptar submissões ────────────────────────────────────────────────
  function _attachToForm(form) {
    // Não interceptar formulários com data-no-validate
    if (form.dataset.noValidate !== undefined) return;
    // Não interceptar formulários de pesquisa (GET)
    if (form.method?.toLowerCase() === 'get') return;

    _attachClearListeners(form);

    form.addEventListener('submit', function (e) {
      if (!_validateForm(this)) {
        e.preventDefault();
        e.stopImmediatePropagation();

        // Notificação toast se disponível
        if (typeof showError === 'function') {
          showError('Preencha todos os campos obrigatórios antes de continuar.');
        } else if (typeof Swal !== 'undefined') {
          Swal.mixin({ toast: true, position: 'top-end', showConfirmButton: false, timer: 3500 })
              .fire({ icon: 'error', title: 'Preencha todos os campos obrigatórios' });
        }
      }
    });
  }

  // ── Inicialização ─────────────────────────────────────────────────────────
  function init() {
    // Formulários existentes
    document.querySelectorAll('form').forEach(_attachToForm);

    // Formulários adicionados dinamicamente (adições da DU, modais, etc.)
    const observer = new MutationObserver(mutations => {
      mutations.forEach(m => {
        m.addedNodes.forEach(node => {
          if (node.nodeType !== 1) return;
          if (node.tagName === 'FORM') _attachToForm(node);
          node.querySelectorAll?.('form').forEach(_attachToForm);
        });
      });
    });
    observer.observe(document.body, { childList: true, subtree: true });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // Expor para uso manual (ex: validar antes de AJAX)
  window.FV = {
    validateForm: _validateForm,
    validateField: _validateField,
    clearFieldError: _clearFieldError,
    showFieldError: _showFieldError,
  };

})();
