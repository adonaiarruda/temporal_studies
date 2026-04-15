import boto3
import json
import os
import re
import time
from botocore.exceptions import ClientError

# Carrega .env do prefi-lite apenas se não houver credenciais já configuradas.
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'prefi-lite', '.env')
if not os.environ.get('AWS_ACCESS_KEY_ID') and os.path.exists(_env_path):
    from dotenv import load_dotenv
    load_dotenv(_env_path, override=False)

_profile = os.environ.get('AWS_PROFILE')
_session = boto3.Session(profile_name=_profile) if _profile else boto3.Session()

# bedrock-agent: buscar e inspecionar prompts
agent_client = _session.client(
    service_name='bedrock-agent',
    region_name=os.environ.get('AWS_DEFAULT_REGION', 'us-east-1'),
)

# bedrock-runtime: invocar modelos
runtime = _session.client(
    service_name='bedrock-runtime',
    region_name=os.environ.get('AWS_DEFAULT_REGION', 'us-east-1'),
)

# Config gerada pelo create_prompts.py
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'prompt_config.json')

# Modelo a usar na Abordagem A (quando não usamos o ARN do prompt)
FALLBACK_MODEL_ID = "amazon.nova-micro-v1:0"


def carregar_config() -> dict:
    try:
        with open(CONFIG_PATH) as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"AVISO: {CONFIG_PATH} não encontrado. Execute create_prompts.py primeiro.")
        return {}


config = carregar_config()


# ─────────────────────────────────────────────────────────────────────────────
# Helpers de exibição
# ─────────────────────────────────────────────────────────────────────────────

def _cabecalho(titulo: str) -> None:
    print(f"\n{'─' * 60}")
    print(f"  {titulo}")
    print(f"{'─' * 60}")


def _exibir_resposta(texto: str, prefixo: str = "Resposta") -> None:
    preview = texto[:400] + ('...' if len(texto) > 400 else '')
    print(f"  {prefixo}: {preview}")


# ─────────────────────────────────────────────────────────────────────────────
# Bloco 1 — Listar prompts registrados no Bedrock
# ─────────────────────────────────────────────────────────────────────────────

