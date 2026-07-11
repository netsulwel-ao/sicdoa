/**
 * Formata um número para o padrão angolano com espaço: 1 234,56
 */
function formatNumber(value) {
    if (value === null || value === undefined || isNaN(value)) return '';
    var n = Number(value);
    var parts = n.toFixed(2).split('.');
    var intPart = parts[0];
    var decPart = parts[1];
    var groups = [];
    while (intPart.length > 3) {
        groups.unshift(intPart.slice(-3));
        intPart = intPart.slice(0, -3);
    }
    if (intPart.length > 0) groups.unshift(intPart);
    return groups.join(' ') + ',' + decPart;
}

/**
 * Converte string em formato angolano (1 234,56 ou 1.234,56) para número JS.
 * Suporta: 20000, 20 000, 20.000, 20.000,00, 20,000.00
 */
function parseNumber(str) {
    if (!str) return 0;
    var s = String(str).trim().replace(/ /g, '');
    
    // Se tem vírgula, é formato europeu (1.234.567,89)
    if (s.indexOf(',') !== -1) {
        s = s.replace(/\./g, '').replace(',', '.');
    } 
    // Se tem ponto, precisa validar se é separador de milhar ou decimal
    else if (s.indexOf('.') !== -1) {
        var parts = s.split('.');
        // Se tem múltiplos pontos OU último grupo tem 3 dígitos (milhar), remove todos
        if (parts.length > 2) {
            // Múltiplos pontos = todos são separadores de milhar
            s = s.replace(/\./g, '');
        } else if (parts.length === 2 && parts[1].length === 3) {
            // Último grupo tem 3 dígitos = é separador de milhar
            s = s.replace(/\./g, '');
        }
        // Senão, deixa como está (é decimal tipo 20.00)
    }
    
    return parseFloat(s) || 0;
}

/**
 * Aplica máscara IMask a inputs com classe .moeda (keyup tempo real).
 * Uso: <input class="moeda" type="text" inputmode="decimal" ...>
 */
document.addEventListener('DOMContentLoaded', function() {
    if (typeof IMask === 'undefined') return;

    document.querySelectorAll('.moeda').forEach(function(input) {
        if (input.disabled || input.readOnly) return;
        try {
            var useScale = input.classList.contains('moeda-inteiro') ? 0 : 2;
            IMask(input, {
                mask: Number,
                thousandsSeparator: ' ',
                radix: ',',
                mapToRadix: ['.'],
                scale: useScale,
                min: 0,
                max: 999999999.99,
                normalizeZeros: true
            });
        } catch(e) {
            // fallback silencioso se IMask falhar
        }
    });

    // Sanitizar valores formatados antes do submit
    window._sanitizarCamposMonetarios = function(form) {
        form.querySelectorAll('.moeda').forEach(function(input) {
            if (input.value) {
                var value;
                if (input.imask && input.imask.typedValue !== undefined && input.imask.typedValue !== null) {
                    value = Number(input.imask.typedValue).toFixed(2);
                } else if (input.imask && input.imask.unmaskedValue !== undefined) {
                    value = parseNumber(input.imask.unmaskedValue).toFixed(2);
                } else {
                    value = parseNumber(input.value).toFixed(2);
                }
                input.value = value;
            }
        });
    };

    document.addEventListener('submit', function(e) {
        window._sanitizarCamposMonetarios(e.target);
    });
});
