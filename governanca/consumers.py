import json
import asyncio
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone
from users.models import Usuario
from .models import Assembleia, PresencaAssembleia, PautaVotacao, Voto, Procuracao, MensagemChat, LogAssembleia, EstadoFinanceiro


class AssembleiaConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.assembleia_pk = self.scope['url_route']['kwargs']['assembleia_pk']
        self.room_group_name = f'assembleia_{self.assembleia_pk}'
        self.usuario = None

        session = self.scope.get('session', {})
        usuario_id = session.get('usuario_id')
        if usuario_id:
            self.usuario = await database_sync_to_async(Usuario.objects.filter(id=usuario_id).first)()

        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()
        print(f'[WS CONNECT] user={self.usuario.nome if self.usuario else "anon"} channel={self.channel_name} group={self.room_group_name}')

        if self.usuario:
            await self._registar_presenca()
            await self._log_assembleia_async('entrada', {'channel': self.channel_name})
            await self._broadcast_quorum()
            await self._enviar_historico_chat()
            await self._enviar_estado_votacao()

    async def dispatch(self, message):
        usr = getattr(self, 'usuario', None)
        nome = usr.nome if usr else 'anon'
        chan = getattr(self, 'channel_name', '?')
        if message.get('type') != 'websocket.connect':
            print(f'[DISPATCH] type={message.get("type")} user={nome} channel={chan}')
        try:
            await super().dispatch(message)
        except ValueError as e:
            print(f'[DISPATCH ERROR] {e}')

    async def disconnect(self, close_code):
        if self.usuario:
            await self._log_assembleia_async('saida', {'close_code': close_code})
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        if text_data is None:
            return
        data = json.loads(text_data)
        action = data.get('action')
        print(f'[WS RECV ACTION] user={self.usuario.nome if self.usuario else "anon"} action={action}')

        handlers = {
            'votar': self._handle_voto,
            'ping': self._handle_ping,
            'solicitar_quorum': self._handle_quorum,
            'chat_message': self._handle_chat_message,
            'chat_reaction': self._handle_chat_reaction,
            'raise_hand': self._handle_raise_hand,
            'lower_hand': self._handle_lower_hand,
        }
        handler = handlers.get(action)
        if handler:
            await handler(data)

    async def _handle_ping(self, data):
        await self.send(text_data=json.dumps({'action': 'pong'}))

    async def _handle_quorum(self, data):
        await self._broadcast_quorum()

    async def _handle_voto(self, data):
        pauta_id = data.get('pauta_id')
        opcao = data.get('opcao')
        em_delegacao = data.get('em_delegacao', False)
        delegado_de_id = data.get('delegado_de_id')

        if not self.usuario or not pauta_id or opcao not in ('Favor', 'Contra', 'Abstencao'):
            await self.send(text_data=json.dumps({'action': 'voto_erro', 'message': 'Dados inválidos'}))
            return

        # Verificar elegibilidade (estado financeiro)
        elegivel = await self._verificar_elegibilidade()
        if not elegivel:
            await self.send(text_data=json.dumps({
                'action': 'voto_erro',
                'message': 'Status financeiro irregular — direito de voto suspenso. Acesso ao streaming autorizado.'
            }))
            return

        try:
            pauta = await database_sync_to_async(PautaVotacao.objects.get)(id=pauta_id, assembleia_id=self.assembleia_pk)
        except PautaVotacao.DoesNotExist:
            await self.send(text_data=json.dumps({'action': 'voto_erro', 'message': 'Pauta não encontrada'}))
            return

        if pauta.status != 'Em Votacao':
            await self.send(text_data=json.dumps({'action': 'voto_erro', 'message': 'Votação não está em curso'}))
            return

        voto, created = await database_sync_to_async(Voto.objects.get_or_create)(
            pauta=pauta,
            usuario_id=self.usuario.id,
            em_delegacao=em_delegacao,
            defaults={
                'opcao': opcao,
                'delegado_de_id': delegado_de_id if em_delegacao else None,
            }
        )

        if not created:
            voto.opcao = opcao
            await database_sync_to_async(voto.save)()
        elif pauta.tipo_votacao == 'Secreta':
            await database_sync_to_async(Voto.objects.filter(pk=voto.pk).update)(opcao='')

        await self.send(text_data=json.dumps({
            'action': 'voto_confirmado',
            'pauta_id': pauta_id,
            'em_delegacao': em_delegacao,
            'hash': voto.hash_auditoria,
        }))

        await self._broadcast_resultados(pauta)

    async def _registar_presenca(self):
        if not self.usuario:
            return
        await database_sync_to_async(
            PresencaAssembleia.objects.get_or_create)(
            assembleia_id=self.assembleia_pk,
            usuario_id=self.usuario.id,
            defaults={'presente_em': timezone.now(), 'ip_registro': ''}
        )

    async def _broadcast_quorum(self):
        data = await self._get_quorum_data()
        await self.channel_layer.group_send(
            self.room_group_name,
            {'type': 'quorum_update', 'data': data}
        )

    async def _broadcast_resultados(self, pauta):
        data = await self._get_pauta_resultados(pauta)
        await self.channel_layer.group_send(
            self.room_group_name,
            {'type': 'resultados_update', 'data': data}
        )

    async def quorum_update(self, event):
        await self.send(text_data=json.dumps({'action': 'quorum', **event['data']}))

    async def resultados_update(self, event):
        await self.send(text_data=json.dumps({'action': 'resultados', **event['data']}))

    async def votacao_aberta(self, event):
        await self.send(text_data=json.dumps({'action': 'votacao_aberta', **event['data']}))

    async def votacao_encerrada(self, event):
        await self.send(text_data=json.dumps({'action': 'votacao_encerrada', **event['data']}))

    async def votacao_reaberta(self, event):
        await self.send(text_data=json.dumps({'action': 'votacao_reaberta', **event['data']}))

    async def voto_registado(self, event):
        await self.send(text_data=json.dumps(event['data']))

    # ─── Chat ─────────────────────────────────────────────────────────────────

    async def _handle_raise_hand(self, data):
        if not self.usuario:
            return
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'broadcast_chat',
                'data': {
                    'action': 'raise_hand',
                    'nome': self.usuario.nome,
                    'user_id': self.usuario.id,
                },
            }
        )

    async def _handle_lower_hand(self, data):
        nome = data.get('nome', '')
        if not nome or not self.usuario:
            return
        papel = getattr(self.usuario, 'papel', '')
        if papel != 'Administrador':
            return
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'broadcast_chat',
                'data': {
                    'action': 'lower_hand',
                    'nome': nome,
                },
            }
        )

    async def _handle_chat_message(self, data):
        texto = data.get('texto', '').strip()
        if not texto or not self.usuario:
            return
        msg = await database_sync_to_async(MensagemChat.objects.create)(
            assembleia_id=self.assembleia_pk,
            usuario=self.usuario,
            tipo='texto',
            texto=texto,
        )
        print(f'[CHAT SEND] user={self.usuario.nome} msg_id={msg.id} texto={texto[:50]} group={self.room_group_name} channel={self.channel_name}')
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'broadcast_chat',
                'data': {
                    'action': 'chat_message',
                    'id': msg.id,
                    'nome': self.usuario.nome,
                    'user_id': self.usuario.id,
                    'texto': texto,
                    'created_at': msg.created_at.isoformat(),
                },
            }
        )
        print(f'[CHAT BROADCAST DONE] group={self.room_group_name}')

    async def _handle_chat_reaction(self, data):
        reacao = data.get('reacao', '')
        if reacao not in ('mao', 'palmas', 'coracao') or not self.usuario:
            return
        msg = await database_sync_to_async(MensagemChat.objects.create)(
            assembleia_id=self.assembleia_pk,
            usuario=self.usuario,
            tipo='reacao',
            reacao=reacao,
        )
        emojis = {'mao': '🖐️', 'palmas': '👏', 'coracao': '❤️'}
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'broadcast_chat',
                'data': {
                    'action': 'chat_reaction',
                    'id': msg.id,
                    'nome': self.usuario.nome,
                    'user_id': self.usuario.id,
                    'reacao': reacao,
                    'emoji': emojis.get(reacao, '❤️'),
                    'created_at': msg.created_at.isoformat(),
                },
            }
        )

    async def broadcast_chat(self, event):
        try:
            user_nome = self.usuario.nome if self.usuario else 'anon'
            data = event['data']
            print(f'[CHAT RECV] target_user={user_nome} action={data.get("action")} from={data.get("nome")} text={str(data.get("texto",""))[:50]}')
            await self.send(text_data=json.dumps(event['data']))
        except Exception as e:
            print(f'[CHAT RECV ERROR] user={self.usuario.nome if self.usuario else "anon"} error={e}')

    async def _enviar_historico_chat(self):
        msgs = await database_sync_to_async(
            lambda: list(MensagemChat.objects.filter(
                assembleia_id=self.assembleia_pk
            ).select_related('usuario').order_by('-created_at')[:50])
        )()
        lista = []
        for m in reversed(msgs):
            item = {
                'id': m.id,
                'tipo': m.tipo,
                'nome': m.usuario.nome,
                'user_id': m.usuario.id,
                'created_at': m.created_at.isoformat(),
            }
            if m.tipo == 'reacao':
                emojis = {'mao': '🖐️', 'palmas': '👏', 'coracao': '❤️'}
                item['reacao'] = m.reacao
                item['emoji'] = emojis.get(m.reacao, '❤️')
            else:
                item['texto'] = m.texto
            lista.append(item)
        await self.send(text_data=json.dumps({
            'action': 'chat_historico',
            'mensagens': lista,
        }))

    async def _enviar_estado_votacao(self):
        """Envia estado atual da votação para o recém-conectado."""
        try:
            pauta_ativa = await database_sync_to_async(
                lambda: PautaVotacao.objects.filter(
                    assembleia_id=self.assembleia_pk,
                    status='Em Votacao'
                ).first()
            )()
            if pauta_ativa:
                print(f'[WS VOTACAO ESTADO] Enviando votacao_aberta para {self.usuario.nome if self.usuario else "anon"} pauta={pauta_ativa.id} {pauta_ativa.titulo}')
                await self.send(text_data=json.dumps({
                    'action': 'votacao_aberta',
                    'pauta_id': pauta_ativa.id,
                    'titulo': pauta_ativa.titulo,
                    'tipo_votacao': pauta_ativa.tipo_votacao,
                    'descricao': pauta_ativa.descricao or '',
                }))
            else:
                print(f'[WS VOTACAO ESTADO] Nenhuma pauta ativa para {self.usuario.nome if self.usuario else "anon"}')
        except Exception as e:
            print(f'[WS VOTACAO ESTADO] ERRO: {e}')

    @database_sync_to_async
    def _get_quorum_data(self):
        try:
            a = Assembleia.objects.get(pk=self.assembleia_pk)
        except Assembleia.DoesNotExist:
            return {'presentes': 0, 'quorum_minimo': 0, 'atingido': False}
        presentes = list(a.presencas.filter(presente_em__isnull=False).select_related('usuario').values('usuario__nome')[:50])
        return {
            'presentes': a.presentes_count,
            'quorum_minimo': a.quorum_minimo,
            'atingido': a.quorum_atingido,
            'lista_presentes': [p['usuario__nome'] for p in presentes],
            'total_eleitores': a.total_eleitores,
        }

    @database_sync_to_async
    def _get_pauta_resultados(self, pauta):
        return {
            'pauta_id': pauta.id,
            'titulo': pauta.titulo,
            'favor': pauta.votos_favor,
            'contra': pauta.votos_contra,
            'abstencao': pauta.votos_abstencao,
            'total': pauta.total_votos,
            'status': pauta.status,
            'resultado_final': pauta.resultado_final,
        }

    @database_sync_to_async
    def _verificar_elegibilidade(self):
        if not self.usuario:
            return False
        ef = EstadoFinanceiro.objects.filter(despachante_id=self.usuario.id).first()
        if ef and ef.estado == 'Irregular':
            return False
        return True

    @database_sync_to_async
    def _log_assembleia_async(self, acao, detalhes=None):
        LogAssembleia.objects.create(
            assembleia_id=self.assembleia_pk,
            usuario=self.usuario,
            acao=acao,
            detalhes=detalhes or {},
        )
