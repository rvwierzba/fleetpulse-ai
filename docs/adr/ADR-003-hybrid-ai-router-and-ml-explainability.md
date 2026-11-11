# ADR-003: Hybrid AI Router, ML Tabular Explicável (SHAP), Auto-Correção e Human-in-the-Loop

- **Status:** Aceito
- **Data:** 2026-11-11
- **Autores:** Rafael Vinicius Wierzba
- **Relacionado a:** [`.agents/SPEC.md`](../../.agents/SPEC.md), [`.agents/ARCHITECTURE.md`](../../.agents/ARCHITECTURE.md), [`.agents/CONVENTIONS.md`](../../.agents/CONVENTIONS.md)

---

## Contexto

Sistemas de IA em produção falham quando tentam resolver tudo com um único prompt de LLM grande na nuvem:
1. **Custo e latência:** estimar probabilidade numérica de falha de hardware ou violação de SLA via LLM é lento, caro e não-calibrado.
2. **Privacidade e resiliência:** telemetria corporativa de frota nem sempre pode depender exclusivamente de APIs externas; além disso, instabilidades de rede ou limite de cota não podem parar a triagem.
3. **Confiabilidade da saída:** modelos locais menores (como `phi4-mini` ou `llama3.1:8b`) executam rápido na máquina local, mas podem ocasionalmente quebrar o schema JSON ou inventar um `runbook_id` plausível porém inexistente.
4. **Risco operacional:** abrir RMA de troca de placa/notebook ou bloquear uma versão de firmware em lote automaticamente a partir de uma resposta de IA é inaceitável sem supervisão humana.

## Decisão

Separar claramente **Machine Learning preditivo**, **Roteamento Híbrido de IA** e **Guardrails determinísticos**:

1. **ML Supervisionado + SHAP antes do Agente:**
   - Um modelo tabular supervisionado (`LightGBM` ou `scikit-learn`) calcula `rma_risk_score` (0–100), `sla_breach_risk` (0–100) e `predicted_subsystem`, acompanhado dos **Top-3 fatores SHAP** que explicam o risco individual do dispositivo.
   - O pipeline de treino aplica **split temporal + agrupamento por `device_id`** para impedir *data leakage* (**Invariante #5**), comparando sempre o modelo final contra um baseline simples e registrando `PR-AUC`, `F1` e calibração (`Brier Score`).

2. **Hybrid AI Router (Local-First + Circuit Breaker + Fallback Opcional):**
   - Por padrão, o Agente de Triagem executa localmente via **Ollama** (`phi4-mini` para triagem leve e `llama3.1:8b` para raciocínio/tool calling com timeouts e `max_tokens` explícitos).
   - Um **Circuit Breaker** monitora falhas consecutivas/timeouts do provedor local e pode acionar um provedor Cloud configurável apenas quando habilitado por variável de ambiente e dentro das políticas de privacidade.
   - Toda chamada registra `provider`, `model`, `latency_ms`, `cache_hit` e `validation_retries`.

3. **Contrato Estrito (Pydantic v2) + Loop de Auto-Correção:**
   - Toda resposta do agente deve passar por validação de schema em **Pydantic v2** e verificação referencial no **Neo4j** (`runbook_id` e `tech_bulletin_id` devem existir na base oficial — **Invariante #3**).
   - Em erro de schema ou ID alucinado, o erro específico é devolvido ao modelo em um **loop de auto-correção de no máximo 2 tentativas** antes de degradar de forma segura para revisão humana ou DLQ.

4. **Guardrails & Human-in-the-Loop Obrigatório:**
   - Descrições textuais vindas de chamados ou logs passam por isolamento de contexto (delimitadores claros sistema vs dado não confiável) e sanitização contra *prompt injection*.
   - Qualquer alerta com `rma_risk_score >= 70`, recomendação de abertura de RMA/troca de hardware, rollback de firmware em lote ou baixa confiança do agente transiciona obrigatoriamente para **`HUMAN_REVIEW`** antes de chegar a **`RESOLVED`** (**Invariante #6**).

## Alternativas Consideradas

- **Usar LLM para estimar diretamente risco de RMA/SLA:** descartado por ausência de calibração probabilística, falta de explicabilidade auditável por feature (SHAP) e custo computacional desnecessário por evento.
- **Usar exclusivamente API Cloud sem modelo local:** descartado pelo custo em cenários de rajada, dependência de conectividade externa e perda do controle de execução local (*Hybrid AI*).
- **Aceitar JSON best-effort ou corrigir silenciosamente IDs ausentes:** descartado por mascarar alucinações e comprometer a rastreabilidade operacional.

## Consequências

### Positivas
- Cada tecnologia resolve o que faz melhor: ML tabular para probabilidade calibrada + SHAP, Grafo/Vetor para contexto, LLM para síntese estruturada e ação assistida.
- Execução local por padrão reduz custo marginal por alerta e mantém o projeto 100% reproduzível offline via Ollama.
- Decisões críticas nunca são executadas sem aprovação humana auditável.

### Trade-offs e Riscos
- Até 2 retries de auto-correção aumentam a latência de cauda (P95) para casos em que o modelo local erra o formato inicial — mitigado usando prompts enxutos, schemas explícitos e registro da taxa de retry para ajuste contínuo do prompt/modelo.
- Dependência de configuração opcional de API key para testar o fallback Cloud — mitigado permitindo simular queda/circuit breaker do Ollama em testes automatizados e benchmark local.
