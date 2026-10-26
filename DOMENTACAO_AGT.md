Gesforma Logo
Pesquisar
Facturação Electrónica

Facturação Electrónica
Introdução
Autenticação & Autorização
Estrutura das Assinaturas Digitais
Serviços Disponíveis
Modelo de Processamento Assíncrono
Gestão de Certificados e Chaves
Especificações do QR Code
Facturação Electrónica
1
Facturação Electrónica
Introdução
Nesta página
Propósito da API
Arquitectura Geral da API
Introdução
A API de Faturação Eletrónica define o conjunto de interfaces, regras e padrões técnicos necessários para a comunicação automática de documentos fiscais entre os softwares de faturação certificados e a Administração Tributária. O objetivo é garantir a integridade, autenticidade e rastreabilidade dos documentos através de mecanismos como assinatura digital JWS e controle de séries.

A arquitetura é suportada por um modelo de processamento assíncrono, permitindo validações baseadas em filas de processamento, com consulta posterior (polling) ou envio de notificações callback (Disponível nas próximas versões). Este documento descreve a visão geral da API, o fluxo de integração ponta a ponta, o modelo de comunicação e os principais conceitos técnicos necessários para implementação correta da solução.

Propósito da API
A API de Faturação Eletrónica tem como objetivo permitir que softwares de faturação comuniquem em tempo real (ou quase real) todos os documentos fiscais à Administração Tributária, garantindo:

Integridade e autenticidade por meio de assinatura digital JWS.

Validação automática e retorno do estado do documento (válido ou inválido).

Sincronização entre os sistemas internos do contribuinte e a base fiscal.

Auditoria e rastreabilidade completa (com requestID, timestamps e histórico de processamento).

Arquitectura Geral da API
A arquitetura da solução é baseada no modelo de comunicação assíncrona:

Processamento Assíncrono

O contribuinte envia o documento JSON.

A API devolve requestID imediatamente, confirmando apenas receção.

O documento entra na fila de processamento.

O contribuinte deve consultar (polling) ou aguardar callback.

Este modelo suporta:

volumes grandes

redução de latência no front-end

isolamento de falhas

Mecanismos disponíveis:

Mecanismo	Como funciona
Polling

Cliente consulta a decisão final.

Callback (se ativado)

A API faz POST para o endpoint do contribuinte quando o documento for validado. (Disponível nas próximas versões)




Gesforma Logo
Pesquisar
Facturação Electrónica

Facturação Electrónica
Introdução
Autenticação & Autorização
Estrutura das Assinaturas Digitais
Serviços Disponíveis
Modelo de Processamento Assíncrono
Gestão de Certificados e Chaves
Especificações do QR Code
Facturação Electrónica
1
Facturação Electrónica
Autenticação & Autorização
Nesta página
Obtenção das Credenciais
Funcionamento do Basic Auth
Exemplo de Header HTTP Completo
Exemplo em cURL
Exemplo em JavaScript (Fetch API)
Exemplo em C# (HttpClient)
Autenticação & Autorização
A API utiliza o mecanismo Basic Authentication para validar e autorizar o acesso dos produtores de software.
O acesso é concedido através de um par de credenciais (username e password) emitido pela entidade gestora da Faturação Eletrónica.

Estas credenciais devem ser enviadas em todas as chamadas aos serviços protegidos da API.

Obtenção das Credenciais
Para solicitar as credenciais de acesso, o produtor de software deve enviar um e-mail formal para:

📧 produtores.dfe.dcrr.agt@minfin.gov.ao

O pedido deve conter:

Nome da Empresa

NIF da Empresa

Funcionamento do Basic Auth
O Basic Auth consiste em enviar as credenciais codificadas em Base64 no cabeçalho HTTP:

Authorization: Basic <Base64(username:password)>

Exemplo de codificação:

Se as credenciais forem:

Username: cliente123

Password: s3nh@F0rte!

Concatenação antes do Base64: cliente123:s3nh@F0rte!

Após Base64: Y2xpZW50ZTEyMzpzM25oQEYwcnRlIQ==

