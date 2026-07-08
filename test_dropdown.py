import requests

url = "http://127.0.0.1:8000/financeiro/requisicoes/1/linha/adicionar/"
response = requests.get(url)

if response.status_code == 200:
    content = response.text
    
    # Check for JavaScript data structure
    checks = [
        ('despesasData = {', 'Data structure present'),
        ('Direitos e importações', 'Documented expenses present'),
        ('Honorários', 'Non-documented expenses present'),
        ('updateDespesaTipoOptions', 'Update function present'),
        ('DOMContentLoaded', 'DOM listener present'),
        ('id_tipo_custo', 'Category select present'),
        ('id_despesa_tipo', 'Expense select present'),
        ('id_documentada', 'Documentation checkbox present'),
    ]
    
    print("VERIFICAÇÃO DO TEMPLATE\n" + "="*50)
    for check, desc in checks:
        if check in content:
            print(f"✓ {desc}")
        else:
            print(f"❌ {desc} - NÃO ENCONTRADO")
    
    # Check for select field
    if '<select' in content and 'id_despesa_tipo' in content:
        print("\n✓ Select field found in HTML")
        # Find the select element
        start = content.find('id_despesa_tipo')
        if start > 0:
            snippet = content[max(0, start-100):min(len(content), start+200)]
            print(f"\nContext: ...{snippet}...")
else:
    print(f"❌ HTTP {response.status_code}")
