# CHANGELOG.md — Histórico do FleetPulse AI

## [Unreleased]

### Sprint 1 — System Design & Máquina de Estados Assíncrona (Concluída)
- Estruturação do pacote `backend/` (`pyproject.toml`, `FastAPI`, `Pydantic`, `SQLAlchemy Async`, `redis.asyncio`, `ruff`, `pytest`).
- Domínio e máquina de estados imutável (`DeviceType`, `Subsystem`, `SLATier`, `AlertStatus`, `VALID_TRANSITIONS`) + persistência transacional no PostgreSQL (`alerts` e `alert_events`).
- Camada Redis (`enqueue_alert`, Rate Limiter por `source_id`, `Idempotency-Key`, trava atômica de deduplicação `SET NX EX`, Sorted Set de retry exponencial, Dead Letter Queue e canal Pub/Sub por alerta).
- Endpoints `POST /v1/alerts` (`202 Accepted`), `GET /v1/alerts/{alert_id}`, `GET /v1/alerts/{alert_id}/stream` (SSE sem perda de eventos entre PostgreSQL e Redis) e `/health`.
- Worker assíncrono (`backend/app/workers/alert_worker.py`) com deduplicação, backoff exponencial e encaminhamento para DLQ, coberto por `14` testes automatizados (`pytest`) e smoke test real contra Docker.

### Sprint 0 — Spec-Driven Development & Arquitetura Base (Concluída)
- **Passo 0.1:** Criação independente do repositório em `C:\DEV\fleetpulse-ai` (`git init -b main`), `.gitignore` e estrutura `.agents/` (`README.md`, `SPEC.md`, `ARCHITECTURE.md`, `CONVENTIONS.md`, `ROADMAP.md`, `skills/`).
- **Passo 0.2:** Registro dos 3 ADRs iniciais em `docs/adr/` (`ADR-001` a `ADR-003`), criação de `README.md`, `.env.example`, `docker-compose.yml` (`pgvector/pgvector:pg16`, `neo4j:5.26-community`, `redis:7-alpine`), script `infra/postgres/init.sql` e validação dos containers locais + Ollama.
