let currentStep = 1;
const totalSteps = 4;

// ============================================================
// NOTIFICAÇÕES — usa SweetAlert2 Toast se disponível
// ============================================================
function showInfo(message) {
  if (typeof window.showInfo === 'function' && window.showInfo !== showInfo) { window.showInfo(message); return; }
  if (typeof Swal !== 'undefined') {
    Swal.mixin({ toast:true, position:'top-end', showConfirmButton:false, timer:3000, timerProgressBar:true })
        .fire({ icon:'info', title: message });
  } else { console.log('INFO:', message); }
}

function showSuccess(message) {
  if (typeof Swal !== 'undefined') {
    Swal.mixin({ toast:true, position:'top-end', showConfirmButton:false, timer:3000, timerProgressBar:true })
        .fire({ icon:'success', title: message });
  } else { console.log('SUCCESS:', message); }
}

function showError(message) {
  if (typeof Swal !== 'undefined') {
    Swal.mixin({ toast:true, position:'top-end', showConfirmButton:false, timer:4000, timerProgressBar:true })
        .fire({ icon:'error', title: message });
  } else { console.error('ERROR:', message); }
}

function showWarning(message) {
  if (typeof Swal !== 'undefined') {
    Swal.mixin({ toast:true, position:'top-end', showConfirmButton:false, timer:3500, timerProgressBar:true })
        .fire({ icon:'warning', title: message });
  } else { console.warn('WARNING:', message); }
}

// Navegação entre passos
function nextStep() {
  if (validateCurrentStep()) {
    if (currentStep < totalSteps) {
      currentStep++;
      updateStep();
      
      // Se chegou no passo 4 (Finalizar), calcular taxas automaticamente
      if (currentStep === 4) {
        if (typeof calcularValoresConvertidos === 'function') {
          calcularValoresConvertidos().then(() => calcularTaxas());
        } else {
          calcularTaxas();
        }
        if (typeof atualizarResumo === 'function') atualizarResumo();
      }
    }
  }
}

function previousStep() {
  if (currentStep > 1) {
    currentStep--;
    updateStep();
  }
}

function updateStep() {
  // Atualizar formulário
  document.querySelectorAll('.form-step-modern').forEach(step => {
    step.classList.remove('active');
  });
  const currentStepElement = document.querySelector(`.form-step-modern[data-step="${currentStep}"]`);
  if (currentStepElement) {
    currentStepElement.classList.add('active');
  }

  // Atualizar indicadores modernos
  document.querySelectorAll('.step-item').forEach((step, index) => {
    step.classList.remove('active', 'completed');
    if (index + 1 < currentStep) {
      step.classList.add('completed');
    } else if (index + 1 === currentStep) {
      step.classList.add('active');
    }
  });

  // Atualizar botões
  const btnPrevious = document.getElementById('btnPrevious');
  const btnNext = document.getElementById('btnNext');
  const btnSubmit = document.getElementById('btnSubmit');
  
  if (btnPrevious) btnPrevious.style.display = currentStep === 1 ? 'none' : 'inline-flex';
  if (btnNext) btnNext.style.display = currentStep === totalSteps ? 'none' : 'inline-flex';
  if (btnSubmit) btnSubmit.style.display = currentStep === totalSteps ? 'inline-flex' : 'none';

  // Atualizar progresso
  const progress = (currentStep / totalSteps) * 100;
  const progressBar = document.getElementById('progressBar');
  const progressLineFill = document.getElementById('progressLineFill');
  const progressPercent = document.getElementById('progressPercent');
  const currentStepNum = document.getElementById('currentStepNum');
  const currentStepDisplay = document.getElementById('currentStepDisplay');

  if (progressBar) progressBar.style.width = progress + '%';
  if (progressLineFill) progressLineFill.style.width = progress + '%';
  if (progressPercent) progressPercent.textContent = Math.round(progress);
  if (currentStepNum) currentStepNum.textContent = currentStep;
  if (currentStepDisplay) currentStepDisplay.textContent = currentStep;

  // Scroll to top suavemente
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

/**
 * Navegar directamente para um step clicando no indicador de progresso.
 * Permite ir para qualquer step sem validação (útil para revisão).
 */
function goToStep(step) {
  if (step < 1 || step > totalSteps) return;
  currentStep = step;
  updateStep();
  if (currentStep === 4) {
    // Calcular taxas ao chegar no passo final
    if (typeof calcularValoresConvertidos === 'function') {
      calcularValoresConvertidos().then(() => calcularTaxas());
    } else {
      calcularTaxas();
    }
    if (typeof atualizarResumo === 'function') atualizarResumo();
  }
}

function _fieldLabel(field) {
  const labelEl = field.closest('.form-field')?.querySelector('label');
  if (labelEl) {
    const txt = labelEl.textContent.replace(/[^a-zA-ZÀ-ÿ0-9\s]/g, '').trim();
    if (txt) return txt;
  }
  const ph = field.placeholder?.trim();
  if (ph) return ph;
  if (field.name) {
    const m = field.name.match(/adicao\[\d+\]\[(.+)\]/);
    return m ? m[1] : field.name;
  }
  return 'Campo obrigatório';
}

function validateCurrentStep() {
  const currentStepElement = document.querySelector(`.form-step-modern[data-step="${currentStep}"]`);
  if (!currentStepElement) return true;
  
  const requiredFields = currentStepElement.querySelectorAll('[required]');
  
  for (let field of requiredFields) {
    if (field.offsetParent === null) continue;
    if (typeof field.value !== 'string' || !field.value.trim()) {
      showError(`Campo obrigatório: ${_fieldLabel(field)}`);
      field.focus();
      field.classList.add('is-invalid');
      return false;
    }
    field.classList.remove('is-invalid');
  }

  const acInputs = currentStepElement.querySelectorAll('.ac-input');
  for (let field of acInputs) {
    const wrapper = field.closest('.ac-wrapper');
    if (!wrapper) continue;
    const prev = wrapper.previousElementSibling;
    if (prev && prev.hasAttribute('required')) {
      const val = field.dataset.value || prev.value;
      if (!val || !val.trim()) {
        showError(`Campo obrigatório: ${_fieldLabel(prev)}`);
        field.focus();
        field.classList.remove('has-value');
        return false;
      }
    }
  }

  return true;
}

// Função para alternar colapso de seções
function toggleCollapse(headerElement) {
  const card = headerElement.closest('.form-card');
  const content = card.querySelector('.collapse-content');
  const icon = headerElement.querySelector('.collapse-icon');
  
  if (card.classList.contains('collapsed')) {
    card.classList.remove('collapsed');
    if (icon) { icon.classList.remove('fa-chevron-up'); icon.classList.add('fa-chevron-down'); }
  } else {
    card.classList.add('collapsed');
    if (icon) { icon.classList.remove('fa-chevron-down'); icon.classList.add('fa-chevron-up'); }
  }
}

// Função para consultar vinhetas
function consultarVinhetas() {
  const vinhetaInput = document.getElementById('vinheta_input');
  const vinhetasDiv = document.getElementById('vinhetas_disponiveis');
  const vinhetaSelect = document.getElementById('vinheta_select');
  
  if (!vinhetaInput || !vinhetasDiv || !vinhetaSelect) return;
  
  const iniciais = vinhetaInput.value.trim().toUpperCase();
  
  if (!iniciais) {
    showError('Digite as iniciais da vinheta para consultar');
    return;
  }
  
  // Simulação de consulta de vinhetas disponíveis
  const vinhetasDisponiveis = [
    { codigo: 'VIN001', descricao: 'Vinheta Importação 001 - Disponível' },
    { codigo: 'VIN002', descricao: 'Vinheta Importação 002 - Disponível' },
    { codigo: 'VIN003', descricao: 'Vinheta Exportação 003 - Disponível' }
  ].filter(v => v.codigo.startsWith(iniciais));
  
  if (vinhetasDisponiveis.length > 0) {
    vinhetaSelect.innerHTML = '<option value="">Selecione uma vinheta disponível...</option>';
    vinhetasDisponiveis.forEach(vinheta => {
      const option = document.createElement('option');
      option.value = vinheta.codigo;
      option.textContent = vinheta.descricao;
      vinhetaSelect.appendChild(option);
    });
    vinhetasDiv.classList.remove('hidden');
    showSuccess(`${vinhetasDisponiveis.length} vinheta(s) encontrada(s)`);
  } else {
    showWarning('Nenhuma vinheta disponível encontrada com essas iniciais');
    vinhetasDiv.classList.add('hidden');
  }
}

function selecionarVinheta() {
  const vinhetaSelect = document.getElementById('vinheta_select');
  const vinhetaInput = document.getElementById('vinheta_input');
  
  if (vinhetaSelect && vinhetaInput && vinhetaSelect.value) {
    vinhetaInput.value = vinhetaSelect.value;
    vinhetaInput.setAttribute('readonly', 'true');
    showSuccess('Vinheta selecionada e bloqueada no sistema');
  }
}

// Função para atualizar campos baseados no destinatário
function atualizarCamposDestinatario() {
  // Esta função é chamada quando o regime aduaneiro muda
  // Redireciona para a função principal
  atualizarCamposRegime();
  atualizarDestinoRegime();
}

// Função para consultar NIF do exportador
function consultarNIF() {
  console.log('consultarNIF() chamada - usando API dinâmica');
  const nifInput = document.getElementById('exportador_codigo');
  const nifResultDiv = document.getElementById('nif_consulta_status');
  
  if (!nifInput) return;
  
  const nif = nifInput.value.trim();
  console.log('NIF digitado:', nif);
  
  if (!nif) {
    showError('Digite o NIF para consultar');
    return;
  }
  
  // Consulta real via API
  showInfo('Consultando NIF...');
  console.log('Fazendo requisição para API...');
  
  fetch(`/du/api/consultar-nif/?nif=${encodeURIComponent(nif)}`)
    .then(response => {
      console.log('Status da resposta:', response.status);
      return response.json();
    })
    .then(data => {
      console.log('Dados recebidos da API:', data);
      
      if (data.encontrado) {
        const dados = data.dados;
        console.log('Dados do cliente:', dados);
        
        // Preencher campos automaticamente
        const nomeField = document.getElementById('exportador_nome');
        const enderecoField = document.getElementById('exportador_endereco');
        
        if (nomeField) {
          nomeField.value = dados.nome;
          console.log('Nome preenchido:', dados.nome);
        }
        if (enderecoField) {
          enderecoField.value = dados.endereco;
          console.log('Endereço preenchido:', dados.endereco);
        }
        
        // Limpar e esconder o container de resultados
        if (nifResultDiv) {
          nifResultDiv.innerHTML = '';
          nifResultDiv.classList.add('hidden');
        }
        
        showSuccess('Cliente encontrado e dados preenchidos');
      } else {
        // Mostrar sugestões ou mensagem de erro
        if (data.sugestoes && data.sugestoes.length > 0) {
          mostrarSugestoes(data.sugestoes, nifResultDiv);
        } else {
          mostrarMensagemErro(data.mensagem, nifResultDiv);
        }
      }
    })
    .catch(error => {
      console.error('Erro ao consultar NIF:', error);
      showError('Erro ao consultar NIF. Tente novamente.');
      if (nifResultDiv) {
        nifResultDiv.innerHTML = '';
        nifResultDiv.classList.add('hidden');
      }
    });
}

function mostrarMensagemErro(mensagem, container) {
  container.innerHTML = `
    <div class="bg-red-50 border border-red-200 rounded-lg p-4 mt-2">
      <div class="flex items-start gap-2">
        <i class="fas fa-times-circle text-red-600 text-base mt-0.5"></i>
        <div>
          <p class="text-sm font-semibold text-red-800">NIF Não Encontrado</p>
          <p class="text-xs text-red-700 mt-1">${mensagem}</p>
        </div>
      </div>
    </div>
  `;
  container.classList.remove('hidden');
  showError(mensagem);
}

function mostrarSugestoes(sugestoes, container) {
  console.log('Mostrando sugestões:', sugestoes);
  
  let html = `
    <div class="bg-blue-50 border border-blue-200 rounded-lg p-3 mt-2">
      <h4 class="font-medium text-blue-800 mb-2">Sugestões de Clientes</h4>
      <div class="space-y-2">
  `;
  
  sugestoes.forEach(cliente => {
    html += `
      <div class="bg-white border border-blue-100 rounded p-2 cursor-pointer hover:bg-blue-50 transition-colors" 
           onclick="selecionarSugestao('${cliente.nif}', '${cliente.nome.replace(/'/g, "\\'")}', '${cliente.localizacao.replace(/'/g, "\\'")}')">
        <p class="text-sm font-medium text-gray-900">${cliente.nome}</p>
        <p class="text-xs text-gray-600">NIF: ${cliente.nif}</p>
        <p class="text-xs text-gray-500">${cliente.localizacao}</p>
      </div>
    `;
  });
  
  html += `
      </div>
      <p class="text-xs text-blue-600 mt-2">Clique em um cliente para selecionar</p>
    </div>
  `;
  
  container.innerHTML = html;
  container.classList.remove('hidden');
}

function selecionarSugestao(nif, nome, localizacao) {
  console.log('Sugestão selecionada:', nif, nome);
  
  // Preencher campos
  const nifField = document.getElementById('exportador_codigo');
  const nomeField = document.getElementById('exportador_nome');
  const enderecoField = document.getElementById('exportador_endereco');
  
  if (nifField) nifField.value = nif;
  if (nomeField) nomeField.value = nome;
  if (enderecoField) enderecoField.value = localizacao;
  
  // Limpar resultados
  const nifResultDiv = document.getElementById('nif_consulta_status');
  if (nifResultDiv) {
    nifResultDiv.innerHTML = `
      <div class="bg-green-50 border border-green-200 rounded-lg p-3 mt-2">
        <h4 class="font-medium text-green-800 mb-1">Cliente Selecionado</h4>
        <p class="text-sm"><strong>Nome:</strong> ${nome}</p>
        <p class="text-sm"><strong>NIF:</strong> ${nif}</p>
      </div>
    `;
  }
  
  showSuccess('Cliente selecionado com sucesso!');
}

function getCookie(name) {
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

// Função para consultar NIF do destinatário
function consultarNIFDestinatario() {
  const nifInput = document.getElementById('destinatario_nif');
  const nifResultDiv = document.getElementById('nif_destinatario_status');
  
  if (!nifInput) return;
  
  const nif = nifInput.value.trim();
  
  if (!nif) {
    showError('Digite o NIF para consultar');
    return;
  }
  
  // Consulta real via API
  showInfo('Consultando NIF do destinatário...');
  
  fetch(`/du/api/consultar-nif/?nif=${encodeURIComponent(nif)}`)
    .then(response => response.json())
    .then(data => {
      if (data.encontrado) {
        const dados = data.dados;
        
        // Preencher campos automaticamente
        const nomeField = document.getElementById('destinatario_nome');
        const enderecoField = document.getElementById('destinatario_endereco');
        const telefoneField = document.getElementById('destinatario_telefone');
        
        if (nomeField) nomeField.value = dados.nome;
        if (enderecoField) enderecoField.value = dados.endereco;
        if (telefoneField && dados.telefone) telefoneField.value = dados.telefone;
        
        // Limpar e esconder o container de resultados
        if (nifResultDiv) {
          nifResultDiv.innerHTML = '';
          nifResultDiv.classList.add('hidden');
        }
        
        showSuccess('Destinatário encontrado e dados preenchidos');
      } else {
        // Mostrar sugestões ou mensagem de erro
        if (data.sugestoes && data.sugestoes.length > 0) {
          mostrarSugestoes(data.sugestoes, nifResultDiv);
        } else {
          mostrarMensagemErro(data.mensagem, nifResultDiv);
        }
      }
    })
    .catch(error => {
      console.error('Erro ao consultar NIF do destinatário:', error);
      showError('Erro ao consultar NIF. Tente novamente.');
      if (nifResultDiv) {
        nifResultDiv.innerHTML = '';
        nifResultDiv.classList.add('hidden');
      }
    });
}

// Função para consultar código pautal
// ==================== PESQUISA PAUTA ADUANEIRA (API) ====================
const PAUTA_API_URL = 'https://api-sic-fields.netsulwel.tech/pautas';
let _pautaCache = null;        // cache em memória
let _pautaCarregando = false;  // flag para evitar chamadas paralelas
let _pautaCallbacks = [];      // fila de callbacks aguardando o carregamento

async function carregarPautas() {
  // Se já está em cache, retornar imediatamente
  if (_pautaCache) return _pautaCache;

  // Se já está a carregar, aguardar na fila
  if (_pautaCarregando) {
    return new Promise(resolve => _pautaCallbacks.push(resolve));
  }

  _pautaCarregando = true;

  try {
    const res = await fetch(PAUTA_API_URL);
    if (!res.ok) throw new Error('Erro ao carregar pautas: ' + res.status);
    _pautaCache = await res.json();

    // Notificar todos os que estavam à espera
    _pautaCallbacks.forEach(cb => cb(_pautaCache));
    _pautaCallbacks = [];

    console.log(`✅ Pauta aduaneira carregada: ${_pautaCache.length} itens`);
    return _pautaCache;
  } catch (e) {
    console.error('❌ Falha ao carregar pauta aduaneira:', e);
    _pautaCallbacks.forEach(cb => cb([]));
    _pautaCallbacks = [];
    return [];
  } finally {
    _pautaCarregando = false;
  }
}

/**
 * Pré-carrega a pauta aduaneira em background assim que a página carrega.
 * Mostra indicador visual de progresso.
 */
function preCarregarPauta() {
  // Criar indicador visual discreto no canto inferior esquerdo
  const indicador = document.createElement('div');
  indicador.id = '_pauta_loading_indicator';
  indicador.style.cssText = [
    'position:fixed', 'bottom:16px', 'left:16px',
    'background:#1e293b', 'color:#94a3b8',
    'padding:8px 14px', 'border-radius:10px',
    'font-size:0.75rem', 'z-index:9998',
    'display:flex', 'align-items:center', 'gap:8px',
    'box-shadow:0 2px 12px rgba(0,0,0,0.25)',
    'transition:opacity 0.4s',
  ].join(';');
  indicador.innerHTML = `
    <span style="display:inline-block;width:10px;height:10px;border-radius:50%;
      border:2px solid #64748b;border-top-color:#38bdf8;
      animation:_pautaSpin 0.8s linear infinite;"></span>
    A carregar pauta aduaneira...
  `;

  // Injetar keyframe de animação uma única vez
  if (!document.getElementById('_pauta_spin_style')) {
    const style = document.createElement('style');
    style.id = '_pauta_spin_style';
    style.textContent = '@keyframes _pautaSpin { to { transform: rotate(360deg); } }';
    document.head.appendChild(style);
  }

  document.body.appendChild(indicador);

  carregarPautas().then(pautas => {
    if (pautas.length > 0) {
      indicador.style.background = '#14532d';
      indicador.style.color = '#86efac';
      indicador.innerHTML = `
        <span style="font-size:14px;">✓</span>
        Pauta pronta (${pautas.length} itens)
      `;
    } else {
      indicador.style.background = '#7f1d1d';
      indicador.style.color = '#fca5a5';
      indicador.innerHTML = `
        <span style="font-size:14px;">✗</span>
        Erro ao carregar pauta
      `;
    }
    // Desaparecer após 2.5 segundos
    setTimeout(() => {
      indicador.style.opacity = '0';
      setTimeout(() => indicador.remove(), 400);
    }, 2500);
  });
}

/**
 * Inicializa o autocomplete de código pautal num input específico.
 * @param {HTMLInputElement} inputEl  - o campo de input
 * @param {number|string} n           - índice da adição (para encontrar campos relacionados)
 */
function initPautaSearch(inputEl, n) {
  if (!inputEl || inputEl._pautaInit) return;
  inputEl._pautaInit = true;

  // Criar dropdown
  const wrapper = inputEl.closest('.input-group') || inputEl.parentElement;
  wrapper.style.position = 'relative';

  const dropdown = document.createElement('ul');
  dropdown.className = 'pauta-dropdown';
  dropdown.style.cssText = `
    display:none; position:absolute; top:100%; left:0; right:0; z-index:9999;
    background:#fff; border:1px solid #d1d5db; border-radius:8px;
    max-height:260px; overflow-y:auto; margin:2px 0; padding:0;
    box-shadow:0 4px 16px rgba(0,0,0,.12); list-style:none;
  `;
  wrapper.appendChild(dropdown);

  let debounceTimer;

  inputEl.addEventListener('input', () => {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => pesquisarPauta(inputEl, dropdown, n), 280);
  });

  inputEl.addEventListener('keydown', (e) => {
    const items = dropdown.querySelectorAll('li[data-idx]');
    const active = dropdown.querySelector('li.pauta-active');
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      const next = active ? active.nextElementSibling : items[0];
      if (next) { active?.classList.remove('pauta-active'); next.classList.add('pauta-active'); next.scrollIntoView({block:'nearest'}); }
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      const prev = active?.previousElementSibling;
      if (prev) { active.classList.remove('pauta-active'); prev.classList.add('pauta-active'); prev.scrollIntoView({block:'nearest'}); }
    } else if (e.key === 'Enter' && active) {
      e.preventDefault();
      active.click();
    } else if (e.key === 'Escape') {
      fecharDropdownPauta(dropdown);
    }
  });

  document.addEventListener('click', (e) => {
    if (!wrapper.contains(e.target)) fecharDropdownPauta(dropdown);
  });
}

