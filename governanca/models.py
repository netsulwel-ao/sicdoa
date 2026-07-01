import uuid
import hashlib
import json
import os
from datetime import date
from decimal import Decimal

from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator

from .utils import (
    validate_date_not_past,
    validate_date_not_future,
    validate_date_range,
    validate_no_overlap,
)


class Assembleia(models.Model):
    STATUS = [
        ('Agendada', 'Agendada'),
        ('Em Curso', 'Em Curso'),
        ('Concluida', 'Concluida'),
        ('Cancelada', 'Cancelada'),
    ]

    titulo = models.CharField(max_length=300)
    descricao = models.TextField(blank=True, default='')
    data_hora = models.DateTimeField(db_index=True)
    data_encerramento = models.DateTimeField(null=True, blank=True)
    local = models.CharField(max_length=300, blank=True, default='Sala Virtual CDOA')

    link_streaming = models.CharField(max_length=500, blank=True, default='')
    livekit_room = models.CharField(max_length=100, blank=True, default='')

    status = models.CharField(max_length=20, choices=STATUS, default='Agendada', db_index=True)

    quorum_minimo = models.IntegerField(default=0, help_text='Número mínimo de presentes para quórum')
    total_eleitores = models.IntegerField(default=0, help_text='Total de despachantes com direito a voto')
    max_procuracao = models.IntegerField(default=1, help_text='Máximo de procurações que um membro pode receber')

    created_by = models.ForeignKey('users.Usuario', on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    ultima_actividade = models.DateTimeField(null=True, blank=True, help_text='Última actividade (chat, voto, presença) para detecting inactividade')

    hash_integridade = models.CharField(max_length=64, blank=True, default='')

    class Meta:
        db_table = 'governanca_assembleias'
        ordering = ['-data_hora']
        verbose_name = 'Assembleia'
        verbose_name_plural = 'Assembleias'

    def __str__(self):
        return f'{self.titulo} - {self.data_hora:%d/%m/%Y %H:%M}'

    def clean(self):
        # Assembleia não pode ser criada para data passada, a menos que seja edição
        if self.pk:
            # Se já existe, permitir editar, mas não alterar data para passado?
            pass
        else:
            validate_date_not_past(self.data_hora, field_name="Data e Hora", allow_today=True)
        
        # Se data de encerramento existe, deve ser depois da data de início
        if self.data_encerramento:
            validate_date_range(self.data_hora, self.data_encerramento, "Data e Hora", "Data de Encerramento")

    def save(self, *args, **kwargs):
        if not kwargs.get('update_fields'):
            self.full_clean()
        super().save(*args, **kwargs)

    @property
    def presentes_count(self):
        membros_mesa_ids = list(self.mesa.values_list('usuario_id', flat=True))
        return self.presencas.filter(
            presente_em__isnull=False
        ).filter(
            Q(usuario__papel__in=['Administrador', 'Despachante Oficial']) |
            (
                Q(usuario__papel='Colaborador Institucional') & (
                    Q(usuario__permissoes_diretas__codigo='gerir_assembleia') |
                    Q(usuario__funcao__permissoes__codigo='gerir_assembleia') |
                    Q(usuario_id__in=membros_mesa_ids)
                )
            )
        ).distinct().count()

    @property
    def quorum_atingido(self):
        return self.presentes_count >= self.quorum_minimo

    @property
    def total_pautas(self):
        return self.pautas.count()

    @property
    def pautas_concluidas(self):
        return self.pautas.filter( status='Concluida' ).count()

    @property
    def quorum_previsto(self):
        return self.respostas_presenca.filter(resposta='Sim').count()

    def gerar_hash_integridade(self):
        dados = {
            'id': self.id,
            'titulo': self.titulo,
            'data_hora': str(self.data_hora),
            'pautas': [
                {
                    'id': p.id,
                    'titulo': p.titulo,
                    'resultado': p.resultado_final,
                    'total_votos': p.total_votos,
                }
                for p in self.pautas.with_vote_counts()
            ],
            'presentes': self.presentes_count,
            'encerramento': str(self.data_encerramento or ''),
        }
        raw = json.dumps(dados, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(raw.encode()).hexdigest()


class PautaVotacaoManager(models.Manager):
    def with_vote_counts(self):
        from django.db.models import Count, Q
        return self.get_queryset().annotate(
            total_votos_count=Count('votos'),
            votos_favor_count=Count('votos', filter=Q(votos__opcao='Favor')),
            votos_contra_count=Count('votos', filter=Q(votos__opcao='Contra')),
            votos_abstencao_count=Count('votos', filter=Q(votos__opcao='Abstencao')),
            votos_delegados_count=Count('votos', filter=Q(votos__em_delegacao=True)),
        )


class PautaVotacao(models.Model):
    STATUS = [
        ('Pendente', 'Pendente'),
        ('Em Votacao', 'Em Votacao'),
        ('Concluida', 'Concluida'),
    ]
    assembleia = models.ForeignKey(Assembleia, on_delete=models.CASCADE, related_name='pautas')
    titulo = models.CharField(max_length=300)
    descricao = models.TextField(blank=True, default='')
    ordem = models.IntegerField(default=0, db_index=True)
    tipo_votacao = models.CharField(max_length=20, choices=[
        ('Aberta', 'Aberta'),
        ('Secreta', 'Secreta'),
    ], default='Aberta')
    status = models.CharField(max_length=20, choices=STATUS, default='Pendente', db_index=True)

    resultado_final = models.CharField(max_length=50, blank=True, default='')

    iniciado_em = models.DateTimeField(null=True, blank=True)
    encerrado_em = models.DateTimeField(null=True, blank=True)
    reaberta = models.BooleanField(default=False)
    reaberta_em = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    objects = PautaVotacaoManager()

    class Meta:
        db_table = 'governanca_pautas'
        ordering = ['ordem']
        verbose_name = 'Pauta de Votação'
        verbose_name_plural = 'Pautas de Votação'

    def __str__(self):
        return f'{self.ordem}. {self.titulo}'

    def clean(self):
        # Valida que data de encerramento é depois de início
        if self.iniciado_em and self.encerrado_em:
            validate_date_range(self.iniciado_em, self.encerrado_em, "Iniciado em", "Encerrado em")

    def save(self, *args, **kwargs):
        if not kwargs.get('update_fields'):
            self.full_clean()
        super().save(*args, **kwargs)

    @property
    def total_votos(self):
        if hasattr(self, 'total_votos_count'):
            return self.total_votos_count
        return self.votos.count()

    @property
    def votos_favor(self):
        if hasattr(self, 'votos_favor_count'):
            return self.votos_favor_count
        return self.votos.filter(opcao='Favor').count()

    @property
    def votos_contra(self):
        if hasattr(self, 'votos_contra_count'):
            return self.votos_contra_count
        return self.votos.filter(opcao='Contra').count()

    @property
    def votos_abstencao(self):
        if hasattr(self, 'votos_abstencao_count'):
            return self.votos_abstencao_count
        return self.votos.filter(opcao='Abstencao').count()

    @property
    def votos_delegados(self):
        if hasattr(self, 'votos_delegados_count'):
            return self.votos_delegados_count
        return self.votos.filter(em_delegacao=True).count()

    def apurar_resultado(self):
        if self.total_votos == 0:
            self.resultado_final = 'Sem votos'
            self.save()
            return
        quorum_atingido = self.assembleia.presentes_count >= self.assembleia.quorum_minimo
        if not quorum_atingido:
            self.resultado_final = 'Quórum não atingido'
            self.save()
            return
        if self.votos_favor > self.votos_contra:
            self.resultado_final = 'Aprovada'
        elif self.votos_contra > self.votos_favor:
            self.resultado_final = 'Rejeitada'
        else:
            self.resultado_final = 'Empate'
        self.save()


class PresencaAssembleia(models.Model):
    assembleia = models.ForeignKey(Assembleia, on_delete=models.CASCADE, related_name='presencas')
    usuario = models.ForeignKey('users.Usuario', on_delete=models.CASCADE)
    presente_em = models.DateTimeField(null=True, blank=True)
    saiu_em = models.DateTimeField(null=True, blank=True)
    ip_registro = models.GenericIPAddressField(blank=True, null=True)

    class Meta:
        db_table = 'governanca_presencas'
        unique_together = ('assembleia', 'usuario')
        verbose_name = 'Presença'
        verbose_name_plural = 'Presenças'

    def clean(self):
        if self.presente_em and self.saiu_em and self.saiu_em < self.presente_em:
            raise ValidationError({'saiu_em': 'A data/hora de saída não pode ser anterior à data/hora de entrada.'})

    def __str__(self):
        return f'{self.usuario.nome} - {self.assembleia.titulo}'


class Procuracao(models.Model):
    STATUS = [
        ('Pendente', 'Pendente'),
        ('Confirmada', 'Confirmada'),
        ('Cancelada', 'Cancelada'),
    ]
    assembleia = models.ForeignKey(Assembleia, on_delete=models.CASCADE, related_name='procuracao')
    outorgante = models.ForeignKey('users.Usuario', on_delete=models.CASCADE, related_name='procuracao_outorgante')
    outorgado = models.ForeignKey('users.Usuario', on_delete=models.CASCADE, related_name='procuracao_outorgado')
    codigo_otp = models.CharField(max_length=64, blank=True, default='')
    status = models.CharField(max_length=20, choices=STATUS, default='Pendente', db_index=True)
    confirmado_em = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'governanca_procuracao'
        unique_together = ('assembleia', 'outorgante')
        verbose_name = 'Procuração'
        verbose_name_plural = 'ProcuraçÃµes'

    def __str__(self):
        return f'{self.outorgante.nome} â†’ {self.outorgado.nome}'


class Voto(models.Model):
    pauta = models.ForeignKey(PautaVotacao, on_delete=models.CASCADE, related_name='votos')
    usuario = models.ForeignKey('users.Usuario', on_delete=models.CASCADE)
    opcao = models.CharField(max_length=20, choices=[
        ('Favor', 'A Favor'),
        ('Contra', 'Contra'),
        ('Abstencao', 'Abstenção'),
    ])
    opcao_encriptada = models.CharField(max_length=128, blank=True, default='')
    em_delegacao = models.BooleanField(default=False)
    delegado_de = models.ForeignKey('users.Usuario', on_delete=models.SET_NULL, null=True, blank=True, related_name='votos_delegados')
    hash_auditoria = models.CharField(max_length=64, blank=True, default='')
    recibo_hash = models.CharField(max_length=64, blank=True, default='')
    votado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'governanca_votos'
        unique_together = ('pauta', 'usuario', 'em_delegacao', 'delegado_de')
        verbose_name = 'Voto'
        verbose_name_plural = 'Votos'

    def __str__(self):
        if self.pauta.tipo_votacao == 'Secreta':
            return f'Voto # {self.id} (secreto)'
        return f'{self.usuario.nome} - {self.opcao}'

    def clean(self):
        if self.delegado_de_id is None:
            dupes = Voto.objects.filter(
                pauta=self.pauta, usuario=self.usuario,
                em_delegacao=self.em_delegacao, delegado_de__isnull=True
            )
        else:
            dupes = Voto.objects.filter(
                pauta=self.pauta, usuario=self.usuario,
                em_delegacao=self.em_delegacao, delegado_de=self.delegado_de
            )
        if self.pk:
            dupes = dupes.exclude(pk=self.pk)
        if dupes.exists():
            raise ValidationError('Já existe um voto registado com esta configuração.')

    def save(self, *args, **kwargs):
        ts = timezone.now().isoformat()
        raw = f'{self.pauta_id}-{self.usuario_id}-{self.opcao}-{self.em_delegacao}-{ts}'
        self.hash_auditoria = hashlib.sha256(raw.encode()).hexdigest()
        recibo_raw = f'{self.pauta_id}-{self.usuario_id}-{ts}-{os.urandom(8).hex()}'
        self.recibo_hash = hashlib.sha256(recibo_raw.encode()).hexdigest()
        if not kwargs.get('update_fields'):
            self.full_clean()
        if self.pauta.tipo_votacao == 'Secreta':
            salt = os.urandom(16).hex()
            self.opcao_encriptada = hashlib.sha256(f'{self.opcao}-{salt}'.encode()).hexdigest()
        super().save(*args, **kwargs)
        if self.pauta.tipo_votacao == 'Secreta':
            self.opcao = ''  # só limpa após save bem-sucedido


class ReciboVoto(models.Model):
    voto = models.OneToOneField(Voto, on_delete=models.CASCADE, related_name='recibo')
    recibo_hash = models.CharField(max_length=64, unique=True)
    pauta_titulo = models.CharField(max_length=300)
    data_voto = models.DateTimeField()
    verificado = models.BooleanField(default=False)

    class Meta:
        db_table = 'governanca_recibos_voto'
        verbose_name = 'Recibo de Voto'
        verbose_name_plural = 'Recibos de Voto'


class ManifestoIntegridade(models.Model):
    assembleia = models.ForeignKey(Assembleia, on_delete=models.CASCADE, related_name='manifestos')
    hash_consolidado = models.CharField(max_length=64)
    dados_json = models.TextField(default='{}')
    gerado_em = models.DateTimeField(auto_now_add=True)
    gerado_por = models.ForeignKey('users.Usuario', on_delete=models.SET_NULL, null=True)

    class Meta:
        db_table = 'governanca_manifestos'
        verbose_name = 'Manifesto de Integridade'
        verbose_name_plural = 'Manifestos de Integridade'

    def __str__(self):
        return f'Manifesto - {self.assembleia.titulo} - {self.gerado_em:%d/%m/%Y}'


class AtaDigital(models.Model):
    STATUS_ASSINATURA = [
        ('Pendente', 'Pendente'),
        ('Aguardando Presidente', 'Aguardando Presidente'),
        ('Aguardando Secretario', 'Aguardando Secretário'),
        ('Assinada', 'Assinada'),
        ('Publicada', 'Publicada'),
    ]
    assembleia = models.ForeignKey(Assembleia, on_delete=models.CASCADE, related_name='atas')
    conteudo = models.TextField()
    assinatura_hash = models.CharField(max_length=64, blank=True, default='')
    assinado_por = models.ForeignKey('users.Usuario', on_delete=models.SET_NULL, null=True, blank=True, related_name='atas_assinadas')
    assinado_em = models.DateTimeField(null=True, blank=True)
    assinatura_hash_presidente = models.CharField(max_length=64, blank=True, default='')
    assinado_presidente_em = models.DateTimeField(null=True, blank=True)
    assinatura_hash_secretario = models.CharField(max_length=64, blank=True, default='')
    assinado_secretario_em = models.DateTimeField(null=True, blank=True)
    status_assinatura = models.CharField(max_length=25, choices=STATUS_ASSINATURA, default='Pendente', db_index=True)
    publicado_em = models.DateTimeField(null=True, blank=True)
    arquivo_pdf = models.CharField(max_length=500, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'governanca_atas'
        ordering = ['-created_at']
        verbose_name = 'Ata Digital'
        verbose_name_plural = 'Atas Digitais'

    def __str__(self):
        return f'Ata - {self.assembleia.titulo} - {self.created_at:%d/%m/%Y}'


class Notificacao(models.Model):
    TIPOS = [
        ('assembleia_agendada', 'Assembleia Agendada'),
        ('assembleia_iniciada', 'Assembleia Iniciada'),
        ('votacao_aberta', 'Votação Aberta'),
        ('procuracao_solicitada', 'Procuração Solicitada'),
        ('procuracao_confirmada', 'Procuração Confirmada'),
        ('resultado_publicado', 'Resultado Publicado'),
        ('ata_publicada', 'Ata Publicada'),
        ('quota_gerada', 'Quota Gerada'),
        ('pagamento_confirmado', 'Pagamento Confirmado'),
        ('certidao_emitida', 'Certidão Emitida'),
        ('carteira_expirada', 'Carteira Expirada'),
        ('estado_suspenso', 'Estado Suspenso'),
        ('estado_regularizado', 'Estado Regularizado'),
        ('consulta_publicada', 'Consulta Publicada'),
        ('novo_comentario', 'Novo Comentário'),
        ('votacao_aberta', 'Votação Aberta'),
        ('consulta_encerrada', 'Consulta Encerrada'),
        ('relatorio_publicado', 'Relatório Publicado'),
        ('versao_final_publicada', 'Versão Final Publicada'),
        ('convocatoria_publicada', 'Convocatória Publicada'),
        ('votacao_reaberta', 'Votação Reaberta'),
        ('ata_assinada', 'Ata Assinada'),
        ('cargo_atribuido', 'Cargo Atribuído'),
        ('cargo_removido', 'Cargo Removido'),
    ]
    usuario = models.ForeignKey('users.Usuario', on_delete=models.CASCADE, related_name='notificacoes')
    tipo = models.CharField(max_length=30, choices=TIPOS, db_index=True)
    titulo = models.CharField(max_length=300)
    mensagem = models.TextField(blank=True, default='')
    link = models.CharField(max_length=500, blank=True, default='')
    lida = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'governanca_notificacoes'
        ordering = ['-created_at']
        verbose_name = 'Notificação'
        verbose_name_plural = 'NotificaçÃµes'
        indexes = [
            models.Index(fields=['usuario', '-created_at'], name='ix_notificacoes_usuario_data'),
        ]

    def __str__(self):
        return f'{self.titulo} - {self.usuario.nome}'


class DocumentoAssembleia(models.Model):
    TIPOS = [
        ('ata', 'Ata'),
        ('relatorio', 'Relatório'),
        ('decreto', 'Decreto'),
        ('outro', 'Outro'),
    ]
    assembleia = models.ForeignKey(Assembleia, on_delete=models.CASCADE, related_name='documentos')
    tipo = models.CharField(max_length=20, choices=TIPOS, default='ata')
    titulo = models.CharField(max_length=300)
    descricao = models.TextField(blank=True, default='')
    conteudo = models.TextField(blank=True, default='')
    arquivo = models.FileField(upload_to='documentos_assembleia/%Y/%m/', max_length=500, blank=True, null=True, validators=[FileExtensionValidator(['pdf', 'doc', 'docx', 'jpg', 'png'])])
    publicado = models.BooleanField(default=False, db_index=True)
    publicado_em = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey('users.Usuario', on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'governanca_documentos'
        ordering = ['-created_at']
        verbose_name = 'Documento'
        verbose_name_plural = 'Documentos'

    def __str__(self):
        return self.titulo


class MembroMesa(models.Model):
    FUNCOES = [
        ('Presidente', 'Presidente'),
        ('Vice-Presidente', 'Vice-Presidente'),
        ('1º Secretário', '1º Secretário'),
        ('2º Secretário', '2º Secretário'),
        ('Secretário', 'Secretário'),
        ('Vogal', 'Vogal'),
    ]
    assembleia = models.ForeignKey(Assembleia, on_delete=models.CASCADE, related_name='mesa')
    usuario = models.ForeignKey('users.Usuario', on_delete=models.CASCADE)
    funcao = models.CharField(max_length=30, choices=FUNCOES)
    ordem = models.IntegerField(default=0, db_index=True)

    class Meta:
        db_table = 'governanca_mesa'
        ordering = ['ordem']
        unique_together = ('assembleia', 'usuario')
        verbose_name = 'Membro da Mesa'
        verbose_name_plural = 'Membros da Mesa'

    def __str__(self):
        return f'{self.usuario.nome} â€” {self.funcao}'


class MensagemChat(models.Model):
    assembleia = models.ForeignKey(Assembleia, on_delete=models.CASCADE, related_name='mensagens_chat')
    usuario = models.ForeignKey('users.Usuario', on_delete=models.CASCADE)
    tipo = models.CharField(max_length=10, choices=[('texto', 'Texto'), ('reacao', 'Reação')], default='texto')
    texto = models.TextField(blank=True, default='')
    reacao = models.CharField(max_length=10, blank=True, default='', choices=[
        ('mao', 'Mão ðŸ–ï¸'),
        ('palmas', 'Palmas ðŸ‘'),
        ('coracao', 'Coração â¤ï¸'),
    ])
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'governanca_chat'
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['assembleia', '-created_at'], name='idx_chat_assembleia_data'),
        ]
        verbose_name = 'Mensagem de Chat'
        verbose_name_plural = 'Mensagens de Chat'

    def __str__(self):
        if self.tipo == 'reacao':
            return f'{self.usuario.nome} â€” reação {self.reacao}'
        return f'{self.usuario.nome}: {self.texto[:50]}'

# ═══════════════════════════════════════════════════════════════════════════════
# Submódulo 3: Escuta Activa, Fórum & Transparência
# ═══════════════════════════════════════════════════════════════════════════════

class ConsultaPublica(models.Model):
    STATUS = [
        ('Rascunho', 'Rascunho'),
        ('Publicada', 'Publicada'),
        ('EmVotacao', 'Em Votação'),
        ('Encerrada', 'Encerrada'),
        ('Aprovada', 'Aprovada (Versão Final)'),
        ('Rejeitada', 'Rejeitada'),
    ]
    titulo = models.CharField(max_length=300)
    descricao = models.TextField(blank=True, default='')
    documento = models.FileField(upload_to='consultas_publicas/%Y/%m/', max_length=500, blank=True, default='', validators=[FileExtensionValidator(['pdf', 'doc', 'docx', 'jpg', 'png'])])
    prazo_fim = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS, default='Rascunho', db_index=True)
    criado_por = models.ForeignKey('users.Usuario', on_delete=models.CASCADE, related_name='consultas_criadas')
    publicado_em = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'governanca_consultas_publicas'
        ordering = ['-created_at']
        verbose_name = 'Consulta Pública'
        verbose_name_plural = 'Consultas Públicas'

    def __str__(self):
        return self.titulo

    def clean(self):
        if self.prazo_fim:
            validate_date_not_past(self.prazo_fim, field_name="Prazo de Fim", allow_today=True)
        if self.publicado_em:
            validate_date_not_future(self.publicado_em, field_name="Data de Publicação")

    def save(self, *args, **kwargs):
        if not kwargs.get('update_fields'):
            self.full_clean()
        super().save(*args, **kwargs)


class ArtigoDocumento(models.Model):
    consulta = models.ForeignKey(ConsultaPublica, on_delete=models.CASCADE, related_name='artigos')
    numero = models.IntegerField()
    titulo = models.CharField(max_length=300, blank=True, default='')
    conteudo = models.TextField(blank=True, default='')
    ordem = models.IntegerField(default=0, db_index=True)

    class Meta:
        db_table = 'governanca_artigos_documento'
        ordering = ['ordem', 'numero']
        unique_together = ('consulta', 'numero')
        verbose_name = 'Artigo do Documento'
        verbose_name_plural = 'Artigos do Documento'

    def __str__(self):
        return f'Artigo {self.numero} — {self.consulta.titulo}'


class Comentario(models.Model):
    artigo = models.ForeignKey(ArtigoDocumento, on_delete=models.CASCADE, related_name='comentarios')
    autor = models.ForeignKey('users.Usuario', on_delete=models.CASCADE, related_name='comentarios_consulta')
    texto = models.TextField()
    resposta_a = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='respostas')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'governanca_comentarios_consulta'
        ordering = ['created_at']
        verbose_name = 'Comentário'
        verbose_name_plural = 'Comentários'

    def __str__(self):
        return f'{self.autor.nome}: {self.texto[:60]}'


