# Skill: review-pr

Checklist técnico de revisão antes de fechar um commit importante ou mergear uma entrega.

## Checklist de Verificação

### 1. System Design & Resiliência
- [ ] A rota de ingestão continua não-bloqueante (sem ML/LLM síncrono)?
- [ ] A operação é idempotente em caso de retry ou alerta duplicado?
- [ ] Todas as chamadas externas (Ollama, Neo4j, Redis, Postgres, Cloud LLM) possuem timeout explícito?
- [ ] Falhas no worker possuem tratamento claro e caminho de DLQ sem engolir exceções silenciosamente?

### 2. Machine Learning & Dados
- [ ] Há risco de *data leakage* entre treino e validação/teste?
- [ ] Transformadores/scalers foram ajustados apenas no conjunto de treino?
- [ ] As métricas registradas refletem o desbalanceamento real do problema (ex.: PR-AUC e F1 além de acurácia)?

### 3. RAG, Agentes & Segurança
- [ ] Saídas de LLM são validadas contra schema estrito e IDs existentes no banco/grafo?
- [ ] Queries geradas por LLM passam por validação read-only?
- [ ] Entradas textuais de dispositivos/usuários estão isoladas contra *prompt injection*?
- [ ] Ações de alto risco exigem `HUMAN_REVIEW`?

### 4. Qualidade de Código
- [ ] Zero segredos hardcoded no código.
- [ ] Código limpo, tipado, sem duplicação e com testes passando após a última edição.