async function pesquisarPauta(inputEl, dropdown, n) {
  const termo = inputEl.value.trim();
  if (termo.length < 2) { fecharDropdownPauta(dropdown); return; }

  dropdown.innerHTML = '<li style="padding:10px 14px;color:#6b7280;font-size:13px;">A carregar...</li>';
  dropdown.style.display = 'block';

  const pautas = await carregarPautas();
  if (!pautas.length) {
    dropdown.innerHTML = '<li style="padding:10px 14px;color:#ef4444;font-size:13px;">Erro ao carregar pauta aduaneira</li>';
    return;
  }

  const termoLower = termo.toLowerCase().replace(/\./g, '');
  const resultados = pautas.filter(p =>
    String(p.codigo_sh).replace(/\./g, '').includes(termoLower) ||
    (p.descricao_mercadoria || '').toLowerCase().includes(termoLower)
  ).slice(0, 40);

  if (!resultados.length) {
    dropdown.innerHTML = '<li style="padding:10px 14px;color:#6b7280;font-size:13px;">Nenhum resultado encontrado</li>';
    return;
  }

  dropdown.innerHTML = '';
  resultados.forEach((p, idx) => {
    const li = document.createElement('li');
    li.dataset.idx = idx;
    li.style.cssText = 'padding:9px 14px;cursor:pointer;border-bottom:1px solid #f3f4f6;font-size:13px;';
    li.innerHTML = `
      <span style="font-weight:600;color:#003366;">${p.codigo_sh}</span>
      <span style="color:#374151;margin-left:8px;">${p.descricao_mercadoria || ''}</span>
      <span style="float:right;color:#6b7280;font-size:11px;">${p.unidade_medida || ''}</span>
    `;
    li.addEventListener('mouseenter', () => {
      dropdown.querySelectorAll('li').forEach(el => el.classList.remove('pauta-active'));
      li.classList.add('pauta-active');
      li.style.background = '#eff6ff';
    });
    li.addEventListener('mouseleave', () => { li.style.background = ''; });
    li.addEventListener('click', () => selecionarPauta(p, inputEl, dropdown, n));
    dropdown.appendChild(li);
  });
}

function selecionarPauta(pauta, inputEl, dropdown, n) {
  // Preencher o campo com o codigo_sh
  inputEl.value = pauta.codigo_sh;
  fecharDropdownPauta(dropdown);

  // Preencher campos relacionados na adição n
  const unidadeField = document.getElementById(`unidade_pauta_${n}`) || document.getElementById('unidade_pauta');
  const quantidadeField = document.getElementById(`quantidade_${n}`) || document.getElementById('quantidade');
  const descricaoField = document.getElementById(`descricao_mercadoria_${n}`) || document.getElementById('descricao_mercadoria');

  if (unidadeField) unidadeField.value = pauta.unidade_medida || '';

  if (quantidadeField) {
    if (pauta.unidade_medida === 'KG') {
      quantidadeField.setAttribute('readonly', 'true');
      quantidadeField.value = '';
      quantidadeField.placeholder = 'Bloqueado (unidade KG)';
      quantidadeField.classList.add('calc-field');
    } else {
      quantidadeField.removeAttribute('readonly');
      quantidadeField.placeholder = 'Digite a quantidade';
      quantidadeField.classList.remove('calc-field');
    }
  }

  if (descricaoField && !descricaoField.value) {
    descricaoField.value = pauta.descricao_mercadoria || '';
  }

  // Guardar dados da pauta no input para uso nos cálculos
  inputEl.dataset.direito = pauta.direito_importacao ?? 0;
  inputEl.dataset.iec = pauta.direito_consumo ?? 0;
  inputEl.dataset.iva = pauta.iva ?? 14;

  // Disparar evento de mudança para atualizar subtítulo
  inputEl.dispatchEvent(new Event('change'));

  // Atualizar subtítulo da adição se função disponível
  if (typeof atualizarSubtituloAdicao === 'function') {
    atualizarSubtituloAdicao(n);
  }

  // Atualizar descrição hint
  const descHint = document.getElementById(`pauta_desc_${n}`);
  if (descHint) descHint.textContent = pauta.descricao_mercadoria || '';

  showSuccess(`Pauta selecionada: ${pauta.codigo_sh} — ${pauta.descricao_mercadoria}`);
}

function fecharDropdownPauta(dropdown) {
  if (dropdown) dropdown.style.display = 'none';
}

// Função legada mantida para compatibilidade com botão "Consultar" estático
function consultarCodigoPautal() {
  // Tentar encontrar o input ativo de código pautal
  const inputAtivo = document.activeElement?.closest('.input-group')?.querySelector('[id^="codigo_pautal"]')
    || document.getElementById('codigo_pautal');
  if (inputAtivo) {
    const dropdown = inputAtivo.closest('.input-group')?.querySelector('.pauta-dropdown');
    if (dropdown) {
      pesquisarPauta(inputAtivo, dropdown, inputAtivo.id.replace('codigo_pautal_', '') || '');
    }
  }
}

// Função para preencher campos automáticos da secção Estância de Destino e Local
function atualizarDestinoRegime() {
  const regimeSelect = document.getElementById('regime_aduaneiro');
  const paisDestinoAuto = document.getElementById('pais_destino_auto');
  const estanciaDestino = document.getElementById('estancia_destino');
  const localCampo54 = document.getElementById('local_campo54');
  const dataCampo54 = document.getElementById('data_campo54');
  const estanciaSelect = document.getElementById('estancia');

  if (!regimeSelect) return;
  const regime = regimeSelect.value;

  // Data atual
  if (dataCampo54 && !dataCampo54.value) {
    dataCampo54.value = new Date().toISOString().split('T')[0];
  }

  if (regime.startsWith('IM')) {
    // Importação → Angola, tudo readonly
    if (paisDestinoAuto) {
      paisDestinoAuto.value = 'AO - Angola';
      paisDestinoAuto.setAttribute('readonly', 'readonly');
      paisDestinoAuto.classList.add('calc-field');
      paisDestinoAuto.placeholder = 'Automático — Angola';
    }
    if (localCampo54) {
      localCampo54.value = 'Luanda, Angola';
      localCampo54.setAttribute('readonly', 'readonly');
      localCampo54.classList.add('calc-field');
    }
  } else if (regime.startsWith('EX')) {
    // Exportação → país e local editáveis (utilizador informa)
    if (paisDestinoAuto) {
      paisDestinoAuto.value = '';
      paisDestinoAuto.removeAttribute('readonly');
      paisDestinoAuto.classList.remove('calc-field');
      paisDestinoAuto.placeholder = 'Informe o país de destino';
    }
    if (localCampo54) {
      localCampo54.value = '';
      localCampo54.removeAttribute('readonly');
      localCampo54.classList.remove('calc-field');
      localCampo54.placeholder = 'Informe o local de destino';
    }
  }

  // Estância de destino = mesma estância selecionada (sempre editável)
  if (estanciaDestino) {
    if (estanciaSelect && estanciaSelect.value) {
      const label = estanciaSelect.options[estanciaSelect.selectedIndex];
      estanciaDestino.value = label ? label.text : estanciaSelect.value;
    }
  }
}

// Função melhorada para consultar vinhetas com pesquisa automática
function consultarVinhetas() {
  const vinhetaInput = document.getElementById('vinheta_input');
  const vinhetasDiv = document.getElementById('vinhetas_disponiveis');
  const vinhetaSelect = document.getElementById('vinheta_select');
  
  if (!vinhetaInput || !vinhetasDiv || !vinhetaSelect) return;
  
  const iniciais = vinhetaInput.value.trim().toUpperCase();
  
  if (!iniciais) {
    vinhetasDiv.classList.add('hidden');
    return;
  }
  
  // Simulação de consulta de vinhetas disponíveis
  const todasVinhetas = [
    { codigo: 'CDOA001', descricao: 'CDOA001 - Vinheta CDOA Importação - Disponível', status: 'disponivel' },
    { codigo: 'CDOA002', descricao: 'CDOA002 - Vinheta CDOA Exportação - Disponível', status: 'disponivel' },
    { codigo: 'CDOA003', descricao: 'CDOA003 - Vinheta CDOA Trânsito - Disponível', status: 'disponivel' },
    { codigo: 'CDOA004', descricao: 'CDOA004 - Vinheta CDOA Armazenagem - Disponível', status: 'disponivel' },
    { codigo: 'CDOA005', descricao: 'CDOA005 - Vinheta CDOA Temporária - Disponível', status: 'disponivel' },
    { codigo: 'AGT001', descricao: 'AGT001 - Vinheta AGT Especial - Disponível', status: 'disponivel' },
    { codigo: 'AGT002', descricao: 'AGT002 - Vinheta AGT Urgente - Disponível', status: 'disponivel' }
  ];
  
  const vinhetasDisponiveis = todasVinhetas.filter(v => 
    v.codigo.startsWith(iniciais) && v.status === 'disponivel'
  );
  
  if (vinhetasDisponiveis.length > 0) {
    vinhetaSelect.innerHTML = '<option value="">Selecione uma vinheta disponível...</option>';
    vinhetasDisponiveis.forEach(vinheta => {
      const option = document.createElement('option');
      option.value = vinheta.codigo;
      option.textContent = vinheta.descricao;
      vinhetaSelect.appendChild(option);
    });
    vinhetasDiv.classList.remove('hidden');
  } else {
    vinhetasDiv.classList.add('hidden');
  }
}

// Função para pesquisa automática enquanto digita
function pesquisaAutomaticaVinheta() {
  const vinhetaInput = document.getElementById('vinheta_input');
  
  if (vinhetaInput) {
    // Adicionar evento de input para pesquisa automática
    vinhetaInput.addEventListener('input', function() {
      // Debounce para evitar muitas consultas
      clearTimeout(this.searchTimeout);
      this.searchTimeout = setTimeout(() => {
        if (this.value.length >= 2) { // Pesquisar após 2 caracteres
          consultarVinhetas();
        } else {
          const vinhetasDiv = document.getElementById('vinhetas_disponiveis');
          if (vinhetasDiv) {
            vinhetasDiv.classList.add('hidden');
          }
        }
      }, 300); // Aguardar 300ms após parar de digitar
    });
  }
}

