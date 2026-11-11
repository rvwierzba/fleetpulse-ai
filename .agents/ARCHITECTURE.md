# ARCHITECTURE.md — Arquitetura do FleetPulse AI

## 1. Visão Geral (Topologia)

```text
  [Simulador / Dispositivos (Notebooks & Smartphones)]
                 │  POST /v1/alerts (Idempotency-Key)
                 ▼
  ┌──────────────────────────────────────────────────────────┐
  │                 FastAPI Ingestion & BFF                  │
  │  • Rate Limiter (Redis)                                  │
  │  • Idempotency Guard (Redis)                             │
  │  • SSE Stream Broker (Redis Pub/Sub -> Vue 3)            │
  │  • Human-in-the-Loop & Analytics Endpoints               │
  └───────────────┬──────────────────────────┬───────────────┘
                  │ Enfileira job            ▲ Eventos SSE
                  ▼                          │
  ┌──────────────────────────────────────────────────────────┐
  │                 Redis (Queue + Cache + PubSub)           │
  │  • Stream / Fila principal + Dead Letter Queue (DLQ)     │
  │  • Semantic Cache L1 / Deduplication Window              │
  └───────────────┬──────────────────────────────────────────┘
                  │ Consome assíncrono
                  ▼
  ┌──────────────────────────────────────────────────────────┐
  │               Async Worker & State Machine               │
  │                                                          │
  │  [1] Deduplicação & Persistência Estado (PostgreSQL)     │
  │  [2] ML Scoring + SHAP (Modelo versionado local)         │
  │  [3] Hybrid RAG:                                         │
  │      ├─ Cache Semântico (pgvector / Redis)               │
  │      ├─ Grafo de Topologia & Firmware (Neo4j)            │
  │      └─ Busca Semântica em Boletins (pgvector + Ollama)  │
  │  [4] Agente Diagnóstico + Hybrid AI Router               │
  │      ├─ Ollama Local (phi4-mini / llama3.1:8b)           │
  │      └─ Circuit Breaker & Fallback Cloud (opcional)      │
  │  [5] Validação Estrita (Pydantic + Checagem Neo4j)       │
  │      └─ Loop de Auto-correção (até 2 retries)            │
  │  [6] Decisão: HUMAN_REVIEW ou AUTO_RECOMMENDED           │
  └──────────────────────────────────────────────────────────┘
```

## 2. Organização Planejada do Código

```text
fleetpulse-ai/
├── .agents/               # Specs, arquitetura, convenções, changelog e skills
├── docs/adr/              # Architecture Decision Records
├── infra/                 # Scripts de inicialização de infraestrutura local (ex.: pgvector init.sql)
├── backend/
│   ├── app/
│   │   ├── api/           # Rotas FastAPI (v1), middlewares de idempotência/rate-limit, SSE
│   │   ├── domain/        # Entidades, enums, máquina de estados e regras de SLA
│   │   ├── workers/       # Consumidor Redis, retries, backoff e DLQ
│   │   ├── ml/            # Treino, validação sem leakage, inferência e SHAP
│   │   ├── rag/           # Neo4j client, pgvector store, semantic cache, Text-to-Cypher
│   │   ├── agents/        # Hybrid LLM router, circuit breaker, guardrails e self-correction
│   │   └── infra/         # Config, DB async, Redis, Ollama client, observabilidade
│   └── tests/             # Testes unitários, de contrato e integração
├── frontend/              # Vue 3 + Vite + TypeScript + Tailwind CSS
├── benchmarks/            # Simulador de rajadas de telemetria e coleta de P50/P95
├── .env.example           # Template versionado de variáveis de ambiente
└── docker-compose.yml     # PostgreSQL (pgvector), Neo4j e Redis
```

## 3. Invariantes Arquiteturais (Nunca Quebrar)

1. **Ingestão não-bloqueante:** a rota `POST /v1/alerts` **nunca** executa inferência de ML nem chamadas a LLM ou Neo4j diretamente; ela apenas valida o payload, aplica rate limit/idempotência, grava o estado `RECEIVED`, publica na fila e retorna `202`.
2. **Transições explícitas de estado:** toda mudança de estado de um alerta passa pelo repositório de máquina de estados, grava histórico auditável (`alert_events`) e emite evento para o canal SSE.
3. **Sem alucinação de ação:** nenhum diagnóstico passa para `SCHEMA_VALIDATED` se citar um `runbook_id` ou `tech_bulletin_id` que não exista no banco/grafo oficial.
4. **Read-only em queries geradas por IA:** qualquer query Cypher ou SQL gerada dinamicamente por LLM deve passar por parser/whitelist bloqueando comandos de escrita ou múltiplas instruções.
5. **Isolamento de ML:** nenhum dado do conjunto de teste (nem o mesmo `device_id` em janelas futuras) entra no pipeline de treino/normalização.
6. **Humano no comando:** recomendações de abertura de RMA, substituição de peça ou bloqueio de versão de firmware em lote exigem transição para `HUMAN_REVIEW` antes de `RESOLVED`.
