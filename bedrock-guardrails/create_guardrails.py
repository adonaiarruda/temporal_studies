import boto3
import json
import os

# Load .env from prefi-lite only if no credentials are already configured.
# STS tokens in .env expire; prefer AWS_PROFILE or ~/.aws/credentials when set.
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'prefi-lite', '.env')
if not os.environ.get('AWS_ACCESS_KEY_ID') and os.path.exists(_env_path):
    from dotenv import load_dotenv
    load_dotenv(_env_path, override=False)

_profile = os.environ.get('AWS_PROFILE')
_session = boto3.Session(profile_name=_profile) if _profile else boto3.Session()
client = _session.client(service_name='bedrock', region_name=os.environ.get('AWS_DEFAULT_REGION', 'us-east-1'))

# Config file always saved next to this script, regardless of where it's run from
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'guardrail_config.json')

GUARDRAIL_NAME = 'TestRedactionGuardrail'


def _buscar_guardrail_existente(name: str) -> tuple[str, str] | None:
    """
    Retorna (guardrail_id, version) se já existe um guardrail com esse nome,
    ou None se não existir.
    """
    paginator = client.get_paginator('list_guardrails')
    for page in paginator.paginate():
        for g in page.get('guardrails', []):
            if g['name'] == name:
                guardrail_id = g['id']
                # Busca a versão mais recente publicada via list_guardrails filtrado pelo ID
                ver_paginator = client.get_paginator('list_guardrails')
                published = []
                for vpage in ver_paginator.paginate(guardrailIdentifier=guardrail_id):
                    published.extend(
                        v for v in vpage.get('guardrails', [])
                        if v.get('version') != 'DRAFT'
                    )
                version = published[-1]['version'] if published else 'DRAFT'
                return guardrail_id, version
    return None


# ── Configuração canônica do guardrail ────────────────────────────────────────
# Definida fora das funções para que create e update usem exatamente a mesma
# config — evita divergência silenciosa entre criação e atualização.

_CONTENT_POLICY = {
    'filtersConfig': [
        # VIOLENCE e HATE não suportam máscara parcial na API do Bedrock.
        # Quando o threshold é atingido, a mensagem inteira é BLOQUEADA.
        {'type': 'HATE',     'inputStrength': 'HIGH', 'outputStrength': 'HIGH'},
        {'type': 'VIOLENCE', 'inputStrength': 'HIGH', 'outputStrength': 'HIGH'},
    ]
}

_SENSITIVE_INFO_POLICY = {
    # A API do Bedrock distingue inputAction e outputAction.
    # Usar apenas 'action' aplica somente ao output — o input fica "Disabled".
    # É preciso setar inputAction explicitamente para que apply_guardrail(source='INPUT')
    # e o guardrail aplicado ao input do modelo funcionem.
    'piiEntitiesConfig': [
        {'type': 'NAME',                      'action': 'ANONYMIZE', 'inputAction': 'ANONYMIZE'},
        {'type': 'EMAIL',                     'action': 'ANONYMIZE', 'inputAction': 'ANONYMIZE'},
        {'type': 'PHONE',                     'action': 'ANONYMIZE', 'inputAction': 'ANONYMIZE'},
        {'type': 'ADDRESS',                   'action': 'ANONYMIZE', 'inputAction': 'ANONYMIZE'},
        {'type': 'US_SOCIAL_SECURITY_NUMBER', 'action': 'ANONYMIZE', 'inputAction': 'ANONYMIZE'},
        {'type': 'CREDIT_DEBIT_CARD_NUMBER',  'action': 'ANONYMIZE', 'inputAction': 'ANONYMIZE'},
        {'type': 'CREDIT_DEBIT_CARD_CVV',     'action': 'ANONYMIZE', 'inputAction': 'ANONYMIZE'},
        {'type': 'IP_ADDRESS',                'action': 'ANONYMIZE', 'inputAction': 'ANONYMIZE'},
        {'type': 'PASSWORD',                  'action': 'ANONYMIZE', 'inputAction': 'ANONYMIZE'},
        {'type': 'USERNAME',                  'action': 'ANONYMIZE', 'inputAction': 'ANONYMIZE'},
        {'type': 'AWS_ACCESS_KEY',            'action': 'BLOCK',     'inputAction': 'BLOCK'},
        {'type': 'AWS_SECRET_KEY',            'action': 'BLOCK',     'inputAction': 'BLOCK'},
    ],
    # Regex customizado para CPF brasileiro (formato: 000.000.000-00)
    'regexesConfig': [
        {
            'name': 'CPF_BRASILEIRO',
            'description': 'Número de CPF no formato brasileiro (000.000.000-00)',
            'pattern': r'\d{3}\.\d{3}\.\d{3}-\d{2}',
            'action': 'ANONYMIZE',
            'inputAction': 'ANONYMIZE',  # obrigatório para source='INPUT'
        }
    ],
}