function selecionarVinheta() {
  const vinhetaSelect = document.getElementById('vinheta_select');
  const vinhetaInput = document.getElementById('vinheta_input');
  
  if (vinhetaSelect && vinhetaInput && vinhetaSelect.value) {
    vinhetaInput.value = vinhetaSelect.value;
    vinhetaInput.setAttribute('readonly', 'true');
    vinhetaInput.classList.add('calc-field');
    showSuccess('Vinheta selecionada e bloqueada no sistema');
    
    // Ocultar lista após seleção
    const vinhetasDiv = document.getElementById('vinhetas_disponiveis');
    if (vinhetasDiv) {
      vinhetasDiv.classList.add('hidden');
    }
  }
}

// Variável global para controlar containers
let containerCounter = 0;
let containersVisible = true;


/* ----------------------------------------------------------
   Função principal — substituir a existente em script.js
---------------------------------------------------------- */
function adicionarContainer() {
  const containerList = document.getElementById('container_list');
  if (!containerList) return;

  containerCounter++;
  const id = containerCounter;

  const containerDiv = document.createElement('div');
  containerDiv.className = 'container-item bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-sm';
  containerDiv.setAttribute('data-container-id', id);

  containerDiv.innerHTML = `
    <!-- Cabeçalho do contentor -->
    <div class="container-header bg-gray-50 dark:bg-gray-700 p-3 rounded-t-lg border-b border-gray-200 dark:border-gray-600">
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-3">
          <i class="fas fa-boxes text-blue-600"></i>
          <h6 class="font-semibold text-gray-900 dark:text-white">Container #${id}</h6>
          <span class="text-xs bg-green-100 text-green-800 px-2 py-1 rounded-full">Novo</span>
        </div>
        <div class="flex items-center gap-2">
          <button type="button" class="text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
            onclick="toggleContainerContent(${id})" title="Minimizar/Expandir">
            <i class="fas fa-chevron-up container-toggle-icon"></i>
          </button>
          <button type="button" class="text-red-600 hover:text-red-800 dark:text-red-400 dark:hover:text-red-300"
            onclick="removerContainer(${id})" title="Remover Container">
            <i class="fas fa-trash"></i>
          </button>
        </div>
      </div>
    </div>

    <!-- Corpo do contentor -->
    <div class="container-content p-4" id="container_content_${id}">
      
      <!-- Linha 1: Item, Número, Pacotes, Tipo -->
      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <div class="form-field">
          <label class="form-label required">Número do Container</label>
          <input type="text" name="container_numero[]" class="form-input uppercase"
            placeholder="Ex: MSKU1234567" required
            oninput="this.value = this.value.toUpperCase()" />
          <p class="field-hint">Número único do container</p>
        </div>
        <div class="form-field">
          <label class="form-label required">Número de Pacotes</label>
          <input type="number" name="container_num_pacotes[]" class="form-input"
            placeholder="0" min="0" required />
          <p class="field-hint">Quantidade de pacotes</p>
        </div>
        <div class="form-field">
          <label class="form-label required">Tipo</label>
          <select name="container_tipo[]" class="form-input" required>
            <option value="">Selecione...</option>
            <option value="20GP">20' GP (General Purpose)</option>
            <option value="40GP">40' GP (General Purpose)</option>
            <option value="40HC">40' HC (High Cube)</option>
            <option value="20RF">20' RF (Refrigerated)</option>
            <option value="40RF">40' RF (Refrigerated)</option>
            <option value="20OT">20' OT (Open Top)</option>
            <option value="40OT">40' OT (Open Top)</option>
            <option value="20FR">20' FR (Flat Rack)</option>
            <option value="40FR">40' FR (Flat Rack)</option>
          </select>
        </div>
      </div>

      <!-- Linha 2: E/F, Peso Vazio, Peso Mercadorias -->
      <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mt-4">
        <div class="form-field">
          <label class="form-label required">E/F</label>
          <select name="container_ef[]" class="form-input" required>
            <option value="">Selecione...</option>
            <option value="E">E - Empty (Vazio)</option>
            <option value="F">F - Full (Cheio)</option>
          </select>
          <p class="field-hint">Estado do container</p>
        </div>
        <div class="form-field">
          <label class="form-label">Peso Vazio (kg)</label>
          <input type="number" name="container_peso_vazio[]" class="form-input"
            placeholder="0.00" step="0.01" min="0" />
          <p class="field-hint">Peso do container vazio</p>
        </div>
        <div class="form-field">
          <label class="form-label">Peso das Mercadorias (kg)</label>
          <input type="number" name="container_peso_mercadorias[]" class="form-input"
            placeholder="0.00" step="0.01" min="0" />
          <p class="field-hint">Peso das mercadorias</p>
        </div>
      </div>

      <!-- Mercadorias (descrição) -->
      <div class="form-field mt-4">
        <label class="form-label">Mercadorias (Goods)</label>
        <textarea name="container_mercadorias[]" class="form-input" rows="2"
          placeholder="Descrição das mercadorias contidas no container"></textarea>
        <p class="field-hint">Descrição geral das mercadorias</p>
      </div>

      <!-- =====================================================
           CAMPO DE ADIÇÕES — NOVO
      ====================================================== -->
      <div class="container-adicoes-field mt-4" id="container_adicoes_field_${id}">
        <div class="container-adicoes-label">
          <i class="fas fa-box"></i>
          <label class="form-label mb-0">
            Adições neste Contentor
            <span class="field-code">Campo 19</span>
          </label>
        </div>

        <!-- Estado: sem adições disponíveis -->
        <div class="container-adicoes-empty" id="container_adicoes_empty_${id}">
          <i class="fas fa-info-circle"></i>
          <span>Nenhuma adição criada ainda. Crie adições no Passo 2 para associar a este contentor.</span>
        </div>

        <!-- Lista de adições como checkboxes -->
        <div class="container-adicoes-list" id="container_adicoes_list_${id}">
          <!-- Preenchido dinamicamente por sincronizarAdicoesContainers() -->
        </div>

        <!-- Campo hidden que guarda os valores seleccionados como JSON -->
        <input type="hidden" name="container_adicoes[]" id="container_adicoes_hidden_${id}" value="[]" />

        <p class="field-hint mt-1">
          Seleccione quais adições estão associadas a este contentor.
          Uma adição pode estar em múltiplos contentores.
        </p>
      </div>
      <!-- /CAMPO DE ADIÇÕES -->

    </div><!-- /container-content -->
  `;

  // Inserir no topo (novos contentores aparecem primeiro)
  containerList.insertBefore(containerDiv, containerList.firstChild);

  // Inicializar Select2 para Tipo e E/F — mostrar apenas o código (antes do espaço)
  if (typeof $ !== 'undefined' && typeof $.fn.select2 !== 'undefined') {
    $(containerDiv).find('select[name="container_tipo[]"]').select2({
      placeholder: 'Selecione...',
      allowClear: true,
      width: '100%',
      language: { noResults: () => 'Nenhum tipo encontrado', searching: () => 'Pesquisando...' },
      templateSelection: function(data) {
        if (!data.id) return data.text;
        // Mostrar apenas "20' GP", "40' HC", etc. — tudo antes do " ("
        return data.text.split(' (')[0];
      }
    });

    $(containerDiv).find('select[name="container_ef[]"]').select2({
      placeholder: 'Selecione...',
      allowClear: true,
      width: '100%',
      minimumResultsForSearch: Infinity,
      templateSelection: function(data) {
        if (!data.id) return data.text;
        // Mostrar apenas "E" ou "F"
        return data.id;
      }
    });
  }

  // Preencher adições disponíveis neste novo contentor
  sincronizarAdicoesContainers();

  // Event listener para actualizar hidden field ao marcar/desmarcar
  containerDiv.addEventListener('change', function(e) {
    if (e.target.matches(`input[name="container_adicao_check_${id}[]"]`)) {
      actualizarHiddenAdicoes(id);
    }
  });

  atualizarContadorContainers();
}


/* ----------------------------------------------------------
   Recolher adições actuais do #adicoes_wrapper
   Devolve array de objectos { num, label }
---------------------------------------------------------- */
function recolherAdicoesDisponiveis() {
  const wrapper = document.getElementById('adicoes_wrapper');
  if (!wrapper) return [];

  const cards = wrapper.querySelectorAll('.adicao-card-wrapper');
  const lista = [];

  cards.forEach(card => {
    const n = card.dataset.adicao;
    if (!n) return;

    // Tentar obter código pautal e descrição para label mais informativo
    const cp = card.querySelector(`[name="adicao[${n}][codigo_pautal]"]`)?.value || '';
    const desc = card.querySelector(`[name="adicao[${n}][descricao_mercadoria]"]`)?.value || '';

    let label = `Adição Nº ${n}`;
    if (cp) label += `  —  ${cp}`;
    if (desc) label += `  ·  ${desc.substring(0, 40)}${desc.length > 40 ? '…' : ''}`;

    lista.push({ num: n, label });
  });

  return lista;
}


/* ----------------------------------------------------------
   Sincronizar campo de adições em TODOS os contentores
   Chamado sempre que uma adição é adicionada/removida/renumerada
---------------------------------------------------------- */
function sincronizarAdicoesContainers() {
  const adicoesDisponiveis = recolherAdicoesDisponiveis();
  const containerList = document.getElementById('container_list');
  if (!containerList) return;

  const containers = containerList.querySelectorAll('[data-container-id]');

  containers.forEach(containerDiv => {
    const id = containerDiv.dataset.containerId;
    renderizarAdicoesNoContainer(id, adicoesDisponiveis);
  });
}


/* ----------------------------------------------------------
   Renderizar checkboxes de adições num contentor específico
---------------------------------------------------------- */
function renderizarAdicoesNoContainer(containerId, adicoesDisponiveis) {
  const listEl   = document.getElementById(`container_adicoes_list_${containerId}`);
  const emptyEl  = document.getElementById(`container_adicoes_empty_${containerId}`);
  const hiddenEl = document.getElementById(`container_adicoes_hidden_${containerId}`);

  if (!listEl || !emptyEl) return;

  // Guardar selecções actuais antes de re-renderizar
  const seleccionadas = hiddenEl
    ? JSON.parse(hiddenEl.value || '[]')
    : [];

  if (adicoesDisponiveis.length === 0) {
    listEl.innerHTML = '';
    listEl.classList.add('hidden');
    emptyEl.classList.remove('hidden');
    return;
  }

  emptyEl.classList.add('hidden');
  listEl.classList.remove('hidden');

  listEl.innerHTML = adicoesDisponiveis.map(({ num, label }) => {
    const checked = seleccionadas.includes(String(num)) ? 'checked' : '';
    return `
      <label class="container-adicao-item ${checked ? 'selected' : ''}"
             id="container_adicao_label_${containerId}_${num}">
        <input
          type="checkbox"
          name="container_adicao_check_${containerId}[]"
          value="${num}"
          ${checked}
          onchange="toggleAdicaoItemStyle(this, ${containerId}, ${num}); actualizarHiddenAdicoes(${containerId})"
        />
        <span class="container-adicao-badge">${num}</span>
        <span class="container-adicao-text">${label}</span>
        <i class="fas fa-check-circle container-adicao-check-icon"></i>
      </label>
    `;
  }).join('');
}


/* ----------------------------------------------------------
   Actualizar visual do item ao marcar/desmarcar
---------------------------------------------------------- */
function toggleAdicaoItemStyle(checkbox, containerId, adicaoNum) {
  const label = document.getElementById(`container_adicao_label_${containerId}_${adicaoNum}`);
  if (label) {
    label.classList.toggle('selected', checkbox.checked);
  }
}


/* ----------------------------------------------------------
   Actualizar campo hidden com valores seleccionados
---------------------------------------------------------- */
function actualizarHiddenAdicoes(containerId) {
  const hiddenEl = document.getElementById(`container_adicoes_hidden_${containerId}`);
  if (!hiddenEl) return;

  const checkboxes = document.querySelectorAll(
    `input[name="container_adicao_check_${containerId}[]"]:checked`
  );
  const valores = Array.from(checkboxes).map(cb => cb.value);
  hiddenEl.value = JSON.stringify(valores);
}

// Função para remover container
function removerContainer(containerId) {
  const containerDiv = document.querySelector(`[data-container-id="${containerId}"]`);
  if (containerDiv) {
    abrirConfirm({
      tipo: 'danger',
      titulo: 'Remover Container',
      mensagem: 'Tem certeza que deseja remover o Container #' + containerId + '?',
      textoBotao: 'Remover',
      textoCancelar: 'Cancelar',
      onConfirm: function() {
        containerDiv.remove();
        atualizarContadorContainers();
        showSuccess('Container #' + containerId + ' removido');
      }
    });
  }
}

// Função para minimizar/expandir conteúdo do container
function toggleContainerContent(containerId) {
  const contentDiv = document.getElementById(`container_content_${containerId}`);
  const toggleIcon = document.querySelector(`[data-container-id="${containerId}"] .container-toggle-icon`);
  
  if (contentDiv && toggleIcon) {
    if (contentDiv.style.display === 'none') {
      contentDiv.style.display = 'block';
      toggleIcon.classList.remove('fa-chevron-down');
      toggleIcon.classList.add('fa-chevron-up');
    } else {
      contentDiv.style.display = 'none';
      toggleIcon.classList.remove('fa-chevron-up');
      toggleIcon.classList.add('fa-chevron-down');
    }
  }
}

// Função para ocultar/mostrar todos os containers
function toggleContainerList() {
  const containerList = document.getElementById('container_list');
  const toggleBtn = document.getElementById('toggle_containers_btn');
  const toggleIcon = toggleBtn?.querySelector('.fas');
  
  if (!containerList || !toggleBtn || !toggleIcon) return;
  
  const containers = containerList.querySelectorAll('.container-item');
  
  if (containersVisible) {
    containers.forEach(container => {
      const content = container.querySelector('.container-content');
      if (content) content.style.display = 'none';
      const icon = container.querySelector('.container-toggle-icon');
      if (icon) { icon.classList.remove('fa-chevron-up'); icon.classList.add('fa-chevron-down'); }
    });
    toggleIcon.classList.remove('fa-eye-slash');
    toggleIcon.classList.add('fa-eye');
    toggleBtn.querySelector('span:last-child').textContent = 'Mostrar Todos';
    containersVisible = false;
  } else {
    containers.forEach(container => {
      const content = container.querySelector('.container-content');
      if (content) content.style.display = 'block';
      const icon = container.querySelector('.container-toggle-icon');
      if (icon) { icon.classList.remove('fa-chevron-down'); icon.classList.add('fa-chevron-up'); }
    });
    toggleIcon.classList.remove('fa-eye');
    toggleIcon.classList.add('fa-eye-slash');
    toggleBtn.querySelector('span:last-child').textContent = 'Ocultar Todos';
    containersVisible = true;
  }
}

// Função para atualizar contador de containers
function atualizarContadorContainers() {
  const containerList = document.getElementById('container_list');
  const counterElement = document.getElementById('container_count');
  
  if (containerList && counterElement) {
    const count = containerList.querySelectorAll('.container-item').length;
    counterElement.textContent = `(${count} container${count !== 1 ? 'es' : ''})`;
  }
}