class VotacaoConsulta(models.Model):
    consulta = models.ForeignKey(ConsultaPublica, on_delete=models.CASCADE, related_name='votacoes')
    data_inicio = models.DateTimeField(auto_now_add=True, db_index=True)
    data_fim = models.DateTimeField(null=True, blank=True)
    ativa = models.BooleanField(default=True)

    class Meta:
        db_table = 'governanca_votacoes_consulta'
        ordering = ['-data_inicio']
        verbose_name = 'Votação de Consulta'
        verbose_name_plural = 'Votações de Consulta'

    def __str__(self):
        return f'Votação — {self.consulta.titulo}'


class VotoConsulta(models.Model):
    VOTO_CHOICES = [
        ('Favor', 'Favor'),
        ('Contra', 'Contra'),
        ('Abstencao', 'Abstenção'),
    ]
    votacao = models.ForeignKey(VotacaoConsulta, on_delete=models.CASCADE, related_name='votos')
    usuario = models.ForeignKey('users.Usuario', on_delete=models.CASCADE, related_name='votos_consulta')
    voto = models.CharField(max_length=10, choices=VOTO_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'governanca_votos_consulta'
        unique_together = ('votacao', 'usuario')
        verbose_name = 'Voto em Consulta'
        verbose_name_plural = 'Votos em Consulta'

    def __str__(self):
        return f'{self.usuario.nome} — {self.voto}'


class RelatorioConsulta(models.Model):
    consulta = models.OneToOneField(ConsultaPublica, on_delete=models.CASCADE, related_name='relatorio')
    conteudo = models.JSONField(blank=True, default=dict)
    assinatura_hash = models.CharField(max_length=64, blank=True, default='')
    arquivo_pdf = models.CharField(max_length=500, blank=True, default='')
    criado_em = models.DateTimeField(auto_now_add=True)
    criado_por = models.ForeignKey('users.Usuario', on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        db_table = 'governanca_relatorios_consulta'
        verbose_name = 'Relatório de Consulta'
        verbose_name_plural = 'Relatórios de Consulta'

    def __str__(self):
        return f'Relatório — {self.consulta.titulo}'


# ═══════════════════════════════════════════════════════════════════════════════
# Submódulo: Gestão Financeira de Quotas
# ═══════════════════════════════════════════════════════════════════════════════

class CategoriaMembro(models.Model):
    nome = models.CharField(max_length=100, db_index=True)
    slug = models.SlugField(max_length=100, unique=True)
    isento = models.BooleanField(default=False)
    ordem = models.IntegerField(default=0, db_index=True)
    class Meta:
        db_table = 'governanca_categorias_membro'
        ordering = ['ordem', 'nome']
        verbose_name = 'Categoria de Membro'
        verbose_name_plural = 'Categorias de Membro'
    def __str__(self):
        return self.nome


class TipoQuota(models.Model):
    nome = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100, unique=True)
    recorrente = models.BooleanField(default=False)
    dias_intervalo = models.IntegerField(null=True, blank=True)
    class Meta:
        db_table = 'governanca_tipos_quota'
        ordering = ['pk']
        verbose_name = 'Tipo de Quota'
        verbose_name_plural = 'Tipos de Quota'
    def __str__(self):
        return self.nome


class QuotaConfig(models.Model):
    categoria = models.ForeignKey(CategoriaMembro, on_delete=models.SET_NULL, null=True, blank=True)
    tipo = models.ForeignKey(TipoQuota, on_delete=models.SET_NULL, null=True, blank=True)
    ano = models.IntegerField(db_index=True)
    mes = models.IntegerField(null=True, blank=True, db_index=True)
    valor = models.DecimalField(max_digits=12, decimal_places=2)
    data_vencimento = models.DateField()
    multa_percentual = models.DecimalField(max_digits=5, decimal_places=2, default=0.50, help_text='Percentagem de multa ao dia sobre o valor da quota (ex: 0.50 = 0.5%)')
    dias_carencia = models.PositiveSmallIntegerField(default=5, help_text='Dias de tolerância após vencimento antes de aplicar multa')
    ativa = models.BooleanField(default=True, help_text='Se ativa, a configuração está disponível para geração de quotas', db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        db_table = 'governanca_quota_config'
        verbose_name = 'Configuração de Quota'
        verbose_name_plural = 'Configurações de Quotas'
        unique_together = ('categoria', 'tipo', 'ano', 'mes')
    def __str__(self):
        label = f'{self.tipo}' if self.tipo else 'Mensal'
        cat = f' [{self.categoria}]' if self.categoria else ''
        return f'{label} {self.mes:02d}/{self.ano}{cat} — Kz {self.valor}' if self.mes else f'{label} {self.ano}{cat} — Kz {self.valor}'


class QuotaGerada(models.Model):
    STATUS = [
        ('Pendente','Pendente'),
        ('Atrasada','Atrasada'),
        ('Pendente Confirmacao','Pendente Confirmação'),
        ('Paga','Paga'),
        ('Cancelada','Cancelada'),
        ('Isenta','Isenta'),
    ]
    despachante = models.ForeignKey('users.Usuario', on_delete=models.CASCADE, related_name='quotas')
    tipo = models.ForeignKey(TipoQuota, on_delete=models.SET_NULL, null=True, blank=True)
    ano = models.IntegerField(null=True, blank=True, db_index=True)
    mes = models.IntegerField(null=True, blank=True, db_index=True)
    periodo_inicio = models.DateField(null=True, blank=True)
    periodo_fim = models.DateField(null=True, blank=True)
    descricao = models.CharField(max_length=300, blank=True, default='')
    valor = models.DecimalField(max_digits=12, decimal_places=2)
    valor_original = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, help_text='Valor base sem multa')
    valor_multa = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    valor_total = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, help_text='Valor original + multa')
    data_vencimento = models.DateField()
    data_envio = models.DateField(null=True, blank=True, help_text='Data em que a quota foi enviada ao membro')
    data_pagamento = models.DateTimeField(null=True, blank=True)
    referencia = models.CharField(max_length=100, unique=True, blank=True, default='', help_text='Referência amigável (ex: QUOTA-MENSAL-06-2026-00001)')
    status = models.CharField(max_length=20, choices=STATUS, default='Pendente', db_index=True)
    fatura_uuid = models.CharField(max_length=36, unique=True, default=uuid.uuid4)
    observacoes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        db_table = 'governanca_quotas_geradas'
        ordering = ['-ano', '-mes']
        verbose_name = 'Quota Gerada'
        verbose_name_plural = 'Quotas Geradas'
    def __str__(self):
        t = f'{self.tipo}' if self.tipo else 'Mensal'
        r = f' [{self.referencia}]' if self.referencia else ''
        return f'{self.despachante.nome} - {t} {self.mes:02d}/{self.ano}{r} - {self.status}'

    def clean(self):
        # Valida período
        if self.periodo_inicio and self.periodo_fim:
            validate_date_range(self.periodo_inicio, self.periodo_fim, "Período Início", "Período Fim")
        
        # Data de pagamento não pode ser futura
        if self.data_pagamento:
            validate_date_not_future(self.data_pagamento, field_name="Data de Pagamento")

    def save(self, *args, **kwargs):
        if not kwargs.get('update_fields'):
            self.full_clean()
        super().save(*args, **kwargs)