def listar_prompts() -> None:
    """
    Exibe todos os prompts registrados no Bedrock Prompt Management.

    Útil para auditar o que está implantado, verificar nomes e IDs,
    e confirmar que create_prompts.py funcionou corretamente.
    """
    _cabecalho("BLOCO 1 — Prompts registrados no Bedrock Prompt Management")

    prompts = []
    next_token = None

    while True:
        kwargs = {'maxResults': 100}
        if next_token:
            kwargs['nextToken'] = next_token
        response = agent_client.list_prompts(**kwargs)
        prompts.extend(response.get('promptSummaries', []))
        next_token = response.get('nextToken')
        if not next_token:
            break

    if not prompts:
        print("  Nenhum prompt encontrado. Execute create_prompts.py primeiro.")
        return

    print(f"  Total: {len(prompts)} prompt(s)\n")
    print(f"  {'Nome':<35} {'ID':<15} {'Versão':<8} {'Atualizado em'}")
    print(f"  {'─'*35} {'─'*15} {'─'*8} {'─'*20}")

    for p in prompts:
        atualizado = p.get('updatedAt', '?')
        if hasattr(atualizado, 'strftime'):
            atualizado = atualizado.strftime('%Y-%m-%d %H:%M')
        print(f"  {p['name']:<35} {p['id']:<15} {p.get('version', '?'):<8} {atualizado}")

    # Exibe detalhes dos prompts que conhecemos (registrados em prompt_config.json)
    for key, info in config.items():
        print(f"\n  [{key}] Detalhes do template:")
        try:
            resp = agent_client.get_prompt(
                promptIdentifier=info['prompt_id'],
                promptVersion=info['version'],
            )
            for variant in resp.get('variants', []):
                template_text = variant.get('templateConfiguration', {}).get('text', {}).get('text', '')
                variables = variant.get('templateConfiguration', {}).get('text', {}).get('inputVariables', [])
                var_names = [v['name'] for v in variables]
                print(f"    Variante  : {variant['name']}")
                print(f"    Variáveis : {var_names}")
                print(f"    Template  : {template_text[:120]}...")
        except ClientError as e:
            print(f"    Erro ao buscar detalhes: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Bloco 2 — Abordagem A: Fetch + Render local
# ─────────────────────────────────────────────────────────────────────────────
#
# Fluxo:
#   1. get_prompt(promptIdentifier, promptVersion) → busca o template no Bedrock
#   2. Substitui {{variavel}} pelo valor real (render local)
#   3. Chama converse() com o texto renderizado como mensagem do usuário
#
# Vantagens:
#   - Funciona com qualquer versão do boto3 / Bedrock
#   - Dá controle total sobre como o template é renderizado
#   - Permite inspecionar o prompt antes de invocar o modelo
#
# Desvantagens:
#   - O modelo a usar fica hardcoded no código (não vem do prompt)
#   - Uma chamada extra (get_prompt) antes de cada invocação
# ─────────────────────────────────────────────────────────────────────────────

def _buscar_template(prompt_id: str, version: str) -> tuple[str, list[str]]:
    """
    Busca o template text e a lista de variáveis de um prompt versionado.
    Retorna (template_text, [variáveis]).
    """
    response = agent_client.get_prompt(
        promptIdentifier=prompt_id,
        promptVersion=version,
    )
    # Usa a variante 'default' (ou a primeira disponível)
    variants = response.get('variants', [])
    variant = next((v for v in variants if v['name'] == 'default'), variants[0])

    text_cfg = variant.get('templateConfiguration', {}).get('text', {})
    template = text_cfg.get('text', '')
    variables = [v['name'] for v in text_cfg.get('inputVariables', [])]

    return template, variables


def _renderizar(template: str, variaveis: dict[str, str]) -> str:
    """
    Substitui {{variavel}} → valor no template.
    Raise ValueError se alguma variável obrigatória estiver ausente.
    """
    resultado = template
    for nome, valor in variaveis.items():
        resultado = resultado.replace(f'{{{{{nome}}}}}', valor)

    # Verifica se sobrou alguma variável não substituída
    nao_substituidas = re.findall(r'\{\{(\w+)\}\}', resultado)
    if nao_substituidas:
        raise ValueError(f"Variáveis não fornecidas: {nao_substituidas}")

    return resultado


def _converse(texto_renderizado: str) -> tuple[str, float]:
    """
    Chama bedrock-runtime.converse com o texto renderizado como mensagem do usuário.
    Retorna (texto_da_resposta, latencia_ms).
    """
    inicio = time.perf_counter()
    response = runtime.converse(
        modelId=FALLBACK_MODEL_ID,
        messages=[{
            'role': 'user',
            'content': [{'text': texto_renderizado}],
        }],
    )
    latencia_ms = (time.perf_counter() - inicio) * 1000
    content = response.get('output', {}).get('message', {}).get('content', [])
    texto = content[0].get('text', '[sem resposta]') if content else '[sem resposta]'
    return texto, latencia_ms


# ─────────────────────────────────────────────────────────────────────────────
# Helpers de Prompt Caching
# ─────────────────────────────────────────────────────────────────────────────

def _converse_com_cache(instrucoes_estaticas: str, mensagem_usuario: str) -> tuple[str, dict, float]:
    """
    Invoca o modelo separando a parte estática (system) da dinâmica (messages),
    com um cachePoint ao final do bloco system.

    Por que essa separação funciona:
    - A instrução de classificação é idêntica para TODOS os usuários.
    - O Bedrock cacheia o conteúdo do system até o cachePoint na primeira chamada.
    - Nas chamadas seguintes (dentro do TTL de 5 min), o modelo recebe os tokens
      do system direto do cache — sem reprocessamento.

    Retorna (texto_da_resposta, uso_de_tokens, latencia_ms).
    """
    inicio = time.perf_counter()
    response = runtime.converse(
        modelId=FALLBACK_MODEL_ID,
        system=[
            {'text': instrucoes_estaticas},
            # cachePoint: tudo acima desta marca pode ser cacheado pelo Bedrock.
            # Na 1ª chamada: grava no cache (cacheWriteInputTokens > 0).
            # Nas próximas (TTL 5 min): lê do cache (cacheReadInputTokens > 0).
            {'cachePoint': {'type': 'default'}},
        ],
        messages=[{
            'role': 'user',
            'content': [{'text': mensagem_usuario}],
        }],
    )
    latencia_ms = (time.perf_counter() - inicio) * 1000

    content = response.get('output', {}).get('message', {}).get('content', [])
    texto = content[0].get('text', '[sem resposta]') if content else '[sem resposta]'
    uso = response.get('usage', {})
    return texto, uso, latencia_ms


def _exibir_uso_cache(uso: dict, chamada: str) -> None:
    """
    Exibe métricas de uso de tokens com destaque para leitura/escrita de cache.

    Significado dos campos:
    - inputTokens          : total de tokens de entrada (estáticos + dinâmicos)
    - cacheWriteInputTokens: tokens gravados no cache nesta chamada (1ª vez, pequeno overhead)
    - cacheReadInputTokens : tokens lidos do cache (chamadas seguintes, ~90% mais barato)
    - outputTokens         : tokens gerados na resposta

    Requisito de tamanho mínimo (Claude 3.5 Haiku): 1.024 tokens no bloco system.
    Se o bloco for menor, o Bedrock não cacheia e os campos de cache ficam em 0.
    """
    write  = uso.get('cacheWriteInputTokens', 0)
    read   = uso.get('cacheReadInputTokens', 0)
    inp    = uso.get('inputTokens', 0)
    out    = uso.get('outputTokens', 0)

    status = "CACHE WRITE (1ª chamada)" if write > 0 else \
             "CACHE READ  (hit!)"       if read  > 0 else \
             "SEM CACHE   (abaixo do mínimo de tokens)"

    print(f"  [{chamada}] {status}")
    print(f"    inputTokens           : {inp}")
    print(f"    cacheWriteInputTokens : {write}  {'← gravado agora' if write else ''}")
    print(f"    cacheReadInputTokens  : {read}   {'← lido do cache (mais barato!)' if read else ''}")
    print(f"    outputTokens          : {out}")


def testar_abordagem_a_emocao(mensagem: str) -> dict | None:
    """
    Abordagem A — emotion_detection:
      get_prompt → render local → converse
    """
    _cabecalho(f"ABORDAGEM A  |  emotion_detection  |  Fetch + Render")
    print(f"  Mensagem: {mensagem}")

    prompt_info = config.get('emotion_detection')
    if not prompt_info:
        print("  AVISO: emotion_detection não encontrado em prompt_config.json")
        return None

    try:
        template, variables = _buscar_template(prompt_info['prompt_id'], prompt_info['version'])
        print(f"  Template buscado do Bedrock ({len(template)} chars, variáveis: {variables})")

        renderizado = _renderizar(template, {'mensagem': mensagem})
        print(f"  Template renderizado localmente.")

        resposta, latencia_ms = _converse(renderizado)
        _exibir_resposta(resposta, "Resposta JSON")
        print(f"  Latência: {latencia_ms:.0f} ms")

        return json.loads(resposta)

    except ClientError as e:
        print(f"  Erro AWS: {e}")
    except (json.JSONDecodeError, ValueError) as e:
        print(f"  Erro de parsing: {e}")
    return None


def testar_abordagem_a_cenario(mensagem: str, estado: str, contexto_anterior: str = "") -> None:
    """
    Abordagem A — scenario_generation:
      get_prompt → render local → converse
    """
    _cabecalho(f"ABORDAGEM A  |  scenario_generation  |  Fetch + Render")
    print(f"  Estado: {estado}  |  Mensagem: {mensagem[:60]}...")

    prompt_info = config.get('scenario_generation')
    if not prompt_info:
        print("  AVISO: scenario_generation não encontrado em prompt_config.json")
        return

    try:
        template, variables = _buscar_template(prompt_info['prompt_id'], prompt_info['version'])
        print(f"  Template buscado do Bedrock ({len(template)} chars, variáveis: {variables})")

        renderizado = _renderizar(template, {
            'mensagem': mensagem,
            'estado_emocional': estado,
            'contexto_anterior': contexto_anterior,
        })
        print(f"  Template renderizado localmente.")

        resposta, latencia_ms = _converse(renderizado)
        _exibir_resposta(resposta, "Cenário gerado")
        print(f"  Latência: {latencia_ms:.0f} ms")

    except ClientError as e:
        print(f"  Erro AWS: {e}")
    except ValueError as e:
        print(f"  Erro de render: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Bloco 3 — Abordagem B: Prompt ARN direto no converse
# ─────────────────────────────────────────────────────────────────────────────
#
# Fluxo:
#   1. Passa o ARN versionado do prompt como modelId no converse
#   2. Passa as variáveis como promptVariables (dict nome → {'text': valor})
#   3. O Bedrock busca o template, substitui as variáveis e invoca o modelo
#      configurado no próprio prompt — tudo em uma única chamada de API
#
# Vantagens:
#   - Uma única chamada de API (sem get_prompt separado)
#   - O modelo e os parâmetros de inferência vêm do prompt (gerenciados centralmente)
#   - Mudanças de prompt/modelo não exigem alteração no código da aplicação
#
# Desvantagens:
#   - Requer suporte ao campo promptVariables no boto3 >= 1.35.x
#   - Menos transparência: você não "vê" o prompt renderizado antes de enviar
# ─────────────────────────────────────────────────────────────────────────────

def testar_abordagem_b_emocao(mensagem: str) -> dict | None:
    """
    Abordagem B — emotion_detection:
      converse(modelId=prompt_arn, promptVariables={...})
    """
    _cabecalho(f"ABORDAGEM B  |  emotion_detection  |  ARN direto")
    print(f"  Mensagem: {mensagem}")

    prompt_info = config.get('emotion_detection')
    if not prompt_info:
        print("  AVISO: emotion_detection não encontrado em prompt_config.json")
        return None

    versioned_arn = prompt_info['versioned_arn']
    print(f"  Prompt ARN: {versioned_arn}")

    try:
        inicio = time.perf_counter()
        response = runtime.converse(
            modelId=versioned_arn,
            promptVariables={
                'mensagem': {'text': mensagem},
            },
        )
        latencia_ms = (time.perf_counter() - inicio) * 1000

        content = response.get('output', {}).get('message', {}).get('content', [])
        resposta = content[0].get('text', '[sem resposta]') if content else '[sem resposta]'
        _exibir_resposta(resposta, "Resposta JSON")
        print(f"  Latência: {latencia_ms:.0f} ms")

        return json.loads(resposta)

    except ClientError as e:
        code = e.response.get('Error', {}).get('Code', '')
        msg = e.response.get('Error', {}).get('Message', str(e))
        print(f"  Erro AWS ({code}): {msg}")
        if 'ValidationException' in code:
            print("  DICA: Verifique se a versão do boto3 suporta promptVariables (>= 1.35.x)")
    except (json.JSONDecodeError, ValueError) as e:
        print(f"  Erro de parsing: {e}")
    return None


def testar_abordagem_b_cenario(mensagem: str, estado: str, contexto_anterior: str = "") -> None:
    """
    Abordagem B — scenario_generation:
      converse(modelId=prompt_arn, promptVariables={...})
    """
    _cabecalho(f"ABORDAGEM B  |  scenario_generation  |  ARN direto")
    print(f"  Estado: {estado}  |  Mensagem: {mensagem[:60]}...")

    prompt_info = config.get('scenario_generation')
    if not prompt_info:
        print("  AVISO: scenario_generation não encontrado em prompt_config.json")
        return

    versioned_arn = prompt_info['versioned_arn']
    print(f"  Prompt ARN: {versioned_arn}")

    try:
        inicio = time.perf_counter()
        response = runtime.converse(
            modelId=versioned_arn,
            promptVariables={
                'mensagem': {'text': mensagem},
                'estado_emocional': {'text': estado},
                'contexto_anterior': {'text': contexto_anterior},
            },
        )
        latencia_ms = (time.perf_counter() - inicio) * 1000

        content = response.get('output', {}).get('message', {}).get('content', [])
        resposta = content[0].get('text', '[sem resposta]') if content else '[sem resposta]'
        _exibir_resposta(resposta, "Cenário gerado")
        print(f"  Latência: {latencia_ms:.0f} ms")

    except ClientError as e:
        code = e.response.get('Error', {}).get('Code', '')
        msg = e.response.get('Error', {}).get('Message', str(e))
        print(f"  Erro AWS ({code}): {msg}")
        if 'ValidationException' in code:
            print("  DICA: Verifique se a versão do boto3 suporta promptVariables (>= 1.35.x)")


# ─────────────────────────────────────────────────────────────────────────────
# Bloco 4 — Prompt Caching: system estático + message dinâmica
# ─────────────────────────────────────────────────────────────────────────────
#
# Estratégia:
#   O template de emotion_detection tem duas partes:
#     1. Instrução estática  : classificador, regras, categorias  →  system[]
#     2. Mensagem do usuário : {{mensagem}} (muda por chamada)    →  messages[]
#
#   Colocando um cachePoint ao final do bloco system, o Bedrock cacheia as
#   instruções na primeira chamada e as reutiliza nas chamadas seguintes.
#
#   Resultado prático:
#   - 1ª chamada : grava no cache (cacheWriteInputTokens > 0, +25% no custo dos tokens estáticos)
#   - Chamadas seguintes (TTL 5 min): lê do cache (cacheReadInputTokens > 0, ~90% mais barato)
# ─────────────────────────────────────────────────────────────────────────────

def testar_cache_emocao(mensagens: list[str]) -> None:
    """
    Executa o emotion_detection com caching para uma lista de mensagens.

    A primeira chamada grava as instruções estáticas no cache.
    As chamadas seguintes leem do cache — só os tokens da mensagem do usuário
    são processados do zero.

    Mostra as métricas de uso de tokens para cada chamada, tornando
    visível a diferença entre cache write e cache read.
    """
    _cabecalho("BLOCO 4 — Prompt Caching  |  system estático + cachePoint")

    prompt_info = config.get('emotion_detection')
    if not prompt_info:
        print("  AVISO: emotion_detection não encontrado em prompt_config.json")
        return

    try:
        template, _ = _buscar_template(prompt_info['prompt_id'], prompt_info['version'])
    except ClientError as e:
        print(f"  Erro ao buscar template: {e}")
        return

    # Divide o template na fronteira da variável dinâmica.
    # Tudo antes de {{mensagem}} vai para o system (sempre igual).
    # A mensagem real do usuário vai para messages (muda por chamada).
    partes = template.split('{{mensagem}}')
    instrucoes_estaticas = partes[0].rstrip()

    print(f"  Template dividido em:")
    print(f"    system (estático, {len(instrucoes_estaticas)} chars) → cachePoint")
    print(f"    messages (dinâmico, varia por usuário)\n")

    for i, mensagem in enumerate(mensagens, start=1):
        print(f"  Chamada {i}: {mensagem[:70]}{'...' if len(mensagem) > 70 else ''}")
        try:
            resposta, uso, latencia_ms = _converse_com_cache(instrucoes_estaticas, mensagem)
            _exibir_uso_cache(uso, f"chamada {i}")
            print(f"    Latência          : {latencia_ms:.0f} ms")
            # Exibe só o estado detectado para manter a saída compacta
            try:
                estado = json.loads(resposta).get('estado', '?')
                print(f"    Estado detectado: {estado}\n")
            except json.JSONDecodeError:
                print(f"    Resposta: {resposta[:100]}\n")
        except ClientError as e:
            print(f"    Erro AWS: {e}\n")


# ─────────────────────────────────────────────────────────────────────────────
# Bloco 5 — Pipeline completo (emoção → cenário) com Abordagem B
# ─────────────────────────────────────────────────────────────────────────────
#
# ─────────────────────────────────────────────────────────────────────────────
# Bloco 6 — TTFT via converse_stream
# ─────────────────────────────────────────────────────────────────────────────
#
# TTFT (Time To First Token) mede o tempo entre o envio da requisição e o
# recebimento do primeiro token de texto. Só é possível medir com streaming:
#   - converse()        → bloqueia até o último token; não expõe TTFT
#   - converse_stream() → emite eventos incrementais; o primeiro
#                         contentBlockDelta com texto é o TTFT
#
# O evento final `metadata` traz metrics.latencyMs (latência total, não TTFT)
# e usage (tokens de entrada/saída).
# ─────────────────────────────────────────────────────────────────────────────

def _stream_com_ttft(
    texto_renderizado: str,
    system: str | None = None,
    model_id: str = FALLBACK_MODEL_ID,
    use_cache: bool = False,
) -> tuple[str, float, float, dict]:
    """
    Invoca o modelo via converse_stream e imprime os chunks em tempo real.

    Parâmetros
    ----------
    texto_renderizado : prompt já com variáveis substituídas (vai em messages[])
    system            : bloco de instruções estáticas opcionais (vai em system[])
    model_id          : modelo Bedrock a invocar
    use_cache         : se True e system fornecido, adiciona cachePoint ao system

    Retorna
    -------
    (texto_completo, ttft_ms, latencia_total_ms, uso)
      ttft_ms           : tempo até o primeiro token (ms)
      latencia_total_ms : latência total reportada pelo Bedrock em metrics.latencyMs
      uso               : dict com inputTokens, outputTokens e campos de cache
    """
    kwargs: dict = {
        'modelId': model_id,
        'messages': [{'role': 'user', 'content': [{'text': texto_renderizado}]}],
    }
    if system:
        system_block = [{'text': system}]
        if use_cache:
            system_block.append({'cachePoint': {'type': 'default'}})
        kwargs['system'] = system_block

    inicio = time.perf_counter()
    ttft_ms: float | None = None
    chunks: list[str] = []
    latencia_total_ms: float = 0.0
    uso: dict = {}

    response = runtime.converse_stream(**kwargs)
    stream = response.get('stream')

    print('  ', end='', flush=True)
    for event in stream:
        if 'contentBlockDelta' in event:
            texto = event['contentBlockDelta'].get('delta', {}).get('text', '')
            if texto:
                if ttft_ms is None:
                    ttft_ms = (time.perf_counter() - inicio) * 1000
                chunks.append(texto)
                print(texto, end='', flush=True)

        elif 'metadata' in event:
            uso = event['metadata'].get('usage', {})
            metrics = event['metadata'].get('metrics', {})
            latencia_total_ms = metrics.get('latencyMs', 0.0)

    print()  # quebra de linha após o streaming
    return ''.join(chunks), ttft_ms or 0.0, latencia_total_ms, uso


def testar_ttft_mensagens(mensagens: list[str]) -> list[dict]:
    """
    Mede TTFT de cada mensagem usando o template emotion_detection via streaming.

    Para cada mensagem:
      1. Renderiza o template localmente (Abordagem A)
      2. Chama converse_stream e imprime os tokens conforme chegam
      3. Exibe TTFT, latência total e uso de tokens
    """
    _cabecalho("BLOCO 6a — TTFT sem cache via converse_stream  |  emotion_detection")

    prompt_info = config.get('emotion_detection')
    if not prompt_info:
        print("  AVISO: emotion_detection não encontrado em prompt_config.json")
        return []

    try:
        template, _ = _buscar_template(prompt_info['prompt_id'], prompt_info['version'])
    except ClientError as e:
        print(f"  Erro ao buscar template: {e}")
        return []

    print(f"  Template carregado ({len(template)} chars). Iniciando streaming...\n")

    resultados: list[dict] = []

    for i, mensagem in enumerate(mensagens, start=1):
        print(f"  ── Mensagem {i}: {mensagem[:70]}{'...' if len(mensagem) > 70 else ''}")
        try:
            renderizado = _renderizar(template, {'mensagem': mensagem})
            texto, ttft_ms, total_ms, uso = _stream_com_ttft(renderizado)

            try:
                estado = json.loads(texto).get('estado', '?')
            except json.JSONDecodeError:
                estado = '?'

            inp = uso.get('inputTokens', 0)
            out = uso.get('outputTokens', 0)
            print(f"  Estado         : {estado}")
            print(f"  TTFT           : {ttft_ms:.0f} ms")
            print(f"  Latência total : {total_ms:.0f} ms")
            print(f"  Tokens entrada : {inp}  |  saída: {out}\n")

            resultados.append({
                'mensagem': mensagem[:50],
                'ttft_ms': ttft_ms,
                'total_ms': total_ms,
            })

        except ClientError as e:
            print(f"  Erro AWS: {e}\n")
        except ValueError as e:
            print(f"  Erro de render: {e}\n")

    if resultados:
        print(f"  {'─' * 56}")
        print(f"  {'Mensagem':<36} {'TTFT (ms)':>10} {'Total (ms)':>10}")
        print(f"  {'─' * 56}")
        for r in resultados:
            print(f"  {r['mensagem']:<36} {r['ttft_ms']:>10.0f} {r['total_ms']:>10.0f}")
        print(f"  {'─' * 56}")

    return resultados

def testar_ttft_com_cache(mensagens: list[str]) -> list[dict]:
    """
    Mede TTFT de cada mensagem usando prompt caching via converse_stream.

    Instruções estáticas do template vão em system[] com cachePoint.
    Só a mensagem do usuário vai em messages[] (muda por chamada).

    - 1ª chamada: grava no cache (cacheWriteInputTokens > 0)
    - Chamadas seguintes (TTL 5 min): lê do cache (cacheReadInputTokens > 0)
    """
    _cabecalho("BLOCO 6b — TTFT com cache via converse_stream  |  emotion_detection")

    prompt_info = config.get('emotion_detection')
    if not prompt_info:
        print("  AVISO: emotion_detection não encontrado em prompt_config.json")
        return []

    try:
        template, _ = _buscar_template(prompt_info['prompt_id'], prompt_info['version'])
    except ClientError as e:
        print(f"  Erro ao buscar template: {e}")
        return []

    instrucoes_estaticas = template.split('{{mensagem}}')[0].rstrip()
    print(f"  Instrução estática: {len(instrucoes_estaticas)} chars → system[] + cachePoint")
    print(f"  Mensagem do usuário                              → messages[]\n")

    resultados: list[dict] = []

    for i, mensagem in enumerate(mensagens, start=1):
        print(f"  ── Mensagem {i}: {mensagem[:70]}{'...' if len(mensagem) > 70 else ''}")
        try:
            _, ttft_ms, total_ms, uso = _stream_com_ttft(
                mensagem,
                system=instrucoes_estaticas,
                use_cache=True,
            )
            write = uso.get('cacheWriteInputTokens', 0)
            read  = uso.get('cacheReadInputTokens', 0)
            inp   = uso.get('inputTokens', 0)
            out   = uso.get('outputTokens', 0)
            cache_status = "WRITE (1ª vez)" if write > 0 else "READ (hit!)" if read > 0 else "sem cache (tokens insuf.)"
            print(f"  TTFT: {ttft_ms:.0f} ms  |  Total: {total_ms:.0f} ms  "
                  f"|  tokens in/out: {inp}/{out}  |  cache: {cache_status}\n")
            resultados.append({'mensagem': mensagem[:50], 'ttft_ms': ttft_ms, 'total_ms': total_ms, 'cache': cache_status})
        except (ClientError, ValueError) as e:
            print(f"  Erro: {e}\n")

    if resultados:
        print(f"  {'─' * 70}")
        print(f"  {'Mensagem':<36} {'TTFT (ms)':>10} {'Total (ms)':>10}  Cache")
        print(f"  {'─' * 70}")
        for r in resultados:
            print(f"  {r['mensagem']:<36} {r['ttft_ms']:>10.0f} {r['total_ms']:>10.0f}  {r['cache']}")
        print(f"  {'─' * 70}")

    return resultados


def _tabela_comparativa_6a_6b(res_6a: list[dict], res_6b: list[dict]) -> None:
    """
    Exibe tabela comparando TTFT e latência total dos Blocos 6a (sem cache)
    e 6b (com cache) para as mesmas mensagens.
    """
    if not res_6a or not res_6b:
        return

    _cabecalho("COMPARATIVO 6a vs 6b  |  sem cache  vs  com cache")

    W = 36
    print(f"  {'Mensagem':<{W}} {'TTFT 6a':>8} {'Tot 6a':>8} {'TTFT 6b':>8} {'Tot 6b':>8}  {'Δ TTFT':>8}  Cache 6b")
    print(f"  {'─' * (W + 60)}")

    for a, b in zip(res_6a, res_6b):
        delta = b['ttft_ms'] - a['ttft_ms']
        delta_str = f"{delta:+.0f}"
        print(
            f"  {a['mensagem']:<{W}}"
            f" {a['ttft_ms']:>8.0f}"
            f" {a['total_ms']:>8.0f}"
            f" {b['ttft_ms']:>8.0f}"
            f" {b['total_ms']:>8.0f}"
            f"  {delta_str:>8}"
            f"  {b.get('cache', '?')}"
        )

    print(f"  {'─' * (W + 60)}")
    print(f"  Δ TTFT = 6b − 6a (ms). Negativo = cache reduziu latência.")


def testar_pipeline_completo(mensagem: str) -> None:
    """
    Demonstra o pipeline real do PreFi Lite usando apenas Abordagem B:
      1. emotion_detection (ARN direto) → detecta o estado
      2. scenario_generation (ARN direto) → usa o estado detectado para gerar cenários

    Isso ilustra como o Bedrock Prompt Management elimina o gerenciamento
    de templates do código da aplicação: o worker/API só conhece os ARNs.
    """
    _cabecalho("BLOCO 5 — Pipeline completo via Prompt ARNs")
    print(f"  Mensagem do usuário: {mensagem}\n")

    # Passo 1: Detectar emoção
    resultado_emocao = testar_abordagem_b_emocao(mensagem)
    if not resultado_emocao:
        print("  Pipeline interrompido: falha na detecção de emoção.")
        return

    estado = resultado_emocao.get('estado', 'CONFUSO')
    confianca = resultado_emocao.get('confianca', 0.0)
    print(f"\n  Estado detectado: {estado} (confiança: {confianca:.2f})")

    # Passo 2: Gerar cenários usando o estado detectado
    testar_abordagem_b_cenario(mensagem, estado)


# ─────────────────────────────────────────────────────────────────────────────
# Suite de testes
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    print("=" * 60)
    print("  SUITE DE TESTES — BEDROCK PROMPT MANAGEMENT")
    print("=" * 60)

    if not config:
        print("\nAVISO: prompt_config.json vazio. Execute create_prompts.py primeiro.\n")

    # ── Bloco 1: Auditoria ────────────────────────────────────────────────────
    listar_prompts()

    # ── Bloco 2: Abordagem A (Fetch + Render) ─────────────────────────────────
    print("\n\n### BLOCO 2: Abordagem A — get_prompt + render local + converse ###")
    print("    (template buscado do Bedrock, variáveis substituídas no código)")

    resultado = testar_abordagem_a_emocao(
        "Quero refinanciar minha casa mas tenho medo de errar alguma coisa e perder tudo."
    )
    if resultado:
        estado_detectado = resultado.get('estado', 'CONFUSO')
        testar_abordagem_a_cenario(
            mensagem="Quero refinanciar minha casa mas tenho medo de errar alguma coisa e perder tudo.",
            estado=estado_detectado,
        )

    testar_abordagem_a_emocao(
        "Já tentei refinanciar três vezes e sempre aparece algum problema no processo. Tô desistindo."
    )

    # ── Bloco 3: Abordagem B (ARN direto) ─────────────────────────────────────
    print("\n\n### BLOCO 3: Abordagem B — converse com prompt ARN + promptVariables ###")
    print("    (template, modelo e inferência gerenciados centralmente no Bedrock)")

    testar_abordagem_b_emocao(
        "Li bastante sobre CET, IPCA+, TR. Quero saber qual indexador é melhor pro meu caso."
    )

    testar_abordagem_b_cenario(
        mensagem="Li bastante sobre CET, IPCA+, TR. Quero saber qual indexador é melhor pro meu caso.",
        estado="CONFIANTE",
    )

    # Cenário com contexto anterior (fluxo de refinamento)
    testar_abordagem_b_cenario(
        mensagem="Não entendi nada sobre a parcela. Como funciona isso?",
        estado="CONFUSO",
        contexto_anterior=(
            "Cenário anterior gerado:\n"
            "Conservador: Prazo 30 anos, parcela ~R$2.100. Otimizado: Prazo 20 anos, parcela ~R$2.800.\n\n"
            "Avaliação do usuário: 2/5\n"
            "Feedback: Muito técnico, não entendi como a parcela é calculada."
        ),
    )

    # ── Bloco 4: Prompt Caching ───────────────────────────────────────────────
    print("\n\n### BLOCO 4: Prompt Caching — system cachePoint ###")
    print("    (instruções estáticas cacheadas; só a mensagem do usuário é nova)")
    print("    Requisito: >= 1.024 tokens no bloco system para o Claude 3.5 Haiku cachear.")
    print("    Se cacheWriteInputTokens = 0, o bloco estático está abaixo do mínimo.")

    testar_cache_emocao([
        "Quero refinanciar minha casa mas tenho medo de errar e perder tudo.",
        "Já pesquisei bastante sobre CET e IPCA+. Quero comparar os indexadores.",
        "Tentei refinanciar três vezes e sempre aparece um problema. Tô desistindo.",
    ])

    # ── Bloco 5: Pipeline completo ────────────────────────────────────────────
    print("\n\n### BLOCO 5: Pipeline completo (emoção → cenário) via Abordagem B ###")

    testar_pipeline_completo(
        "Minha dívida tá me sufocando. Ouvi falar em refinanciamento mas não sei se é pra mim."
    )

    # ── Bloco 6a: TTFT via streaming ───────────────────────────────────────────
    print("\n\n### BLOCO 6a: TTFT — converse_stream (tokens impressos em tempo real) ###")
    print("    (TTFT = tempo até o 1º token; latência total = tempo até o último)")

    MENSAGENS_TTFT = [
        "Quero refinanciar minha casa mas tenho medo de errar alguma coisa e perder tudo.",
        "Já tentei refinanciar três vezes e sempre aparece algum problema. Tô desistindo.",
        "Li bastante sobre CET, IPCA+, TR. Quero saber qual indexador é melhor pro meu caso.",
        "Não entendi nada sobre a parcela. Como funciona isso?",
        "Minha dívida tá me sufocando. Ouvi falar em refinanciamento mas não sei se é pra mim.",
    ]

    res_6a = testar_ttft_mensagens(MENSAGENS_TTFT)

    # ── Bloco 6b: TTFT com cache ──────────────────────────────────────────────
    print("\n\n### BLOCO 6b: TTFT — com cache (system[] + cachePoint) ###")
    print("    (1ª mensagem: cache WRITE; seguintes: cache READ se dentro do TTL de 5 min)")

    res_6b = testar_ttft_com_cache(MENSAGENS_TTFT)

    # ── Comparativo 6a vs 6b ──────────────────────────────────────────────────
    _tabela_comparativa_6a_6b(res_6a, res_6b)

    print(f"\n{'=' * 60}")
    print("  Testes concluídos.")
    print(f"{'=' * 60}\n")