// Função para atualizar campos baseados no regime aduaneiro (inclui destino)
function atualizarCamposRegime() {
  const regimeSelect = document.getElementById('regime_aduaneiro');
  const nifExportador = document.getElementById('exportador_codigo');
  const nomeExportador = document.getElementById('exportador_nome');
  const enderecoExportador = document.getElementById('exportador_endereco');
  const nomeDestinatario = document.getElementById('destinatario_nome');
  const paisDestinoAuto = document.getElementById('pais_destino_auto');
  const estanciaDestino = document.getElementById('estancia_destino');
  const localCampo54 = document.getElementById('local_campo54');
  const estanciaSelect = document.getElementById('estancia');
  const dataCampo54 = document.getElementById('data_campo54');

  if (!regimeSelect) return;
  const regime = regimeSelect.value;

  // Data atual
  if (dataCampo54 && !dataCampo54.value) {
    dataCampo54.value = new Date().toISOString().split('T')[0];
  }

  // Regras para campos do exportador/destinatário — NIF e Nome sempre obrigatórios
  const destinatarioNif = document.getElementById('destinatario_nif');
  if (destinatarioNif) destinatarioNif.setAttribute('required', 'true');
  if (nomeDestinatario) nomeDestinatario.setAttribute('required', 'true');
  if (nifExportador) nifExportador.setAttribute('required', 'true');
  if (nomeExportador) nomeExportador.setAttribute('required', 'true');

  if (regime.startsWith('IM')) {
    if (enderecoExportador) enderecoExportador.removeAttribute('required');
    if (paisDestinoAuto) {
      paisDestinoAuto.value = 'AO - Angola';
      paisDestinoAuto.readOnly = true;
      paisDestinoAuto.classList.add('calc-field');
      paisDestinoAuto.placeholder = 'Automático — Angola';
    }
    if (localCampo54) {
      localCampo54.value = 'Luanda, Angola';
      localCampo54.readOnly = true;
      localCampo54.classList.add('calc-field');
    }
  } else if (regime.startsWith('EX')) {
    if (enderecoExportador) enderecoExportador.removeAttribute('required');
    if (paisDestinoAuto) {
      paisDestinoAuto.value = '';
      paisDestinoAuto.readOnly = false;
      paisDestinoAuto.classList.remove('calc-field');
      paisDestinoAuto.placeholder = 'Informe o país de destino';
    }
    if (localCampo54) {
      localCampo54.value = '';
      localCampo54.readOnly = false;
      localCampo54.classList.remove('calc-field');
      localCampo54.placeholder = 'Informe o local de destino';
    }
  }

  // Estância de destino = mesma estância selecionada (sempre editável)
  if (estanciaDestino) {
    if (estanciaSelect && estanciaSelect.value) {
      const label = estanciaSelect.options[estanciaSelect.selectedIndex];
      estanciaDestino.value = label ? label.text : estanciaSelect.value;
    }
  }
}