class PagamentoQuota(models.Model):
    METODOS = [
        ('Multicaixa Express','Multicaixa Express'),
        ('Transferencia IBAN','Transferência IBAN'),
        ('Deposito Bancario','Depósito Bancário'),
    ]
    STATUS = [
        ('Pendente Confirmacao','Pendente Confirmação'),
        ('Confirmado','Confirmado'),
        ('Rejeitado','Rejeitado'),
    ]
    quota = models.ForeignKey(QuotaGerada, on_delete=models.CASCADE, related_name='pagamentos')
    despachante = models.ForeignKey('users.Usuario', on_delete=models.CASCADE, related_name='pagamentos_quota')
    metodo = models.CharField(max_length=30, choices=METODOS)
    comprovativo = models.FileField(upload_to='comprovativos/%Y/%m/', max_length=500, blank=True, default='')
    valor_pago = models.DecimalField(max_digits=12, decimal_places=2)
    codigo_transferencia = models.CharField(max_length=100, blank=True, default='')
    iban_origem = models.CharField(max_length=50, blank=True, default='')
    data_pagamento = models.DateTimeField(auto_now_add=True, db_index=True)
    status = models.CharField(max_length=25, choices=STATUS, default='Pendente Confirmacao', db_index=True)
    status_anterior_quota = models.CharField(max_length=20, blank=True, default='', help_text='Estado da quota antes da submissão do pagamento (para reverter se rejeitado)')
    confirmado_por = models.ForeignKey('users.Usuario', on_delete=models.SET_NULL, null=True, blank=True, related_name='pagamentos_confirmados')
    confirmado_em = models.DateTimeField(null=True, blank=True)
    observacoes = models.TextField(blank=True, default='')
    class Meta:
        db_table = 'governanca_pagamentos_quota'
        ordering = ['-data_pagamento']
        verbose_name = 'Pagamento de Quota'
        verbose_name_plural = 'Pagamentos de Quotas'
    def __str__(self):
        return f'{self.despachante.nome} - {self.metodo} - {self.status}'

    def clean(self):
        # Data de pagamento não pode ser futura
        validate_date_not_future(self.data_pagamento, field_name="Data de Pagamento")
        if self.confirmado_em:
            validate_date_not_future(self.confirmado_em, field_name="Data de Confirmação")

    def save(self, *args, **kwargs):
        if not kwargs.get('update_fields'):
            self.full_clean()
        super().save(*args, **kwargs)


