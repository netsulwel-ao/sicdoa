/**
 * autocomplete-select.js
 * Componente de autocomplete: campo de texto que filtra opções ao digitar.
 * O dropdown só aparece quando há correspondências.
 * Não abre dropdown ao clicar — apenas ao escrever.
 *
 * Uso: autocompleteSelect(selector, { ... opcoes ... })
 */
(function() {
  'use strict';

  /* ── Estilos injetados uma única vez ────────────────────────── */
  var AUTOCOMPLETE_CSS = `
<style id="autocomplete-select-styles">
.ac-wrapper  { position:relative; width:100%; }
.ac-input    { width:100%; padding:0.875rem 1rem; font-size:0.9375rem;
               border:2px solid #d1d5db; border-radius:0.5rem;
               background:#fff; color:#111827; outline:none;
               transition:border-color .2s, box-shadow .2s;
               box-sizing:border-box; height:46px; }
.ac-input:focus { border-color:#137fec; box-shadow:0 0 0 3px rgba(19,127,236,0.1); }
.ac-input.has-value { border-color:#137fec; background:#f0f7ff; }
.ac-dropdown { position:fixed !important; max-height:220px; overflow-y:auto;
               min-width:200px;
               background:#fff !important; border:2px solid #137fec !important; border-radius:0.5rem;
               box-shadow:0 10px 15px -3px rgba(0,0,0,0.1);
               z-index:999999 !important; display:none; }
.ac-option  { padding:0.625rem 1rem; cursor:pointer; font-size:0.9375rem;
              color:#111827; border-bottom:1px solid #f3f4f6;
              transition:background .15s; }
.ac-option:last-child { border-bottom:none; }
.ac-option:hover,
.ac-option.highlighted { background:#137fec; color:#fff; }
.ac-option .ac-code { font-weight:600; }
.ac-option .ac-desc { margin-left:6px; }
.ac-option .ac-tag  { float:right; font-size:11px; background:#f3f4f6;
                       color:#6b7280; padding:1px 6px; border-radius:4px; }
.ac-option:hover .ac-tag,
.ac-option.highlighted .ac-tag { background:rgba(255,255,255,0.2); color:#fff; }
.ac-no-results { padding:1.5rem 1rem; text-align:center; color:#9ca3af; font-size:0.9rem; }
/* Dark mode */
.dark .ac-input { background:#374151; border-color:#4b5563; color:#f3f4f6; }
.dark .ac-input:focus { border-color:#137fec; }
.dark .ac-input.has-value { background:#1e3a5f; border-color:#137fec; }
.dark .ac-dropdown { background:#374151; border-color:#137fec; }
.dark .ac-option { color:#f3f4f6; border-color:#4b5563; }
.dark .ac-option:hover,
.dark .ac-option.highlighted { background:#137fec; }
.dark .ac-option .ac-tag { background:#4b5563; color:#d1d5db; }
</style>`;

  if (!document.getElementById('autocomplete-select-styles')) {
    document.head.insertAdjacentHTML('beforeend', AUTOCOMPLETE_CSS);
  }

  /* ── Componente ─────────────────────────────────────────────── */
  function autocompleteSelect(el, opts) {
    if (!el || el.dataset.acInit) return;
    el.dataset.acInit = '1';

    opts = opts || {};
    var placeholder  = opts.placeholder  || el.placeholder || 'Digite para pesquisar...';
    var onSelect     = opts.onSelect     || null;
    var templateFn   = opts.templateResult || null;

    var originalSelect = (el.tagName === 'SELECT') ? el : null;

    /* ── Container ────────────────────────────────────────────── */
    var wrapper = document.createElement('div');
    wrapper.className = 'ac-wrapper';

    var input = document.createElement('input');
    input.type = 'text';
    input.className = 'ac-input';
    input.placeholder = placeholder;
    input.autocomplete = 'off';
    input.spellcheck = false;

    var dropdown = document.createElement('div');
    dropdown.className = 'ac-dropdown';
    document.body.appendChild(dropdown); /* Fora de qualquer container para não ser cortado */

    wrapper.appendChild(input);

    if (originalSelect) {
      originalSelect.style.display = 'none';
      originalSelect.parentNode.insertBefore(wrapper, originalSelect.nextSibling);
    } else {
      el.parentNode.insertBefore(wrapper, el.nextSibling);
    }

    var _options = [];  // { value, label, data? }
    var _ajax = opts.ajax || null;

    /* ── Posicionar dropdown sobre o input ────────────────────── */
    function positionDropdown() {
      var rect = input.getBoundingClientRect();
      dropdown.style.top  = (rect.bottom + 4) + 'px';
      dropdown.style.left = rect.left + 'px';
      dropdown.style.width = rect.width + 'px';
    }

    /* Reposicionar em scroll/resize se o dropdown estiver visível */
    function repositionOnScroll() {
      if (dropdown.style.display !== 'none') {
        positionDropdown();
      }
    }
    if (window.addEventListener) {
      window.addEventListener('scroll', repositionOnScroll, true);
      window.addEventListener('resize', repositionOnScroll);
    }

    /* ── Carregar opções do select original ───────────────────── */
    function loadOptions() {
      _options = [];
      if (!originalSelect) return;
      var opt, label;
      for (var i = 0; i < originalSelect.options.length; i++) {
        opt = originalSelect.options[i];
        if (!opt.value) continue;
        label = opt.text || opt.value;
        _options.push({ value: opt.value, label: label, data: (opt.dataset || {}) });
      }
    }
    loadOptions();

    /* ── Observar mutações no select (quando API carrega opções) ── */
    if (originalSelect && window.MutationObserver) {
      var obs = new MutationObserver(function() {
        loadOptions();
        // Se o select tem um valor seleccionado após refresh, actualizar input
        if (originalSelect.value) {
          for (var k = 0; k < _options.length; k++) {
            if (_options[k].value === originalSelect.value) {
              setValue(_options[k].value, _options[k].label);
              break;
            }
          }
        }
      });
      obs.observe(originalSelect, { childList: true, subtree: true, attributes: false });
    }

    /* ── Filtrar (local ou AJAX) ──────────────────────────────── */
    function filterOptions(query, callback) {
      if (_ajax) {
        _ajax(query, function(results) {
          _options = results || [];
          callback(_options);
        });
        return;
      }
      if (!query.trim()) { callback([]); return; }
      var q = query.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
      var results = [];
      for (var i = 0; i < _options.length; i++) {
        var o = _options[i];
        var label = o.label.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
        var val   = o.value.toLowerCase();
        if (val.indexOf(q) !== -1 || label.indexOf(q) !== -1) {
          results.push(o);
        }
      }
      callback(results);
    }

    /* ── Renderizar dropdown ──────────────────────────────────── */
    function renderDropdown(results) {
      dropdown.innerHTML = '';
      dropdown._acResults = results;

      positionDropdown();

      if (results.length === 0) {
        dropdown.innerHTML = '<div class="ac-no-results">Nenhum resultado encontrado</div>';
        dropdown.style.display = 'block';
        positionDropdown();
        return;
      }
      results.forEach(function(o, idx) {
        var item = document.createElement('div');
        item.className = 'ac-option';
        item.dataset.value = o.value;
        item.dataset.index = idx;

        var code = o.value;
        var desc = o.label;
        var dashIdx = o.label.indexOf(' - ');
        if (dashIdx !== -1) {
          code = o.label.substring(0, dashIdx);
          desc = o.label.substring(dashIdx + 3);
        }

        if (templateFn) {
          item.innerHTML = templateFn(o, code, desc);
        } else {
          item.innerHTML = '<span class="ac-code">' + escapeHtml(code) + '</span>' +
                           '<span class="ac-desc">' + escapeHtml(desc) + '</span>';
        }

        item.addEventListener('mousedown', function(e) {
          e.preventDefault();
          selectOption(o);
        });
        dropdown.appendChild(item);
      });
      dropdown.style.display = 'block';
      positionDropdown();
    }

    /* ── Selecionar ───────────────────────────────────────────── */
    function selectOption(o) {
      var displayLabel = o.label;
      var dashIdx = o.label.indexOf(' - ');
      var shortLabel = dashIdx !== -1 ? o.label.substring(0, dashIdx) : o.label;

      input.value = shortLabel;
      input.dataset.value = o.value;
      input.classList.add('has-value');

      if (originalSelect) {
        originalSelect.value = o.value;
        originalSelect.dispatchEvent(new Event('change', { bubbles: true }));
      }

      dropdown.style.display = 'none';

      if (typeof onSelect === 'function') {
        onSelect(o);
      }
    }

    /* ── Eventos do input ─────────────────────────────────────── */
    var debounceTimer = null;

    input.addEventListener('input', function() {
      var val = this.value;
      delete this.dataset.value;
      this.classList.remove('has-value');

      if (originalSelect) {
        originalSelect.value = '';
      }

      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(function() {
        filterOptions(val, function(results) {
          renderDropdown(results);
        });
      }, 150);
    });

    input.addEventListener('focus', function() {
      /* Mostra todas as opções ao clicar no campo */
      var val = this.value;
      if (!val.trim()) {
        if (_ajax) {
          /* AJAX: buscar resultados iniciais com termo vazio */
          _ajax('', function(results) {
            if (results && results.length > 0) {
              renderDropdown(results);
            }
          });
          return;
        }
        if (_options.length === 0) return; /* Ainda a carregar */
        renderDropdown(_options);
      } else {
        filterOptions(val, function(results) {
          renderDropdown(results);
        });
      }
    });

    input.addEventListener('blur', function() {
      setTimeout(function() {
        dropdown.style.display = 'none';
        /* Se não selecionou nada e tem valor, limpar */
        if (!input.dataset.value && input.value) {
          input.value = '';
          input.classList.remove('has-value');
        }
      }, 200);
    });

    input.addEventListener('keydown', function(e) {
      var items = dropdown.querySelectorAll('.ac-option');
      var highlighted = dropdown.querySelector('.ac-option.highlighted');
      var idx = -1;
      if (highlighted) {
        idx = parseInt(highlighted.dataset.index);
      }

      if (e.key === 'ArrowDown') {
        e.preventDefault();
        if (items.length === 0) return;
        var nextIdx = (idx + 1) % items.length;
        if (highlighted) highlighted.classList.remove('highlighted');
        items[nextIdx].classList.add('highlighted');
        items[nextIdx].scrollIntoView({ block: 'nearest' });
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        if (items.length === 0) return;
        var prevIdx = (idx <= 0) ? items.length - 1 : idx - 1;
        if (highlighted) highlighted.classList.remove('highlighted');
        items[prevIdx].classList.add('highlighted');
        items[prevIdx].scrollIntoView({ block: 'nearest' });
      } else if (e.key === 'Enter') {
        if (highlighted) {
          e.preventDefault();
          var idx = parseInt(highlighted.dataset.index);
          if (_ajax && dropdown._acResults) {
            var opt = dropdown._acResults[idx];
            if (opt) selectOption(opt);
          } else {
            var opt = _options[idx];
            if (opt) selectOption(opt);
          }
        } else if (items.length === 1) {
          e.preventDefault();
          if (_ajax && dropdown._acResults) {
            var opt2 = dropdown._acResults[0];
            if (opt2) selectOption(opt2);
          } else {
            var opt2 = _options[0];
            if (opt2) selectOption(opt2);
          }
        }
      } else if (e.key === 'Escape') {
        dropdown.style.display = 'none';
      }
    });

    /* ── Set value programmatically ───────────────────────────── */
    function setValue(val, label) {
      if (!val) {
        input.value = '';
        input.dataset.value = '';
        input.classList.remove('has-value');
        if (originalSelect) { originalSelect.value = ''; }
        return;
      }
      input.value = label || val;
      input.dataset.value = val;
      input.classList.add('has-value');
      if (originalSelect) { originalSelect.value = val; }
    }

    /* Preencher se select já tiver um valor */
    if (originalSelect && originalSelect.value) {
      for (var i = 0; i < _options.length; i++) {
        if (_options[i].value === originalSelect.value) {
          setValue(_options[i].value, _options[i].label);
          break;
        }
      }
    }

    /* ── API pública no elemento wrapper ──────────────────────── */
    wrapper._ac = {
      setValue: setValue,
      refresh: loadOptions,
      input: input,
      dropdown: dropdown,
      selectOption: selectOption
    };

    return wrapper;
  }

  /* ── Helper ─────────────────────────────────────────────────── */
  function escapeHtml(str) {
    if (!str) return '';
    var d = document.createElement('div');
    d.textContent = str;
    return d.innerHTML;
  }

  /* ── Export ─────────────────────────────────────────────────── */
  window.autocompleteSelect = autocompleteSelect;
  window.escapeHtml = escapeHtml;

  /* ── Auto-init para elementos com data-ac ────────────────────── */
  document.addEventListener('DOMContentLoaded', function() {
    document.querySelectorAll('[data-ac]').forEach(function(el) {
      autocompleteSelect(el);
    });
  });

})();