// Função para calcular taxas — itera por cada adição e aplica as regras do documento.js
function calcularTaxas() {
  console.log('=== INICIANDO CÁLCULO DE TAXAS ===');

  // ── 1. Dados globais da DU ────────────────────────────────────────────────
  const regimeCod  = document.getElementById('regime_aduaneiro')?.value || '';
  const exportador = document.getElementById('exportador_codigo')?.value || '';
  console.log('[DU] regime_aduaneiro:', regimeCod);
  console.log('[DU] exportador_codigo:', exportador);

  // ── 2. Recolher todos os cards de adição ──────────────────────────────────
  const cards = document.querySelectorAll('[data-adicao]');
  if (cards.length === 0) {
    showWarning('Adicione pelo menos uma adição antes de calcular as taxas.');
    console.warn('Nenhuma adição encontrada.');
    return;
  }

  // Acumuladores totais por imposto (só crédito "1" — valores a pagar)
  let totalDERIMP  = 0;
  let totalIEC     = 0;
  let totalEMGEAD  = 0;
  let totalDEREXP  = 0;
  let totalIVA     = 0;

  // Valores brutos para exibição na tabela (incluindo suspensos/isentos)
  let ultimaValBrutaDERIMP = 0, ultimaTaxaDERIMP = 0, ultimaBaseDERIMP = 0;
  let ultimaValBrutaIEC    = 0, ultimaTaxaIEC    = 0, ultimaBaseIEC    = 0;
  let ultimaValBrutaEMGEAD = 0, ultimaTaxaEMGEAD = 0, ultimaBaseEMGEAD = 0;
  let ultimaValBrutaDEREXP = 0, ultimaTaxaDEREXP = 0, ultimaBaseDEREXP = 0;
  let ultimaValBrutaIVA    = 0, ultimaTaxaIVA    = 0, ultimaBaseIVA    = 0;

  // Estado de cada imposto para badge visual
  let estadoDERIMP = 'zero', estadoIEC = 'zero', estadoEMGEAD = 'zero';
  let estadoDEREXP = 'zero', estadoIVA = 'zero';

  // ── Implementação de inListTar ────────────────────────────────────────────
  // Retorna 0 se o código pautal pertence à lista, diferente de 0 caso contrário.
  const LISTAS_PAUTAIS = {
    CPEXDE: new Set([
        '43011000','43013000','43016000','43018000','43021100','43021900','43022000','43023000',
        '43031000','43039000','43040000','96011000','96019000','05071000'
    ]),

    PRODUTOEXPORTACAO: new Set([
        '02011000','02012000','02013000','02021000','02022000','02023000','02031100','02031200',
        '02031900','02032100','02032200','02032900','02041000','02042100','02042200','02042300',
        '02043000','02044100','02044200','02044300','02045000','02050000','02061000','02062100',
        '02062200','02062900','02063000','02064100','02064900','02068000','02069000','02071100',
        '02071200','02071300','02071400','02072400','02072500','02072600','02072700','02074100',
        '02074200','02074300','02074400','02074500','02075100','02075200','02075300','02075400',
        '02075500','02076000','02081000','02091000','02099000','02101100','02101200','02101900',
        '02102000','03021100','03021300','03021400','03021900','03022100','03022200','03022300',
        '03022400','03024100','03024200','03024300','03024400','03024500','03024600','03024700',
        '03024900','03025100','03025200','03025300','03025400','03025500','03025600','03025900',
        '03027100','03027200','03027300','03027400','03027900','03028100','03028200','03028300',
        '03028400','03028500','03028900','03029100','03029200','03029900','03031100','03031200',
        '03031300','03031400','03031900','03032300','03032400','03032500','03032600','03032900',
        '03033100','03033200','03033300','03033400','03033900','03034100','03034200','03034300',
        '03034400','03034500','03034600','03034900','03035100','03035300','03035400','03035500',
        '03035600','03035700','03035900','03036300','03036400','03036500','03036600','03036700',
        '03036800','03036900','03038100','03038200','03038300','03038400','03038900','03039100',
        '03039200','03039900','03043100','03043200','03043300','03043900','03044100','03044200',
        '03044300','03044400','03044500','03044600','03044700','03044800','03044900','03045100',
        '03045200','03045300','03045400','03045500','03045600','03045700','03045900','03046100',
        '03046200','03046300','03046900','03047100','03047200','03047300','03047400','03047500',
        '03047900','03048100','03048200','03048300','03048400','03048500','03048600','03048700',
        '03048800','03048900','03049100','03049200','03049300','03049400','03049500','03049600',
        '03049700','03049900','03051000','03052000','03053100','03053200','03053900','03054100',
        '03054200','03054300','03054400','03054900','03055100','03055200','03055300','03055400',
        '03055900','03056100','03056200','03056300','03056400','03056900','03057100','03057200',
        '03057900','03061100','03061200','03061400','03061500','03061600','03061700','03061900',
        '03063100','03063200','03063300','03063400','03063500','03063600','03063900','03069100',
        '03069200','03069300','03069400','03069500','03069900','03071100','03071200','03071900',
        '03072100','03072200','03072900','03073100','03073200','03073900','03074200','03074300',
        '03074900','03075100','03075200','03075900','03076000','03077100','03077200','03077900',
        '03078100','03078200','03078300','03078400','03078700','03078800','03079100','03079200',
        '03079900','03081100','03081200','03081900','03082100','03082200','03082900','03083000',
        '03089000','04011000','04011010','04011020','04011090','04012010','04012090','04014010',
        '04014090','04015010','04015090','04021010','04021020','04021090','04022110','04022120',
        '04022190','04022910','04022920','04022990','04029110','04029120','04029190','04029910',
        '04029920','04029930','04029990','04031000','04032000','04039000','04039010','04039090',
        '04041000','04049000','04051010','04051090','04052000','04059000','04061000','04062000',
        '04063000','04064000','04069000','04071100','04071900','04072100','04072900','04079000',
        '04081100','04081900','04089100','04089900','04090000','04100000','04101010','04101090',
        '04109000','05010000','05021000','05029000','05040000','07011000','07019000','07020000',
        '07031000','07032000','07039000','07041000','07042000','07049000','07051100','07051900',
        '07052100','07052900','07061010','07061090','07069000','07070000','07081000','07082000',
        '07089000','07092000','07093000','07094000','07095100','07095200','07095300','07095400',
        '07095500','07095600','07095900','07096000','07097000','07099100','07099200','07099300',
        '07099900','07101000','07102100','07102200','07102900','07103000','07104000','07108000',
        '07109000','07112000','07114000','07115100','07115900','07119000','07122000','07123100',
        '07123200','07123300','07123400','07123900','07129000','07131000','07132000','07133100',
        '07133200','07133300','07133400','07133500','07133900','07134000','07135000','07136000',
        '07139000','07141000','07142000','07143000','07144000','07145000','07149000','08011100',
        '08011200','08011900','08012100','08012200','08013100','08013200','08021100','08021200',
        '08022100','08022200','08023100','08023200','08024100','08024200','08025100','08025200',
        '08026100','08026200','08027000','08028000','08029000','08029100','08029200','08029900',
        '08031000','08039000','08041000','08042000','08043000','08044000','08045000','08051000',
        '08052100','08052200','08052900','08054000','08055000','08059000','08061000','08062000',
        '08071100','08071900','08072000','08081000','08083000','08084000','08091000','08092100',
        '08092900','08093000','08094000','08101000','08102000','08103000','08104000','08105000',
        '08106000','08107000','08109000','08111000','08112000','08119000','08121000','08129000',
        '08131000','08132000','08133000','08134000','08135000','08140000','09011100','09011200',
        '09012100','09012200','09019000','09021000','09022000','09023000','09024000','09030000',
        '09041100','09041200','09042100','09042200','09051000','09052000','09061100','09061900',
        '09062000','09071000','09072000','09081100','09081200','09082100','09082200','09083100',
        '09083200','09092100','09092200','09093100','09093200','09096100','09096200','09101100',
        '09101200','09102000','09103000','09109100','09109900','10011100','10011900','10019100',
        '10019900','10021000','10029000','10031000','10039000','10041000','10049000','10051000',
        '10059000','10061000','10062000','10063000','10064000','10071000','10079000','10081000',
        '10082100','10082900','10083000','10084000','10085000','10086000','10089000','11010010',
        '11010090','11010011','11010019','11022010','11022090','11029010','11029090','11031100',
        '11031110','11031190','11031300','11031900','11032000','11041200','11041900','11042200',
        '11042300','11042900','11043000','11051000','11052000','11061000','11062010','11062090',
        '11063000','11071000','11072000','11081100','11081200','11081300','11081400','11081900',
        '11082000','11090000','12011000','12019000','12023000','12024100','12024200','12030000',
        '12040000','12051000','12059000','12060000','12071000','12072100','12072900','12073000',
        '12074000','12075000','12076000','12077000','12079100','12079900','12081000','12089000',
        '12091000','12092100','12092200','12092300','12092400','12092500','12092900','12093000',
        '12099100','12101000','12102000','12112000','12113000','12114000','12115000','12116000',
        '12119000','12122100','12122900','12129100','12129200','12129300','12129400','12129900',
        '12141000','12149000','13012000','13019000','13021100','13021200','13021300','13021400',
        '13021900','13022000','13023100','13023200','13023900','15011000','15012000','15019000',
        '15021000','15029000','15030000','15041000','15042000','15043000','15050000','15060000',
        '15071000','15079000','15079010','15079090','15081000','15089000','15091000','15092000',
        '15093000','15094000','15099000','15100000','15101000','15109000','15111000','15119000',
        '15119010','15119090','15121100','15121900','15121910','15121990','15122100','15122900',
        '15131100','15131900','15132100','15132900','15141100','15141900','15149100','15149900',
        '15151100','15151900','15152100','15152900','15153000','15155000','15156000','15159000',
        '15161000','15162000','15163000','15171000','15179000','16010000','16021000','16022000',
        '16023100','16023200','16023900','16024100','16024200','16024900','16025000','16029000',
        '16030000','16041100','16041200','16041300','16041400','16041500','16041600','16041700',
        '16041800','16041900','16042000','16043100','16043200','16051000','16052100','16052900',
        '16053000','16054000','16055100','16055200','16055300','16055400','16055500','16055600',
        '16055700','16055800','16055900','16056100','16056200','16056300','16056900','17011210',
        '17011290','17011310','17011390','17011410','17011490','17019110','17019119','17019910',
        '17019919','17021100','17021900','17022000','17023000','17024000','17025000','17026000',
        '17029000','17031000','17039000','17041000','17049010','17049020','17049090','18010000',
        '18020000','18031000','18032000','18040000','18050000','18061000','18062000','18063100',
        '18063200','18069000','19011000','19012000','19019010','19019020','19019030','19019040',
        '19019050','19019090','19021100','19021900','19022000','19023000','19024000','19030000',
        '19041000','19042000','19043000','19049000','19051000','19052000','19053100','19053200',
        '19054000','19059010','19059020','19059030','19059090','19099900','20011000','20019000',
        '20021000','20029000','20031000','20039000','20041000','20049000','20051000','20052000',
        '20054000','20055100','20055900','20056000','20057000','20058000','20059100','20059900',
        '20060000','20071000','20079100','20079900','20081100','20081900','20082000','20083000',
        '20084000','20085000','20086000','20087000','20088000','20089100','20089300','20089700',
        '20089900','20091100','20091200','20091900','20092100','20092900','20093100','20093900',
        '20094100','20094900','20095000','20096110','20096190','20096900','20097100','20097900',
        '20098100','20098900','20099000','21011100','21011200','21012000','21013000','21021000',
        '21021010','21021090','21022000','21023000','21031000','21032000','21033000','21039010',
        '21039020','21039090','21041000','21042000','21050000','21061000','21069010','21069020',
        '21069030','21069090','22011000','22011090','22019000','22021000','22021010','22021020',
        '22021090','22029100','22029900','22029910','22029920','22029930','22029990','22030000',
        '22041010','22041090','22042100','22042200','22042900','22043000','22051000','22060000',
        '22071000','22072010','22072019','22082000','22083000','22084000','22085000','22086000',
        '22087000','22089000','22090000','28432100','29362100','29362200','29362300','29362400',
        '29362500','29362600','29362700','29362800','29362900','29369000','29371100','29371200',
        '29371900','29372100','29372200','29372300','29372900','29375000','29379000','30012000',
        '30019000','30021100','30021200','30021300','30021400','30021500','30021900','30022000',
        '30023000','30024111','30024112','30024119','30024200','30024900','30025100','30025900',
        '30029000','30031000','30032000','30033100','30033900','30034100','30034200','30034300',
        '30034900','30036000','30039000','30041000','30042000','30043100','30043200','30043900',
        '30044100','30044200','30044300','30044900','30045000','30046000','30049000','30051000',
        '30059010','30059090','30061000','30062000','30063000','30064000','30065000','30066000',
        '30067000','30069100','30069200','30069300','33079010','34011190','38210000','38220000',
        '39232920','39232930','39233010','39269010','39269020','39269030','39269040','40141000',
        '40149000','40151100','40151200','40159000','48185000','62114200','63023210','63042000',
        '63079000','65050000','70101000','70109090','70112000','70119000','70151000','70171000',
        '70172000','70179000','84192000','87032110','87032121','87032210','87032221','87032310',
        '87032331','87032441','87032451','87033115','87033121','87033231','87033241','87033351',
        '87033361','87131000','87139000','90011000','90012000','90013000','90014000','90019000',
        '90022000','90029000','90031100','90031900','90039000','90041000','90049000','90063000',
        '90101000','90105000','90106000','90109000','90111000','90112000','90118000','90119000',
        '90121000','90129000','90138000','90139000','90181100','90181200','90181300','90181400',
        '90181900','90182000','90183100','90183200','90183900','90184100','90184900','90185000',
        '90189000','90191000','90192000','90200000','90211000','90212100','90212900','90213100',
        '90213900','90214000','90215000','90219000','90221200','90221300','90221400','90221900',
        '90222100','90222900','90223000','90229000','90230000','90251100','90251900','90258000',
        '90271000','90272000','90273000','90275000','90278000','90278100','90278900','90279000',
        '90292000','90301000','90302000','90303100','90303200','90303300','90303900','90304000',
        '90308200','90308400','90308900','90309000','90312000','94021000','94029000'
    ]),

    CPEXDMB: new Set([
        '25061000','25062000','25070000','25081000','25083000','25084000','25085000','25086000',
        '25087000','25090000','25101000','25102000','25111000','25112000','25120000','25131000',
        '25132000','25140000','25151100','25151200','25152000','25161100','25161200','25162000',
        '25169000','25171000','25172000','25173000','25174100','25174900','25181000','25182000',
        '25191000','25199000','25201000','25202000','25210000','25221000','25222000','25223000',
        '25241000','25249000','25251000','25252000','25253000','25261000','25262000','25280000',
        '25291000','25292100','25292200','25293000','25301000','25302000','25309000','26011100',
        '26011200','26012000','26020000','26030000','26040000','26050000','26060000','26070000',
        '26080000','26090000','26100000','26110000','26121000','26122000','26131000','26139000',
        '26140000','26151000','26159000','26161000','26169000','26171000','26179000','71023100',
        '71081100','71081200','71081300','71082000'
    ])
};
  function inListTar(nomeLista, cp) {
    const lista = LISTAS_PAUTAIS[nomeLista];
    if (!lista) return 1;
    const cpLimpo = String(cp || '').replace(/\./g, '');
    return lista.has(cpLimpo) ? 0 : 1; // 0 = pertence, 1 = não pertence
  }

  // ── 3. Iterar por cada adição ─────────────────────────────────────────────
  cards.forEach((card, idx) => {
    const n           = card.dataset.adicao;           // número sequencial da adição
    const itemNumber  = parseInt(n, 10);               // ItmNber (1-based)
    // --- Capturar campos da adição ---
    const codigoPautalEl  = card.querySelector(`[name="adicao[${n}][codigo_pautal]"]`);
    const codigoPautal    = codigoPautalEl?.value || '';

    // Taxas vêm do dataset guardado quando o código pautal foi selecionado
    const aliquotaCol1    = parseFloat(codigoPautalEl?.dataset?.direito ?? 0) || 0; // direito_importacao
    const aliquotaCol2    = parseFloat(codigoPautalEl?.dataset?.iec     ?? 0) || 0; // direito_consumo
    const aliquotaCol3    = parseFloat(codigoPautalEl?.dataset?.iva     ?? 14) || 14; // iva

    const procedimento    = card.querySelector(`[name="adicao[${n}][codigo_procedimento]"]`)?.value || '';
    const codigoIsencao   = card.querySelector(`[name="adicao[${n}][codigo_isencao]"]`)?.value || '000';
    const paisOrigem      = card.querySelector(`[name="adicao[${n}][pais_origem]"]`)?.value || '';

    // valorCIF = montante_kz (FOB + Seguro + Frete em KZ) — ItmCIFNcy
    const valorCIF        = parseFloat(document.getElementById(`montante_kz_${n}`)?.value) || 0;

    // valorFOB = fob_kz da adição — ItmFobNcy
    const valorFOB        = parseFloat(document.getElementById(`fob_kz_${n}`)?.value) || 0;

    // valorFatura = FOB em KZ (usado no EMGEAD para exportação)
    const valorFatura     = valorFOB;

    // ── LOG dos parâmetros capturados ──────────────────────────────────────
    console.group(`[Adição ${n}] Parâmetros capturados`);
    console.log('  regimeCod      (regime_aduaneiro)    :', regimeCod);
    console.log('  procedimento   (codigo_procedimento) :', procedimento);
    console.log('  codigoIsencao  (codigo_isencao)      :', codigoIsencao);
    console.log('  codigoPautal   (codigo_pautal)       :', codigoPautal);
    console.log('  aliquotaCol1   (direito_importacao)  :', aliquotaCol1, '%');
    console.log('  aliquotaCol2   (direito_consumo)     :', aliquotaCol2, '%');
    console.log('  aliquotaCol3   (iva)                 :', aliquotaCol3, '%');
    console.log('  valorCIF       (montante_kz)         :', valorCIF, 'KZ');
    console.log('  valorFOB       (fob_kz)              :', valorFOB, 'KZ');
    console.log('  paisOrigem     (pais_origem)         :', paisOrigem);
    console.log('  itemNumber     (nº adição)           :', itemNumber);
    console.groupEnd();

    // ── Calcular cada imposto para esta adição ─────────────────────────────

    // DERIMP — Direitos de Importação (02K)
    const resDERIMP = calcularDERIMP({
      regimeCod,
      procedimento,
      codigoIsencao,
      aliquotaCol1,
      valorCIF
    });

    // IEC — Imposto Especial de Consumo
    const resIEC = calcularIEC({
      regimeCod,
      procedimento,
      codigoIsencao,
      aliquotaCol2,
      valorCIF
    });

    // EMGEAD — Emolumentos Gerais (05M)
    const resEMGEAD = calcularEMGEAD({
      regimeCod,
      procedimento,
      codigoPautal,
      paisOrigem,
      valorCIF,
      valorFatura,
      itemNumber
    });

    // DIREXP — Direitos de Exportação (01K)
    const resDEREXP = calcularDEREXP({
      regimeCod,
      procedimento,
      codigoPautal,
      paisOrigem,
      valorFatura,
      exportador,
      inListTar: (nomeLista) => inListTar(nomeLista, codigoPautal)
    });

    // IVA — base inclui FOB + DERIMP + IEC + EMGEAD + DIREXP
    const resIVA = calcularIVA({
      codigoIsencao,
      aliquotaCol3,
      valorFOB,
      valorDERIMP : resDERIMP.valor,
      valorIEC    : resIEC.valor,
      valorEMGEAD : resEMGEAD.valor,
      valorDEREXP : resDEREXP.valor
    });

    // ── LOG dos resultados desta adição ────────────────────────────────────
    console.group(`[Adição ${n}] Resultados`);
    console.log('  DERIMP  → ação:', resDERIMP.acao,  '| crédito:', resDERIMP.credito,  '| valor:', resDERIMP.valor.toFixed(2),  'KZ | taxa:', resDERIMP.taxa,  '% | base:', (resDERIMP.base||0).toFixed(2));
    console.log('  IEC     → ação:', resIEC.acao,     '| crédito:', resIEC.credito,     '| valor:', resIEC.valor.toFixed(2),     'KZ | taxa:', resIEC.taxa,     '% | base:', (resIEC.base||0).toFixed(2));
    console.log('  EMGEAD  → ação:', resEMGEAD.acao,  '| crédito:', resEMGEAD.credito,  '| valor:', resEMGEAD.valor.toFixed(2),  'KZ | taxa:', resEMGEAD.taxa,  '% | base:', (resEMGEAD.base||0).toFixed(2));
    console.log('  DIREXP  → ação:', resDEREXP.acao,  '| crédito:', resDEREXP.credito,  '| valor:', resDEREXP.valor.toFixed(2),  'KZ | taxa:', resDEREXP.taxa,  '% | base:', (resDEREXP.base||0).toFixed(2));
    console.log('  IVA     → ação:', resIVA.acao,     '| crédito:', resIVA.credito,     '| valor:', resIVA.valor.toFixed(2),     'KZ | taxa:', resIVA.taxa,     '% | base:', (resIVA.base||0).toFixed(2));
    console.groupEnd();

    // ── Acumular totais — só DoTax com crédito "1" entra no total a pagar ──
    // Suspensões (crédito "0"), isenções (RelTax) e anulações (DelTax) ficam separadas
    if (resDERIMP.acao  === 'DoTax' && resDERIMP.credito  === '1') totalDERIMP  += resDERIMP.valor;
    if (resIEC.acao     === 'DoTax' && resIEC.credito     === '1') totalIEC     += resIEC.valor;
    if (resEMGEAD.acao  === 'DoTax' && resEMGEAD.credito  === '1') totalEMGEAD += resEMGEAD.valor;
    if (resDEREXP.acao !== 'N/A'   && resDEREXP.credito  === '1') totalDEREXP  += resDEREXP.valor;
    if (resIVA.acao     === 'DoTax' && resIVA.credito     === '1') totalIVA     += resIVA.valor;

    // Rastrear estado de cada imposto para exibição visual
    // Estado: 'pagar' | 'suspenso' | 'isento' | 'zero'
    function _estado(res) {
      if (res.acao === 'N/A')     return 'zero';
      if (res.acao === 'DelTax')  return 'isento';
      if (res.acao === 'RelTax')  return 'isento';
      if (res.credito === '0')    return 'suspenso';
      return 'pagar';
    }
    estadoDERIMP  = _estado(resDERIMP);
    estadoIEC     = _estado(resIEC);
    estadoEMGEAD  = _estado(resEMGEAD);
    estadoDEREXP  = _estado(resDEREXP);
    estadoIVA     = _estado(resIVA);

    // Guardar valor bruto (incluindo suspensos) para exibir na tabela
    if (resDERIMP.valor > 0 || estadoDERIMP !== 'zero')  { ultimaValBrutaDERIMP = resDERIMP.valor; ultimaTaxaDERIMP = resDERIMP.taxa || 0; ultimaBaseDERIMP = resDERIMP.base || 0; }
    if (resIEC.valor > 0    || estadoIEC     !== 'zero')  { ultimaValBrutaIEC    = resIEC.valor;    ultimaTaxaIEC    = resIEC.taxa    || 0; ultimaBaseIEC    = resIEC.base    || 0; }
    if (resEMGEAD.valor > 0 || estadoEMGEAD !== 'zero')  { ultimaValBrutaEMGEAD = resEMGEAD.valor; ultimaTaxaEMGEAD = resEMGEAD.taxa || 0; ultimaBaseEMGEAD = resEMGEAD.base || 0; }
    if (resDEREXP.valor > 0 || estadoDEREXP !== 'zero')  { ultimaValBrutaDEREXP = resDEREXP.valor; ultimaTaxaDEREXP = resDEREXP.taxa || 0; ultimaBaseDEREXP = resDEREXP.base || 0; }
    if (resIVA.valor > 0    || estadoIVA     !== 'zero')  { ultimaValBrutaIVA    = resIVA.valor;    ultimaTaxaIVA    = resIVA.taxa    || 0; ultimaBaseIVA    = resIVA.base    || 0; }

    // ── Persistir resultados por adição em campo hidden ───────────────────
    // Garante que _submeterDU inclui o breakdown completo de impostos por adição
    const impostosAdicao = {
      DERIMP : { valor: resDERIMP.valor,  taxa: resDERIMP.taxa  || 0, base: resDERIMP.base  || 0, acao: resDERIMP.acao,  credito: resDERIMP.credito  },
      IEC    : { valor: resIEC.valor,     taxa: resIEC.taxa     || 0, base: resIEC.base     || 0, acao: resIEC.acao,     credito: resIEC.credito     },
      EMGEAD : { valor: resEMGEAD.valor,  taxa: resEMGEAD.taxa  || 0, base: resEMGEAD.base  || 0, acao: resEMGEAD.acao,  credito: resEMGEAD.credito  },
      DIREXP : { valor: resDEREXP.valor,  taxa: resDEREXP.taxa  || 0, base: resDEREXP.base  || 0, acao: resDEREXP.acao,  credito: resDEREXP.credito  },
      IVA    : { valor: resIVA.valor,     taxa: resIVA.taxa     || 0, base: resIVA.base     || 0, acao: resIVA.acao,     credito: resIVA.credito     },
    };
    // Criar ou actualizar campo hidden dentro do card da adição
    let hiddenImpostos = card.querySelector(`[name="adicao[${n}][impostos_json]"]`);
    if (!hiddenImpostos) {
      hiddenImpostos = document.createElement('input');
      hiddenImpostos.type = 'hidden';
      hiddenImpostos.name = `adicao[${n}][impostos_json]`;
      card.appendChild(hiddenImpostos);
    }
    hiddenImpostos.value = JSON.stringify(impostosAdicao);
  });

  // ── 4. Totais finais ──────────────────────────────────────────────────────
  const totalGeral = totalDERIMP + totalIEC + totalEMGEAD + totalDEREXP + totalIVA;

  // Persistir totais em campos hidden para que _submeterDU os leia de forma fiável
  // (independentemente de o utilizador ter visto o Step 4 ou não)
  function _setHidden(id, val) {
    let el = document.getElementById(id);
    if (!el) {
      el = document.createElement('input');
      el.type = 'hidden';
      el.id   = id;
      const form = document.getElementById('formDU');
      if (form) form.appendChild(el); else document.body.appendChild(el);
    }
    el.value = val;
  }
  _setHidden('_calc_total_derimp', totalDERIMP.toFixed(2));
  _setHidden('_calc_total_iec',    totalIEC.toFixed(2));
  _setHidden('_calc_total_emgead', totalEMGEAD.toFixed(2));
  _setHidden('_calc_total_direxp', totalDEREXP.toFixed(2));
  _setHidden('_calc_total_iva',    totalIVA.toFixed(2));
  _setHidden('_calc_total_geral',  totalGeral.toFixed(2));
  _setHidden('_calc_done',         '1'); // flag: cálculo foi executado

  console.group('=== TOTAIS FINAIS ===');
  console.log('  DERIMP  total:', totalDERIMP.toFixed(2),  'KZ');
  console.log('  IEC     total:', totalIEC.toFixed(2),     'KZ');
  console.log('  EMGEAD  total:', totalEMGEAD.toFixed(2),  'KZ');
  console.log('  DIREXP  total:', totalDEREXP.toFixed(2),  'KZ');
  console.log('  IVA     total:', totalIVA.toFixed(2),     'KZ');
  console.log('  TOTAL A PAGAR:', totalGeral.toFixed(2),   'KZ');
  console.groupEnd();

  // ── 5. Atualizar campos do Step 4 ─────────────────────────────────────────
  const fmtKZ = v => v.toLocaleString('pt-AO', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' KZ';
  const setVal = (id, val) => { const el = document.getElementById(id); if (el) el.value = val; };
  const setTxt = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };

  // Campos hidden (taxa/base)
  setVal('taxa_direitos',    ultimaTaxaDERIMP.toFixed(2));
  setVal('base_direitos',    ultimaBaseDERIMP.toFixed(2));
  setVal('taxa_iec',         ultimaTaxaIEC.toFixed(2));
  setVal('base_iec',         ultimaBaseIEC.toFixed(2));
  setVal('taxa_emolumentos', ultimaTaxaEMGEAD.toFixed(2));
  setVal('base_emolumentos', ultimaBaseEMGEAD.toFixed(2));
  setVal('taxa_direxp',      ultimaTaxaDEREXP.toFixed(2));
  setVal('base_direxp',      ultimaBaseDEREXP.toFixed(2));
  setVal('taxa_iva',         ultimaTaxaIVA.toFixed(2));
  setVal('base_iva',         ultimaBaseIVA.toFixed(2));

  // Helper: renderiza valor + badge de estado na célula da tabela
  function _renderCelula(idSpanValor, idRow, valorBruto, valorPagar, estado) {
    const spanValor = document.getElementById(idSpanValor);
    const row       = document.getElementById(idRow);
    if (!spanValor) return;

    const BADGE = {
      pagar    : '',   // sem badge — valor normal
      suspenso : '<span style="margin-left:8px;padding:2px 8px;border-radius:20px;font-size:0.7rem;font-weight:700;background:#fef3c7;color:#92400e;border:1px solid #fde68a;">Suspenso</span>',
      isento   : '<span style="margin-left:8px;padding:2px 8px;border-radius:20px;font-size:0.7rem;font-weight:700;background:#dcfce7;color:#166534;border:1px solid #bbf7d0;">Isento</span>',
      zero     : '',
    };

    const badge = BADGE[estado] || '';

    if (estado === 'suspenso') {
      // Valor em cinzento com badge — não entra no total
      spanValor.innerHTML = `<span style="color:#94a3b8;text-decoration:line-through;">${fmtKZ(valorBruto)}</span>${badge}`;
    } else if (estado === 'isento') {
      spanValor.innerHTML = `<span style="color:#94a3b8;">${fmtKZ(valorBruto)}</span>${badge}`;
    } else if (estado === 'zero') {
      spanValor.innerHTML = fmtKZ(0);
    } else {
      // pagar — valor normal a negrito
      spanValor.innerHTML = fmtKZ(valorPagar);
    }

    // Linha com opacidade reduzida se não paga
    if (row) {
      row.style.opacity = (estado === 'zero') ? '0.45' : '1';
    }
  }

  _renderCelula('valor_direitos',   'row_derimp',   ultimaValBrutaDERIMP, totalDERIMP,  estadoDERIMP);
  _renderCelula('valor_iec',        'row_iec',       ultimaValBrutaIEC,    totalIEC,     estadoIEC);
  _renderCelula('valor_emolumentos','row_emgead',    ultimaValBrutaEMGEAD, totalEMGEAD,  estadoEMGEAD);
  _renderCelula('valor_direxp',     'row_direxp',    ultimaValBrutaDEREXP, totalDEREXP,  estadoDEREXP);
  _renderCelula('valor_iva',        'row_iva',       ultimaValBrutaIVA,    totalIVA,     estadoIVA);

  // Label da taxa IVA na tabela
  const labelTaxaIva = document.getElementById('label_taxa_iva_tabela');
  if (labelTaxaIva) labelTaxaIva.textContent = ultimaTaxaIVA;

  // Total geral (span destacado — só valores a pagar)
  const totalGeralEl    = document.getElementById('total_geral');
  const totalGeralAoaEl = document.getElementById('total_geral_aoa');
  if (totalGeralEl)    totalGeralEl.textContent = fmtKZ(totalGeral);
  if (totalGeralAoaEl) totalGeralAoaEl.value    = totalGeral.toFixed(2);

  // ── 6. Atualizar painel lateral (sidebar) ────────────────────────────────
  const setText = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };

  // Sidebar mostra sempre o valor a pagar (0 se suspenso/isento)
  setText('painel_direitos',    fmtKZ(totalDERIMP));
  setText('painel_iec',         fmtKZ(totalIEC));
  setText('painel_emolumentos', fmtKZ(totalEMGEAD));
  setText('painel_direxp',      fmtKZ(totalDEREXP));
  setText('painel_iva',         fmtKZ(totalIVA));
  setText('painel_total',       fmtKZ(totalGeral));

  // Se DERIMP está suspenso, mostrar nota no sidebar
  const painelDireitosEl = document.getElementById('painel_direitos');
  if (painelDireitosEl && estadoDERIMP === 'suspenso') {
    painelDireitosEl.innerHTML =
      `0,00 KZ <span style="font-size:0.65rem;color:#92400e;background:#fef3c7;padding:1px 5px;border-radius:10px;margin-left:4px;">Susp.</span>`;
  }

  // Atualizar label IVA com a taxa real
  const labelIva = document.getElementById('label_painel_iva');
  if (labelIva) labelIva.textContent = `IVA (${ultimaTaxaIVA}%)`;

  console.log('=== CÁLCULO CONCLUÍDO ===');
  showSuccess('Cálculos atualizados com sucesso!');
}