class EstadoFinanceiro(models.Model):
    ESTADOS = [('Regular','Regular'),('Irregular','Irregular'),('Suspenso','Suspenso')]
    despachante = models.OneToOneField('users.Usuario', on_delete=models.CASCADE, related_name='estado_financeiro')
    estado = models.CharField(max_length=15, choices=ESTADOS, default='Regular', db_index=True)
    ultima_atualizacao = models.DateTimeField(auto_now=True)
    observacoes = models.TextField(blank=True, default='')
    class Meta:
        db_table = 'governanca_estado_financeiro'
        verbose_name = 'Estado Financeiro'
        verbose_name_plural = 'Estados Financeiros'
    def __str__(self):
        return f'{self.despachante.nome} — {self.estado}'


class IsencaoMembro(models.Model):
    despachante = models.ForeignKey('users.Usuario', on_delete=models.CASCADE, related_name='isencoes')
    tipo_quota = models.ForeignKey(TipoQuota, on_delete=models.SET_NULL, null=True, blank=True)
    data_inicio = models.DateField(db_index=True)
    data_fim = models.DateField(null=True, blank=True, db_index=True)
    motivo = models.TextField(blank=True, default='')
    aprovado_por = models.ForeignKey('users.Usuario', on_delete=models.SET_NULL, null=True, blank=True, related_name='isencoes_aprovadas')
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        db_table = 'governanca_isencoes_membro'
        verbose_name = 'Isenção de Membro'
        verbose_name_plural = 'Isenções de Membro'
    def __str__(self):
        t = f' ({self.tipo_quota})' if self.tipo_quota else ''
        return f'{self.despachante.nome}{t} - {self.data_inicio} a {self.data_fim or "indeterminado"}'

    def clean(self):
        if self.data_inicio and self.data_fim:
            validate_date_range(self.data_inicio, self.data_fim, "Data de Início", "Data de Fim")

    def save(self, *args, **kwargs):
        if not kwargs.get('update_fields'):
            self.full_clean()
        super().save(*args, **kwargs)


