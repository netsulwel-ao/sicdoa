from django.shortcuts import render, get_object_or_404
from django.http import Http404
from .models import Vaga, Candidatura


def candidatura_externa_view(request, link_uuid):
    """Formulário público de candidatura via link único"""
    try:
        vaga = Vaga.objects.get(link_externo=link_uuid, estado='Aberta')
    except Vaga.DoesNotExist:
        raise Http404("Vaga não encontrada ou encerrada")
    
    if request.method == 'POST':
        nome = request.POST.get('nome', '').strip()
        email = request.POST.get('email', '').strip()
        
        if not nome or not email:
            return render(request, 'rh/public/candidatura_form.html', {
                'vaga': vaga,
                'erro': 'Nome e email são obrigatórios.',
                'form_data': request.POST,
            })
        
        # Verificar email duplicado
        if vaga.candidaturas.filter(email=email).exists():
            return render(request, 'rh/public/candidatura_form.html', {
                'vaga': vaga,
                'erro': 'Já existe uma candidatura com este email para esta vaga.',
                'form_data': request.POST,
            })
        
        candidatura = Candidatura.objects.create(
            vaga=vaga,
            nome=nome,
            email=email,
            telefone=request.POST.get('telefone', '').strip(),
            carta_motivacao=request.POST.get('carta_motivacao', '').strip(),
        )
        
        # Anexar CV se enviado
        if 'cv' in request.FILES:
            candidatura.cv = request.FILES['cv']
            candidatura.save()
        
        return render(request, 'rh/public/candidatura_sucesso.html', {
            'vaga': vaga,
            'candidatura': candidatura,
        })
    
    return render(request, 'rh/public/candidatura_form.html', {
        'vaga': vaga,
    })


def vaga_publica_view(request, link_uuid):
    """Visualização pública da vaga"""
    try:
        vaga = Vaga.objects.get(link_externo=link_uuid, estado='Aberta')
    except Vaga.DoesNotExist:
        raise Http404("Vaga não encontrada ou encerrada")
    
    return render(request, 'rh/public/vaga_detalhe.html', {
        'vaga': vaga,
    })