// Função auxiliar para atualizar resumo
function atualizarResumo() {
  calcularTaxas();
}

// Funções auxiliares para cálculo de taxas
function obterTaxaDireitos(regime, procedimento) {
  // Simulação de taxas de direitos baseadas no regime e procedimento
  const taxasPorRegime = {
    'IM4': 5.0,  // Importação definitiva
    'IM5': 0.0,  // Importação temporária
    'IM6': 2.5,  // Trânsito
    'EX1': 2.0,  // Exportação definitiva
    'EX2': 0.0   // Exportação temporária
  };
  
  return taxasPorRegime[regime] || 5.0; // Taxa padrão
}

function obterTaxaIEC(regime) {
  // Taxa IEC baseada no tipo de produto (simulação)
  return 2.0; // Taxa padrão de 2%
}

function isProdutoAlimentar() {
  // Verificar se o código pautal corresponde a produto alimentar
  const codigoPautal = document.getElementById('codigo_pautal')?.value || '';
  // Simulação - códigos que começam com 01-24 são geralmente alimentares
  return codigoPautal.startsWith('01') || codigoPautal.startsWith('02') || 
         codigoPautal.startsWith('03') || codigoPautal.startsWith('04');
}

function isInsumoAgricola() {
  // Verificar se é insumo agrícola
  const codigoPautal = document.getElementById('codigo_pautal')?.value || '';
  return codigoPautal.startsWith('31'); // Fertilizantes
}

function isIsentoIVA(natureza) {
  // Naturezas isentas de IVA
  const naturezasIsentas = [
    '001', '002', '003', '004', '006', '007', '009', '011', '016', '017', '018', '019',
    '020', '021', '024', '025', '026', '028', '029', '033', '034', '035', '036', '037',
    '038', '040', '044', '045', '046', '050', '051', '055', '057', '058', '061', '063',
    '064', '067', '068', '070', '071', '400', '401', '423', '435', '453', '461'
  ];
  
  return naturezasIsentas.includes(natureza);
}

function formatarMoeda(valor) {
  return new Intl.NumberFormat('pt-AO', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  }).format(valor);
}

function mostrarStatusCalculos(sucesso) {
  const statusElements = document.querySelectorAll('.calculation-status');
  statusElements.forEach(element => {
    element.className = `calculation-status ${sucesso ? 'success' : 'pending'}`;
    element.textContent = sucesso ? 'Calculado' : 'Pendente';
  });
}

function atualizarCampoResumo(fieldId, value) {
  const field = document.getElementById(fieldId);
  if (field) {
    field.textContent = value;
  }
}

// Função para atualizar resumo completo
function atualizarResumo() {
  // Coletar dados dos passos anteriores
  const dadosResumo = {
    regime: document.getElementById('regime_aduaneiro')?.value || '',
    vinheta: document.getElementById('vinheta_input')?.value || '',
    exportador: document.getElementById('nome_exportador')?.value || '',
    fob: document.getElementById('valor_fob')?.value || '0',
    cif: document.getElementById('valor_cif')?.value || '0',
    moeda: document.getElementById('moeda')?.value || 'USD'
  };
  
  // Atualizar campos do resumo
  Object.keys(dadosResumo).forEach(key => {
    const element = document.getElementById(`resumo_${key}`);
    if (element) {
      element.textContent = dadosResumo[key];
    }
  });
}

// Função para minimizar/maximizar painel lateral
function toggleSidebar() {
  const sidebar = document.getElementById('calculation-sidebar');
  const toggleBtn = document.getElementById('sidebar-toggle');
  const toggleIcon = document.getElementById('sidebar-toggle-icon');
  
  if (!sidebar || !toggleBtn || !toggleIcon) return;
  
  if (sidebar.classList.contains('minimized')) {
    sidebar.classList.remove('minimized');
    toggleIcon.classList.remove('fa-chevron-left');
    toggleIcon.classList.add('fa-chevron-right');
    toggleBtn.setAttribute('title', 'Minimizar painel');
  } else {
    sidebar.classList.add('minimized');
    toggleIcon.classList.remove('fa-chevron-right');
    toggleIcon.classList.add('fa-chevron-left');
    toggleBtn.setAttribute('title', 'Expandir painel');
  }
}

// Função para recalcular taxas manualmente
function recalcularTaxas() {
  showInfo('Recalculando taxas...');
  setTimeout(() => {
    calcularTaxas();
    showSuccess('Taxas recalculadas com sucesso');
  }, 500);
}

// Função para consultar pauta aduaneira
function consultarPauta() {
  // Redireciona para a função principal
  consultarCodigoPautal();
}

// Função para atualizar unidade da pauta
function atualizarUnidadePauta() {
  // Esta função é chamada quando o código pautal muda
  // Redireciona para a função principal
  consultarCodigoPautal();
}

// Função para guardar rascunho — envia para o backend via AJAX
function guardarRascunho() {
  showInfo('Guardando rascunho...');
  _submeterDU(false);
}

/**
 * Valida se os totais do Step 1 correspondem aos totais das adições.
 * @param {boolean} submeter - true = submissão final, false = rascunho
 * @returns {Array} Array de mensagens de erro (vazio se tudo OK ou se for rascunho)
 */
function validarTotaisStep1VsAdicoes(submeter = false) {
  // Em rascunho, não bloquear — apenas registar no console para debug
  if (!submeter) {
    const cards = document.querySelectorAll('[data-adicao]');
    if (cards.length > 0) {
      const fobStep1 = parseFloat(document.getElementById('valor_fob_kz')?.value || '0') || 0;
      let fobTotal = 0;
      cards.forEach(card => {
        fobTotal += parseFloat(document.getElementById(`fob_kz_${card.dataset.adicao}`)?.value || '0') || 0;
      });
      if (Math.abs(fobStep1 - fobTotal) > 1) {
        console.info('[Rascunho] FOB Step1 vs Adições:', fobStep1.toFixed(2), 'vs', fobTotal.toFixed(2));
      }
    }
    return []; // Rascunho: sem erros bloqueantes
  }

  // Submissão final: validar com margem tolerante (1 KZ para arredondamentos de câmbio)
  const erros = [];
  const margem = 1.0;
  const cards = document.querySelectorAll('[data-adicao]');

  // Só validar se houver adições
  if (cards.length === 0) return erros;

  // 1. Validar FOB
  const fobStep1 = parseFloat(document.getElementById('valor_fob_kz')?.value || '0') || 0;
  let fobTotal = 0;
  cards.forEach(card => {
    fobTotal += parseFloat(document.getElementById(`fob_kz_${card.dataset.adicao}`)?.value || '0') || 0;
  });
  if (fobStep1 > 0 && fobTotal > 0 && Math.abs(fobStep1 - fobTotal) > margem) {
    erros.push(`FOB do Step 1 (${fobStep1.toFixed(2)} KZ) não corresponde ao total das adições (${fobTotal.toFixed(2)} KZ). Diferença: ${Math.abs(fobStep1 - fobTotal).toFixed(2)} KZ`);
  }

  // 2. Validar Frete (só se ambos > 0)
  const freteStep1 = parseFloat(document.getElementById('valor_frete_kz')?.value || '0') || 0;
  let freteTotal = 0;
  cards.forEach(card => {
    freteTotal += parseFloat(document.getElementById(`frete_kz_${card.dataset.adicao}`)?.value || '0') || 0;
  });
  if (freteStep1 > 0 && freteTotal > 0 && Math.abs(freteStep1 - freteTotal) > margem) {
    erros.push(`Frete do Step 1 (${freteStep1.toFixed(2)} KZ) não corresponde ao total das adições (${freteTotal.toFixed(2)} KZ). Diferença: ${Math.abs(freteStep1 - freteTotal).toFixed(2)} KZ`);
  }

  // 3. Validar Seguro (só se ambos > 0)
  const seguroStep1 = parseFloat(document.getElementById('valor_seguro_kz')?.value || '0') || 0;
  let seguroTotal = 0;
  cards.forEach(card => {
    seguroTotal += parseFloat(document.getElementById(`seguro_kz_${card.dataset.adicao}`)?.value || '0') || 0;
  });
  if (seguroStep1 > 0 && seguroTotal > 0 && Math.abs(seguroStep1 - seguroTotal) > margem) {
    erros.push(`Seguro do Step 1 (${seguroStep1.toFixed(2)} KZ) não corresponde ao total das adições (${seguroTotal.toFixed(2)} KZ). Diferença: ${Math.abs(seguroStep1 - seguroTotal).toFixed(2)} KZ`);
  }

  if (erros.length === 0) {
    console.log('✅ Validação de totais: PASSOU');
  }

  return erros;
}