class HistoricoQuota(models.Model):
    ACOES = [
        ('QUOTA_GERADA', 'Quota Gerada'),
        ('QUOTA_VENCIDA', 'Quota Vencida'),
        ('PAGAMENTO_SUBMETIDO', 'Pagamento Submetido'),
        ('PAGAMENTO_APROVADO', 'Pagamento Aprovado'),
        ('PAGAMENTO_REJEITADO', 'Pagamento Rejeitado'),
        ('QUOTA_CANCELADA', 'Quota Cancelada'),
        ('QUOTA_ISENTADA', 'Quota Isentada'),
        ('ISENCAO_CRIADA', 'Isenção Criada'),
        ('ISENCAO_REMOVIDA', 'Isenção Removida'),
        ('ESTADO_FINANCEIRO_ALTERADO', 'Estado Financeiro Alterado'),
    ]
    membro = models.ForeignKey('users.Usuario', on_delete=models.CASCADE, related_name='historico_quotas')
    quota = models.ForeignKey(QuotaGerada, on_delete=models.SET_NULL, null=True, blank=True, related_name='historico')
    pagamento = models.ForeignKey(PagamentoQuota, on_delete=models.SET_NULL, null=True, blank=True, related_name='historico')
    acao = models.CharField(max_length=30, choices=ACOES, db_index=True)
    descricao = models.TextField(blank=True, default='')
    utilizador = models.ForeignKey('users.Usuario', on_delete=models.SET_NULL, null=True, blank=True, related_name='historico_quotas_acao')
    ip = models.GenericIPAddressField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    class Meta:
        db_table = 'governanca_historico_quotas'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['membro', 'created_at']),
            models.Index(fields=['quota', 'created_at']),
        ]
        verbose_name = 'Histórico de Quota'
        verbose_name_plural = 'Históricos de Quotas'
    def __str__(self):
        return f'{self.membro.nome} — {self.acao} ({self.created_at:%d/%m/%Y %H:%M})'


