# Bedrock Prompt Management — POC

Demo de gerenciamento centralizado de prompts no AWS Bedrock, usando os prompts
do PreFi Lite (detecção de emoção e geração de cenários) como caso de uso real.

---

## O que é o Bedrock Prompt Management

Permite criar, versionar e gerenciar prompts diretamente na AWS, fora do código.
Cada prompt tem:
- **Template** com variáveis no formato `{{variavel}}`
- **Variantes** (ex: tom formal vs. informal para o mesmo prompt)
- **Versões imutáveis** (snapshots publicados para produção)
- **Configuração de modelo e inferência** (temperatura, maxTokens) embutidas

O resultado é que o código da aplicação passa a conhecer apenas o **ARN do prompt**,
sem hardcodar templates, modelos ou parâmetros.

---

## Dois serviços boto3 envolvidos

| Serviço         | Para quê                                          |
|-----------------|---------------------------------------------------|
| `bedrock-agent` | Criar, atualizar, versionar e listar prompts      |
| `bedrock-runtime` | Invocar modelos (Converse API) com os prompts   |

---

## Duas abordagens de uso

### Abordagem A — Fetch + Render local

```
get_prompt(id, version)          ← busca template do Bedrock
    ↓
render: {{variavel}} → valor     ← substituição local no código
    ↓
converse(modelId=MODEL_ID, ...)  ← invoca o modelo com o texto renderizado
```

- Sempre funciona (qualquer versão de boto3)
- Você controla e inspeciona o template antes de enviar
- O modelo é escolhido no código (não vem do prompt)

### Abordagem B — ARN direto no converse

```
converse(
    modelId=prompt_arn,          ← ARN versionado do prompt
    promptVariables={...},       ← Bedrock faz o render internamente
)
```

- Uma única chamada de API (sem get_prompt separado)
- Modelo e parâmetros de inferência vêm do prompt (gerenciados centralmente)
- Mudanças de prompt/modelo não exigem deploy do código da aplicação
- Requer boto3 >= 1.35.x com suporte a `promptVariables`

---

## Pré-requisitos

- Python 3.11+
- Conta AWS com Bedrock habilitado na região `us-east-1`
- Modelo `amazon.nova-micro-v1:0` ativo (ou outro com suporte a `cachePoint`)

### Permissões IAM necessárias

```json
{
  "Effect": "Allow",
  "Action": [
    "bedrock:CreatePrompt",
    "bedrock:UpdatePrompt",
    "bedrock:CreatePromptVersion",
    "bedrock:GetPrompt",
    "bedrock:ListPrompts",
    "bedrock-runtime:Converse",
    "bedrock-runtime:InvokeModel"
  ],
  "Resource": "*"
}
```

---

## Instalação

```bash
cd temporal_studies/bedrock-prompt-management
pip install -r requirements.txt
```

---

## Execução

### Passo 1 — Criar os prompts na AWS

```bash
python create_prompts.py
```

Saída esperada:

```
[emotion_detection]
  Criando prompt 'PreFiLite_EmocaoDeteccao'...
  Prompt criado! ID: ABCDEF1234
  Versão 1 publicada! ARN: arn:aws:bedrock:us-east-1:...:prompt/ABCDEF1234:1
[scenario_generation]
  Criando prompt 'PreFiLite_CenarioGeracao'...
  ...
  Configuração salva em .../prompt_config.json
```

Se rodar novamente (idempotente):

```
[emotion_detection]
  Prompt 'PreFiLite_EmocaoDeteccao' já existe (ID: ABCDEF1234). Atualizando DRAFT...
  DRAFT atualizado.
  Versão 2 publicada! ARN: arn:aws:bedrock:us-east-1:...:prompt/ABCDEF1234:2
```

### Passo 2 — Executar os testes

```bash
python test_prompts.py
```

---

## O que os testes demonstram

| Bloco | Prompt(s) | API Bedrock | O que faz | Conceito central |
|-------|-----------|-------------|-----------|------------------|
| 1 | ambos | `bedrock-agent` | Lista todos os prompts registrados + exibe template, variáveis e metadados de cada um | Auditoria / inspeção |
| 2 | `emotion_detection` + `scenario_generation` | `Converse` | **Abordagem A**: `get_prompt` → render local de `{{variavel}}` → `converse` com texto pronto | Controle total do template no código |
| 3 | `emotion_detection` + `scenario_generation` | `Converse` | **Abordagem B**: `converse(modelId=ARN, promptVariables={...})` — Bedrock faz o render internamente | Uma chamada de API, modelo definido no prompt |
| 4 | `emotion_detection` | `Converse` | **Prompt Caching**: instruções estáticas vão no `system[]` com `cachePoint`; só a mensagem do usuário varia. Exibe `cacheWriteInputTokens` (1ª chamada) e `cacheReadInputTokens` (chamadas seguintes) | Cache write vs. cache read |
| 5 | `emotion_detection` → `scenario_generation` | `Converse` | **Pipeline completo** via Abordagem B: detecta emoção com ARN do `emotion_detection`, usa o estado retornado para gerar o cenário com ARN do `scenario_generation` | Composição de prompts sem template no código |
| 6a | `emotion_detection` | `ConverseStream` | **TTFT sem cache**: busca o template do Bedrock, envia o prompt completo em `messages[]` via streaming. Imprime tokens em tempo real e mede TTFT (tempo até o 1º token) e latência total | Linha de base de latência sem cache |
| 6b | `emotion_detection` | `ConverseStream` | **TTFT com cache**: busca o template do Bedrock, separa a parte estática em `system[]` com `cachePoint` e envia só a mensagem do usuário em `messages[]` via streaming. Exibe `cacheWriteInputTokens` / `cacheReadInputTokens` e mede o impacto do cache no TTFT | Cache + streaming combinados |

---

## Variável `{{contexto_anterior}}` no cenário

No prompt `scenario_generation`, a variável `{{contexto_anterior}}` pode ser:

- **Vazia** (`""`) no `AnalysisWorkflow` (geração inicial)
- **Preenchida** no `RefinementWorkflow`:

```python
contexto_anterior = (
    f"Cenário anterior:\n{cenario_anterior}\n\n"
    f"Avaliação: {nota}/5\n"
    f"Feedback: {feedback}"
)
```

O Bedrock substitui o `{{contexto_anterior}}` em ambos os casos — basta passar
string vazia quando não houver histórico.

---

## Arquivos

```
bedrock-prompt-management/
├── create_prompts.py    # Cria/atualiza prompts e publica versões
├── test_prompts.py      # Demonstra as duas abordagens de uso
├── requirements.txt     # boto3>=1.35, python-dotenv
├── prompt_config.json   # Gerado pelo create_prompts.py (não versionar)
└── README.md
```

---

## Diferença em relação aos prompts locais (prefi-lite/prompts/)

| Aspecto                  | Prompt local (arquivo .txt)      | Bedrock Prompt Management         |
|--------------------------|----------------------------------|-----------------------------------|
| Sintaxe de variável      | `{variavel}` (chave simples)     | `{{variavel}}` (dupla chave)      |
| Versionamento            | Git                              | Bedrock (imutável, com ARN)       |
| Modelo configurado       | No código                        | No próprio prompt                 |
| Auditoria / rollback     | Git log                          | Bedrock Console + ARN por versão  |
| Custo extra              | Nenhum                           | Nenhum (só paga o modelo)         |
