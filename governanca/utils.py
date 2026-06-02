import hashlib
import os
import time

from django.utils import timezone
from django.template.loader import render_to_string

from .models import DocumentoAssembleia


def gerar_conteudo_documento(assembleia, tipo, created_by=None):
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
