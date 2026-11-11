# ROADMAP.md — Plano de Sprints, Aprendizado Prático & Divulgação

## 1. Pilares de Engenharia & Referências do Projeto

Este projeto consolida cinco pilares práticos em um único sistema distribuído para frotas de **notebooks e smartphones**:

1. **RAG Híbrido (Grafo + Vetor + Cache + Text-to-Query)** — Ref.: Erick Wendel (*"RAG na Prática: Como Ensinar uma IA a Buscar Respostas no Seu Banco de dados"*, `yPz8LDcAcdA`).
2. **Workflow com AI Agents & Spec-Driven Development** — Ref.: Attekita Dev (*"Meu workflow para desenvolver com IA: da ideia aos agentes"*, `paXHXZyRSsM`).
3. **System Design Clássico (Filas, Idempotência, Cache, Carga)** — Ref.: Lucas Montano (*"tu deveria estudar apenas System Design"*, `16IYx0CekVc`).
4. **AI System Design (Máquina de Estados, SSE, Structured Output + Auto-Correção, Fallback)** — Ref.: Augusto Galego (*"System Design para Aplicações com IA"*, `2Ls_uc0fo-Y`).
5. **Machine Learning na Prática (Pipeline supervisionado, SHAP, anti-leakage e versionamento)**.

---

## 2. Ambiente Local Validado (Máquina de Desenvolvimento)

- **Stack escolhida:** Python (`FastAPI` + Workers + ML + RAG) + `Vue 3` (`TypeScript` + `Tailwind CSS`)
- **Ferramentas disponíveis:** Git `2.56`, Python `3.14.6`, Node `v24.16.0`, `.NET SDK 10.0.303`, Docker `29.5.3`
- **Ollama `0.40.16` (modelos já disponíveis localmente):**
  - `nomic-embed-text:latest` (embeddings locais)
  - `phi4-mini:latest` (modelo leve e rápido para triagem local)
  - `llama3.1:8b` (modelo local para raciocínio/tool calling)
  - `qwen2.5-coder:7b` e `qwen2.5-coder:1.5b-base`
- **Repositório alvo:** `https://github.com/rvwierzba/fleetpulse-ai` (push via `git` remoto; `gh` CLI não instalado).

---

## 3. Roadmap em 6 Sprints (Modo Live Passo a Passo)

### Sprint 0 — Spec-Driven Development, `.agents/`, ADRs & Infra Base
- **Passo 0.1 (Concluído):** criação isolada em `C:\DEV\fleetpulse-ai`, `git init -b main`, `.gitignore`, `.agents/` (`README.md`, `SPEC.md`, `ARCHITECTURE.md`, `CONVENTIONS.md`, `CHANGELOG.md`, `ROADMAP.md`, `skills/`).
- **Passo 0.2 (Concluído):** criação dos 3 primeiros ADRs em `docs/adr/`, `README.md` completo, `.env.example`, `docker-compose.yml` (`PostgreSQL + pgvector`, `Neo4j`, `Redis`), validação dos containers e primeiro commit local (pronto para `git push` no GitHub).

### Sprint 1 — System Design & Máquina de Estados Assíncrona
- API `FastAPI` com `POST /v1/alerts` (`202 Accepted`), `Idempotency-Key` no Redis, Rate Limiter, fila assíncrona no Redis, Worker com retry exponencial e **Dead Letter Queue (DLQ)**.
- Persistência da máquina de estados no PostgreSQL (`alert_events`) e streaming de progresso em tempo real via **SSE (`GET /v1/alerts/{id}/stream`)**.
- Testes unitários e de contrato (`pytest`).

### Sprint 2 — Machine Learning na Prática (Risco de RMA & SLA + SHAP)
- Gerador/dataset realista de telemetria de **notebooks e smartphones** (ciclos de bateria, temperatura, erros S.M.A.R.T./NVMe, kernel panics, versão de firmware, histórico e tier de SLA).
- Pipeline de treino sem *data leakage* (split temporal + agrupamento por `device_id`), comparação baseline vs modelo final (`LightGBM` / `scikit-learn`), métricas (`PR-AUC`, `F1`, calibração) e explicabilidade local com **SHAP** servida pelo worker.

