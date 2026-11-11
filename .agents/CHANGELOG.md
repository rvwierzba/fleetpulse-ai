# CHANGELOG.md — Histórico do FleetPulse AI

## [Unreleased]

### Sprint 0 — Spec-Driven Development & Arquitetura Base (Concluída)
- **Passo 0.1:** Criação independente do repositório em `C:\DEV\fleetpulse-ai` (`git init -b main`), `.gitignore` e estrutura `.agents/` (`README.md`, `SPEC.md`, `ARCHITECTURE.md`, `CONVENTIONS.md`, `ROADMAP.md`, `skills/`).
- **Passo 0.2:** Registro dos 3 ADRs iniciais em `docs/adr/` (`ADR-001` a `ADR-003`), criação de `README.md`, `.env.example`, `docker-compose.yml` (`pgvector/pgvector:pg16`, `neo4j:5.26-community`, `redis:7-alpine`), script `infra/postgres/init.sql` e validação dos containers locais + Ollama.