// Recolhe todos os dados do formulário e envia ao backend
function _submeterDU(submeter) {
  const form = document.getElementById('formDU');
  if (!form) return;

  // Bloquear auto-save durante submissão
  isSubmitting = true;

  // ── Validação client-side antes de enviar ────────────────────────────────
  const errosClient = [];

  const regimeEl = document.getElementById('regime_aduaneiro');
  const regimeWrapper = regimeEl?.nextElementSibling;
  const regimeAc = regimeWrapper?.classList?.contains('ac-wrapper') ? regimeWrapper.querySelector('.ac-input') : null;
  const regime = regimeAc?.dataset?.value || regimeEl?.value?.trim();
  if (!regime) errosClient.push('Regime Aduaneiro é obrigatório (Step 1).');

  const ref = form.querySelector('[name="ref_despachante"]')?.value?.trim();
  if (!ref) errosClient.push('Referência Interna é obrigatória (Step 1).');

  // Validar totais do Step 1 vs Adições — só bloqueia na submissão final
  const errosTotais = validarTotaisStep1VsAdicoes(submeter);
  errosClient.push(...errosTotais);

  // Na submissão final, validações adicionais
  if (submeter) {
    const cards = document.querySelectorAll('[data-adicao]');
    if (cards.length === 0) {
      errosClient.push('Adicione pelo menos uma adição (Step 2).');
    } else {
      cards.forEach((card, i) => {
        const n = card.dataset.adicao;
        const cpEl = card.querySelector(`[name="adicao[${n}][codigo_pautal]"]`);
        const cpWrapper = cpEl?.nextElementSibling;
        const cpAc = cpWrapper?.classList?.contains('ac-wrapper') ? cpWrapper.querySelector('.ac-input') : null;
        const cpVal = cpAc?.dataset?.value || cpEl?.value?.trim();
        if (!cpVal) errosClient.push(`Adição ${i + 1}: Código Pautal é obrigatório.`);
        const poEl = card.querySelector(`[name="adicao[${n}][pais_origem]"]`);
        const poWrapper = poEl?.nextElementSibling;
        const poAc = poWrapper?.classList?.contains('ac-wrapper') ? poWrapper.querySelector('.ac-input') : null;
        const poVal = poAc?.dataset?.value || poEl?.value?.trim();
        if (!poVal) errosClient.push(`Adição ${i + 1}: País de Origem é obrigatório.`);
      });
    }

    const formaPag = form.querySelector('[name="forma_pagamento"]')?.value?.trim();
    if (!formaPag) errosClient.push('Forma de Pagamento é obrigatória (Step 4).');

    // Validação: nome e NIF do Exportador e Destinatário sempre obrigatórios
    const expNome = form.querySelector('[name="exportador_nome"]')?.value?.trim();
    if (!expNome) errosClient.push('Nome do Exportador é obrigatório (Step 3).');
    const expNif = form.querySelector('[name="exportador_codigo"]')?.value?.trim();
    if (!expNif) errosClient.push('NIF do Exportador é obrigatório (Step 3).');
    const destNome = form.querySelector('[name="destinatario_nome"]')?.value?.trim();
    if (!destNome) errosClient.push('Nome do Destinatário é obrigatório (Step 3).');
    const destNif = form.querySelector('[name="destinatario_nif"]')?.value?.trim();
    if (!destNif) errosClient.push('NIF do Destinatário é obrigatório (Step 3).');
  }

  if (errosClient.length > 0) {
    isSubmitting = false;
    showError(errosClient[0]);
    errosClient.forEach(e => console.warn('[Validação DU]', e));
    return;
  }

  // Dados gerais
  const dados = {};
  const formData = new FormData(form);
  for (const [k, v] of formData.entries()) {
    if (!k.startsWith('adicao[')) {
      const el = form.querySelector(`[name="${k}"]`);
      const wrapper = el?.nextElementSibling;
      const ac = wrapper?.classList?.contains('ac-wrapper') ? wrapper.querySelector('.ac-input') : null;
      dados[k] = ac?.dataset?.value || v;
    }
  }

  // Adições — recolher como array
  const cards = document.querySelectorAll('[data-adicao]');
  const adicoes = [];
  cards.forEach(card => {
    const n = card.dataset.adicao;
    const ad = {};
    card.querySelectorAll('[name]').forEach(el => {
      const nome = el.name.replace(`adicao[${n}][`, '').replace(']', '');
      const wrapper = el.nextElementSibling;
      const ac = wrapper?.classList?.contains('ac-wrapper') ? wrapper.querySelector('.ac-input') : null;
      ad[nome] = ac?.dataset?.value || el.value;
    });
    // Converter impostos_json de string para objecto (se existir)
    if (ad.impostos_json) {
      try { ad.impostos = JSON.parse(ad.impostos_json); } catch(e) {}
      delete ad.impostos_json;
    }
    adicoes.push(ad);
  });
  dados.adicoes = adicoes;

  // Totais calculados — preferir campos hidden fiáveis (_calc_*) gerados por calcularTaxas()
  // Se o cálculo ainda não foi executado, executar agora de forma síncrona
  const calcDone = document.getElementById('_calc_done')?.value === '1';
  if (!calcDone && cards.length > 0) {
    // Executar cálculo silenciosamente (sem toast de sucesso)
    try { calcularTaxas(); } catch(e) { console.warn('calcularTaxas falhou:', e); }
  }

  function _parsHidden(id) {
    return parseFloat(document.getElementById(id)?.value || '0') || 0;
  }
  function _parsKZ(id) {
    const el = document.getElementById(id);
    if (!el) return 0;
    const txt = (el.textContent || el.value || '').replace(/[^\d,\.]/g, '').replace(',', '.');
    return parseFloat(txt) || 0;
  }

  // Usar campos hidden se disponíveis, senão fallback para spans visíveis
  const totais = {
    derimp : _parsHidden('_calc_total_derimp') || _parsKZ('valor_direitos'),
    iec    : _parsHidden('_calc_total_iec')    || _parsKZ('valor_iec'),
    emgead : _parsHidden('_calc_total_emgead') || _parsKZ('valor_emolumentos'),
    direxp : _parsHidden('_calc_total_direxp') || _parsKZ('valor_direxp'),
    iva    : _parsHidden('_calc_total_iva')    || _parsKZ('valor_iva'),
    total  : _parsHidden('_calc_total_geral')  || _parsKZ('total_geral'),
  };

  // UUID da DU em edição (se existir)
  const duUuid = document.getElementById('du_uuid_hidden')?.value || null;

  const payload = { uuid: duUuid, submeter, dados, totais };

  fetch('/du/guardar/', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': _getCsrf(),
      'X-Requested-With': 'XMLHttpRequest',
    },
    body: JSON.stringify(payload),
  })
  .then(r => {
    // Verificar se a sessão expirou (401 Unauthorized)
    if (r.status === 401) {
      showError('Sessão expirada. A redirecionar para o login...');
      setTimeout(() => {
        window.location.href = '/login/';
      }, 2000);
      return Promise.reject('Sessão expirada');
    }
    
    // Verificar se não tem permissão (403 Forbidden)
    if (r.status === 403) {
      showError('Sem permissão para realizar esta operação');
      return Promise.reject('Sem permissão');
    }
    
    return r.json();
  })
  .then(d => {
    if (d.sucesso) {
      // Guardar UUID para edições subsequentes
      let hiddenUuid = document.getElementById('du_uuid_hidden');
      if (!hiddenUuid) {
        hiddenUuid = document.createElement('input');
        hiddenUuid.type = 'hidden';
        hiddenUuid.id   = 'du_uuid_hidden';
        document.getElementById('formDU').appendChild(hiddenUuid);
      }
      hiddenUuid.value = d.uuid;

      // Mostrar código de processo em destaque
      if (d.codigo_processo) {
        let cpEl = document.getElementById('du_codigo_processo_display');
        if (!cpEl) {
          cpEl = document.createElement('div');
          cpEl.id = 'du_codigo_processo_display';
          cpEl.style.cssText = [
            'position:fixed', 'bottom:80px', 'right:24px',
            'background:#0f172a', 'color:#fff',
            'padding:12px 20px', 'border-radius:14px',
            'font-size:0.85rem', 'z-index:9999',
            'box-shadow:0 4px 24px rgba(0,0,0,0.35)',
            'border:1px solid rgba(255,255,255,0.1)',
          ].join(';');
          document.body.appendChild(cpEl);
        }
        cpEl.innerHTML = `
          <div style="opacity:0.6;font-size:0.7rem;margin-bottom:2px;">Código do Processo</div>
          <div style="font-size:1.3rem;font-weight:800;letter-spacing:3px;font-family:monospace;">${d.codigo_processo}</div>
          <div style="opacity:0.5;font-size:0.65rem;margin-top:2px;">Guarde este código para localizar a DU</div>`;
        cpEl.style.display = 'block';
        setTimeout(() => { if (cpEl) cpEl.style.display = 'none'; }, 8000);
      }

      if (submeter) {
        showSuccess(`DU ${d.numero_du} submetida e aprovada!`);
        setTimeout(() => { window.location.href = '/du/lista/'; }, 1800);
      } else {
        isSubmitting = false;
        showSuccess('Rascunho guardado! Código: ' + (d.codigo_processo || ''));
      }
    } else {
      isSubmitting = false;
      showError(d.erro || 'Erro ao guardar');
      // Mostrar erros de validação server-side se disponíveis
      if (d.erros && Array.isArray(d.erros)) {
        d.erros.forEach(msg => console.warn('[Validação]', msg));
      }
    }
  })
  .catch(err => {
    isSubmitting = false;
    if (err !== 'Sessão expirada' && err !== 'Sem permissão') {
      showError('Erro de ligação ao servidor');
    }
  });
}

function _getCsrf() {
  const el = document.querySelector('[name=csrfmiddlewaretoken]');
  return el ? el.value : '';
}

// Função para alternar painel de cálculos
function togglePainelCalculos() {
  // Redireciona para a função principal
  toggleSidebar();
}

// Garantir que as funções estejam disponíveis globalmente
window.guardarRascunho = guardarRascunho;
window._submeterDU = _submeterDU;

// ── Auto-save de rascunho a cada 2 minutos ──────────────────────────────────
let autoSaveTimer = null;
let formChanged = false;
let isSubmitting = false;

function iniciarAutoSave() {
  // Marcar formulário como alterado quando qualquer campo muda
  const form = document.getElementById('formDU');
  if (form) {
    form.addEventListener('input', function() {
      formChanged = true;
    });
    
    form.addEventListener('change', function() {
      formChanged = true;
    });
  }
  
  // Auto-save a cada 2 minutos se houver alterações
  autoSaveTimer = setInterval(function() {
    if (formChanged && !isSubmitting) {
      console.log('🔄 Auto-save: Guardando rascunho automaticamente...');
      guardarRascunho();
      formChanged = false;
    }
  }, 2 * 60 * 1000); // 2 minutos
}

// Iniciar auto-save e inicializar campos automáticos quando a página carregar
document.addEventListener('DOMContentLoaded', function() {
  // Inicializar data atual no campo data_campo54
  var dataField = document.getElementById('data_campo54');
  if (dataField && !dataField.value) {
    dataField.value = new Date().toISOString().split('T')[0];
  }

  // Inicializar estância de destino com o valor atual da estância (se já preenchido)
  var estanciaSelect = document.getElementById('estancia');
  var estanciaDestino = document.getElementById('estancia_destino');
  if (estanciaDestino && estanciaSelect && estanciaSelect.value) {
    var label = estanciaSelect.options[estanciaSelect.selectedIndex];
    estanciaDestino.value = label ? label.text : estanciaSelect.value;
  }

  // Quando a estância principal mudar, atualizar estância de destino
  if (estanciaSelect) {
    estanciaSelect.addEventListener('change', function() {
      if (estanciaDestino && this.value) {
        var label = this.options[this.selectedIndex];
        estanciaDestino.value = label ? label.text : this.value;
      }
    });
  }

  // Quando o regime mudar, atualizar destino
  var regimeSelect = document.getElementById('regime_aduaneiro');
  if (regimeSelect) {
    regimeSelect.addEventListener('change', function() {
      atualizarDestinoRegime();
    });
  }

  setTimeout(iniciarAutoSave, 1000);
});

// Limpar timer ao sair da página
window.addEventListener('beforeunload', function() {
  if (autoSaveTimer) {
    clearInterval(autoSaveTimer);
  }
});
window.atualizarCodigoIsencao = atualizarCodigoIsencao;
window.toggleContainer = toggleContainer;
window.consultarVinhetas = consultarVinhetas;
window.selecionarVinheta = selecionarVinheta;
window.consultarCodigoPautal = consultarCodigoPautal;
window.pesquisaAutomaticaVinheta = pesquisaAutomaticaVinheta;
window.adicionarContainer = adicionarContainer;
window.removerContainer = removerContainer;
// Função para atualizar código de isenção
function atualizarCodigoIsencao() {
  const procedimentoSelect = document.getElementById('codigo_procedimento');
  const isencaoSelect = document.getElementById('codigo_isencao');
  
  if (!procedimentoSelect || !isencaoSelect) return;
  
  const procedimento = procedimentoSelect.value;
  
  // Limpar opções de isenção
  isencaoSelect.innerHTML = '<option value="">Selecione...</option>';
  
  // Códigos de isenção baseados no procedimento (usando códigos completos)
  const isencoesPorProcedimento = {
    '1000': [
      { codigo: '001', descricao: 'Isenção Diplomática' },
      { codigo: '002', descricao: 'Isenção Organizações Internacionais' }
    ],
    '2000': [
      { codigo: '014', descricao: 'Exportação Temporária' },
      { codigo: '015', descricao: 'Admissão Temporária' }
    ],
    '4000': [
      { codigo: '001', descricao: 'Isenção Diplomática' },
      { codigo: '002', descricao: 'Isenção Organizações Internacionais' },
      { codigo: '003', descricao: 'Isenção Cooperação Técnica' }
    ],
    '5000': [
      { codigo: '014', descricao: 'Importação Temporária' },
      { codigo: '015', descricao: 'Admissão Temporária' }
    ]
  };
  
  const isencoes = isencoesPorProcedimento[procedimento] || [];
  
  isencoes.forEach(isencao => {
    const option = document.createElement('option');
    option.value = isencao.codigo;
    option.textContent = `${isencao.codigo} - ${isencao.descricao}`;
    isencaoSelect.appendChild(option);
  });
  
  if (isencoes.length > 0) {
    showInfo(`${isencoes.length} código(s) de isenção disponível(is) para este procedimento`);
  }
}

// Função para alternar containers
function toggleContainer(selectElement) {
  const containerDiv = document.getElementById('containerNumDiv');
  
  if (!containerDiv) return;
  
  if (selectElement.value === '1') {
    // Mostrar seção de containers
    containerDiv.classList.remove('hidden');
  } else {
    // Ocultar seção de containers
    containerDiv.classList.add('hidden');
  }
}

// Função para alternar containers com radio button
function toggleContainerRadio(radioElement) {
  const containerDiv = document.getElementById('containerNumDiv');
  const containerList = document.getElementById('container_list');
  
  if (!containerDiv || !containerList) return;
  
  if (radioElement.value === '1') {
    // Mostrar seção de containers
    containerDiv.classList.remove('hidden');
    
    // Adicionar container padrão se não existir
    if (containerList.children.length === 0) {
      adicionarContainer();
    }
  } else {
    // Ocultar seção de containers
    containerDiv.classList.add('hidden');
  }
}

/* ============================================================
   FUNÇÕES DE REPARTIÇÃO DE FRETE E SEGURO
============================================================ */

/**
 * Handle repartition mode change for freight or insurance
 * @param {string} tipo - 'frete' or 'seguro'
 * @param {string} modo - 'sem_reparticao', 'valor', or 'peso'
 */
function handleReparticaoChange(tipo, modo) {
  console.log(`Repartição ${tipo} mudou para: ${modo}`);
  
  if (modo === 'sem_reparticao') {
    // Habilitar campos em todas as adições
    habilitarCamposAdicao(tipo, true);
    // Limpar valores calculados
    limparValoresRepartidos(tipo);
  } else {
    // Calcular valores automaticamente PRIMEIRO
    calcularReparticao(tipo, modo);
    // DEPOIS desabilitar campos em todas as adições
    habilitarCamposAdicao(tipo, false);
  }
}

/**
 * Enable/disable freight or insurance fields in all adições
 * @param {string} tipo - 'frete' or 'seguro'
 * @param {boolean} habilitar - true to enable, false to disable
 */
function habilitarCamposAdicao(tipo, habilitar) {
  const cards = document.querySelectorAll('#adicoes_wrapper .adicao-card-wrapper');
  
  cards.forEach(card => {
    const n = card.dataset.adicao;
    if (!n) return;
    
    const campoValor = document.getElementById(`${tipo}_${n}`);
    const campoMoeda = document.getElementById(`moeda_${tipo}_${n}`);
    const campoKz = document.getElementById(`${tipo}_kz_${n}`);
    
    if (campoValor) {
      campoValor.disabled = !habilitar;
      campoValor.classList.toggle('calc-field', !habilitar);
      // Adicionar feedback visual
      if (!habilitar) {
        campoValor.style.backgroundColor = '#f3f4f6';
        campoValor.style.cursor = 'not-allowed';
        campoValor.readOnly = true;  // Adicionar readOnly para garantir
      } else {
        campoValor.style.backgroundColor = '';
        campoValor.style.cursor = '';
        campoValor.readOnly = false;
      }
    }
    if (campoMoeda) {
      campoMoeda.disabled = !habilitar;
      if (!habilitar) {
        campoMoeda.style.backgroundColor = '#f3f4f6';
        campoMoeda.style.cursor = 'not-allowed';
        campoMoeda.readOnly = true;
      } else {
        campoMoeda.style.backgroundColor = '';
        campoMoeda.style.cursor = '';
        campoMoeda.readOnly = false;
      }
    }
    if (campoKz) {
      campoKz.disabled = !habilitar;
      campoKz.classList.toggle('calc-field', !habilitar);
      // Adicionar feedback visual para campo KZ também
      if (!habilitar) {
        campoKz.style.backgroundColor = '#f3f4f6';
        campoKz.style.cursor = 'not-allowed';
        campoKz.readOnly = true;
      } else {
        campoKz.style.backgroundColor = '';
        campoKz.style.cursor = '';
        campoKz.readOnly = false;
      }
    }
  });
  
  }

/**
 * Clear repartitioned values from all adições
 * @param {string} tipo - 'frete' or 'seguro'
 */
