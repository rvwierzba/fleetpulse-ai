# SPEC.md — Especificação Oficial do FleetPulse AI

## 1. Visão do Produto

O **FleetPulse AI** é uma plataforma distribuída de **telemetria proativa, triagem inteligente de alertas e proteção de SLA** para frotas corporativas de **notebooks e smartphones** (operações de Device-as-a-Service, suporte técnico N2/N3 e garantia B2B).

Em vez de reagir quando o usuário já está sem equipamento ou quando um lote inteiro falha após uma atualização de firmware/BIOS, o sistema ingere eventos de telemetria em rajada, calcula risco de falha e risco de violação de SLA com **Machine Learning explicável**, investiga correlações em **RAG Híbrido (Grafo + Vetor + Cache Semântico)** e executa um **Agente de Triagem** com validação rígida e aprovação **Human-in-the-Loop**.

---

## 2. Domínio & Contratos Principais

### 2.1 Equipamentos Monitorados
- `device_type`: `NOTEBOOK` | `SMARTPHONE`
- `subsystem`: `BATTERY_POWER` | `STORAGE_NVME` | `THERMAL_BOARD` | `FIRMWARE_OS` | `DISPLAY_PERIPHERAL`
- Atributos mínimos do ativo: `device_id`, `device_type`, `model_code`, `batch_id`, `firmware_version`, `sla_tier`, `age_days`.

### 2.2 Tiers de SLA Corporativo
| Tier | Primeira Resposta | Resolução / Troca | Impacto no Score de Prioridade |
|---|---|---|---|
| `PLATINUM` | 4h | 24h | Peso máximo de urgência |
| `GOLD` | 8h | 48h | Peso intermediário |
| `STANDARD` | 24h | 72h | Peso padrão |

### 2.3 Máquina de Estados de um Alerta (Imutável)
Todo evento aceito na ingestão possui um ciclo de vida persistido no PostgreSQL:

1. `RECEIVED` — Evento validado na API e publicado na fila com `Idempotency-Key`.
2. `DEDUPED` — Verificado contra janela de deduplicação (eventos duplicados do mesmo `device_id` + `error_code` dentro da janela são marcados como `IGNORED_DUPLICATE`).
3. `ML_SCORED` — Modelo supervisionado calculou `rma_risk_score` (0–100), `sla_breach_risk` (0–100), `predicted_subsystem` e contribuições SHAP.
4. `CONTEXT_RETRIEVED` — Consulta em Cache Semântico → (em *miss*) Grafo Neo4j + Busca Vetorial `pgvector` retornaram boletins técnicos, incidentes correlatos no mesmo lote/firmware e runbooks elegíveis.
5. `AGENT_DIAGNOSED` — Roteador Hybrid AI (Ollama local por padrão, fallback opcional cloud) produziu diagnóstico estruturado + recomendação de ação.
6. `SCHEMA_VALIDATED` — Saída JSON validada via Pydantic **e** referências (`runbook_id`, `bulletin_id`) confirmadas contra o Neo4j (com loop de auto-correção até 2 tentativas em caso de erro).
7. Estado de decisão:
   - `HUMAN_REVIEW` — Obrigatório quando `rma_risk_score >= 70`, quando há recomendação de troca de peça (RMA) / rollback de firmware em lote, ou quando há baixa confiança do agente.
   - `AUTO_RECOMMENDED` — Alertas de baixo risco com runbook preventivo não-destrutivo e alta confiança.
8. `RESOLVED` — Operador aprovou/ajustou ação ou alerta preventivo encerrado com trilha de auditoria.
9. `FAILED_DLQ` — Movido para Dead Letter Queue após esgotar retentativas de worker.

---

## 3. Requisitos por Pilar Técnico (Critérios de Aceite)

### 3.1 System Design (Sprints 1 e 5)
- `POST /v1/alerts` exige header `Idempotency-Key` e responde `202 Accepted` em baixa latência (sem esperar ML ou LLM).
- Rate limiting por `source_id` na camada de API usando Redis.
- Processamento assíncrono via fila no Redis com retry exponencial e encaminhamento explícito para DLQ.
- Streaming de progresso em tempo real via **Server-Sent Events (`GET /v1/alerts/{id}/stream`)**.
- Simulador de carga ("Tempestade de Firmware") medindo throughput, P50/P95/P99 e taxa de acerto de cache.

### 3.2 Machine Learning na Prática (Sprint 2)
- Pipeline reproduzível de ingestão, *feature engineering* e treino com split **temporal e agrupado por `device_id`** (proibido *data leakage*).
- Comparação documentada entre baseline simples e modelo final (`LightGBM` ou `HistGradientBoosting` / `RandomForest`).
- Métricas registradas em artefato versionado (`PR-AUC`, `F1`, `Brier Score` / calibração, matriz de confusão).
- Explicabilidade local com **SHAP** retornando Top-3 fatores que explicam o risco de cada dispositivo.

### 3.3 RAG Híbrido & Cache Semântico (Sprint 3)
- **Neo4j:** grafo relacionando `DeviceType → Model → Batch → Subsystem → FirmwareVersion → ErrorCode → TechBulletin → Runbook`.
- **`pgvector`:** chunks de boletins técnicos, notas de firmware e post-mortems com embeddings locais via Ollama (`nomic-embed-text`).
- **Cache Semântico:** consulta por similaridade de cosseno (threshold configurável, ex. `>= 0.90`) com TTL e métricas de *hit/miss*.
- **Text-to-Cypher controlado:** geração de leitura para perguntas de impacto de frota, bloqueando qualquer cláusula mutável (`CREATE`, `MERGE`, `DELETE`, `SET`, `DROP`).

### 3.4 AI System Design & Agentes (Sprint 4)
- **Hybrid AI Router:** tenta modelo local no Ollama (`phi4-mini` ou `llama3.1:8b`) e aciona fallback apenas em falha/circuit breaker aberto ou baixa confiança configurada.
- **Auto-correção de contrato:** erro de validação Pydantic ou `runbook_id` inexistente no grafo é devolvido ao LLM para correção (máximo 2 retries).
- **Guardrails:** sanitização contra *prompt injection* em descrições livres vindas de chamados/logs de usuários; limite explícito de passos e ferramentas do agente.

### 3.5 Front-end Observável (Sprint 5)
- Dashboard **Vue 3 + TypeScript + Tailwind** exibindo:
  - Fluxo ao vivo da máquina de estados via SSE;
  - Painel de decisão com **SHAP** + trilha do **Grafo de Causa Raiz** + **Aprovação Human-in-the-Loop**;
  - Painel de observabilidade de IA e System Design (latência, cache hit-rate, uso local vs fallback, DLQ).