class CertidaoRegularidade(models.Model):
    despachante = models.ForeignKey('users.Usuario', on_delete=models.CASCADE, related_name='certidoes')
    codigo_certidao = models.CharField(max_length=36, unique=True, default=uuid.uuid4)
    data_emissao = models.DateTimeField(auto_now_add=True, db_index=True)
    data_validade = models.DateField()
    arquivo_pdf = models.CharField(max_length=500, blank=True, default='')
    assinatura_hash = models.CharField(max_length=64, blank=True, default='')
    emitido_por = models.ForeignKey('users.Usuario', on_delete=models.SET_NULL, null=True, blank=True, related_name='certidoes_emitidas')
    class Meta:
        db_table = 'governanca_certidoes_regularidade'
        ordering = ['-data_emissao']
        verbose_name = 'Certidão de Regularidade'
        verbose_name_plural = 'Certidões de Regularidade'
    def __str__(self):
        return f'Certidão {self.codigo_certidao[:8]} — {self.despachante.nome}'


class CarteiraProfissional(models.Model):
    STATUS = [('Activa','Activa'),('Expirada','Expirada'),('Suspensa','Suspensa')]
    despachante = models.OneToOneField('users.Usuario', on_delete=models.CASCADE, related_name='carteira_profissional')
    numero_carteira = models.CharField(max_length=50, unique=True)
    data_emissao = models.DateField(); data_validade = models.DateField()
    data_renovacao = models.DateField(null=True, blank=True)
    arquivo_pdf = models.CharField(max_length=500, blank=True, default='')
    status = models.CharField(max_length=15, choices=STATUS, default='Activa', db_index=True)
    class Meta:
        db_table = 'governanca_carteiras_profissionais'
        verbose_name = 'Carteira Profissional'
        verbose_name_plural = 'Carteiras Profissionais'
    def __str__(self):
        return f'{self.numero_carteira} - {self.despachante.nome} ({self.status})'

    def clean(self):
        validate_date_range(self.data_emissao, self.data_validade, "Data de Emissão", "Data de Validade")
        if self.data_renovacao:
            validate_date_range(self.data_emissao, self.data_renovacao, "Data de Emissão", "Data de Renovação")
            validate_date_not_future(self.data_renovacao, field_name="Data de Renovação")

    def save(self, *args, **kwargs):
        if not kwargs.get('update_fields'):
            self.full_clean()
        super().save(*args, **kwargs)


