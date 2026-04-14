# Bedrock Guardrails — Redação de PII e Bloqueio de Conteúdo

Demo de guardrails do AWS Bedrock com dois comportamentos:

- **Redação (ANONYMIZE)** — mascara dados sensíveis inline, ex: `João Silva` → `{NAME}`
- **Bloqueio (BLOCK)** — bloqueia a mensagem inteira quando há violência ou discurso de ódio

---

## Pré-requisitos

- Python 3.11+
- Conta AWS com acesso ao Bedrock habilitado
- Modelo `anthropic.claude-3-haiku-20240307-v1:0` ativo na região `us-east-1`

### Permissões IAM necessárias

```json
{
  "Effect": "Allow",
  "Action": [
    "bedrock:CreateGuardrail",
    "bedrock:CreateGuardrailVersion",
    "bedrock-runtime:ApplyGuardrail",
    "bedrock-runtime:InvokeModel",
    "bedrock-runtime:Converse"
  ],
  "Resource": "*"
}
```

---

## Configuração de credenciais AWS

Edite o arquivo `~/.aws/credentials` com suas chaves:

```ini
[default]
aws_access_key_id = SUA_ACCESS_KEY_AQUI
aws_secret_access_key = SUA_SECRET_KEY_AQUI
```

A região já está configurada em `~/.aws/config`:

```ini
[default]
region = us-east-1
```

> Para obter as chaves: AWS Console → IAM → Users → Security credentials → Create access key

---

## Instalação

```bash
cd temporal_studies/bedrock-guardrails
pip install -r requirements.txt
```

---

## Execução

### Passo 1 — Criar o guardrail na AWS

```bash
python create_guardrails.py
```

Saída esperada:

```
Guardrail criado! ID: abc123xyz
Versão 1 publicada!
Configuração salva em .../guardrail_config.json
```

O ID e a versão são salvos automaticamente em `guardrail_config.json`.
Este arquivo é lido pelo script de testes — não é necessário editar nada.

### Passo 2 — Executar a suite de testes

```bash
python test_guardrails.py
```

---

## O que os testes validam

| Bloco | Tipo | Comportamento esperado |
|-------|------|------------------------|
| 1 | Texto limpo | Sem intervenção |
| 2 | PII (nome, e-mail, CPF, cartão, senha, IP, AWS key) | Redação inline com `{TIPO}` |
| 3 | Violência | Mensagem bloqueada |
| 4 | Discurso de ódio | Mensagem bloqueada |
| 5 | Modelo real (Converse API) | Redação no input antes do modelo + bloqueio direto |

### Exemplo de saída — redação

```
  REDACAO aplicada (3 substituicao(oes)):
    'Joao Silva'            =>  {NAME}
    'joao.silva@email.com'  =>  {EMAIL}
    '(11) 98888-7777'       =>  {PHONE}
  Antes : Meu nome e Joao Silva, email joao.silva@email.com, tel (11) 98888-7777.
  Depois: Meu nome e {NAME}, email {EMAIL}, tel {PHONE}.
```

### Exemplo de saída — bloqueio

```
  BLOQUEADO
  Motivo  : VIOLENCE (confianca: HIGH)
  Resposta: Sua mensagem contém conteúdo proibido e não pode ser processada.
```

### Exemplo de saída — modelo com PII

```
  REDACAO no input — modelo recebeu dados mascarados:
    'Maria Oliveira'        =>  {NAME}
    '987.654.321-00'        =>  {CPF_BRASILEIRO}
    'maria@test.com'        =>  {EMAIL}
  Resposta do modelo: Olá {NAME}, sobre sua dívida de R$150.000...
```

---

## Arquivos

```
bedrock-guardrails/
├── create_guardrails.py   # Cria o guardrail na AWS e salva o ID
├── test_guardrails.py     # Suite de testes (apply_guardrail + converse)
├── requirements.txt       # boto3>=1.35
├── guardrail_config.json  # Gerado pelo create_guardrails.py (não versionar)
└── README.md
```