function limparValoresRepartidos(tipo) {
  const cards = document.querySelectorAll('#adicoes_wrapper .adicao-card-wrapper');
  
  cards.forEach(card => {
    const n = card.dataset.adicao;
    if (!n) return;
    
    const campoValor = document.getElementById(`${tipo}_${n}`);
    const campoKz = document.getElementById(`${tipo}_kz_${n}`);
    
    if (campoValor) {
      campoValor.value = '';
      campoValor.style.backgroundColor = '';
      campoValor.style.cursor = '';
      campoValor.classList.remove('calc-field');
      campoValor.disabled = false;
    }
    if (campoKz) {
      campoKz.value = '';
      campoKz.style.backgroundColor = '';
      campoKz.style.cursor = '';
      campoKz.classList.remove('calc-field');
      campoKz.disabled = false;
    }
  });
  
  }

/**
 * Obter taxa de câmbio com fallback e cache
 * @param {string} moeda - 'USD', 'EUR', etc.
 * @returns {Promise<number>} - Taxa de câmbio para AOA (KZ)
 */
async function obterTaxaCambioDinamica(moeda) {
  if (moeda === 'AOA' || moeda === 'KZ') return 1; // AOA para AOA é 1
  
  // Cache de taxas (válido por 1 hora)
  const cacheKey = `taxa_${moeda}_AOA`;
  const cached = localStorage.getItem(cacheKey);
  if (cached) {
    const { taxa, timestamp } = JSON.parse(cached);
    const agora = Date.now();
    const umaHora = 60 * 60 * 1000; // 1 hora em ms
    
    if (agora - timestamp < umaHora) {
      console.log(`💾 Taxa de câmbio do cache: ${moeda} → AOA = ${taxa}`);
      return taxa;
    }
  }
  
  // Taxas de fallback (atualizadas manualmente quando necessário)
  const taxasFallback = {
    'USD': 850.0,  // Aproximadamente 850 KZ por USD
    'EUR': 920.0,  // Aproximadamente 920 KZ por EUR
    'GBP': 1050.0, // Aproximadamente 1050 KZ por GBP
    'BRL': 160.0,  // Aproximadamente 160 KZ por BRL
    'ZAR': 45.0    // Aproximadamente 45 KZ por ZAR
  };
  
  try {
    const response = await fetch(`https://api-sic-fields.netsulwel.tech/converter-moeda?valor=1&de=${moeda}&para=AOA`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    
    const data = await response.json();
    const taxa = data.taxa_cambio || 0;
    
    if (taxa > 0) {
      // Salvar no cache
      localStorage.setItem(cacheKey, JSON.stringify({
        taxa: taxa,
        timestamp: Date.now()
      }));
      
      console.log(`📡 Taxa de câmbio obtida via API: ${moeda} → AOA = ${taxa}`);
      return taxa;
    } else {
      throw new Error('Taxa inválida da API');
    }
  } catch (error) {
    console.warn(`⚠️ API de câmbio falhou para ${moeda}, usando fallback:`, error);
    
    const taxaFallback = taxasFallback[moeda] || 0;
    if (taxaFallback > 0) {
      console.log(`🔄 Usando taxa de fallback: ${moeda} → AOA = ${taxaFallback}`);
      
      // Mostrar aviso ao usuário
      if (typeof showWarning === 'function') {
        showWarning(`Taxa de câmbio obtida offline para ${moeda}. Verifique se está atualizada.`);
      }
      
      return taxaFallback;
    } else {
      console.error(`❌ Nenhuma taxa disponível para ${moeda}`);
      
      // Mostrar erro ao usuário
      if (typeof showError === 'function') {
        showError(`Erro: Taxa de câmbio não disponível para ${moeda}. Contacte o suporte.`);
      }
      
      return 0;
    }
  }
}

/**
 * Calculate repartitioned values for freight or insurance
 * @param {string} tipo - 'frete' or 'seguro'
 * @param {string} modo - 'valor' or 'peso'
 */
async function calcularReparticao(tipo, modo) {
  // Busca o valor TOTAL do frete ou seguro já convertido para KZ do STEP 1 (Geral)
  const campoTotalKz = document.getElementById(`valor_${tipo}_kz`);
  const valorTotal = parseFloat(campoTotalKz?.value) || 0;
  
  console.log(`=== INÍCIO CÁLCULO REPARTIÇÃO ${tipo.toUpperCase()} ===`);
  console.log(`Modo: ${modo}`);
  console.log(`Campo encontrado: valor_${tipo}_kz =`, campoTotalKz ? 'SIM' : 'NÃO');
  console.log(`Valor do campo: "${campoTotalKz?.value}"`);
  console.log(`Valor Total (${tipo}_kz): ${valorTotal}`);
  
  // Tentar buscar dos campos originais também para debug
  const campoOriginal = document.getElementById(`valor_${tipo}`);
  const valorOriginal = parseFloat(campoOriginal?.value) || 0;
  const campoMoeda = document.getElementById(`moeda_${tipo}`);
  const moeda = campoMoeda?.value || 'USD';
  
  console.log(`Campo original: valor_${tipo} =`, campoOriginal ? 'SIM' : 'NÃO');
  console.log(`Valor original: "${campoOriginal?.value}"`);
  console.log(`Valor Original parseado: ${valorOriginal}`);
  console.log(`Moeda: ${moeda}`);
  
  if (valorTotal <= 0) {
    console.log(`VALOR TOTAL INVÁLIDO, CANCELANDO CÁLCULO`);
    console.log(`Tentando converter valor original usando API dinâmica...`);
    if (valorOriginal > 0) {
      try {
        // Buscar taxa de câmbio dinamicamente da API
        const taxaCambio = await obterTaxaCambioDinamica(moeda);
        
        if (taxaCambio > 0) {
          const valorConvertido = valorOriginal * taxaCambio;
          if (campoTotalKz) {
            campoTotalKz.value = valorConvertido.toFixed(2);
            console.log(`✅ Campo ${tipo}_kz preenchido com API: ${valorOriginal} ${moeda} × ${taxaCambio} = ${valorConvertido.toFixed(2)} KZ`);
            
            // Atualizar campo de câmbio também
            const campoCambio = document.getElementById(`cambio_${tipo}`);
            if (campoCambio) {
              campoCambio.value = taxaCambio.toFixed(4);
              console.log(`📡 Taxa de câmbio atualizada: ${taxaCambio.toFixed(4)}`);
            }
            
            // Chamar novamente com o valor convertido
            setTimeout(() => calcularReparticao(tipo, modo), 100);
            return;
          }
        } else {
          console.log(`❌ Taxa de câmbio inválida para ${moeda}`);
          
          // Mostrar erro específico ao usuário
          if (typeof showError === 'function') {
            showError(`Erro na conversão de ${moeda} para KZ. Verifique a conexão ou contacte o suporte.`);
          }
        }
      } catch (error) {
        console.error(`❌ Erro ao converter valor via API:`, error);
        
        // Mostrar erro ao usuário
        if (typeof showError === 'function') {
          showError(`Erro na conversão de moeda. Verifique a conexão com a internet.`);
        }
      }
    }
    
    // Se chegou aqui, não há valor válido para repartir
    console.log(`❌ CANCELANDO REPARTIÇÃO: Valor total de ${tipo} é 0 ou inválido`);
    return;
  }

  // Buscar todas as adições
  const adicoes = document.querySelectorAll('.adicao-card-wrapper');
  if (adicoes.length === 0) {
    console.log(`❌ Nenhuma adição encontrada para repartir ${tipo}`);
    return;
  }

  console.log(`📊 Repartindo ${valorTotal.toFixed(2)} KZ de ${tipo} entre ${adicoes.length} adições`);

  let totalBase = 0;
  const valoresBase = [];

  // Calcular base total (peso ou valor FOB)
  adicoes.forEach((adicao, index) => {
    let valorBase = 0;
    
    if (modo === 'peso') {
      const campoBase = adicao.querySelector('[name$="_peso_liquido"]');
      valorBase = parseFloat(campoBase?.value) || 0;
    } else if (modo === 'valor') {
      const campoBase = adicao.querySelector('[name$="_fob_kz"]');
      valorBase = parseFloat(campoBase?.value) || 0;
    }
    
    valoresBase.push(valorBase);
    totalBase += valorBase;
    
    console.log(`  Adição ${index + 1}: Base = ${valorBase} ${modo === 'peso' ? 'kg' : 'KZ'}`);
  });

  console.log(`📊 Total da base (${modo}): ${totalBase} ${modo === 'peso' ? 'kg' : 'KZ'}`);

  if (totalBase <= 0) {
    console.log(`❌ Base total inválida para repartição por ${modo}`);
    
    if (typeof showError === 'function') {
      const tipoBase = modo === 'peso' ? 'peso líquido' : 'valor FOB';
      showError(`Não é possível repartir ${tipo} por ${tipoBase}: valores não preenchidos ou inválidos.`);
    }
    return;
  }

  // Repartir proporcionalmente
  let totalRepartido = 0;
  
  adicoes.forEach((adicao, index) => {
    const valorBase = valoresBase[index];
    const proporcao = valorBase / totalBase;
    const valorRepartido = valorTotal * proporcao;
    
    // Encontrar campo de destino
    const campoDestino = adicao.querySelector(`[name$="_${tipo}_kz"]`);
    if (campoDestino) {
      campoDestino.value = valorRepartido.toFixed(2);
      totalRepartido += valorRepartido;
      
      console.log(`  ✅ Adição ${index + 1}: ${valorBase} ${modo === 'peso' ? 'kg' : 'KZ'} (${(proporcao * 100).toFixed(1)}%) → ${valorRepartido.toFixed(2)} KZ`);
      
      // Disparar evento de mudança para recalcular impostos
      campoDestino.dispatchEvent(new Event('input', { bubbles: true }));
    } else {
      console.log(`❌ Campo ${tipo}_kz não encontrado na adição ${index + 1}`);
    }
  });

  console.log(`📊 Total repartido: ${totalRepartido.toFixed(2)} KZ (diferença: ${Math.abs(valorTotal - totalRepartido).toFixed(2)} KZ)`);
  console.log(`=== FIM CÁLCULO REPARTIÇÃO ${tipo.toUpperCase()} ===`);
  
  // Mostrar sucesso ao usuário
  if (typeof showSuccess === 'function') {
    const tipoBase = modo === 'peso' ? 'peso líquido' : 'valor FOB';
    showSuccess(`${tipo.charAt(0).toUpperCase() + tipo.slice(1)} repartido por ${tipoBase}: ${valorTotal.toFixed(2)} KZ entre ${adicoes.length} adições`);
  }
}

// ── Código legado removido (duplicado) ──────────────────────────────────────
// A função calcularReparticao acima substitui completamente a versão anterior.

// Event listeners principais
document.addEventListener('DOMContentLoaded', function() {
  console.log('DOM carregado - inicializando funções');

  // ── Pré-carregar pauta aduaneira imediatamente ──────────────────────────
  preCarregarPauta();

  // Event listener para cálculo automático quando peso_liquido for alterado no Step 2
  function setupPesoLiquidoListeners() {
    // Observer para detectar novas adições
    const observer = new MutationObserver(function(mutations) {
      mutations.forEach(function(mutation) {
        if (mutation.addedNodes.length) {
          mutation.addedNodes.forEach(function(node) {
            if (node.nodeType === 1 && node.classList && node.classList.contains('adicao-card-wrapper')) {
              // Nova adição adicionada - configurar listeners
              setupPesoLiquidoListener(node);
            }
          });
        }
      });
    });

    // Observar o wrapper de adições
    const adicoesWrapper = document.getElementById('adicoes_wrapper');
    if (adicoesWrapper) {
      observer.observe(adicoesWrapper, { childList: true, subtree: true });
      
      // Configurar adições existentes
      const adicoesExistentes = adicoesWrapper.querySelectorAll('.adicao-card-wrapper');
      adicoesExistentes.forEach(setupPesoLiquidoListener);
    }
  }

  // Configurar listener para uma adição específica
  function setupPesoLiquidoListener(adicaoCard) {
    const n = adicaoCard.dataset.adicao;
    const campoPeso = adicaoCard.querySelector(`#peso_liquido_${n}`);
    
    if (campoPeso) {
      console.log(`🔧 Configurando listener para peso_liquido_${n}`);
      
      campoPeso.addEventListener('input', function() {
        clearTimeout(campoPeso._reparticaoTimer);
        campoPeso._reparticaoTimer = setTimeout(function() {
          console.log(`⚡ Peso alterado na adição ${n} - recalculando repartição`);
          
          // Verificar se o modo de repartição está em "peso" para frete ou seguro
          ['frete', 'seguro'].forEach(tipo => {
            const modoReparticao = document.getElementById(`reparticao_${tipo}`)?.value;
            if (modoReparticao === 'peso') {
              console.log(`🔄 Recalculando ${tipo} em modo peso`);
              calcularReparticao(tipo, 'peso');
            }
          });
        }, 500); // Debounce de 500ms
      });
    }
  }

  // Inicializar os listeners de peso
  setupPesoLiquidoListeners();

  // Calcular valores convertidos automaticamente quando FOB/Seguro/Frete mudarem
  ['valor_fob', 'moeda_fob', 'valor_seguro', 'moeda_seguro', 'valor_frete', 'moeda_frete'].forEach(fieldId => {
    const field = document.getElementById(fieldId);
    if (field) {
      field.addEventListener('change', function() {
        if (typeof calcularValoresConvertidos === 'function') {
          calcularValoresConvertidos().then(() => {
            const montante = parseFloat(document.getElementById('montante_aduaneiro_kz')?.value) || 0;
            if (montante > 0 && currentStep === 4) calcularTaxas();
          });
        }
        
        // Recalcular repartição se necessário
        if (fieldId === 'valor_seguro' || fieldId === 'valor_frete') {
          const tipo = fieldId.replace('valor_', '');
          const modoReparticao = document.getElementById(`reparticao_${tipo}`)?.value;
          if (modoReparticao && modoReparticao !== 'sem_reparticao') {
            calcularReparticao(tipo, modoReparticao);
          }
        }
      });
      field.addEventListener('input', function() {
        clearTimeout(field._calcTimer);
        field._calcTimer = setTimeout(function() {
          if (typeof calcularValoresConvertidos === 'function') {
            calcularValoresConvertidos().then(() => {
              const montante = parseFloat(document.getElementById('montante_aduaneiro_kz')?.value) || 0;
              if (montante > 0 && currentStep === 4) calcularTaxas();
            });
          }
          
          // Recalcular repartição se necessário
          if (fieldId === 'valor_seguro' || fieldId === 'valor_frete') {
            const tipo = fieldId.replace('valor_', '');
            const modoReparticao = document.getElementById(`reparticao_${tipo}`)?.value;
            if (modoReparticao && modoReparticao !== 'sem_reparticao') {
              calcularReparticao(tipo, modoReparticao);
            }
          }
        }, 600);
      });
    }
  });

  // Event listeners para repartição de frete e seguro
  const reparticaoFreteSelect = document.getElementById('reparticao_frete');
  const reparticaoSeguroSelect = document.getElementById('reparticao_seguro');
  
  if (reparticaoFreteSelect) {
    reparticaoFreteSelect.addEventListener('change', function() {
      handleReparticaoChange('frete', this.value);
    });
  }
  
  if (reparticaoSeguroSelect) {
    reparticaoSeguroSelect.addEventListener('change', function() {
      handleReparticaoChange('seguro', this.value);
    });
  }

  // Inicializar pesquisa automática de vinhetas
  pesquisaAutomaticaVinheta();

  // Preencher data automaticamente
  const dataField = document.getElementById('data_campo54');
  if (dataField && !dataField.value) {
    dataField.value = new Date().toISOString().split('T')[0];
  }

  // Inicializar primeiro passo
  updateStep();
});

// carregarEstancias está definida no du.html (inline script) — não duplicar aqui