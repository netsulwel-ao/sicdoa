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
 */
function parseNumber(str) {
    if (!str) return 0;
    var s = String(str).trim().replace(/ /g, '');
    if (s.indexOf(',') !== -1) {
        s = s.replace(/\./g, '').replace(',', '.');
    } else if (s.indexOf('.') !== -1 && s.split('.').length > 2) {
        s = s.replace(/\./g, '');
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
        try {
            IMask(input, {
                mask: Number,
                thousandsSeparator: ' ',
                radix: ',',
                mapToRadix: ['.'],
                scale: 2,
                min: 0,
                max: 999999999.99,
                normalizeZeros: true
            });
        } catch(e) {
            // fallback silencioso se IMask falhar
        }
    });

    // Sanitizar valores formatados antes do submit
    document.addEventListener('submit', function(e) {
        var form = e.target;
        form.querySelectorAll('.moeda').forEach(function(input) {
            if (input.value) {
                input.value = parseNumber(input.value);
            }
        });
    });
});
