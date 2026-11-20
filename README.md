# FleetPulse AI

Plataforma distribuída de **telemetria proativa, triagem inteligente de alertas e proteção de SLA** para frotas corporativas de **notebooks e smartphones** (Device-as-a-Service, suporte técnico N2/N3 e garantia B2B).

Construído em **Spec-Driven Development** (`.agents/` + ADRs) integrando **System Design assíncrono**, **Machine Learning explicável (SHAP)**, **RAG Híbrido (Neo4j + pgvector + Cache Semântico)**, **Hybrid AI Router (Ollama local + fallback opcional)** e **dashboard em Vue 3**.

---

## Arquitetura Geral

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
  │  • Fila principal + Dead Letter Queue (DLQ)              │
  │  • Janela de deduplicação                                │
  └───────────────┬──────────────────────────────────────────┘
                  │ Consome assíncrono
                  ▼
  ┌──────────────────────────────────────────────────────────┐
  │               Async Worker & State Machine               │
  │  [1] Deduplicação & Estado Persistido (PostgreSQL)       │
  │  [2] ML Scoring + SHAP (Modelo versionado local)         │
  │  [3] Hybrid RAG: Cache Semântico + Neo4j + pgvector      │
  │  [4] Agente Diagnóstico (Ollama local + Circuit Breaker) │
  │  [5] Validação Pydantic + Checagem Neo4j (Auto-correção) │
  │  [6] Decisão: HUMAN_REVIEW ou AUTO_RECOMMENDED           │
  └──────────────────────────────────────────────────────────┘
```

Detalhes completos de requisitos, máquina de estados e invariantes arquiteturais:
- Especificação do produto: [`.agents/SPEC.md`](.agents/SPEC.md)
- Arquitetura e invariantes: [`.agents/ARCHITECTURE.md`](.agents/ARCHITECTURE.md)
- Convenções de engenharia: [`.agents/CONVENTIONS.md`](.agents/CONVENTIONS.md)
- Roadmap das 6 Sprints: [`.agents/ROADMAP.md`](.agents/ROADMAP.md)
- Decisões arquiteturais (ADRs): [`docs/adr/`](docs/adr/)

---

## Stack Tecnológica

- **API & Workers:** Python, FastAPI, Pydantic v2, SQLAlchemy Async
- **Mensageria, Cache & Rate Limit:** Redis (AOF, política `noeviction`)
- **Persistência Transacional & Vetores:** PostgreSQL + `pgvector`
- **Grafo de Topologia & Firmware:** Neo4j 5 Community
- **IA Local & Embeddings:** Ollama (`phi4-mini`, `llama3.1:8b`, `nomic-embed-text`)
- **ML Explicável:** `scikit-learn` / `LightGBM` + SHAP
- **Front-end (Sprint 5):** Vue 3, TypeScript, Vite, Tailwind CSS

---

## Subindo a Infraestrutura Base (Sprint 0)

### Pré-requisitos
- Docker + Docker Compose
- [Ollama](https://ollama.com/) rodando localmente (`http://localhost:11434`) com os modelos:
  - `nomic-embed-text:latest`
  - `phi4-mini:latest`
  - `llama3.1:8b`

### Configuração e Inicialização

1. Copie o arquivo de variáveis de ambiente:
```bash
cp .env.example .env
```

2. Suba os serviços de infraestrutura (`PostgreSQL + pgvector`, `Neo4j` e `Redis`):
```bash
docker compose up -d
```

3. Verifique o status e healthchecks:
```bash
docker compose ps
```

Portas padrão expostas localmente:
- **PostgreSQL (`pgvector`):** `localhost:5432`
- **Neo4j Browser / Bolt:** `http://localhost:7474` / `bolt://localhost:7687`
- **Redis:** `localhost:6379`
- **Ollama (host):** `http://localhost:11434`

---

## Decisões Arquiteturais (ADRs)

- [ADR-001](docs/adr/ADR-001-async-ingestion-and-state-machine.md): Ingestão Não-Bloqueante, Idempotência e Máquina de Estados Assíncrona
- [ADR-002](docs/adr/ADR-002-hybrid-rag-neo4j-pgvector-semantic-cache.md): RAG Híbrido (Neo4j + pgvector + Cache Semântico) e Text-to-Cypher Read-Only
- [ADR-003](docs/adr/ADR-003-hybrid-ai-router-and-ml-explainability.md): Hybrid AI Router, ML Tabular Explicável (SHAP), Auto-Correção e Human-in-the-Loop

---

## Status do Roadmap

- [x] **Sprint 0 — Passo 0.1:** Estrutura `.agents/`, `SPEC.md`, `ARCHITECTURE.md`, `CONVENTIONS.md`, `ROADMAP.md` e skills operacionais
- [x] **Sprint 0 — Passo 0.2:** ADRs (`ADR-001` a `ADR-003`), `README.md`, `.env.example`, `docker-compose.yml` e validação de infraestrutura
- [x] **Sprint 1:** Ingestão FastAPI (`202 Accepted`), Idempotency-Key, Rate Limiter, Redis Queue + DLQ, Máquina de Estados e SSE (`14` testes em `pytest` + fluxo validado contra Docker)
- [x] **Sprint 2:** Telemetria realista de frotas (notebooks e smartphones), pipeline de ML tabular sem data leakage (split temporal + agrupamento por dispositivo), avaliação rigorosa com PR-AUC e calibração de Brier score, explicabilidade local via SHAP TreeExplainer e integração assíncrona no worker avançando o estado para `ML_SCORED` (`18` testes automatizados passando)
- [x] **Sprint 3:** RAG Híbrido em 3 camadas: Grafo de Conhecimento e Topologia no Neo4j, Base Vetorial de Manuais e Boletins Técnicos no PostgreSQL com `pgvector` e embeddings locais (`nomic-embed-text`), Cache Semântico em dois níveis (Redis L1 + pgvector L2 com threshold `>= 0.90`), Validador Text-to-Cypher estritamente Read-Only e transição assíncrona do worker para `CONTEXT_RETRIEVED` (`24` testes automatizados passando)
- [x] **Sprint 4:** Hybrid AI Router, Auto-correção Pydantic/Neo4j, Guardrails e Human-in-the-Loop
- [x] **Sprint 5:** Dashboard Vue 3 + Simulador de carga "Tempestade de Firmware" + Benchmarks

---

## Licença

Uso educacional e portfólio técnico — [github.com/rvwierzba/fleetpulse-ai](https://github.com/rvwierzba/fleetpulse-ai).
