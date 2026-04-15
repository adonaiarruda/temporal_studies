import boto3
import json
import os

# Carrega .env do prefi-lite apenas se não houver credenciais já configuradas.
# Tokens STS expiram; prefere AWS_PROFILE ou ~/.aws/credentials quando disponível.
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'prefi-lite', '.env')
if not os.environ.get('AWS_ACCESS_KEY_ID') and os.path.exists(_env_path):
    from dotenv import load_dotenv
    load_dotenv(_env_path, override=False)

_profile = os.environ.get('AWS_PROFILE')
_session = boto3.Session(profile_name=_profile) if _profile else boto3.Session()

# bedrock-agent: serviço usado para gerenciar Prompts, Knowledge Bases e Flows
# (diferente de bedrock-runtime, que é usado para invocar modelos)
client = _session.client(
    service_name='bedrock-agent',
    region_name=os.environ.get('AWS_DEFAULT_REGION', 'us-east-1'),
)

# Config salvo ao lado deste script, independente do cwd de onde é executado
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'prompt_config.json')

# Modelo padrão para inferência nos prompts
MODEL_ID = "anthropic.claude-3-haiku-20240307-v1:0"


# ── Definições canônicas dos prompts ─────────────────────────────────────────
#
# Variáveis usam sintaxe {{nome}} (duplas chaves) — padrão do Bedrock Prompt Management.
# Isso difere dos prompts locais em prefi-lite/prompts/ que usam {nome} (chave simples).
#
# Definidas fora das funções para que create e update usem exatamente a mesma
# configuração — evita divergência silenciosa entre criação e atualização.

