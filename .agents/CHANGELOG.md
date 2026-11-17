# CHANGELOG.md — Histórico do FleetPulse AI

## [Unreleased]

### Sprint 4 — AI System Design, Agentes, Auto-Correção & Guardrails (Concluída)
- Módulo `backend/app/agents/` estruturado com contratos Pydantic v2 (`schemas.py`), guardrails contra prompt injection (`prompt_guard.py`), roteador inteligente com Circuit Breaker (`router.py`), motor de decisão Human-in-the-Loop (`decision.py`) e Agente de Triagem com loop de auto-correção (`triage_agent.py`).
- **Contrato Pydantic Estrito (`TriageDiagnosis`):** Saída estruturada via JSON Mode com `extra="forbid"`, tipos garantidos, pontuação de confiança limitada matematicamente entre 0.0 e 1.0, e ações operacionais tipadas via Enum (`REMOTE_PATCH`, `DISPATCH_TECH`, `REPLACE_HARDWARE`, `UPDATE_FIRMWARE`, `ESCALATE_TIER2`).
- **Guardrails contra Prompt Injection:** Sanitização de entradas livres de usuários e logs de telemetria, neutralização de instruções maliciosas (`ignore previous instructions`, `system override`, `<|im_start|>`) e isolamento de contexto em delimitadores invioláveis (`### UNTRUSTED_ALERT_DATA_START ###`).
- **Hybrid AI Router com Circuit Breaker:** Roteamento primário para modelo local no Ollama (`phi4-mini:latest`) com transição automática para fallback (`llama3.1:8b`) após 3 falhas consecutivas, suporte a estados `CLOSED`, `OPEN` e `HALF_OPEN`, e rastreamento de métricas em tempo de execução (latência em ms, contagem de tokens).
- **Loop de Auto-Correção (Self-Correction):** Interceptação imediata de erros de validação Pydantic ou de IDs de Runbooks alucinados não existentes no Neo4j (Invariante Arquitetural #3). O erro cirúrgico é injetado no prompt de correção permitindo ao modelo consertar a resposta em até 2 tentativas sem derrubar o sistema.
- **Portão de Decisão Human-in-the-Loop (Invariante Arquitetural #6):** Transição mandatória para `HUMAN_REVIEW` para alertas com risco de RMA >= 0.70, substituição física de peças, atualizações em lote de firmware ou confiança do agente < 0.75; apenas ações remotas de alta certeza sem dano físico transitam para `AUTO_RECOMMENDED`.
- **Evolução da Máquina de Estados:** Extensão do pipeline no worker assíncrono avançando por `CONTEXT_RETRIEVED -> AGENT_DIAGNOSED -> SCHEMA_VALIDATED -> HUMAN_REVIEW / AUTO_RECOMMENDED` com persistência no PostgreSQL e publicação em tempo real via SSE.
- Cobertura com `10` novos testes unitários e de contrato em `test_agent.py` e atualização da suíte de worker, totalizando testes verdes com validação de lint e formatação no `ruff`.

### Sprint 3 — RAG Híbrido (Neo4j + pgvector + Cache Semântico) (Concluída)
- Módulo `backend/app/rag/` estruturado com schemas de domínio (`RunbookSummary`, `TechBulletinSummary`, `DocumentChunk`, `GraphContext`, `HybridRAGResult`), cliente Neo4j assíncrono (`graph_service.py`), cliente de embeddings locais (`embeddings.py`), busca vetorial no PostgreSQL (`vector_service.py`), cache semântico de 2 níveis (`semantic_cache.py`), seed de dados (`seed_data.py`) e orquestrador híbrido (`orchestrator.py`).
- Grafo de Conhecimento no Neo4j com constraints de unicidade, mapeando topologia completa de hardware (`NOTEBOOK`, `SMARTPHONE`), modelos ThinkPad e Motorola, lotes de manufatura, versões de BIOS/firmware, códigos de erro e procedimentos operacionais padronizados (Runbooks).
- Base vetorial no PostgreSQL com extensão `pgvector`, armazenando manuais e boletins técnicos com embeddings gerados localmente pelo Ollama (`nomic-embed-text:latest`, 768 dimensões) e busca por distância de cosseno.
- Cache Semântico de dois níveis combinando Redis L1 (chave determinística em memória para acertos instantâneos) e pgvector L2 (similaridade de cosseno com threshold `>= 0.90` e TTL configurável) para blindar a infraestrutura contra rajadas de incidentes repetidos na frota.
- Validador Text-to-Cypher estritamente Read-Only (Invariante Arquitetural #4), bloqueando comandos de mutação (`CREATE`, `MERGE`, `DELETE`, `SET`, `DROP`) e permitindo apenas leitura segura.
- Validação determinística de existência de IDs de Runbooks e Boletins contra o Neo4j (Invariante Arquitetural #3).
- Integração no worker assíncrono avançando o estado do alerta de `ML_SCORED` para `CONTEXT_RETRIEVED`, persistindo `rag_context`, `matched_runbook_id`, `matched_bulletin_id` e `semantic_cache_hit` no PostgreSQL e emitindo eventos via SSE.
- `24` testes automatizados no `pytest` cobrindo o fluxo completo de ponta a ponta sem falhas.

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
