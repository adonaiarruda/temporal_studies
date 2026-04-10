# PreFi Lite

Simulação educacional do fluxo do Clarity Engine usando Temporal + AWS Bedrock.

## Pré-requisitos

- Python 3.11+
- Docker
- Credenciais AWS com acesso ao Bedrock

## Setup

```bash
# 1. Clonar e entrar no diretório
cd prefi-lite

# 2. Configurar variáveis de ambiente
cp .env.example .env
# editar .env com suas credenciais AWS

# 3. Criar e ativar o ambiente virtual
python3 -m venv .venv
source .venv/bin/activate

# 4. Instalar dependências
pip install -e ".[dev]"
```

## Executando

**Terminal 1 — Temporal (Docker)**
```bash
docker compose -f docker/docker-compose.yml up -d
```
Aguarde ~20 segundos. Acompanhe com:
```bash
docker compose -f docker/docker-compose.yml logs -f temporal
```
UI disponível em http://localhost:8080

**Terminal 2 — Worker**
```bash
source .venv/bin/activate
python src/worker.py
```

**Terminal 3 — API**
```bash
source .venv/bin/activate
uvicorn src.api:app --reload
```
Docs disponíveis em http://localhost:8000/docs

## Uso

```bash
# Iniciar análise
curl -X POST http://localhost:8000/analysis/start \
  -H "Content-Type: application/json" \
  -d '{"mensagem": "Quero refinanciar minha casa mas tenho medo de errar"}'

# Buscar resultado (substituir pelo workflow_id retornado)
curl http://localhost:8000/analysis/{workflow_id}/result

# Refinamento (quando nota <= 3)
curl -X POST http://localhost:8000/refinement/start \
  -H "Content-Type: application/json" \
  -d '{"analysis_id": "{workflow_id}", "nota": 2, "feedback": "Muito técnico"}'

# Buscar resultado do refinamento
curl http://localhost:8000/refinement/{workflow_id}/result
```

## Testes

```bash
pytest tests/unit/ -v
```

## Parar

```bash
docker compose -f docker/docker-compose.yml down
```