_BLOCKED_INPUT_MSG  = "Sua mensagem contém conteúdo proibido (violência ou ódio) e não pode ser processada."
_BLOCKED_OUTPUT_MSG = "A resposta foi bloqueada por conter conteúdo proibido."


def _publicar_versao(guardrail_id: str, descricao: str) -> str:
    version_res = client.create_guardrail_version(
        guardrailIdentifier=guardrail_id,
        description=descricao,
    )
    version = version_res['version']
    print(f"Versão {version} publicada!")
    return version


def _salvar_config(guardrail_id: str, version: str) -> None:
    config = {'guardrail_id': guardrail_id, 'version': version}
    with open(CONFIG_PATH, 'w') as f:
        json.dump(config, f, indent=2)
    print(f"Configuração salva em {CONFIG_PATH}")


def criar_guardrail_redacao():
    """
    Cria ou atualiza o guardrail 'TestRedactionGuardrail' com:

    1. Violência e Ódio → BLOCK (filtros de conteúdo não suportam máscara parcial)
    2. Dados sensíveis (PII) → ANONYMIZE (redação inline, substitui por {TIPO})

    Se o guardrail já existe, aplica update_guardrail com a config canônica atual
    e publica uma nova versão — garantindo que a AWS reflita o código.
    """
    existente = _buscar_guardrail_existente(GUARDRAIL_NAME)

    try:
        if existente:
            guardrail_id, _ = existente
            print(f"Guardrail '{GUARDRAIL_NAME}' já existe (ID: {guardrail_id}). Atualizando...")

            client.update_guardrail(
                guardrailIdentifier=guardrail_id,
                name=GUARDRAIL_NAME,
                description='Bloqueia violência/ódio e mascara dados sensíveis via redação.',
                contentPolicyConfig=_CONTENT_POLICY,
                sensitiveInformationPolicyConfig=_SENSITIVE_INFO_POLICY,
                blockedInputMessaging=_BLOCKED_INPUT_MSG,
                blockedOutputsMessaging=_BLOCKED_OUTPUT_MSG,
            )
            print("Guardrail atualizado (DRAFT).")

            version = _publicar_versao(guardrail_id, 'Atualização — config canônica sincronizada')

        else:
            print(f"Criando guardrail '{GUARDRAIL_NAME}'...")

            response = client.create_guardrail(
                name=GUARDRAIL_NAME,
                description='Bloqueia violência/ódio e mascara dados sensíveis via redação.',
                contentPolicyConfig=_CONTENT_POLICY,
                sensitiveInformationPolicyConfig=_SENSITIVE_INFO_POLICY,
                blockedInputMessaging=_BLOCKED_INPUT_MSG,
                blockedOutputsMessaging=_BLOCKED_OUTPUT_MSG,
            )
            guardrail_id = response['guardrailId']
            print(f"Guardrail criado! ID: {guardrail_id}")

            version = _publicar_versao(guardrail_id, 'V1 — Redação de PII + Bloqueio de Violência/Ódio')

        _salvar_config(guardrail_id, version)
        return guardrail_id, version

    except Exception as e:
        print(f"Erro ao criar/atualizar guardrail: {e}")
        raise


if __name__ == '__main__':
    criar_guardrail_redacao()
