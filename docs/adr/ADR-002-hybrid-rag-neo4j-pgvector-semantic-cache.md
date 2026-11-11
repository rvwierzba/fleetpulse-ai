# ADR-002: RAG Híbrido (Neo4j + pgvector + Cache Semântico) e Text-to-Cypher Read-Only

- **Status:** Aceito
- **Data:** 2026-11-11
- **Autores:** Rafael Vinicius Wierzba
- **Relacionado a:** [`.agents/SPEC.md`](../../.agents/SPEC.md), [`.agents/ARCHITECTURE.md`](../../.agents/ARCHITECTURE.md)

---

## Contexto

Alertas em frotas corporativas de notebooks e smartphones frequentemente têm causa estrutural compartilhada: um mesmo lote de fabricação (`Batch`), uma versão recém-distribuída de firmware/BIOS (`FirmwareVersion`), um subsistema específico (`Subsystem`) e códigos de erro correlacionados (`ErrorCode`).

Um pipeline de **RAG puramente vetorial** apresenta duas limitações críticas nesse domínio:
1. **Cegueira relacional:** embeddings de texto capturam similaridade semântica entre descrições de incidentes, mas não respondem com precisão determinística a travessias estruturais multi-hop (ex.: *"qual runbook oficial se aplica ao erro `ERR_NVME_TIMEOUT` especificamente na combinação Modelo X + Firmware Y?"* ou *"quantos dispositivos do mesmo lote estão afetados?"*).
2. **Custo e latência repetitiva em rajadas:** quando 80 equipamentos disparam sintomas semanticamente equivalentes na mesma hora, reexecutar busca completa e síntese de LLM para cada alerta desperdiça GPU/CPU local e aumenta o P95.

## Decisão

Adotar uma arquitetura de **RAG Híbrido em três camadas** combinando **Cache Semântico**, **Grafo de Conhecimento (`Neo4j`)** e **Busca Vetorial (`PostgreSQL + pgvector`)**:

1. **Grafo de Topologia e Conhecimento (`Neo4j`):**
   - Modelagem explícita das entidades e relações do domínio:
     `DeviceType → Model → Batch → Subsystem → FirmwareVersion → ErrorCode → TechBulletin → Runbook`
   - Permite:
     - Recuperar boletins e runbooks exatos ligados ao contexto técnico do alerta.
     - Identificar incidentes correlatos no mesmo lote ou firmware.
     - Validar determinísticamente se `runbook_id` e `tech_bulletin_id` sugeridos pelo agente existem e são elegíveis.

2. **Busca Vetorial em Boletins e Post-Mortems (`PostgreSQL + pgvector`):**
   - Armazenamento de chunks de boletins técnicos, release notes de firmware e post-mortems históricos com embeddings gerados localmente via **Ollama (`nomic-embed-text`)**.
   - Complementa o grafo quando o sintoma chega com descrição textual livre de chamado N1/N2 ou sem mapeamento direto prévio de `ErrorCode`.

3. **Cache Semântico (`Redis L1` + `pgvector`):**
   - Antes de consultar Neo4j + busca vetorial completa + LLM, o pipeline consulta o Cache Semântico usando embedding da assinatura normalizada do incidente (similaridade de cosseno com threshold configurável, padrão `>= 0.90`, e TTL explícito).
   - Em *cache hit*, reutiliza o contexto/diagnóstico cacheado elegível e registra métricas explícitas (`cache_hit=true`) para observabilidade; o score de ML/SHAP e a verificação de regras de risco do dispositivo continuam sendo avaliados por dispositivo.

4. **Text-to-Cypher Controlado (Somente Leitura):**
   - Consultas exploratórias de impacto na frota geradas por LLM passam obrigatoriamente por validador sintático/whitelist que bloqueia instruções de escrita ou múltiplas queries (`CREATE`, `MERGE`, `DELETE`, `SET`, `REMOVE`, `DROP`, `CALL dbms...`).

## Alternativas Consideradas

- **RAG vetorial puro (`pgvector` isolado):** descartado por não preservar relações exatas entre versão de firmware, lote e runbook oficial, além de não permitir validação estrutural determinística das referências retornadas pelo LLM.
- **Banco vetorial dedicado (Qdrant/Milvus) separado do PostgreSQL:** descartado para evitar manter mais um serviço de persistência e sincronização transacional. Como `PostgreSQL` já é o banco oficial da máquina de estados e auditoria, a extensão `pgvector` consolida dados relacionais, vetores e cache semântico com garantias ACID.
- **Cache apenas por chave exata no Redis:** insuficiente, pois logs de dispositivos variam em timestamps, IDs de série e pequenas diferenças textuais mantendo o mesmo problema técnico. O cache semântico captura equivalência mesmo com variação de texto.

## Consequências

### Positivas
- Recuperação precisa combinando contexto relacional exato (Neo4j) e busca semântica em texto livre (`pgvector`).
- Redução expressiva de chamadas ao LLM em tempestades de alertas via Cache Semântico.
- Proteção direta das **Invariantes #3** (checagem oficial de IDs) e **#4** (Text-to-Cypher estritamente read-only).

### Trade-offs e Riscos
- **Risco de falso positivo no Cache Semântico:** se o threshold de cosseno for baixo demais, um alerta diferente pode receber contexto errado. Mitigado com threshold conservador (`>= 0.90`), filtro por metadados críticos (`device_type`, `subsystem`) e TTL configurável.
- **Custo operacional de manter PostgreSQL + Neo4j sincronizados:** mitigado mantendo o Neo4j focado em topologia/conhecimento técnico e o PostgreSQL como fonte de verdade transacional de alertas e eventos.
