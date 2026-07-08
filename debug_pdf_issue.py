#!/usr/bin/env python
import os
import django
import sys

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sicdoa.settings')
django.setup()

from financeiro.models import RequisicaoFundo
from datetime import datetime
from decimal import Decimal
import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.platypus.flowables import HRFlowable
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from utils.format_kz import fmt_kz

requisicao = RequisicaoFundo.objects.first()

if not requisicao:
    print("Nenhuma requisição encontrada")
    sys.exit(1)

buffer = io.BytesIO()
PAGE_W, PAGE_H = A4
MARGIN = 0.7 * cm
W = PAGE_W - 2 * MARGIN

try:
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=0.5 * cm, bottomMargin=1.0 * cm,
        title=f"Requisição de Fundos {requisicao.numero_requisicao}",
    )
    print("✓ SimpleDocTemplate criado")
except Exception as e:
    print(f"✗ Erro ao criar SimpleDocTemplate: {e}")
    sys.exit(1)

COR_PRETO = colors.HexColor('#0f172a')
COR_CINZA = colors.HexColor('#64748b')

def st(name, **kw):
    defaults = dict(fontName='Helvetica', fontSize=9, textColor=COR_PRETO, leading=11)
    defaults.update(kw)
    return ParagraphStyle(name, **defaults)

story = []

try:
    p = Paragraph("Test", st('test'))
    story.append(p)
    print("✓ Paragraph adicionado")
except Exception as e:
    print(f"✗ Erro ao adicionar Paragraph: {e}")

try:
    doc.build(story)
    print("✓ doc.build() executado com sucesso")
except Exception as e:
    print(f"✗ Erro ao executar doc.build(): {e}")
    import traceback
    traceback.print_exc()

buffer.seek(0)
content = buffer.read()
print(f"✓ Tamanho do buffer: {len(content)} bytes")

if len(content) > 0:
    print("✓ PDF foi gerado corretamente")
else:
    print("✗ PDF está vazio")
