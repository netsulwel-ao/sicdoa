/* ═══════════════════════════════════════════════════════════════
   SALA_ASSEMBLEIA.JS — Google Meet-like Assembly Room
   Controlo de vídeo, grelha, chat, votações, moderação
   ═══════════════════════════════════════════════════════════════ */

(function() {
  'use strict';

  // ── Config ─────────────────────────────────────────────────
  var CONFIG = {
    ASSEMBLEIA_ID: window.MEET_DATA?.assembleia_id || 0,
    USER_NOME: window.MEET_DATA?.user_nome || 'Anónimo',
    USER_ID: window.MEET_DATA?.user_id || 0,
    PAPEL: window.MEET_DATA?.papel || 'Visualizador',
    LIVEKIT_ROOM: window.MEET_DATA?.livekit_room || '',
    LIVEKIT_TOKEN: window.MEET_DATA?.livekit_token || '',
    LIVEKIT_URL: window.MEET_DATA?.livekit_url || '',
    CSRF: document.querySelector('[name=csrfmiddlewaretoken]')?.value || '',
    WS_URL: window.MEET_DATA?.ws_url || '',
    MINHAS_PROCURACAO: window.MEET_DATA?.minhas_procuracao || [],
  };

  // ── State ─────────────────────────────────────────────────
  var state = {
    room: null,
    connected: false,
    participantes: {},
    participantesPresenca: [],
    participantesMesa: [],
    pautas: [],
    votacaoAtiva: null,
    jaVotou: {},
    chatAberto: false,
    sideAba: 'chat',
    mensagensChat: [],
    chatNaoLidas: 0,
    votosIndividuais: [],
    maosLevantadas: {},
    speakerId: null,
    screenShareAtiva: false,
    screenShareParticipant: null,
    elapsedTimer: null,
    totalParticipantes: 0,
    quorum: { presentes: 0, minimo: 0, atingido: false },
    // Paginação para grandes audiências
    gridPage: 0,
    gridPageSize: 50,
    totalPaginas: 1,
    roleColors: {
      'Presidente': '#22c55e','Vice-Presidente':'#3b82f6','1 Secretário':'#a855f7',
      '2 Secretário':'#a855f7','Secretário':'#f59e0b','Vogal':'#6b7280'
    },
    avatarColors: [
      '#22c55e','#3b82f6','#ef4444','#f59e0b','#a855f7','#ec4899',
      '#14b8a6','#f97316','#6366f1','#84cc16'
    ],
  };

  // ── DOM refs (preenchido no init) ──────────────────────────
  var DOM = {};

  // ── INIT ───────────────────────────────────────────────────
  function init() {
    if (!CONFIG.ASSEMBLEIA_ID) return;

    DOM.grid = document.getElementById('meet-grid');
    DOM.screenShareArea = document.getElementById('screen-share-area');
    DOM.topbar = document.getElementById('meet-topbar');
    DOM.bottombar = document.getElementById('meet-bottombar');
    DOM.sidepanel = document.getElementById('meet-sidepanel');
    DOM.panelBody = document.getElementById('panel-body');
    DOM.chatInput = document.getElementById('chat-input');
    DOM.chatSend = document.getElementById('chat-send');
    DOM.toastContainer = document.getElementById('meet-toasts');
    DOM.timerEl = document.getElementById('meet-timer');
    DOM.statusBadge = document.getElementById('meet-status-badge');
    DOM.presentesCount = document.getElementById('presentes-count');
    DOM.quorumText = document.getElementById('quorum-text');
    DOM.btnHand = document.getElementById('btn-hand');
    DOM.btnChat = document.getElementById('btn-chat');
    DOM.btnParticipants = document.getElementById('btn-participants');
    DOM.btnVoting = document.getElementById('btn-voting');
    DOM.chatBadge = document.getElementById('chat-badge');
    DOM.btnMic = document.getElementById('btn-mic');
    DOM.btnCam = document.getElementById('btn-cam');
    DOM.btnScreen = document.getElementById('btn-screen');
    DOM.btnEnd = document.getElementById('btn-end');
    DOM.btnFullscreen = document.getElementById('btn-fullscreen');
    DOM.btnSettings = document.getElementById('btn-settings');
    DOM.chatReactions = document.getElementById('chat-reactions');

    // WebSocket
    conectarWebSocket();

    // LiveKit
    if (CONFIG.LIVEKIT_TOKEN) {
      iniciarLiveKit();
    }

    // Timer
    iniciarTimer();

    // Event listeners
    bindEvents();

    // Estado inicial
    if (DOM.statusBadge && DOM.statusBadge.dataset.status === 'Em Curso') {
      DOM.statusBadge.className = 'status-badge live';
    }
  }

  // ── WEBSOCKET ──────────────────────────────────────────────
  var ws = null;
  var wsReconnectTimer = null;

  function conectarWebSocket() {
    if (!CONFIG.WS_URL) return;
    if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return;

    try {
      ws = new WebSocket(CONFIG.WS_URL);

      ws.onopen = function() {
        console.log('[WS] Conectado a', CONFIG.WS_URL);
        if (wsReconnectTimer) { clearTimeout(wsReconnectTimer); wsReconnectTimer = null; }
      };

      ws.onmessage = function(e) {
        try {
          var msg = JSON.parse(e.data);
          tratarMensagemWS(msg);
        } catch(err) { /* ignorar */ }
      };

      ws.onclose = function() {
        ws = null;
        if (!wsReconnectTimer) {
          wsReconnectTimer = setTimeout(conectarWebSocket, 3000);
        }
      };

      ws.onerror = function(e) {
        console.error('[WS] Erro de conexão:', CONFIG.WS_URL, e);
      };
    } catch(e) {
      wsReconnectTimer = setTimeout(conectarWebSocket, 5000);
    }
  }

  function enviarWS(msg) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(msg));
    }
  }

  function tratarMensagemWS(msg) {
    switch (msg.action) {
      case 'chat_message':
      case 'chat_reaction':
        adicionarMensagemChat(msg);
        break;
      case 'raise_hand':
        if (state.participantes[msg.nome]) {
          state.participantes[msg.nome].handRaised = true;
          atualizarTile(msg.nome);
        }
        break;
      case 'lower_hand':
        if (state.participantes[msg.nome]) {
          state.participantes[msg.nome].handRaised = false;
          atualizarTile(msg.nome);
        }
        break;
      case 'quorum':
        atualizarQuorum(msg);
        break;
      case 'votacao_aberta':
        abrirVotacao(msg);
        break;
      case 'votacao_encerrada':
        encerrarVotacao(msg);
        break;
      case 'resultados':
        atualizarResultadosVotacao(msg);
        break;
      case 'votacao_reaberta':
        reabrirVotacao(msg);
        break;
      case 'assembleia_iniciada':
        mostrarToast('Assembleia iniciada automaticamente!', '#22c55e');
        setTimeout(function() { location.reload(); }, 2000);
        break;
      case 'voto_registado':
        adicionarVotoRegistado(msg);
        break;
      case 'chat_historico':
        carregarHistoricoChat(msg.mensagens);
        break;
    }
  }

  // ── LIVEKIT ────────────────────────────────────────────────
  async function iniciarLiveKit() {
    try {
      var LK = window.LivekitClient;
      if (!LK) {
        // LiveKit library not loaded yet
        if (window._lkRetryCount === undefined) window._lkRetryCount = 0;
        window._lkRetryCount++;
        if (window._lkRetryCount > 10) {
          mostrarToast('Biblioteca LiveKit não carregou. Verifique a consola.', '#ef4444');
          return;
        }
        setTimeout(iniciarLiveKit, 500);
        return;
      }

      var room = new LK.Room({
        adaptiveStream: true,
        dynacast: true,
        videoCaptureDefaults: { resolution: LK.VideoPresets.h720.resolution },
      });

      state.room = room;

      room.on(LK.RoomEvent.TrackSubscribed, function(track, pub, participant) {
        if (participant.isLocal) return;
        adicionarTrackParticipante(participant.identity, track);
      });

      room.on(LK.RoomEvent.TrackUnsubscribed, function(track, pub, participant) {
        if (participant.isLocal) return;
        removerTrackParticipante(participant.identity, track);
      });

      room.on(LK.RoomEvent.ParticipantConnected, function(participant) {
        adicionarParticipante(participant);
      });

      room.on(LK.RoomEvent.ParticipantDisconnected, function(participant) {
        removerParticipante(participant.identity);
      });

      room.on(LK.RoomEvent.ActiveSpeakersChanged, function(speakers) {
        atualizarSpeakers(speakers);
      });

      room.on(LK.RoomEvent.Disconnected, function() {
        state.connected = false;
        mostrarToast('Desligado da videoconferência', '#ef4444');
      });

      room.on(LK.RoomEvent.TrackMuted, function(pub, participant) {
        if (participant && pub.kind === 'audio') {
          if (state.participantes[participant.identity]) {
            state.participantes[participant.identity].audioMuted = true;
            atualizarTile(participant.identity);
          }
        }
      });

      room.on(LK.RoomEvent.TrackUnmuted, function(pub, participant) {
        if (participant && pub.kind === 'audio') {
          if (state.participantes[participant.identity]) {
            state.participantes[participant.identity].audioMuted = false;
            atualizarTile(participant.identity);
          }
        }
      });

      room.on(LK.RoomEvent.ConnectionQualityChanged, function(quality, participant) {
        // Indicador de qualidade (excelente/good/poor)
        var id = participant ? participant.identity : null;
        if (id && state.participantes[id]) {
          var qEl = document.getElementById('quality-' + CSS.escape(id));
          if (!qEl) {
            qEl = document.createElement('div');
            qEl.id = 'quality-' + CSS.escape(id);
            qEl.className = 'quality-indicator';
            document.getElementById('tile-' + CSS.escape(id))?.appendChild(qEl);
          }
          qEl.className = 'quality-indicator quality-' + quality;
        }
      });

      await room.connect(CONFIG.LIVEKIT_URL, CONFIG.LIVEKIT_TOKEN);
      state.connected = true;
      console.log('[LiveKit] Conectado à sala', CONFIG.LIVEKIT_ROOM);

      // Ativar mic e cam por defeito
      var localP = room.localParticipant;
      try {
        var camPub = await localP.setCameraEnabled(true);
        console.log('[LiveKit] Câmara ativada', camPub ? 'com publicação' : 'sem publicação');
      } catch(e) {
        console.warn('[LiveKit] Camera error:', e);
        if (e.name === 'NotAllowedError' || e.message?.includes('permission')) {
          mostrarToast('Permissão da câmara negada. Verifique as definições do browser.', '#ef4444');
        } else if (e.name === 'NotFoundError') {
          mostrarToast('Câmara não encontrada neste dispositivo.', '#f59e0b');
        } else {
          mostrarToast('Câmara indisponível: ' + (e.message || 'erro'), '#f59e0b');
        }
      }
      try {
        var micPub = await localP.setMicrophoneEnabled(true);
        console.log('[LiveKit] Microfone ativado', micPub ? 'com publicação' : 'sem publicação');
      } catch(e) {
        console.warn('[LiveKit] Mic error:', e);
        if (e.name === 'NotAllowedError' || e.message?.includes('permission')) {
          mostrarToast('Permissão do microfone negada.', '#ef4444');
        } else if (e.name === 'NotFoundError') {
          mostrarToast('Microfone não encontrado.', '#f59e0b');
        } else {
          mostrarToast('Microfone indisponível: ' + (e.message || 'erro'), '#f59e0b');
        }
      }

      // Adicionar participantes já conectados
      if (room.remoteParticipants && room.remoteParticipants.forEach) {
        room.remoteParticipants.forEach(function(p) { adicionarParticipante(p); });
      } else {
        console.warn('[LiveKit] remoteParticipants não disponível');
      }

      // Adicionar local
      adicionarParticipanteLocal();

      // Atualizar layout da grelha
      atualizarGrid();

      // Mostrar toast
      mostrarToast('Conectado à sala', '#22c55e');

    } catch(e) {
      mostrarToast('Erro ao conectar vídeo: ' + (e.message || 'erro'), '#ef4444');
    }
  }

  // CSS.escape polyfill
  if (!CSS.escape) {
    CSS.escape = function(value) {
      return String(value).replace(/([^\w-])/g, '\\$1');
    };
  }

  function adicionarParticipanteLocal() {
    var r = state.room;
    if (!r) return;
    var p = r.localParticipant;
    var identity = p.identity;

    if (state.participantes[identity]) return;

    state.totalParticipantes++;
    // Manter na página atual se possível
    if (state.totalParticipantes <= state.gridPageSize) state.gridPage = 0;

    var nome = identity || CONFIG.USER_NOME;
    var cor = obterCorAvatar(identity);
    var iniciais = obterIniciais(nome);
    var papel = obterPapel(identity);

    state.participantes[identity] = {
      identity: identity,
      nome: nome,
      isLocal: true,
      participant: p,
      videoTrack: null,
      audioMuted: !p.isMicrophoneEnabled,
      videoMuted: !p.isCameraEnabled,
      isSpeaking: false,
      handRaised: false,
      avatarColor: cor,
      iniciais: iniciais,
      papel: papel,
    };

    // Monitorizar alterações locais
    var LK = window.LivekitClient;
    var evtTrackPub = LK.ParticipantEvent?.TrackPublished || 'trackPublished';
    var evtTrackUnpub = LK.ParticipantEvent?.TrackUnpublished || 'trackUnpublished';

    p.on(evtTrackPub, function(pub) {
      console.log('[LiveKit] TrackPublished local', pub.kind, identity);
      if (pub.kind === 'video') {
        state.participantes[identity].videoTrack = pub.track;
        state.participantes[identity].videoMuted = false;
        atualizarTile(identity);
      }
    });
    p.on(evtTrackUnpub, function(pub) {
      console.log('[LiveKit] TrackUnpublished local', pub.kind, identity);
      if (pub.kind === 'video') {
        state.participantes[identity].videoMuted = true;
        state.participantes[identity].videoTrack = null;
        atualizarTile(identity);
      }
    });
    // Para tracks que já existem (ex: ao reconectar)
    var pubs = null;
    if (p.trackPublications && p.trackPublications.forEach) pubs = p.trackPublications;
    else if (p.videoTracks) pubs = p.videoTracks;
    else if (p.tracks) pubs = p.tracks;
    if (pubs) {
      pubs.forEach(function(pub) {
        if (pub && pub.track && pub.track.kind === 'video') {
          state.participantes[identity].videoTrack = pub.track;
          state.participantes[identity].videoMuted = false;
          console.log('[LiveKit] Track existente encontrada para', identity);
        }
      });
    }
    // Debug: mostrar quantas tracks temos
    console.log('[LiveKit] trackPublications size:', p.trackPublications?.size || p.trackPublications?.length || 0);

    criarTile(identity, nome, cor, iniciais, papel, true);
    atualizarGrid();
    atualizarListaParticipantes();
    atualizarContagem();
  }

  function adicionarParticipante(participant) {
    var identity = participant.identity;
    if (state.participantes[identity]) return;

    state.totalParticipantes++;

    var nome = participant.name || identity;
    var cor = obterCorAvatar(identity);
    var iniciais = obterIniciais(nome);
    var papel = obterPapel(identity);

    state.participantes[identity] = {
      identity: identity,
      nome: nome,
      isLocal: false,
      participant: participant,
      videoTrack: null,
      audioMuted: !participant.isMicrophoneEnabled,
      videoMuted: !participant.isCameraEnabled,
      isSpeaking: false,
      handRaised: false,
      avatarColor: cor,
      iniciais: iniciais,
      papel: papel,
    };

    // Verificar tracks existentes
    var remoteTracks = participant.videoTracks || participant.trackPublications || [];
    if (remoteTracks.forEach) {
      remoteTracks.forEach(function(pub) {
        if (pub && pub.track && pub.track.kind === 'video') {
          state.participantes[identity].videoTrack = pub.track;
        }
      });
    } else if (remoteTracks instanceof Map) {
      remoteTracks.forEach(function(pub) {
        if (pub && pub.track && pub.track.kind === 'video') {
          state.participantes[identity].videoTrack = pub.track;
        }
      });
    }

    criarTile(identity, nome, cor, iniciais, papel, false);
    atualizarGrid();
    atualizarListaParticipantes();
    atualizarContagem();
  }

  function removerParticipante(identity) {
    if (!state.participantes[identity]) return;
    delete state.participantes[identity];
    state.totalParticipantes--;
    // Ajustar página se necessário
    var maxPage = Math.max(0, Math.ceil(state.totalParticipantes / state.gridPageSize) - 1);
    if (state.gridPage > maxPage) state.gridPage = maxPage;
    var tile = document.getElementById('tile-' + CSS.escape(identity));
    if (tile) tile.remove();
    if (state.maosLevantadas[identity]) {
      delete state.maosLevantadas[identity];
    }
    atualizarGrid();
    atualizarListaParticipantes();
    atualizarContagem();
  }

  function adicionarTrackParticipante(identity, track) {
    if (!state.participantes[identity]) return;
    if (track.kind === 'video') {
      state.participantes[identity].videoTrack = track;
      state.participantes[identity].videoMuted = false;
    }
    atualizarTile(identity);
  }

  function removerTrackParticipante(identity, track) {
    if (!state.participantes[identity]) return;
    if (track.kind === 'video') {
      state.participantes[identity].videoTrack = null;
      state.participantes[identity].videoMuted = true;
    }
    atualizarTile(identity);
  }

  function atualizarSpeakers(speakers) {
    var newSpeakerId = null;
    var audioLevels = {};

    speakers.forEach(function(s) {
      if (!s.isLocal) {
        newSpeakerId = s.identity;
      }
      // Guardar nível de áudio (0-1) para visualização
      audioLevels[s.identity] = s.audioLevel || 0;
      if (s.isLocal) {
        audioLevels[state.room?.localParticipant?.identity] = s.audioLevel || 0;
      }
    });

    // Limpar speakers antigos que já não falam ativamente
    Object.keys(state.participantes).forEach(function(id) {
      var wasSpeaking = state.participantes[id].isSpeaking;
      var isNowSpeaker = !state.participantes[id].isLocal && id === newSpeakerId;
      if (audioLevels[id] > 0.02 && !state.participantes[id].isLocal) {
        // Ainda está a falar (audioLevel > threshold)
        if (!isNowSpeaker) {
          state.participantes[id].isSpeaking = false;
        }
      } else {
        if (wasSpeaking && !isNowSpeaker) {
          state.participantes[id].isSpeaking = false;
        }
      }
      state.participantes[id].isSpeaking = isNowSpeaker || state.participantes[id].isSpeaking;
      if (state.participantes[id].isSpeaking !== wasSpeaking) {
        atualizarTile(id);
      }
    });

    if (newSpeakerId && state.participantes[newSpeakerId]) {
      state.participantes[newSpeakerId].isSpeaking = true;
      state.speakerId = newSpeakerId;
      atualizarTile(newSpeakerId);
    } else {
      state.speakerId = null;
    }
  }

  // ── TILES (grelha de participantes) ────────────────────────
  function criarTile(identity, nome, cor, iniciais, papel, isLocal) {
    if (document.getElementById('tile-' + CSS.escape(identity))) return;
    // Se já temos muitos tiles na página atual, esconder os mais antigos
    var ids = Object.keys(state.participantes);
    var pageSize = state.gridPageSize;
    var page = state.gridPage;
    var start = page * pageSize;
    var end = start + pageSize;
    var idx = ids.indexOf(identity);

    var tile = document.createElement('div');
    tile.id = 'tile-' + CSS.escape(identity);
    tile.className = 'meet-tile';
    tile.dataset.identity = identity;
    if (idx >= 0 && (idx < start || idx >= end)) {
      tile.style.display = 'none';
    }

    tile.innerHTML =
      '<div class="tile-placeholder" id="ph-' + CSS.escape(identity) + '">' +
        '<div class="avatar-circle" style="background:' + cor + '">' + iniciais + '</div>' +
        '<div class="avatar-name">' + escapeHtml(nome) + '</div>' +
      '</div>' +
      '<div class="tile-info">' +
        '<span class="tile-name">' + escapeHtml(nome) + (isLocal ? ' (Tu)' : '') + '</span>' +
        (papel ? '<span class="tile-badge">' + papel + '</span>' : '') +
        '<span class="tile-icon tile-mic-icon"><i class="fas fa-microphone"></i></span>' +
      '</div>';

    DOM.grid.appendChild(tile);

    // Se este tile é o primeiro da página, garantir que fica visível
    if (idx >= start && idx < end) {
      tile.style.display = '';
    }
  }

  function atualizarTile(identity) {
    var p = state.participantes[identity];
    if (!p) return;
    var tile = document.getElementById('tile-' + CSS.escape(identity));
    if (!tile) return;

    var placeholder = document.getElementById('ph-' + CSS.escape(identity));
    var existingVideo = tile.querySelector('video');

    console.log('[Tile] atualizarTile', identity, 'track=', !!p.videoTrack, 'muted=', p.videoMuted, 'isLocal=', p.isLocal);

    // Atualizar placeholder vs video
    if (p.videoTrack && !p.videoMuted) {
      if (placeholder) {
        placeholder.style.display = 'none';
        placeholder.classList.add('video-active');
      }
      if (!existingVideo) {
        try {
          var vid = p.videoTrack.attach();
          if (!vid) {
            console.warn('[Tile] attach() returned null para', identity);
            return;
          }
          vid.id = 'vid-' + CSS.escape(identity);
          vid.style.cssText = 'position:absolute !important;top:0;left:0;right:0;bottom:0;width:100%;height:100%;object-fit:cover;border-radius:12px;z-index:2';
          vid.setAttribute('playsinline', '');
          vid.setAttribute('autoplay', '');
          vid.muted = true;
          tile.style.position = 'relative';
          tile.insertBefore(vid, tile.firstChild);
          console.log('[Tile] Video attached para', identity);
        } catch(e) {
          console.error('[Tile] Erro attach video:', e);
        }
      }
    } else {
      if (existingVideo) {
        try { p.videoTrack?.detach(); } catch(e) {}
        existingVideo.remove();
      }
      if (placeholder) {
        placeholder.style.display = '';
        placeholder.classList.remove('video-active');
      }
    }

    // Speaking indicator
    tile.classList.toggle('tile-speaking', p.isSpeaking);

    // Audio mute indicator
    var micIcon = tile.querySelector('.tile-mic-icon i');
    if (micIcon) {
      micIcon.className = 'fas ' + (p.audioMuted ? 'fa-microphone-slash text-red-400' : 'fa-microphone');
    }

    // Hand raise
    var existingHand = tile.querySelector('.tile-raise-hand');
    if (p.handRaised && !existingHand) {
      var hand = document.createElement('div');
      hand.className = 'tile-raise-hand';
      hand.textContent = '🖐️';
      tile.appendChild(hand);
    } else if (!p.handRaised && existingHand) {
      existingHand.remove();
    }
  }

  function atualizarGrid() {
    var ids = Object.keys(state.participantes);
    var count = ids.length;

    // Remover classes de layout anteriores
    var layouts = ['layout-1','layout-2','layout-3','layout-4','layout-5','layout-6',
      'layout-7','layout-8','layout-9','layout-10','layout-11','layout-12',
      'layout-13','layout-14','layout-15','layout-16','layout-17','layout-18',
      'layout-19','layout-20','layout-21','layout-22','layout-23','layout-24',
      'layout-25','layout-26','layout-37','layout-100','layout-max'];
    DOM.grid.classList.remove.apply(DOM.grid.classList, layouts);

    if (count <= 1) DOM.grid.classList.add('layout-1');
    else if (count === 2) DOM.grid.classList.add('layout-2');
    else if (count <= 4) DOM.grid.classList.add('layout-4');
    else if (count <= 6) DOM.grid.classList.add('layout-6');
    else if (count <= 9) DOM.grid.classList.add('layout-9');
    else if (count <= 12) DOM.grid.classList.add('layout-12');
    else if (count <= 16) DOM.grid.classList.add('layout-16');
    else if (count <= 25) DOM.grid.classList.add('layout-25');
    else if (count <= 36) DOM.grid.classList.add('layout-26');
    else if (count <= 64) DOM.grid.classList.add('layout-37');
    else if (count <= 100) DOM.grid.classList.add('layout-100');
    else DOM.grid.classList.add('layout-max');

    // Paginação para grandes audiências
    state.totalPaginas = Math.max(1, Math.ceil(count / state.gridPageSize));
    if (state.gridPage >= state.totalPaginas) {
      state.gridPage = state.totalPaginas - 1;
    }
    // Mostrar/esconder tiles com base na página atual
    var pageSize = state.gridPageSize;
    var page = state.gridPage;
    var start = page * pageSize;
    var end = start + pageSize;
    ids.forEach(function(id, idx) {
      var tile = document.getElementById('tile-' + CSS.escape(id));
      if (tile) {
        tile.style.display = (idx >= start && idx < end) ? '' : 'none';
      }
    });
    // Remover paginação antiga
    var oldPagination = DOM.grid.querySelector('.grid-pagination');
    if (oldPagination) oldPagination.remove();
    // Adicionar paginação se necessário (middle of grid or bottom)
    if (state.totalPaginas > 1) {
      var pag = document.createElement('div');
      pag.className = 'grid-pagination';
      pag.style.cssText = 'position:sticky;bottom:0;left:0;right:0;display:flex;align-items:center;justify-content:center;gap:8px;padding:6px;background:rgba(30,30,46,0.9);border-radius:8px;z-index:10;width:100%;flex-shrink:0;';
      pag.innerHTML =
        '<button class="pag-prev" ' + (page <= 0 ? 'disabled' : '') + ' style="background:rgba(255,255,255,0.1);border:none;color:#e5e7eb;padding:4px 12px;border-radius:6px;cursor:pointer;font-size:12px;"><i class="fas fa-chevron-left"></i></button>' +
        '<span style="color:#9ca3af;font-size:12px;">' + (page + 1) + ' / ' + state.totalPaginas + '</span>' +
        '<button class="pag-next" ' + (page >= state.totalPaginas - 1 ? 'disabled' : '') + ' style="background:rgba(255,255,255,0.1);border:none;color:#e5e7eb;padding:4px 12px;border-radius:6px;cursor:pointer;font-size:12px;"><i class="fas fa-chevron-right"></i></button>' +
        '<span style="color:#6b7280;font-size:11px;margin-left:4px;">' + count + ' participantes</span>';
      DOM.grid.appendChild(pag);

      pag.querySelector('.pag-prev').addEventListener('click', function() {
        if (state.gridPage > 0) { state.gridPage--; atualizarGrid(); }
      });
      pag.querySelector('.pag-next').addEventListener('click', function() {
        if (state.gridPage < state.totalPaginas - 1) { state.gridPage++; atualizarGrid(); }
      });
    }

    // Screen share layout
    if (state.screenShareAtiva && state.screenShareParticipant) {
      DOM.grid.classList.add('hidden');
      DOM.screenShareArea.classList.remove('hidden');
      // Mover tiles para a sidebar
      var sidebar = DOM.screenShareArea.querySelector('.share-sidebar');
      sidebar.innerHTML = '';
      // Na screen share, mostrar só página atual
      var visibleIds = ids.slice(start, end);
      visibleIds.forEach(function(id) {
        var tile = document.getElementById('tile-' + CSS.escape(id));
        if (tile) sidebar.appendChild(tile.cloneNode(true));
      });
    } else {
      DOM.grid.classList.remove('hidden');
      DOM.screenShareArea.classList.add('hidden');
    }
  }

  function atualizarContagem() {
    var count = state.totalParticipantes;
    if (DOM.presentesCount) DOM.presentesCount.textContent = count;
    if (DOM.btnParticipants) {
      var badge = DOM.btnParticipants.querySelector('.btn-badge');
      if (badge) badge.textContent = count;
    }
  }

  // ── CHAT ───────────────────────────────────────────────────
  function carregarHistoricoChat(mensagens) {
    if (!mensagens) return;
    state.mensagensChat = mensagens.slice();
    // Se estiver na tab chat, renderizar
    if (state.sideAba === 'chat' && state.chatAberto) {
      renderChat();
    }
  }

  function adicionarMensagemChat(msg) {
    // Guardar no array de mensagens
    state.mensagensChat.push(msg);

    // Incrementar badge se não estiver no chat
    if (state.sideAba !== 'chat' || !state.chatAberto) {
      state.chatNaoLidas++;
      if (DOM.chatBadge) {
        DOM.chatBadge.classList.remove('hidden');
        DOM.chatBadge.textContent = state.chatNaoLidas;
      }
      return; // Não renderizar no DOM se não estiver na tab chat
    }

    renderMensagemChat(msg);
    if (DOM.panelBody) DOM.panelBody.scrollTop = DOM.panelBody.scrollHeight;
  }

  function renderMensagemChat(msg) {
    var container = DOM.panelBody;
    if (!container) return;
    if (msg.tipo === 'reacao') {
      var div = document.createElement('div');
      div.className = 'chat-reaction';
      div.innerHTML =
        '<span>' + escapeHtml(msg.nome) + '</span> ' +
        (msg.reacao === 'mao' ? '🖐️' : msg.reacao === 'palmas' ? '👏' : '❤️');
      container.appendChild(div);
    } else {
      var div = document.createElement('div');
      div.className = 'chat-msg';
      div.innerHTML =
        '<div class="chat-author">' + escapeHtml(msg.nome || 'Anónimo') + '</div>' +
        '<div class="chat-text">' + escapeHtml(msg.texto || '') + '</div>' +
        '<div class="chat-time">' + (msg.created_at || 'agora') + '</div>';
      container.appendChild(div);
    }
  }

  function enviarMensagem(texto) {
    if (!texto.trim()) return;
    enviarWS({ action: 'chat_message', texto: texto.trim() });
    if (DOM.chatInput) DOM.chatInput.value = '';
  }

  function enviarReacao(reacao) {
    enviarWS({ action: 'chat_reaction', reacao: reacao });
  }

  // ── VOTAÇÃO BANNER ─────────────────────────────────────────
  var votacaoBannerTimer = null;
  var votacaoBannerStart = null;

  function mostrarBannerVotacao(pautaTitulo, pautaId) {
    var banner = document.getElementById('votacao-banner');
    var pautaEl = document.getElementById('votacao-banner-pauta');
    var timerEl = document.getElementById('votacao-banner-timer');
    var barEl = document.getElementById('votacao-banner-bar');
    if (!banner || !pautaEl) return;

    pautaEl.textContent = pautaTitulo || 'Pauta #' + pautaId;
    banner.classList.remove('hidden');
    banner.classList.remove('minimized');

    // Iniciar timer
    votacaoBannerStart = Date.now();
    if (votacaoBannerTimer) clearInterval(votacaoBannerTimer);
    votacaoBannerTimer = setInterval(function() {
      if (!votacaoBannerStart) return;
      var diff = Math.floor((Date.now() - votacaoBannerStart) / 1000);
      var m = Math.floor(diff / 60);
      var s = diff % 60;
      if (timerEl) timerEl.textContent = m.toString().padStart(2,'0') + ':' + s.toString().padStart(2,'0');
    }, 1000);
  }

  function esconderBannerVotacao() {
    var banner = document.getElementById('votacao-banner');
    if (banner) banner.classList.add('hidden');
    if (votacaoBannerTimer) { clearInterval(votacaoBannerTimer); votacaoBannerTimer = null; }
    votacaoBannerStart = null;
  }

  // ── VOTAÇÃO ────────────────────────────────────────────────
  function abrirVotacao(msg) {
    state.votacaoAtiva = msg;
    carregarVotosPauta(msg.pauta_id);
    if (state.sideAba === 'voting' && state.chatAberto) {
      renderVotingPanel();
    }
    abrirSidePanel('voting');
    mostrarBannerVotacao(msg.titulo, msg.pauta_id);
    mostrarToast('📊 Votação aberta: ' + (msg.titulo || 'Pauta'), '#22c55e');
    if (DOM.btnVoting) {
      var badge = DOM.btnVoting.querySelector('.btn-badge');
      if (badge) { badge.classList.remove('hidden'); badge.textContent = '!'; }
    }
    // Registrar no historial da pauta
    if (state.pautas && state.pautas.length > 0) {
      var pauta = state.pautas.find(function(p) { return p.id === msg.pauta_id; });
      if (pauta) pauta.status = 'Em Votacao';
    }
  }

  function encerrarVotacao(msg) {
    state.votacaoAtiva = null;
    esconderBannerVotacao();
    mostrarToast('✅ Votação encerrada', '#f59e0b');
    if (DOM.btnVoting) {
      var badge = DOM.btnVoting.querySelector('.btn-badge');
      if (badge) badge.classList.add('hidden');
    }
    if (state.sideAba === 'voting' && state.chatAberto) {
      renderVotingResults(msg);
    }
    // Atualizar status da pauta
    if (state.pautas && state.pautas.length > 0) {
      var pauta = state.pautas.find(function(p) { return p.id === msg.pauta_id; });
      if (pauta) {
        pauta.status = 'Concluida';
        pauta.resultado_final = msg.resultado_final || '';
      }
    }
  }

  function atualizarResultadosVotacao(msg) {
    if (state.votacaoAtiva && state.votacaoAtiva.pauta_id === msg.pauta_id) {
      state.votacaoAtiva.favor = msg.favor;
      state.votacaoAtiva.contra = msg.contra;
      state.votacaoAtiva.abstencao = msg.abstencao;
    }
    if (state.sideAba === 'voting' && state.chatAberto) {
      renderVotingResults(msg);
    }
  }

  function reabrirVotacao(msg) {
    state.votacaoAtiva = msg;
    abrirSidePanel('voting');
    mostrarBannerVotacao(msg.titulo, msg.pauta_id);
    mostrarToast('🔄 Votação reaberta: ' + (msg.titulo || ''), '#22c55e');
  }

  function adicionarVotoRegistado(msg) {
    state.votosIndividuais.push(msg);
    if (state.sideAba === 'voting' && state.chatAberto) {
      renderVotosIndividuais();
    }
  }

  function carregarVotosPauta(pautaId) {
    state.votosIndividuais = [];
    fetch('/governanca/api/pauta/' + pautaId + '/votos/')
      .then(function(r) { return r.json(); })
      .then(function(data) {
        if (data.votos) {
          state.votosIndividuais = data.votos;
          if (state.sideAba === 'voting' && state.chatAberto) {
            renderVotosIndividuais();
          }
        }
      })
      .catch(function() {});
  }

  function renderVotosIndividuais() {
    if (!DOM.panelBody) return;
    var votos = state.votosIndividuais || [];
    if (votos.length === 0) return;
    var seletor = document.getElementById('votos-individuais');
    if (!seletor) return;
    var html = '';
    var isAberta = state.votacaoAtiva && state.votacaoAtiva.tipo_votacao !== 'Secreta';
    votos.forEach(function(v) {
      if (isAberta && v.opcao) {
        var icone = v.opcao === 'Favor' ? '✅' : v.opcao === 'Contra' ? '❌' : '⬜';
        html += '<div class="flex items-center justify-between py-1.5 px-3 rounded-lg bg-gray-800/40 border border-gray-700/30 text-sm">' +
          '<span class="text-gray-200">' + escapeHtml(v.nome || '***') + '</span>' +
          '<span>' + icone + ' <span class="' + (v.opcao === 'Favor' ? 'text-green-400' : v.opcao === 'Contra' ? 'text-red-400' : 'text-yellow-400') + '">' + v.opcao + '</span></span>' +
        '</div>';
      } else if (!isAberta) {
        html += '<div class="flex items-center justify-between py-1.5 px-3 rounded-lg bg-gray-800/40 border border-gray-700/30 text-sm">' +
          '<span class="text-gray-400 text-xs">Voto registado</span>' +
          '<span class="text-gray-500">🔒</span>' +
        '</div>';
      }
    });
    seletor.innerHTML = html;
  }

  function votar(opcao) {
    if (!state.votacaoAtiva) return;
    var pautaId = state.votacaoAtiva.pauta_id;
    fetch('/governanca/api/pauta/' + pautaId + '/votar/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CONFIG.CSRF },
      body: JSON.stringify({ opcao: opcao }),
    })
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (data.status === 'ok') {
        state.jaVotou[pautaId] = true;
        mostrarToast('Voto registado com sucesso!', '#22c55e');
        renderVotingConfirmed();
      } else {
        mostrarToast(data.message || 'Erro ao votar', '#ef4444');
      }
    })
    .catch(function() {
      mostrarToast('Erro de conexão ao votar', '#ef4444');
    });
  }

  function renderVotingPanel() {
    if (!DOM.panelBody) return;
    var va = state.votacaoAtiva;
    if (!va) {
      DOM.panelBody.innerHTML = '<div class="text-center text-gray-500 mt-8"><i class="fas fa-check-circle text-3xl mb-2"></i><p class="text-sm">Nenhuma votação ativa</p></div>';
      return;
    }
    var pautaId = va.pauta_id;

    if (state.jaVotou[pautaId]) {
      // Já votou — verificar se tem procurações para votar em nome de outrem
      var procs = CONFIG.MINHAS_PROCURACAO || [];
      if (procs.length > 0) {
        renderProxyVoting(procs);
      } else {
        renderVotingConfirmed();
      }
      return;
    }
    DOM.panelBody.innerHTML =
      '<div class="voting-panel">' +
        '<div class="voting-title">' + escapeHtml(va.titulo || 'Votação') + '</div>' +
        '<div class="voting-desc">' + escapeHtml(va.descricao || '') + '</div>' +
        '<div class="voting-options">' +
          '<button class="vote-favor" onclick="window.MEET_VOTAR(\'Favor\')"><i class="fas fa-thumbs-up mr-1"></i> Sim</button>' +
          '<button class="vote-contra" onclick="window.MEET_VOTAR(\'Contra\')"><i class="fas fa-thumbs-down mr-1"></i> Não</button>' +
          '<button class="vote-abst" onclick="window.MEET_VOTAR(\'Abstencao\')"><i class="fas fa-minus-circle mr-1"></i> Abstenção</button>' +
        '</div>' +
        '<hr class="my-3 border-gray-600">' +
        '<div class="text-xs text-gray-400 font-medium mb-2">Votos registados</div>' +
        '<div id="votos-individuais" class="space-y-1"></div>' +
      '</div>';
    renderVotosIndividuais();
  }

  function renderProxyVoting(procs) {
    if (!DOM.panelBody) return;
    var html =
      '<div class="voting-panel">' +
        '<div class="voting-confirmed"><i class="fas fa-check-circle mr-1"></i> Já votou pessoalmente</div>' +
        '<hr class="my-3 border-gray-600">' +
        '<div class="voting-title text-sm">Votar como procurador (em nome de):</div>' +
        '<div class="voting-proxy-list">';
    procs.forEach(function(p) {
      html +=
        '<div class="voting-proxy-item" style="display:flex;align-items:center;justify-content:space-between;padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.08)">' +
          '<span class="text-sm">' + escapeHtml(p.outorgante_nome) + '</span>' +
          '<div class="flex gap-1">' +
            '<button class="vote-favor vote-proxy-btn" style="padding:4px 12px;font-size:12px" onclick="window.MEET_VOTAR_PROXY(' + p.id + ',' + p.outorgante_id + ',\'Favor\')"><i class="fas fa-thumbs-up mr-1"></i> Sim</button>' +
            '<button class="vote-contra vote-proxy-btn" style="padding:4px 12px;font-size:12px" onclick="window.MEET_VOTAR_PROXY(' + p.id + ',' + p.outorgante_id + ',\'Contra\')"><i class="fas fa-thumbs-down mr-1"></i> Não</button>' +
            '<button class="vote-abst vote-proxy-btn" style="padding:4px 12px;font-size:12px" onclick="window.MEET_VOTAR_PROXY(' + p.id + ',' + p.outorgante_id + ',\'Abstencao\')"><i class="fas fa-minus-circle mr-1"></i> Abstenção</button>' +
          '</div>' +
        '</div>';
    });
    html += '</div></div>';
    DOM.panelBody.innerHTML = html;
  }

  function renderVotingConfirmed() {
    if (!DOM.panelBody) return;
    DOM.panelBody.innerHTML =
      '<div class="voting-panel">' +
        '<div class="voting-confirmed"><i class="fas fa-check-circle mr-1"></i> Voto registado com sucesso!</div>' +
        '<hr class="my-3 border-gray-600">' +
        '<div class="text-xs text-gray-400 font-medium mb-2">Votos registados</div>' +
        '<div id="votos-individuais" class="space-y-1"></div>' +
      '</div>';
    renderVotosIndividuais();
  }

  function renderVotingResults(msg) {
    if (!DOM.panelBody) return;
    var total = (msg.favor || 0) + (msg.contra || 0) + (msg.abstencao || 0);
    var pFavor = total > 0 ? ((msg.favor || 0) / total * 100) : 0;
    var pContra = total > 0 ? ((msg.contra || 0) / total * 100) : 0;
    var pAbst = total > 0 ? ((msg.abstencao || 0) / total * 100) : 0;

    DOM.panelBody.innerHTML =
      '<div class="voting-panel">' +
        '<div class="voting-title">Resultados: ' + escapeHtml(msg.titulo || '') + '</div>' +
        '<div class="voting-desc">' + (msg.resultado_final || '') + '</div>' +
        '<div class="voting-results">' +
          '<div class="voting-result-row"><span class="result-label">Favor</span><div class="result-bar"><div class="bar-fill bg-green-500" style="width:' + pFavor + '%"></div></div><span class="result-count">' + (msg.favor || 0) + '</span></div>' +
          '<div class="voting-result-row"><span class="result-label">Contra</span><div class="result-bar"><div class="bar-fill bg-red-500" style="width:' + pContra + '%"></div></div><span class="result-count">' + (msg.contra || 0) + '</span></div>' +
          '<div class="voting-result-row"><span class="result-label">Abstenção</span><div class="result-bar"><div class="bar-fill bg-yellow-500" style="width:' + pAbst + '%"></div></div><span class="result-count">' + (msg.abstencao || 0) + '</span></div>' +
        '</div>' +
        '<hr class="my-3 border-gray-600">' +
        '<div class="text-xs text-gray-400 font-medium mb-2">Votos registados</div>' +
        '<div id="votos-individuais" class="space-y-1"></div>' +
      '</div>';
    renderVotosIndividuais();
  }

  function verificarVotacaoAtivaAPI() {
    fetch('/governanca/api/assembleia/' + CONFIG.ASSEMBLEIA_ID + '/status/')
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (data.pauta_ativa_id && !state.votacaoAtiva) {
        state.votacaoAtiva = {
          pauta_id: data.pauta_ativa_id,
          titulo: data.pauta_ativa_titulo,
          tipo_votacao: data.pauta_ativa_tipo,
        };
        mostrarBannerVotacao(data.pauta_ativa_titulo, data.pauta_ativa_id);
        renderVotingPanel();
      } else if (!data.pauta_ativa_id && !state.votacaoAtiva) {
        // Nenhuma pauta ativa — mostrar mensagem
        if (DOM.panelBody) {
          DOM.panelBody.innerHTML =
            '<div class="voting-panel">' +
              '<div class="text-center text-gray-500 mt-8">' +
                '<i class="fas fa-vote-yea text-4xl mb-3"></i>' +
                '<p class="text-sm">Nenhuma pauta em votação</p>' +
              '</div>' +
            '</div>';
        }
      }
    })
    .catch(function() {});
  }

  window.MEET_VOTAR = votar;

  function votarProxy(procuracaoId, delegadoDeId, opcao) {
    if (!state.votacaoAtiva) return;
    var pautaId = state.votacaoAtiva.pauta_id;
    fetch('/governanca/api/pauta/' + pautaId + '/votar/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CONFIG.CSRF },
      body: JSON.stringify({ opcao: opcao, em_delegacao: true, delegado_de_id: delegadoDeId }),
    })
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (data.status === 'ok') {
        var nomeProc = '';
        CONFIG.MINHAS_PROCURACAO.forEach(function(p) {
          if (p.outorgante_id === delegadoDeId) nomeProc = p.outorgante_nome;
        });
        mostrarToast('Voto de procuração registado para ' + escapeHtml(nomeProc), '#22c55e');
        // Remover este outorgante da lista
        var idx = -1;
        for (var i = 0; i < CONFIG.MINHAS_PROCURACAO.length; i++) {
          if (CONFIG.MINHAS_PROCURACAO[i].outorgante_id === delegadoDeId) {
            idx = i; break;
          }
        }
        if (idx >= 0) CONFIG.MINHAS_PROCURACAO.splice(idx, 1);
        // Re-renderizar painel
        if (CONFIG.MINHAS_PROCURACAO.length > 0) {
          renderProxyVoting(CONFIG.MINHAS_PROCURACAO);
        } else {
          renderVotingConfirmed();
        }
      } else {
        mostrarToast(data.message || 'Erro ao votar como procurador', '#ef4444');
      }
    })
    .catch(function() {
      mostrarToast('Erro de conexão ao votar como procurador', '#ef4444');
    });
  }

  window.MEET_VOTAR_PROXY = votarProxy;

  // ── LISTA DE PARTICIPANTES ─────────────────────────────────
  function atualizarListaParticipantes() {
    // Usado quando a aba participantes está ativa
    if (state.sideAba !== 'participants' || !state.chatAberto) return;
    renderParticipantList();
  }

  function renderParticipantList() {
    if (!DOM.panelBody) return;
    var html = '';
    var mesaMap = {};
    state.participantesMesa.forEach(function(m) {
      mesaMap[m.usuario_nome] = m.funcao;
    });

    Object.keys(state.participantes).forEach(function(id) {
      var p = state.participantes[id];
      var papel = mesaMap[p.nome] || '';
      var cor = p.avatarColor;
      html +=
        '<div class="participant-row">' +
          '<div class="part-avatar" style="background:' + cor + '">' + p.iniciais + '</div>' +
          '<div class="part-info">' +
            '<div class="part-name">' + escapeHtml(p.nome) + (p.isLocal ? ' (Tu)' : '') + '</div>' +
            (papel ? '<div class="part-role">' + papel + '</div>' : '') +
          '</div>' +
          '<div class="part-icons">' +
            (p.audioMuted ? '<i class="fas fa-microphone-slash text-red-400"></i>' : '<i class="fas fa-microphone text-green-400"></i>') +
            (p.handRaised ? '🖐️' : '') +
          '</div>' +
        '</div>';
    });

    // Adicionar presencas que nao estao no LiveKit
    state.participantesPresenca.forEach(function(pr) {
      if (state.participantes[pr.nome]) return;
      var iniciais = obterIniciais(pr.nome);
      var cor = obterCorAvatar(pr.nome);
      var papel = mesaMap[pr.nome] || '';
      html +=
        '<div class="participant-row opacity-60">' +
          '<div class="part-avatar" style="background:' + cor + '">' + iniciais + '</div>' +
          '<div class="part-info">' +
            '<div class="part-name">' + escapeHtml(pr.nome) + ' (apenas áudio)</div>' +
            (papel ? '<div class="part-role">' + papel + '</div>' : '') +
          '</div>' +
          '<div class="part-icons"><i class="fas fa-video-slash text-gray-500"></i></div>' +
        '</div>';
    });

    DOM.panelBody.innerHTML = html;
  }

  // ── SIDE PANEL ─────────────────────────────────────────────
  function abrirSidePanel(aba) {
    state.chatAberto = true;
    state.sideAba = aba;
    DOM.sidepanel.classList.remove('hidden-panel');
    DOM.grid.classList.add('has-sidepanel');

    // Tabs
    DOM.sidepanel.querySelectorAll('.panel-tab').forEach(function(t) {
      t.classList.toggle('active', t.dataset.tab === aba);
    });

    // Reset badge
    if (aba === 'chat' && DOM.chatBadge) {
      DOM.chatBadge.classList.add('hidden');
      state.chatNaoLidas = 0;
    }

    renderSideContent(aba);
  }

  function fecharSidePanel() {
    state.chatAberto = false;
    DOM.sidepanel.classList.add('hidden-panel');
    DOM.grid.classList.remove('has-sidepanel');
  }

  function renderSideContent(aba) {
    switch (aba) {
      case 'chat':
        renderChat();
        break;
      case 'participants':
        renderParticipantList();
        break;
      case 'voting':
        if (state.votacaoAtiva) {
          renderVotingPanel();
        } else {
          // Tentar buscar estado atual via API (fallback para join tardio)
          verificarVotacaoAtivaAPI();
          DOM.panelBody.innerHTML =
            '<div class="voting-panel">' +
              '<div class="text-center text-gray-500 mt-8">' +
                '<i class="fas fa-vote-yea text-4xl mb-3"></i>' +
                '<p class="text-sm">A verificar...</p>' +
              '</div>' +
            '</div>';
        }
        break;
    }
  }

  function renderChat() {
    if (!DOM.panelBody) return;
    DOM.panelBody.innerHTML = '';
    var msgs = state.mensagensChat || [];
    if (msgs.length === 0) {
      DOM.panelBody.innerHTML = '<div class="text-center text-gray-500 mt-8"><i class="fas fa-comments text-3xl mb-2"></i><p class="text-sm">Mensagens aparecerão aqui</p></div>';
      return;
    }
    msgs.forEach(function(m) { renderMensagemChat(m); });
    DOM.panelBody.scrollTop = DOM.panelBody.scrollHeight;
  }

  // ── QUORUM ─────────────────────────────────────────────────
  function atualizarQuorum(msg) {
    state.quorum = msg;
    if (DOM.quorumText) {
      DOM.quorumText.textContent = 'Quórum: ' + (msg.presentes || 0) + '/' + (msg.quorum_minimo || 0) + ' ' + (msg.atingido ? '✔️' : '⏳');
      DOM.quorumText.className = 'text-sm ' + (msg.atingido ? 'text-green-400' : 'text-yellow-400');
    }
  }

  // ── RAISE HAND ─────────────────────────────────────────────
  function toggleHand() {
    var identity = CONFIG.USER_NOME;
    var isRaised = !!state.maosLevantadas[identity];

    if (isRaised) {
      delete state.maosLevantadas[identity];
      if (state.participantes[identity]) {
        state.participantes[identity].handRaised = false;
        atualizarTile(identity);
      }
      if (DOM.btnHand) DOM.btnHand.classList.remove('meet-btn-warn');
      enviarWS({ action: 'lower_hand', nome: identity });
    } else {
      state.maosLevantadas[identity] = true;
      if (state.participantes[identity]) {
        state.participantes[identity].handRaised = true;
        atualizarTile(identity);
      }
      if (DOM.btnHand) DOM.btnHand.classList.add('meet-btn-warn');
      enviarWS({ action: 'raise_hand' });
    }
  }

  // ── TIMER ──────────────────────────────────────────────────
  function iniciarTimer() {
    var startStr = DOM.timerEl?.dataset?.start;
    if (!startStr) return;
    var startTime = new Date(startStr).getTime();
    if (isNaN(startTime)) return;

    function atualizar() {
      var diff = Math.floor((Date.now() - startTime) / 1000);
      var h = Math.floor(diff / 3600);
      var m = Math.floor((diff % 3600) / 60);
      var s = diff % 60;
      if (DOM.timerEl) {
        DOM.timerEl.textContent =
          (h > 0 ? h.toString().padStart(2,'0') + ':' : '') +
          m.toString().padStart(2,'0') + ':' + s.toString().padStart(2,'0');
      }
    }

    atualizar();
    state.elapsedTimer = setInterval(atualizar, 1000);
  }

  // ── TOAST ──────────────────────────────────────────────────
  function mostrarToast(msg, cor) {
    if (!DOM.toastContainer) return;
    var el = document.createElement('div');
    el.className = 'meet-toast-item';
    el.style.background = cor || '#333';
    el.textContent = msg;
    DOM.toastContainer.appendChild(el);
    setTimeout(function() {
      el.classList.add('leave');
      setTimeout(function() { el.remove(); }, 3500);
    }, 500);
  }

  // ── BIND EVENTS ────────────────────────────────────────────
  function bindEvents() {
    // Chat send
    if (DOM.chatSend && DOM.chatInput) {
      DOM.chatSend.addEventListener('click', function() { enviarMensagem(DOM.chatInput.value); });
      DOM.chatInput.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') enviarMensagem(DOM.chatInput.value);
      });
    }

    // Chat reactions
    if (DOM.chatReactions) {
      DOM.chatReactions.querySelectorAll('button').forEach(function(btn) {
        btn.addEventListener('click', function() {
          enviarReacao(this.dataset.reacao);
        });
      });
    }

    // Bottom bar buttons
    if (DOM.btnMic) {
      DOM.btnMic.addEventListener('click', async function() {
        if (!state.room) return;
        var ativa = state.room.localParticipant.isMicrophoneEnabled;
        try {
          await state.room.localParticipant.setMicrophoneEnabled(!ativa);
        } catch(e) {}
        DOM.btnMic.classList.toggle('meet-btn-danger', ativa);
        if (state.participantes[CONFIG.USER_NOME]) {
          state.participantes[CONFIG.USER_NOME].audioMuted = ativa;
          atualizarTile(CONFIG.USER_NOME);
        }
      });
    }

    if (DOM.btnCam) {
      DOM.btnCam.addEventListener('click', async function() {
        if (!state.room) return;
        var ativa = state.room.localParticipant.isCameraEnabled;
        var identity = CONFIG.USER_NOME;
        try {
          var pub = await state.room.localParticipant.setCameraEnabled(!ativa);
          if (!ativa && pub && pub.track) {
            // Camera was turned ON, save track
            if (state.participantes[identity]) {
              state.participantes[identity].videoTrack = pub.track;
            }
          }
        } catch(e) {
          console.warn('[LiveKit] toggle camera error:', e);
        }
        DOM.btnCam.classList.toggle('meet-btn-danger', ativa);
        if (state.participantes[identity]) {
          state.participantes[identity].videoMuted = ativa;
          if (ativa) state.participantes[identity].videoTrack = null;
          atualizarTile(identity);
        }
      });
    }

    if (DOM.btnScreen) {
      DOM.btnScreen.addEventListener('click', async function() {
        if (!state.room) return;
        state.screenShareAtiva = !state.screenShareAtiva;
        try {
          await state.room.localParticipant.setScreenShareEnabled(state.screenShareAtiva);
        } catch(e) {
          state.screenShareAtiva = !state.screenShareAtiva;
        }
        DOM.btnScreen.classList.toggle('meet-btn-active', state.screenShareAtiva);
        if (state.screenShareAtiva) {
          state.screenShareParticipant = CONFIG.USER_NOME;
          mostrarToast('A partilhar ecrã', '#22c55e');
        } else {
          state.screenShareParticipant = null;
        }
        atualizarGrid();
      });
    }

    if (DOM.btnHand) {
      DOM.btnHand.addEventListener('click', toggleHand);
    }

    if (DOM.btnChat) {
      DOM.btnChat.addEventListener('click', function() {
        if (state.chatAberto && state.sideAba === 'chat') fecharSidePanel();
        else abrirSidePanel('chat');
      });
    }

    if (DOM.btnParticipants) {
      DOM.btnParticipants.addEventListener('click', function() {
        if (state.chatAberto && state.sideAba === 'participants') fecharSidePanel();
        else abrirSidePanel('participants');
      });
    }

    if (DOM.btnVoting) {
      DOM.btnVoting.addEventListener('click', function() {
        if (state.chatAberto && state.sideAba === 'voting') fecharSidePanel();
        else abrirSidePanel('voting');
      });
    }

    // End call
    if (DOM.btnEnd) {
      DOM.btnEnd.addEventListener('click', function() {
        if (state.room) state.room.disconnect();
        window.location.href = '/governanca/assembleias/';
      });
    }

    // Fullscreen toggle
    if (DOM.btnFullscreen) {
      DOM.btnFullscreen.addEventListener('click', function() {
        var el = document.getElementById('app-root');
        if (!document.fullscreenElement) {
          if (el.requestFullscreen) {
            el.requestFullscreen();
          } else if (el.webkitRequestFullscreen) {
            el.webkitRequestFullscreen();
          } else if (el.msRequestFullscreen) {
            el.msRequestFullscreen();
          }
          DOM.btnFullscreen.innerHTML = '<i class="fas fa-compress"></i>';
          DOM.btnFullscreen.title = 'Sair do ecrã inteiro';
        } else {
          if (document.exitFullscreen) {
            document.exitFullscreen();
          } else if (document.webkitExitFullscreen) {
            document.webkitExitFullscreen();
          } else if (document.msExitFullscreen) {
            document.msExitFullscreen();
          }
          DOM.btnFullscreen.innerHTML = '<i class="fas fa-expand"></i>';
          DOM.btnFullscreen.title = 'Ecrã Inteiro';
        }
      });
      // Listen for fullscreen change to sync icon
      document.addEventListener('fullscreenchange', function() {
        if (!document.fullscreenElement) {
          DOM.btnFullscreen.innerHTML = '<i class="fas fa-expand"></i>';
          DOM.btnFullscreen.title = 'Ecrã Inteiro';
        }
      });
      document.addEventListener('webkitfullscreenchange', function() {
        if (!document.webkitFullscreenElement) {
          DOM.btnFullscreen.innerHTML = '<i class="fas fa-expand"></i>';
          DOM.btnFullscreen.title = 'Ecrã Inteiro';
        }
      });
    }

    // Side panel tabs
    DOM.sidepanel?.querySelectorAll('.panel-tab').forEach(function(tab) {
      tab.addEventListener('click', function() {
        abrirSidePanel(this.dataset.tab);
      });
    });

    // Close panel
    var closeBtn = DOM.sidepanel?.querySelector('.panel-close');
    if (closeBtn) {
      closeBtn.addEventListener('click', fecharSidePanel);
    }

    // Admin mute controls (delegated to participant list)
    document.addEventListener('click', function(e) {
      var muteBtn = e.target.closest('.btn-admin-mute');
      if (muteBtn) {
        var identity = muteBtn.dataset.identity;
        controlarParticipante(identity, 'mute');
      }
      var camBtn = e.target.closest('.btn-admin-cam');
      if (camBtn) {
        var identity = camBtn.dataset.identity;
        controlarParticipante(identity, 'camera_off');
      }
    });

    // Votação banner close (minimizar)
    var bannerClose = document.getElementById('votacao-banner-close');
    if (bannerClose) {
      bannerClose.addEventListener('click', function() {
        var banner = document.getElementById('votacao-banner');
        if (banner) banner.classList.toggle('minimized');
      });
    }
  }

  // ── ADMIN REMOTE CONTROL ──────────────────────────────────
  function controlarParticipante(identity, acao) {
    fetch('/governanca/api/livekit/mute/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CONFIG.CSRF },
      body: JSON.stringify({ room: CONFIG.LIVEKIT_ROOM, identity: identity, acao: acao }),
    })
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (data.status === 'ok') mostrarToast('Comando executado', '#22c55e');
      else mostrarToast(data.message || 'Erro', '#ef4444');
    })
    .catch(function() { mostrarToast('Erro de conexão', '#ef4444'); });
  }

  // ── UTILITIES ──────────────────────────────────────────────
  function obterCorAvatar(identity) {
    var hash = 0;
    for (var i = 0; i < (identity || '').length; i++) {
      hash = identity.charCodeAt(i) + ((hash << 5) - hash);
    }
    return state.avatarColors[Math.abs(hash) % state.avatarColors.length];
  }

  function obterIniciais(nome) {
    if (!nome) return '?';
    var partes = nome.trim().split(/\s+/);
    if (partes.length === 1) return partes[0].substring(0, 2).toUpperCase();
    return (partes[0][0] + partes[partes.length - 1][0]).toUpperCase();
  }

  function obterPapel(identity) {
    var mesa = state.participantesMesa || [];
    for (var i = 0; i < mesa.length; i++) {
      if (mesa[i].usuario_nome === identity || mesa[i].nome === identity) {
        return mesa[i].funcao;
      }
    }
    return '';
  }

  function escapeHtml(str) {
    if (!str) return '';
    var div = document.createElement('div');
    div.appendChild(document.createTextNode(str));
    return div.innerHTML;
  }

  // ── Expor ─────────────────────────────────────────────────
  window.MEET = {
    init: init,
    votar: votar,
    toggleHand: toggleHand,
    abrirSidePanel: abrirSidePanel,
    fecharSidePanel: fecharSidePanel,
    atualizarParticipantesPresenca: function(lista) { state.participantesPresenca = lista || []; },
    atualizarMesa: function(lista) {
      state.participantesMesa = lista || [];
      atualizarListaParticipantes();
    },
    atualizarPautas: function(lista) { state.pautas = lista || []; },
    enviarMensagem: enviarMensagem,
  };

  // ── Auto-init ─────────────────────────────────────────────
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();