class Convocatoria(models.Model):
    STATUS = [
        ('Rascunho', 'Rascunho'),
        ('Publicada', 'Publicada'),
    ]
    assembleia = models.ForeignKey(Assembleia, on_delete=models.CASCADE, related_name='convocatorias')
    titulo = models.CharField(max_length=300)
    descricao = models.TextField(blank=True, default='')
    documento = models.FileField(upload_to='convocatorias/%Y/%m/', max_length=500, blank=True, default='')
    data_envio = models.DateTimeField(auto_now_add=True, db_index=True)
    prazo_confirmacao = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS, default='Rascunho', db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'governanca_convocatorias'
        ordering = ['-data_envio']
        verbose_name = 'Convocatória'
        verbose_name_plural = 'Convocatórias'

    def __str__(self):
        return f'{self.titulo} — {self.assembleia.titulo}'


class RespostaPresenca(models.Model):
    RESPOSTAS = [
        ('Sim', 'Sim'),
        ('Nao', 'Não'),
        ('Talvez', 'Talvez'),
    ]
    assembleia = models.ForeignKey(Assembleia, on_delete=models.CASCADE, related_name='respostas_presenca')
    usuario = models.ForeignKey('users.Usuario', on_delete=models.CASCADE, related_name='respostas_presenca')
    resposta = models.CharField(max_length=10, choices=RESPOSTAS)
    respondido_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'governanca_respostas_presenca'
        unique_together = ('assembleia', 'usuario')
        verbose_name = 'Resposta de Presença'
        verbose_name_plural = 'Respostas de Presença'

    def __str__(self):
        return f'{self.usuario.nome} — {self.get_resposta_display()} — {self.assembleia.titulo}'