### Sprint 3 — RAG Híbrido (Neo4j + pgvector + Cache Semântico)
- Modelagem do grafo no **Neo4j** (`DeviceType → Model → Batch → Subsystem → FirmwareVersion → ErrorCode → TechBulletin → Runbook`).
- Ingestão de boletins técnicos e notas no **`pgvector`** com `nomic-embed-text` (Ollama).
- **Cache Semântico** (similaridade de cosseno + TTL) com métricas de *hit/miss* e **Text-to-Cypher** somente leitura com validação por whitelist.

### Sprint 4 — AI System Design, Agentes, Auto-Correção & Guardrails
- **Hybrid AI Router** (Ollama local primeiro + Circuit Breaker + fallback configurável para Cloud) medindo latência e custo evitado.
- **Agente de Triagem** com *tool calling* controlado, saída JSON estrita (Pydantic) + **loop de auto-correção** (até 2 tentativas se o modelo errar schema ou citar `runbook_id`/`bulletin_id` inexistente no Neo4j).
- Guardrails contra *prompt injection* + regra obrigatória de `HUMAN_REVIEW` para casos críticos.

### Sprint 5 — Dashboard Vue 3, Simulador de Carga & Documentação Final
- Interface **Vue 3 + TypeScript + Tailwind** com acompanhamento ao vivo via SSE, painel de explicabilidade (SHAP + trilha do grafo Neo4j) e fluxo de aprovação **Human-in-the-Loop**.
- **Simulador "Tempestade de Firmware"** (`benchmarks/`) disparando rajadas de alertas para coletar métricas reais (P50/P95, throughput, economia do Cache Semântico, estabilidade da fila/DLQ).
- Atualização final do `README.md` com prints, métricas medidas e fechamento do `CHANGELOG.md`.

---

## 4. Plano Editorial de Posts no LinkedIn (Sem Cara de IA)

Todos os posts seguem as regras de [skills/linkedin-post.md](skills/linkedin-post.md): linguagem natural de engenheiro, foco em dor real + trade-off + evidência real da máquina, e link direto para `https://github.com/rvwierzba/fleetpulse-ai`.

1. **Post #1 (Fim da Sprint 0):** *Por que comecei meu novo projeto de IA escrevendo especificações e regras de arquitetura antes de abrir um único arquivo Python* — mostrando `.agents/`, ADRs e como evitar o caos do *vibe coding* (com print da estrutura/diagrama e link do repo).
2. **Post #2 (Fim da Sprint 1):** *Por que nunca se deve chamar LLM direto dentro de um endpoint HTTP* — explicando na prática Idempotency-Key, fila no Redis, DLQ, máquina de estados persistida e SSE funcionando ao vivo.
3. **Post #3 (Fim da Sprint 2):** *Nem tudo em sistema de IA precisa de LLM (e como o ML clássico + SHAP economiza custo e latência)* — mostrando *data leakage* evitado, métricas reais de treino e os fatores SHAP explicando risco de falha em notebooks e smartphones.
4. **Post #4 (Fim da Sprint 3):** *Onde o RAG vetorial puro erra — e por que juntei Neo4j (Grafo) + pgvector + Cache Semântico* — mostrando um caso de erro após atualização de firmware onde a relação no grafo resolveu e o cache cortou chamadas repetidas ao Ollama.
5. **Post #5 (Fim da Sprint 4):** *O que acontece quando o modelo local alucina um JSON ou inventa um Runbook* — explicando Hybrid AI (Ollama local ↔ fallback), loop de auto-correção, guardrails e *Human-in-the-Loop*.
6. **Post #6 (Fim da Sprint 5):** *Coloquei uma tempestade de alertas de frota pra bater no meu sistema local — os números reais de P95, cache hit-rate e o dashboard em Vue 3* — fechamento completo com vídeo/print do sistema rodando ponta a ponta.
