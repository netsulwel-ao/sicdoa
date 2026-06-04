import hashlib
import os
import time
from datetime import date

from django.utils import timezone
from django.core.exceptions import ValidationError
from django.template.loader import render_to_string


def validate_date_not_past(date_value, field_name="Data", allow_today=False):
    """Valida que uma data não está no passado (opcionalmente permite hoje)."""
    if not date_value:
        return
    if isinstance(date_value, date) and not isinstance(date_value, timezone.datetime):
        now = timezone.now()
    elif timezone.is_naive(date_value):
        now = timezone.now()
    else:
        now = timezone.localtime()
    if isinstance(date_value, timezone.datetime):
        if allow_today:
            if date_value.date() < now.date():
                raise ValidationError({field_name: f"{field_name} não pode estar no passado."})
        else:
            if date_value < now:
                raise ValidationError({field_name: f"{field_name} não pode estar no passado."})
    else:
        if allow_today:
            if date_value < now.date():
                raise ValidationError({field_name: f"{field_name} não pode estar no passado."})
        else:
            if date_value < now.date():
                raise ValidationError({field_name: f"{field_name} não pode estar no passado."})


def validate_date_not_future(date_value, field_name="Data"):
    """Valida que uma data não está no futuro."""
    if not date_value:
        return
    if isinstance(date_value, date) and not isinstance(date_value, timezone.datetime):
        now = timezone.now()
    elif timezone.is_naive(date_value):
        now = timezone.now()
    else:
        now = timezone.localtime()
    if isinstance(date_value, timezone.datetime):
        if date_value > now:
            raise ValidationError({field_name: f"{field_name} não pode estar no futuro."})
    else:
        if date_value > now.date():
            raise ValidationError({field_name: f"{field_name} não pode estar no futuro."})


def validate_date_range(start_date, end_date, start_field_name="Data de Início", end_field_name="Data de Fim"):
    """Valida que o intervalo de datas é válido (início < fim)."""
    if not start_date or not end_date:
        return
    if start_date > end_date:
        raise ValidationError(f"{start_field_name} não pode ser maior que {end_field_name}.")


def validate_no_overlap(queryset, start_field, end_field, start_value, end_value, exclude_pk=None):
    """Valida que um intervalo não se sobrepõe com outros registos."""
    filter_kwargs = {}
    if end_value:
        filter_kwargs[f"{start_field}__lt"] = end_value
    if start_value:
        filter_kwargs[f"{end_field}__gt"] = start_value
    query = queryset.filter(**filter_kwargs)
    if exclude_pk:
        query = query.exclude(pk=exclude_pk)
    if query.exists():
        raise ValidationError("Este intervalo de datas se sobrepõe com um registo já existente.")


def gerar_conteudo_documento(assembleia, tipo, created_by=None):
    from .models import DocumentoAssembleia
    presencas = assembleia.presencas.select_related('usuario').all()
    mesa = assembleia.mesa.select_related('usuario').order_by('ordem').all()
    pautas = assembleia.pautas.prefetch_related('votos__usuario').all()

    presentes = [p.usuario for p in presencas if p.presente_em]
    membros_mesa = [(m.usuario, m.get_funcao_display()) for m in mesa]
    votos_por_pauta = []
    for p in pautas:
        votos = p.votos.all()
        favor = votos.filter(opcao='Favor').count()
        contra = votos.filter(opcao='Contra').count()
        abstencao = votos.filter(opcao='Abstencao').count()
        total_votos = favor + contra + abstencao
        if p.tipo_votacao == 'Secreta':
            votos_por_pauta.append({
                'pauta': p,
                'favor': '***',
                'contra': '***',
                'abstencao': '***',
                'total': total_votos,
                'resultado': p.resultado_final,
            })
        else:
            votos_por_pauta.append({
                'pauta': p,
                'favor': favor,
                'contra': contra,
                'abstencao': abstencao,
                'total': total_votos,
                'resultado': p.resultado_final,
            })

    context = {
        'assembleia': assembleia,
        'presentes': presentes,
        'total_presentes': len(presentes),
        'membros_mesa': membros_mesa,
        'pautas': pautas,
        'votos_por_pauta': votos_por_pauta,
        'gerado_em': timezone.now(),
        'assinatura': f'Documento gerado digitalmente pelo sistema CDOA em {timezone.now():%d/%m/%Y às %H:%M}',
        'hash': hashlib.sha256(f'{assembleia.id}-{tipo}-{timezone.now().isoformat()}'.encode()).hexdigest()[:16],
    }

    template_map = {
        'ata': 'governanca/documentos/ata_template.html',
        'relatorio': 'governanca/documentos/relatorio_template.html',
        'decreto': 'governanca/documentos/decreto_template.html',
    }
    template_name = template_map.get(tipo, 'governanca/documentos/ata_template.html')
    return render_to_string(template_name, context)
