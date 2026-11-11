# Skill: implement-spec

Protocolo inspirado em Spec-Driven Development para implementar qualquer etapa ou sprint do FleetPulse AI sem cair em *vibe coding*.

## Passos obrigatórios

1. **Ler contexto antes de agir:**
   - Verificar os requisitos da sprint em `.agents/SPEC.md`.
   - Conferir fluxos e invariantes em `.agents/ARCHITECTURE.md` e regras em `.agents/CONVENTIONS.md`.
2. **Quebrar em entregas pequenas e testáveis:**
   - Definir primeiro os contratos de dados (schemas Pydantic, enums de estado, interfaces).
   - Listar quais invariantes arquiteturais precisam ser protegidas nessa entrega.
3. **Implementar com testes junto:**
   - Escrever testes de unidade e contrato cobrindo caminho feliz, idempotência/duplicação e falhas esperadas.
   - Evitar lógica duplicada entre API, worker e módulos de IA.
4. **Verificar na prática:**
   - Executar os testes (`pytest` / `npm test`) e verificar comportamento real em runtime/Docker.
5. **Fechar o ciclo:**
   - Atualizar `.agents/CHANGELOG.md` e, se houve mudança de design ou decisão relevante, registrar/atualizar ADR em `docs/adr/`.
