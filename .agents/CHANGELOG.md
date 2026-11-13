# CHANGELOG.md — Histórico do FleetPulse AI

## [Unreleased]

### Sprint 2 — Machine Learning na Prática (Risco de RMA & SLA + SHAP) (Concluída)
- Módulo `backend/app/ml/` estruturado com schemas (`SHAPFactor`, `MLScoreResult`), gerador de telemetria realista (`dataset_generator.py`), pipeline de treino com anti-leakage (`train.py`) e serviço de inferência em tempo real com SHAP (`service.py`).
- Prevenção estrita de data leakage: divisão temporal (70% inicial para treino, 30% final para teste) combinada com agrupamento estritamente disjunto por `device_id` (337 dispositivos de treino, 92 de teste, zero sobreposição).
- Avaliação com baselines e métricas adequadas a desbalanceamento tabular: `DummyClassifier` (PR-AUC 0.3330), `LogisticRegression` (PR-AUC 0.6051), `RandomForestClassifier` (PR-AUC 0.6535, ROC-AUC 0.7712, Brier score 0.1610).
- Explicabilidade com `shap.TreeExplainer` extraindo os 3 principais fatores de risco com sinal de impacto e gerando justificativas humanas legíveis em português.
- Extensão do schema no PostgreSQL (`alerts.rma_risk_score`, `alerts.sla_breach_risk`, `alerts.predicted_subsystem`, `alerts.shap_factors`) e transição automática no worker (`DEDUPED -> ML_SCORED`) com broadcast via SSE.
- `18` testes unitários e de integração no `pytest` cobrindo gerador, split anti-leakage, inferência SHAP, worker e SSE.

### Sprint 1 — System Design & Máquina de Estados Assíncrona (Concluída)
- Estruturação do pacote `backend/` (`pyproject.toml`, `FastAPI`, `Pydantic`, `SQLAlchemy Async`, `redis.asyncio`, `ruff`, `pytest`).
- Domínio e máquina de estados imutável (`DeviceType`, `Subsystem`, `SLATier`, `AlertStatus`, `VALID_TRANSITIONS`) + persistência transacional no PostgreSQL (`alerts` e `alert_events`).
- Camada Redis (`enqueue_alert`, Rate Limiter por `source_id`, `Idempotency-Key`, trava atômica de deduplicação `SET NX EX`, Sorted Set de retry exponencial, Dead Letter Queue e canal Pub/Sub por alerta).
- Endpoints `POST /v1/alerts` (`202 Accepted`), `GET /v1/alerts/{alert_id}`, `GET /v1/alerts/{alert_id}/stream` (SSE sem perda de eventos entre PostgreSQL e Redis) e `/health`.
- Worker assíncrono (`backend/app/workers/alert_worker.py`) com deduplicação, backoff exponencial e encaminhamento para DLQ, coberto por `14` testes automatizados (`pytest`) e smoke test real contra Docker.

### Sprint 0 — Spec-Driven Development & Arquitetura Base (Concluída)
- **Passo 0.1:** Criação independente do repositório em `C:\DEV\fleetpulse-ai` (`git init -b main`), `.gitignore` e estrutura `.agents/` (`README.md`, `SPEC.md`, `ARCHITECTURE.md`, `CONVENTIONS.md`, `ROADMAP.md`, `skills/`).
- **Passo 0.2:** Registro dos 3 ADRs iniciais em `docs/adr/` (`ADR-001` a `ADR-003`), criação de `README.md`, `.env.example`, `docker-compose.yml` (`pgvector/pgvector:pg16`, `neo4j:5.26-community`, `redis:7-alpine`), script `infra/postgres/init.sql` e validação dos containers locais + Ollama.
