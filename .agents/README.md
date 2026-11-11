# .agents — Contexto e Especificações do FleetPulse AI

Este diretório é a fonte única de verdade de engenharia para agentes de IA e desenvolvedores humanos trabalhando no **FleetPulse AI**.

## Ordem obrigatória de leitura antes de codar

1. [SPEC.md](SPEC.md) — Requisitos do produto, regras de SLA, máquina de estados e critérios de aceite por sprint.
2. [ARCHITECTURE.md](ARCHITECTURE.md) — Topologia, contratos entre serviços e invariantes arquiteturais.
3. [ROADMAP.md](ROADMAP.md) — Plano das 6 sprints, referências de estudo, entregáveis e plano de posts técnicos.
4. [CONVENTIONS.md](CONVENTIONS.md) — Padrões de Python, Vue 3, testes, commits e segurança.
5. [skills/](skills/) — Protocolos operacionais de implementação, revisão e comunicação técnica.
6. [CHANGELOG.md](CHANGELOG.md) — Histórico incremental de decisões e entregas.

> Se existir um arquivo local `.agents/MENTOR_PRIVATE.md` (ignorado pelo Git), leia-o também para preservar preferências de mentoria, ritmo passo a passo e contexto de carreira sem expô-lo ao repositório público.

## Regras de governança

- **Spec-Driven Development:** nenhuma funcionalidade nova é implementada sem estar especificada em `SPEC.md`.
- **Decisões arquiteturais:** mudanças relevantes de stack, banco ou protocolo exigem um ADR em `../docs/adr/` e atualização de `ARCHITECTURE.md` no mesmo commit.
- **Verificabilidade:** nenhuma tarefa é considerada concluída sem testes automatizados ou validação reproduzível rodando após a edição final.