Exemplo de Header HTTP Completo
Requisição POST

 POST /sigt/fe/v1/registarFactura HTTP/1.1
 Host: https://sifphml.minfin.gov.ao
 Authorization: Basic Y2xpZW50ZTEyMzpzM25oQEYwcnRlIQ==
 Content-Type: application/json
 Accept: application/json
 Content-Length: 524
Exemplo em cURL
 curl -X POST "https://sifphml.minfin.gov.ao/sigt/fe/v1/registarFactura"
 -u cliente123:"s3nh@F0rte!"
 -H "Accept: application/json"
Nota: O curl já faz o Base64 automaticamente quando usamos -u.

Exemplo em JavaScript (Fetch API)
const auth = btoa("cliente123:s3nh@F0rte!");

 fetch("https://sifphml.minfin.gov.ao/sigt/fe/v1/registarFactura ",{

    method: "POST",
    headers:{
        "Authorization": `Basic $\{auth}`,
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

 }).then(res => res.json()).then(console.log);
Exemplo em C# (HttpClient)
 var client = new HttpClient();

 var byteArray = Encoding.ASCII.GetBytes("cliente123:s3nh@F0rte!");

 client.DefaultRequestHeaders.Authorization =
    new AuthenticationHeaderValue("Basic",Convert.ToBase64String(byteArray));

 var response = await client.GetAsync("https://sifphml.minfin.gov.ao/sigt/fe/v1/registarFactura");
 var content = await response.Content.ReadAsStringAsync();




 Gesforma Logo
Pesquisar
Facturação Electrónica

Facturação Electrónica
Introdução
Autenticação & Autorização
Estrutura das Assinaturas Digitais
Serviços Disponíveis
Modelo de Processamento Assíncrono
Gestão de Certificados e Chaves
Especificações do QR Code
Facturação Electrónica
1
Facturação Electrónica
Estrutura das Assinaturas Digitais
Nesta página
Algoritmo Utilizado (RS256)
Geração da Assinatura (Resumo do Processo)
Assinatura jwsSoftwareSignature
Assinatura jwsDocumentSignature
Assinatura jwsSignature (Assinatura da Requisição)
Exemplos de Geração em Diferentes Linguagens
Node.js
Java
C# (.NET)*
Go
Python
Erros Comuns na Geração de JWS
Estrutura das Assinaturas Digitais (JWS)
A API de Faturação Eletrónica utiliza JSON Web Signature (JWS) como mecanismo padrão para assinatura digital de:

Informações do software (jwsSoftwareSignature)

Documentos fiscais (jwsDocumentSignature)

Requisições feitas ao serviço (jwsSignature)

O objetivo é garantir:

Integridade – os dados não foram alterados.

Autenticidade – o emissor é quem diz ser.

Não-repúdio – o emissor não pode negar a autoria.

Cada assinatura utiliza a chave privada do contribuinte ou do produtor, dependendo do tipo de assinatura.

Algoritmo Utilizado (RS256)
Todas as assinaturas JWS utilizam o algoritmo:

✔ RS256 – RSA com SHA-256

Características:

Chave privada RSA a partir de 2048 bits (recomenda-se 4096).

Hash criptográfico SHA-256.

Cabeçalho JWS:

 {
    "alg": "RS256",
    "typ": "JWT"
 }
Para garantir melhor consistência, recomendamos que o objeto a assinar deve ser transformado em JSON canônico antes da assinatura.

Regras de JSON canônico:

Sem quebras de linha.

Sem espaços ou indentação.

Aspas duplas sempre obrigatórias.

Números sem formatação adicional.

Exemplo de objeto:

 {
    "productId":"Nome",
    "productVersion":"1.0",
    "softwareValidationNumber":"123"
 }
Geração da Assinatura (Resumo do Processo)
Todas as assinaturas seguem este fluxo:

Criar um objeto JSON (canônico recomendado) contendo apenas os campos exigidos.

Montar o JWS Compact Serialization:

base64url(header) + "." + base64url(payload)

Assinar com RSA-SHA256 usando a chave privada.

Gerar o JWS final:

header.payload.signature

Assinatura jwsSoftwareSignature
Assina o objeto:

 {
   "productId": "",
   "productVersion": "",
   "softwareValidationNumber": ""
 }
O payload é o objeto inteiro, e não concatenação de campos.

Assinatura jwsDocumentSignature
Assina os elementos principais do documento fiscal, como:

 {
    "documentNo": "...",
    "taxRegistrationNumber": "...",
    "documentType": "...",
    "documentDate": "...",
    "customerTaxID": "...",
    "customerCountry": "...",
    "companyName": "...",
    "documentTotals": {
        "taxPayable": 70,
        "netTotal": 500,
        "grossTotal": 570
     }
 }
❗ Novamente, assina-se o objeto completo.

Assinatura jwsSignature (Assinatura da Requisição)
Assina o objeto principal da requisição — por exemplo:

 {
    "taxRegistrationNumber": "5001234567",
    "requestID": "REQ-000001"
 }
NOTA: O payload pode variar de acordo a requisição.

Isto permite autenticação forte a cada chamada importante.

Exemplos de Geração em Diferentes Linguagens
Node.js
 const fs = require("fs");
 const jwt = require("jsonwebtoken");
 const privateKey = fs.readFileSync("private.pem", "utf8");
 const payload = {
    productId: "ClinicaHub",
    productVersion: "1.0.0",
    softwareValidationNumber: "123456789"
 };

 const token = jwt.sign(payload, privateKey, { algorithm: "RS256" });

 console.log(token);
Java
 import java.nio.file.*;
 import java.security.*;
 import java.security.spec.*;
 import io.jsonwebtoken.*;
 String key = Files.readString(Path.of("private.pem"));
 PrivateKey privateKey = Keys.privateKeyFromPem(key);
 Map<String, Object> payload = Map.of(
 "productId", "ClinicaHub",
 "productVersion", "1.0.0",
 "softwareValidationNumber", "123456789"
 );

 String jws = Jwts.builder()

.setClaims(payload)

.signWith(privateKey, SignatureAlgorithm.RS256)

.compact();

 System.out.println(jws);
C# (.NET)*
 using System.IdentityModel.Tokens.Jwt;
 using Microsoft.IdentityModel.Tokens;
 using System.Security.Cryptography;
 var payload = new Dictionary<string, object>

 {
    { "productId", "ClinicaHub" },
    { "productVersion", "1.0.0" },
    { "softwareValidationNumber", "123456789" }
 };

 var privateKey = RSA.Create();
 privateKey.ImportFromPem(File.ReadAllText("private.pem"));
 var credentials = new SigningCredentials(
 new RsaSecurityKey(privateKey),
 SecurityAlgorithms.RsaSha256
 ) ;

 var token = new JwtSecurityToken(
 claims: payload.Select(kv => new Claim(kv.Key, kv.Value.ToString())), signingCredentials: credentials
);

var jwt = new JwtSecurityTokenHandler().WriteToken(token);

Console.WriteLine(jwt);
Go
package main

 import ("fmt" "os" jwt "github.com/golang-jwt/jwt/v5")

 func main(){

 keyData, _ := os.ReadFile("private.pem")
 privateKey, _ := jwt.ParseRSAPrivateKeyFromPEM(keyData)

 payload := jwt.MapClaims
 {
    "productId": "ClinicaHub",
    "productVersion": "1.0.0",
    "softwareValidationNumber": "123456789",
 }

 token := jwt.NewWithClaims(jwt.SigningMethodRS256, payload)
 signed, _ := token.SignedString(privateKey)
 fmt.Println(signed)
}
Python
 import jwt

 with open("private.pem", "r") as f:

 private_key = f.read()

 payload = {
    "productId": "ClinicaHub",
    "productVersion": "1.0.0",
    "softwareValidationNumber": "123456789"
 }

 token = jwt.encode(payload, private_key, algorithm="RS256")

 print(token)
Erros Comuns na Geração de JWS
❌ Concatenar campos ao invés de assinar o JSON
✔ A assinatura é sempre sobre o objeto JSON completo.

❌ Usar RSA com chave inferior a 2048 bits
✔ Recomendado: no mínimo 2048 bits.

❌ Assinar com chave pública
✔ A assinatura é feita com private key.

❌ Codificação Base64 normal
✔ Deve usar Base64URL, sem padding =.


Gesforma Logo
Pesquisar
Facturação Electrónica

Facturação Electrónica
Introdução
Autenticação & Autorização
Estrutura das Assinaturas Digitais
Serviços Disponíveis
Modelo de Processamento Assíncrono
Gestão de Certificados e Chaves
Especificações do QR Code
Facturação Electrónica
1
Facturação Electrónica
Gestão de Certificados e Chaves
Nesta página
Como são entregues as chaves aos contribuintes
Estrutura da chave (RSA mínimo 2048 bits)
Procedimento em caso de comprometimento
Como a API valida a assinatura
Gestão de Certificados e Chaves
A infraestrutura de assinatura digital utilizada no sistema de Faturação Eletrónica baseia-se em criptografia assimétrica (RSA) com chaves privadas mantidas pelos produtores de software e chaves públicas registadas e validadas pela Administração Geral Tributária (AGT). As chaves privadas e públicas dos contribuintes serão geradas pela Administração Geral Tributária (AGT) podendo e disponibilizadas na conta do portal do contribinte.
Este capítulo descreve como as chaves são distribuídas, utilizadas, validadas e atualizadas.

Como são entregues as chaves aos contribuintes
As chaves dos contribuintes utilizadas para assinatura de documentos e requisições (jwsDocumentSignature e jwsSignature) serão emitidas AGT e estarão disponiveis na conta do portaltal do contribuinte de cada contribuinte para consulta.

As chaves utilizadas para assinatura do software (jwsSoftwareSignature) não são emitidas pela AGT.
Cada produtor de software deve:

Gerar localmente um par de chaves RSA (privada + pública)
  A chave privada nunca deve sair do ambiente do produtor.
  A chave publica será enviada à AGT.

Submeter a chave pública durante o processo de registo do Software Produtor, via portal do parceiro:

Testes: https://portaldoparceiro.hml.minfin.gov.ao/

Produção: https://portaldoparceiro.minfin.gov.ao/

Estrutura da chave (RSA mínimo 2048 bits)
Para garantir interoperabilidade, desempenho e segurança, as chaves usadas têm:

Tipo: RSA

Tamanho: mínimo 2048 bits

Formato recomendado: PEM

Codificação: Base64 (padrão para PEM)

Exemplo de chave pública válida:

-----BEGIN PUBLIC KEY-----

MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAw12…​

…​restante conteúdo…​

-----END PUBLIC KEY-----

Exemplo de chave privada (que nunca deve ser enviada):

-----BEGIN PRIVATE KEY-----

MIIEvAIBADANBgkqhkiG9w0BAQEFAASCBK…​

-----END PRIVATE KEY-----

Procedimento em caso de comprometimento
Se o produtor suspeitar que a chave privada foi exposta:

A chave comprometida deve ser imediatamente revogada

O produtor deve:

Gerar um novo par de chaves RSA

Atualizar o software com a nova chave públi no portal do parceiro

Marcar a chave antiga como revogada a partir do portal

Impacto sobre documentos

Documentos assinados com a chave comprometida permanecem válidos se:

Já tiverem sido processados e aceites pela AGT

A assinatura digital for tecnicamente válida

Porém, novas submissões deixam de ser aceites com a chave revogada.

Como a API valida a assinatura
O processo de verificação funciona assim:

Receção do documento

O sistema lê o JSON recebido e extrai:

jwsSoftwareSignature

jwsDocumentSignature (se aplicável)

jwsSignature (se aplicável)

Busca da chave pública ativa (ou correspondente à versão)

A API localiza a chave pública do produtor.

Validação do JWS (RS256)

O servidor:

Reconstrói o JSON canônico

Recalcula o hash

Usa a chave pública para validar o signature

Resultado

Se válido → documento segue para processamento

Se inválido → retorna erro de assinatura