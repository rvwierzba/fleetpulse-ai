# ADR-001: Ingestão Não-Bloqueante, Idempotência e Máquina de Estados Assíncrona

- **Status:** Aceito
- **Data:** 2026-11-11
- **Autores:** Rafael Vinicius Wierzba
- **Relacionado a:** [`.agents/SPEC.md`](../../.agents/SPEC.md), [`.agents/ARCHITECTURE.md`](../../.agents/ARCHITECTURE.md)

---

## Contexto

O **FleetPulse AI** monitora frotas corporativas de notebooks e smartphones sujeitas a rajadas de eventos de telemetria (por exemplo, dezenas ou centenas de alertas simultâneos após uma atualização defeituosa de firmware ou BIOS — cenário de *"tempestade de firmware"*).

Esses alertas precisam passar por etapas potencialmente lentas ou sujeitas a falhas transitórias:
1. Scoring de risco de RMA e violação de SLA com Machine Learning + explicabilidade SHAP.
2. Consultas híbridas de contexto (Cache Semântico, Grafo Neo4j e busca vetorial `pgvector`).
3. Diagnóstico estruturado via LLM local (Ollama) ou fallback Cloud, com eventual retry de validação.

Se qualquer uma dessas etapas rodar de forma síncrona dentro da requisição HTTP de ingestão:
- O tempo de resposta da API degrada sob carga e estoura timeouts nos coletores de borda.
- Retentativas dos dispositivos/coletores criam alertas duplicados e desperdiçam inferência.
- Falhas transitórias no Ollama ou no banco de grafo derrubam o recebimento da telemetria, violando SLAs corporativos (`PLATINUM`: 4h/24h, `GOLD`: 8h/48h, `STANDARD`: 24h/72h).

## Decisão

Adotar uma arquitetura orientada a eventos com **ingestão não-bloqueante**, **idempotência explícita** e **máquina de estados auditável**:

1. **Fronteira HTTP (`FastAPI`):**
   - `POST /v1/alerts` exige o header `Idempotency-Key`.
   - Aplica **Rate Limiting** por `source_id` e **Idempotency Guard** no **Redis**.
   - Valida o contrato de entrada via **Pydantic v2**, persiste o estado inicial `RECEIVED` no **PostgreSQL**, publica o job na fila assíncrona do Redis e responde **`202 Accepted`** imediatamente (sem executar ML, Neo4j, `pgvector` ou LLM).

2. **Processamento Assíncrono & Resiliência (`Worker` + `Redis`):**
   - Workers consomem a fila do Redis com política de **retry exponencial** para falhas transitórias.
   - Ao esgotar as tentativas configuradas, o alerta transiciona explicitamente para **`FAILED_DLQ`** e é encaminhado para uma **Dead Letter Queue (DLQ)** no Redis para inspeção e reprocessamento seguro.

3. **Máquina de Estados Persistida e Auditável (`PostgreSQL`):**
   - Toda transição ocorre por um repositório dedicado de máquina de estados e grava um registro imutável em `alert_events`:
     `RECEIVED` → `DEDUPED` (ou `IGNORED_DUPLICATE`) → `ML_SCORED` → `CONTEXT_RETRIEVED` → `AGENT_DIAGNOSED` → `SCHEMA_VALIDATED` → (`HUMAN_REVIEW` | `AUTO_RECOMMENDED`) → `RESOLVED` (ou `FAILED_DLQ`).
   - Uma janela de deduplicação no Redis evita reprocessamento de rajadas idênticas (`device_id` + `error_code`) dentro da janela configurada, encerrando duplicatas como `IGNORED_DUPLICATE`.

4. **Observabilidade em Tempo Real (`SSE`):**
   - Cada transição de estado publica um evento no **Redis Pub/Sub**, consumido pelo BFF FastAPI e entregue ao front-end Vue 3 via **Server-Sent Events (`GET /v1/alerts/{id}/stream`)**.

## Alternativas Consideradas

- **Processamento síncrono no endpoint HTTP:** descartado por acoplar a disponibilidade da ingestão à latência de inferência do LLM e causar timeouts em rajadas.
- **Apache Kafka / RabbitMQ desde a Sprint 0:** descartado neste estágio para evitar sobrecarga operacional no ambiente local. O Redis já resolve fila/DLQ, idempotência, rate limiting e Pub/Sub em um único componente leve, mantendo a camada de fila isolada atrás de abstração caso seja necessária troca futura.
- **WebSockets em vez de SSE:** descartado para o acompanhamento de alertas por ser bidirecional sem necessidade; o fluxo de progresso é unidirecional (servidor → dashboard), onde SSE sobre HTTP padrão oferece reconexão nativa (`EventSource`) e menor complexidade.

## Consequências

### Positivas
- Latência previsível e baixa na rota `POST /v1/alerts`, preservando a **Invariante #1** (ingestão não-bloqueante).
- Trilha completa de auditoria para cada alerta (**Invariante #2**), permitindo depurar exatamente em qual etapa um evento parou ou falhou.
- Proteção contra rajadas duplicadas e retries de rede sem perder eventos reais.

### Trade-offs e Riscos
- Consistência eventual entre o aceite HTTP (`202`) e a conclusão do diagnóstico no worker — mitigada pelo streaming ao vivo via SSE.
- Redis passa a ser dependência crítica para ingestão e filas — mitigado com persistência AOF habilitada no Docker e healthchecks explícitos.