class LogAssembleia(models.Model):
    ACOES = [
        ('entrada', 'Entrada'),
        ('saida', 'Saída'),
        ('reconexao', 'Reconexão'),
        ('procuracao_solicitada', 'Procuração Solicitada'),
        ('procuracao_confirmada', 'Procuração Confirmada'),
        ('votacao', 'Votação'),
        ('votacao_aberta', 'Votação Aberta'),
        ('votacao_encerrada', 'Votação Encerrada'),
        ('votacao_reaberta', 'Votação Reaberta'),
        ('encerramento', 'Encerramento'),
        ('reabertura', 'Reabertura'),
        ('criacao', 'Criação'),
        ('edicao', 'Edição'),
        ('assembleia_iniciada', 'Assembleia Iniciada'),
        ('assembleia_concluida', 'Assembleia Concluída'),
        ('assembleia_cancelada', 'Assembleia Cancelada'),
    ]
    assembleia = models.ForeignKey(Assembleia, on_delete=models.CASCADE, related_name='logs')
    usuario = models.ForeignKey('users.Usuario', on_delete=models.SET_NULL, null=True, blank=True)
    acao = models.CharField(max_length=30, choices=ACOES)
    detalhes = models.JSONField(blank=True, default=dict)
    ip = models.GenericIPAddressField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'governanca_logs_assembleia'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['assembleia', 'created_at']),
        ]
        verbose_name = 'Log da Assembleia'
        verbose_name_plural = 'Logs da Assembleia'

    def __str__(self):
        return f'{self.acao} — {self.assembleia.titulo} ({self.created_at:%d/%m/%Y %H:%M})'