_PROMPTS = {
    'emotion_detection': {
        'name': 'PreFiLite_EmotionDetection',
        'description': (
            'Classifica o estado emocional do usuário (ANSIOSO, CONFUSO, CONFIANTE, FRUSTRADO) '
            'com base em texto livre. Retorna JSON com estado, confiança e justificativa.'
        ),
        'template': (
            'Você é um classificador de estado emocional para uma plataforma financeira.\n\n'
            'Analise a mensagem abaixo e classifique o estado emocional do usuário em\n'
            'EXATAMENTE uma das categorias:\n\n'
            '- ANSIOSO: preocupação, medo de errar, urgência, insegurança financeira\n'
            '- CONFUSO: não entende os termos, faz perguntas básicas, parece perdido\n'
            '- CONFIANTE: tom assertivo, já pesquisou, sabe o que quer\n'
            '- FRUSTRADO: já tentou antes e não conseguiu, irritação, descrença\n\n'
            'Responda SOMENTE com JSON, sem explicações:\n'
            '{"estado": "ANSIOSO"|"CONFUSO"|"CONFIANTE"|"FRUSTRADO", "confianca": 0.0-1.0, "justificativa": "..."}\n\n'
            'Mensagem do usuário:\n'
            '{{mensagem}}'
        ),
        'variables': ['mensagem'],
        'inference': {'temperature': 0.0, 'maxTokens': 256},
    },
    'scenario_generation': {
        'name': 'PreFiLite_CenarioGeracao',
        'description': (
            'Gera 2 cenários de refinanciamento imobiliário adaptados ao estado emocional do usuário. '
            'Suporta contexto anterior para o fluxo de refinamento.'
        ),
        'template': (
            'Você é um assistente de educação financeira para refinanciamento imobiliário.\n\n'
            'Tom a usar com base no estado emocional detectado:\n'
            '- ANSIOSO: calmo, reassuring, passo a passo, sem jargão\n'
            '- CONFUSO: didático, analogias simples, definições curtas\n'
            '- CONFIANTE: direto, técnico, com números\n'
            '- FRUSTRADO: empático, reconhece a dificuldade, mostra caminho concreto\n\n'
            'Estado detectado: {{estado_emocional}}\n\n'
            '{{contexto_anterior}}\n\n'
            'Com base na situação descrita abaixo, gere 2 cenários de refinanciamento\n'
            'simplificados (Cenário Conservador e Cenário Otimizado).\n'
            'Para cada cenário inclua: objetivo, prazo estimado, próximo passo concreto.\n'
            'Não faça recomendações — apresente opções neutras.\n\n'
            'Situação do usuário:\n'
            '{{mensagem}}'
        ),
        'variables': ['mensagem', 'estado_emocional', 'contexto_anterior'],
        'inference': {'temperature': 0.5, 'maxTokens': 1024},
    },
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _buscar_prompt_existente(name: str) -> tuple[str, str] | None:
    """
    Retorna (prompt_id, arn) se já existe um prompt com esse nome,
    ou None se não existir.

    list_prompts sem promptIdentifier retorna apenas a versão DRAFT de cada prompt.
    """
    next_token = None
    while True:
        kwargs = {'maxResults': 100}
        if next_token:
            kwargs['nextToken'] = next_token

        response = client.list_prompts(**kwargs)

        for p in response.get('promptSummaries', []):
            if p['name'] == name:
                return p['id'], p['arn']

        next_token = response.get('nextToken')
        if not next_token:
            break

    return None


def _construir_variante(prompt_key: str) -> dict:
    """
    Monta o objeto `variant` para create_prompt / update_prompt a partir
    da configuração canônica em _PROMPTS.
    """
    cfg = _PROMPTS[prompt_key]
    return {
        'name': 'default',
        'templateType': 'TEXT',
        'templateConfiguration': {
            'text': {
                'text': cfg['template'],
                'inputVariables': [{'name': v} for v in cfg['variables']],
            }
        },
        'modelId': MODEL_ID,
        'inferenceConfiguration': {
            'text': cfg['inference'],
        },
    }


def _publicar_versao(prompt_id: str, descricao: str) -> tuple[str, str]:
    """
    Publica uma nova versão imutável do prompt DRAFT.
    Retorna (version_number, versioned_arn).
    """
    response = client.create_prompt_version(
        promptIdentifier=prompt_id,
        description=descricao,
    )
    version = response['version']
    arn = response['arn']
    print(f"  Versão {version} publicada! ARN: {arn}")
    return version, arn


def _salvar_config(config: dict) -> None:
    with open(CONFIG_PATH, 'w') as f:
        json.dump(config, f, indent=2)
    print(f"  Configuração salva em {CONFIG_PATH}")


# ── Criação / atualização de um prompt ───────────────────────────────────────

def criar_ou_atualizar_prompt(prompt_key: str) -> tuple[str, str, str]:
    """
    Cria ou atualiza um prompt no Bedrock Prompt Management.

    Retorna (prompt_id, version, versioned_arn).

    Estratégia idempotente:
      - Se o prompt já existe → update_prompt (sincroniza DRAFT) → create_prompt_version
      - Se não existe          → create_prompt → create_prompt_version
    """
    cfg = _PROMPTS[prompt_key]
    name = cfg['name']
    variante = _construir_variante(prompt_key)

    existente = _buscar_prompt_existente(name)

    try:
        if existente:
            prompt_id, _ = existente
            print(f"  Prompt '{name}' já existe (ID: {prompt_id}). Atualizando DRAFT...")

            client.update_prompt(
                promptIdentifier=prompt_id,
                name=name,
                description=cfg['description'],
                defaultVariant='default',
                variants=[variante],
            )
            print(f"  DRAFT atualizado.")
            version, versioned_arn = _publicar_versao(prompt_id, 'Atualização — config canônica sincronizada')

        else:
            print(f"  Criando prompt '{name}'...")

            response = client.create_prompt(
                name=name,
                description=cfg['description'],
                defaultVariant='default',
                variants=[variante],
            )
            prompt_id = response['id']
            print(f"  Prompt criado! ID: {prompt_id}")
            version, versioned_arn = _publicar_versao(prompt_id, 'V1 — versão inicial')

        return prompt_id, version, versioned_arn

    except Exception as e:
        print(f"  Erro ao criar/atualizar '{name}': {e}")
        raise


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == '__main__':
    print("=" * 60)
    print("  BEDROCK PROMPT MANAGEMENT — CRIAÇÃO DE PROMPTS")
    print("=" * 60)

    config = {}

    for key in _PROMPTS:
        print(f"\n[{key}]")
        prompt_id, version, versioned_arn = criar_ou_atualizar_prompt(key)
        config[key] = {
            'prompt_id': prompt_id,
            'version': version,
            'versioned_arn': versioned_arn,
        }

    print()
    _salvar_config(config)

    print(f"\n{'=' * 60}")
    print("  Prompts prontos para uso.")
    print(f"{'=' * 60}\n")
