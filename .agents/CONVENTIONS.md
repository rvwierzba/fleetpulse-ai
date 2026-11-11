# CONVENTIONS.md — Convenções de Engenharia

## 1. Python (Back-end, Workers, ML e RAG)
- **Tipagem:** type hints obrigatórios em todas as funções públicas, modelos de entrada/saída e contratos de domínio.
- **Modelagem:** usar `Pydantic v2` (`BaseModel`, `ConfigDict`) para fronteiras de API e contratos de resposta estruturada de LLM; `Enum` explícito para estados, tipos de dispositivo, subsistemas e tiers de SLA.
- **Async I/O:** operações de banco (`SQLAlchemy` async), `Redis`, `Neo4j` e chamadas HTTP (`httpx`) devem usar `async/await` com timeouts explícitos configurados.
- **Funções pequenas e coesas:** preferir composição e funções de responsabilidade única com *early return* em vez de aninhamentos profundos.
- **Sem duplicação:** lógicas compartilhadas (ex.: normalização de telemetria, cálculo de métricas de latência, clientes de LLM) ficam em módulos dedicados e reutilizáveis.
- **Comentários e docstrings:** docstrings concisas em classes/funções públicas; comentários apenas para explicar o **porquê** de trade-offs, limites ou invariantes não óbvias.
- **Qualidade e Testes:** `ruff` para lint/formatação e `pytest` (`pytest-asyncio`) para testes de domínio, máquina de estados, guardrails e endpoints.

## 2. Front-end (Vue 3 + TypeScript)
- Usar `<script setup lang="ts">` e Composition API.
- Tipagem estrita em TypeScript (proibido `any` sem justificativa documentada).
- Componentes focados em responsabilidade única; chamadas HTTP e assinatura `EventSource` (SSE) isoladas em `services/` ou `composables/`.
- Estilização com Tailwind CSS mantendo interface limpa e orientadas à tomada de decisão operacional (estado, SHAP, grafo e aprovação humana).

## 3. Segurança & Engenharia de IA
- **Nunca** versionar chaves de API ou arquivos `.env` reais.
- **Sempre** separar instruções de sistema de texto vindo do usuário/dispositivo (delimitadores claros + sanitização contra *prompt injection*).
- **Sempre** definir `max_retries`, `timeout_seconds` e `max_tokens` explícitos em chamadas de LLM.
- **Sempre** registrar `provider`, `model`, `latency_ms`, `cache_hit` e `validation_retries` para observabilidade.

## 4. Git & Fluxo de Sprints
- Padrão **Conventional Commits**:
  - `feat:` nova capacidade funcional
  - `docs:` documentação, `.agents/` e ADRs
  - `fix:` correção de bug
  - `refactor:` melhoria interna sem alterar contrato
  - `test:` cobertura ou ajustes de teste
  - `bench:` scripts e resultados de benchmark/carga
  - `chore:` dependências, Docker e configuração
- Ao concluir cada sprint, atualizar `.agents/CHANGELOG.md` e validar se `.agents/ARCHITECTURE.md` e `.agents/SPEC.md` continuam sincronizados com o código.
