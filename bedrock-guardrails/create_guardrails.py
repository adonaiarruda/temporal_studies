import boto3
import json
import os

client = boto3.client(service_name='bedrock', region_name='us-east-1')

# Config file always saved next to this script, regardless of where it's run from
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'guardrail_config.json')

def criar_guardrail_redacao():
    """
    Cria um guardrail com dois comportamentos distintos:

    1. Violência e Ódio → BLOCK (filtros de conteúdo não suportam máscara parcial)
    2. Dados sensíveis (PII) → ANONYMIZE (redação inline, substitui por {TIPO})

    O mode ANONYMIZE é o "redaction" real: o texto volta com o dado mascarado,
    sem bloquear a mensagem inteira.
    """
    try:
        response = client.create_guardrail(
            name='GuardrailRedacaoSeguranca',
            description='Bloqueia violência/ódio e mascara dados sensíveis via redação.',

            # ── Filtros de Conteúdo ────────────────────────────────────────────
            # VIOLENCE e HATE não suportam máscara parcial na API do Bedrock.
            # Quando o threshold é atingido, a mensagem inteira é BLOQUEADA.
            contentPolicyConfig={
                'filtersConfig': [
                    {'type': 'HATE',     'inputStrength': 'HIGH', 'outputStrength': 'HIGH'},
                    {'type': 'VIOLENCE', 'inputStrength': 'HIGH', 'outputStrength': 'HIGH'},
                ]
            },

            # ── Dados Sensíveis com ANONYMIZE = Redação ───────────────────────
            # action: ANONYMIZE → substitui o dado por {TIPO_PII} no texto.
            # action: BLOCK     → bloqueia a mensagem inteira (como content filters).
            sensitiveInformationPolicyConfig={
                'piiEntitiesConfig': [
                    {'type': 'NAME',                          'action': 'ANONYMIZE'},
                    {'type': 'EMAIL',                         'action': 'ANONYMIZE'},
                    {'type': 'PHONE',                         'action': 'ANONYMIZE'},
                    {'type': 'ADDRESS',                       'action': 'ANONYMIZE'},
                    {'type': 'US_SOCIAL_SECURITY_NUMBER',     'action': 'ANONYMIZE'},  # análogo ao CPF
                    {'type': 'CREDIT_DEBIT_CARD_NUMBER',      'action': 'ANONYMIZE'},
                    {'type': 'CREDIT_DEBIT_CARD_CVV',         'action': 'ANONYMIZE'},
                    {'type': 'IP_ADDRESS',                    'action': 'ANONYMIZE'},
                    {'type': 'PASSWORD',                      'action': 'ANONYMIZE'},
                    {'type': 'USERNAME',                      'action': 'ANONYMIZE'},
                    {'type': 'AWS_ACCESS_KEY',                'action': 'ANONYMIZE'},
                    {'type': 'AWS_SECRET_KEY',                'action': 'ANONYMIZE'},
                ],
                # Regex customizado para CPF brasileiro (formato: 000.000.000-00)
                'regexesConfig': [
                    {
                        'name': 'CPF_BRASILEIRO',
                        'description': 'Número de CPF no formato brasileiro (000.000.000-00)',
                        'pattern': r'\d{3}\.\d{3}\.\d{3}-\d{2}',
                        'action': 'ANONYMIZE',
                    }
                ]
            },

            blockedInputMessaging=(
                "Sua mensagem contém conteúdo proibido (violência ou ódio) "
                "e não pode ser processada."
            ),
            blockedOutputsMessaging=(
                "A resposta foi bloqueada por conter conteúdo proibido."
            ),
        )

        guardrail_id = response['guardrailId']
        print(f"Guardrail criado! ID: {guardrail_id}")

        version_res = client.create_guardrail_version(
            guardrailIdentifier=guardrail_id,
            description='V1 — Redação de PII + Bloqueio de Violência/Ódio',
        )
        version = version_res['version']
        print(f"Versão {version} publicada!")

        # Salva ID e versão para o script de teste ler automaticamente
        config = {'guardrail_id': guardrail_id, 'version': version}
        with open(CONFIG_PATH, 'w') as f:
            json.dump(config, f, indent=2)
        print(f"Configuração salva em {CONFIG_PATH}")

        return guardrail_id, version

    except Exception as e:
        print(f"Erro ao criar guardrail: {e}")
        raise


if __name__ == '__main__':
    criar_guardrail_redacao()
