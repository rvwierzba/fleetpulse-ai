"""Seed data generator for Neo4j fleet knowledge graph and pgvector technical documents."""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.rag.embeddings import EmbeddingService, get_embedding_service
from app.rag.graph_service import GraphService, get_graph_service
from app.rag.vector_service import VectorService, get_vector_service

logger = logging.getLogger(__name__)

TECH_DOCUMENTS_SEED = [
    {
        "doc_id": "DOC-TB-2024-001",
        "title": "Boletim de Engenharia TB-2024-001: Degradação Acelerada de Células de Bateria",
        "doc_type": "service_bulletin",
        "device_type": "NOTEBOOK",
        "subsystem": "BATTERY_POWER",
        "content": (
            "Dispositivos do lote BATCH-2024-Q3-T14 operando com ciclos de recarga superiores a 900 "
            "e temperatura média acima de 65C apresentam perda abrupta de retenção de carga e "
            "quedas repentinas de tensão (ERR_BATT_VOLTAGE_DROP). Recomendada a substituição proativa "
            "do módulo de bateria antes do rompimento do SLA corporativo via Runbook RBK-BATT-01."
        ),
        "doc_metadata": {"bulletin_id": "TB-2024-001", "recommended_runbook": "RBK-BATT-01"},
    },
    {
        "doc_id": "DOC-TB-2024-002",
        "title": "Boletim de Engenharia TB-2024-002: Bloqueio Térmico e Throttling em BIOS-1.42.0",
        "doc_type": "service_bulletin",
        "device_type": "NOTEBOOK",
        "subsystem": "THERMAL_BOARD",
        "content": (
            "A atualização de firmware BIOS-1.42.0 introduziu uma curva de disparo térmico excessivamente "
            "agressiva nos processadores de notebooks ThinkPad T14 Gen 5. Quando o sensor detecta 78C, "
            "a CPU trava em 400MHz permanentemente (ERR_THERMAL_THROTTLE_LOCK). "
            "O procedimento de contenção exige rollback de emergência para BIOS-1.41 ou avanço para BIOS-1.45.1 "
            "conforme documentado no Runbook RBK-THERM-02."
        ),
        "doc_metadata": {"bulletin_id": "TB-2024-002", "recommended_runbook": "RBK-THERM-02"},
    },
    {
        "doc_id": "DOC-TB-2024-003",
        "title": "Boletim Técnico TB-2024-003: Timeouts de I/O em Armazenamento UFS/NVMe",
        "doc_type": "service_bulletin",
        "device_type": "SMARTPHONE",
        "subsystem": "STORAGE_NVME",
        "content": (
            "Frotas de smartphones corporativos ThinkPhone e Edge 50 Pro com desgaste superior a 25% "
            "no módulo de armazenamento sofrem com timeouts intermitentes em transações de banco local "
            "(ERR_NVME_TIMEOUT). Aplicar Runbook RBK-SMARTPHONE-04 para coleta de dump de kernel e "
            "atualização emergencial via MDM corporativo."
        ),
        "doc_metadata": {"bulletin_id": "TB-2024-003", "recommended_runbook": "RBK-SMARTPHONE-04"},
    },
    {
        "doc_id": "DOC-MAN-RBK-BATT-01",
        "title": "Procedimento Operacional Padrão RBK-BATT-01: Substituição Proativa de Bateria",
        "doc_type": "runbook_manual",
        "device_type": "NOTEBOOK",
        "subsystem": "BATTERY_POWER",
        "content": (
            "Passo a passo técnico para substituição de bateria em campo: "
            "1. Validar no relatório de telemetria se battery_cycles > 800 e health < 55%. "
            "2. Executar diagnóstico de célula pré-troca pelo software de suporte. "
            "3. Enviar técnico N2 para troca física em até 4 horas (SLA Platinum). "
            "4. Rodar ciclo completo de calibração pós-troca e registrar ID da nova bateria."
        ),
        "doc_metadata": {"runbook_id": "RBK-BATT-01", "sla_hours": 4},
    },
    {
        "doc_id": "DOC-MAN-RBK-NVME-03",
        "title": "Procedimento Técnico RBK-NVME-03: Remapeamento e Clonagem NVMe",
        "doc_type": "runbook_manual",
        "device_type": "NOTEBOOK",
        "subsystem": "STORAGE_NVME",
        "content": (
            "Instruções para incidentes de falha iminente em discos NVMe corporativos: "
            "1. Realizar snapshot de backup imediato em nuvem segura. "
            "2. Solicitar aprovação humana de troca devido ao risco de perda de imagem corporativa. "
            "3. Proceder com a substituição física do SSD M.2 PCIe e restauração da imagem criptografada."
        ),
        "doc_metadata": {"runbook_id": "RBK-NVME-03", "requires_approval": True},
    },
]


async def seed_neo4j_knowledge_graph(graph_service: GraphService | None = None) -> dict[str, int]:
    """Populate Neo4j with fleet models, batches, firmwares, error codes, bulletins, and runbooks."""
    service = graph_service or get_graph_service()
    driver = service.get_driver()

    queries = [
        # 1. Constraints / Indexes for fast lookup
        "CREATE CONSTRAINT IF NOT EXISTS FOR (d:Device) REQUIRE d.id IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (m:Model) REQUIRE m.code IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (b:Batch) REQUIRE b.id IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (fv:FirmwareVersion) REQUIRE fv.version IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (ec:ErrorCode) REQUIRE ec.code IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (tb:TechBulletin) REQUIRE tb.id IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (rb:Runbook) REQUIRE rb.id IS UNIQUE",
        # 2. Device Types & Models
        """
        MERGE (dt_nb:DeviceType {name: 'NOTEBOOK'})
        MERGE (dt_sp:DeviceType {name: 'SMARTPHONE'})
        MERGE (m1:Model {code: 'T14-GEN5'}) SET m1.name = 'ThinkPad T14 Gen 5'
        MERGE (m2:Model {code: 'X1-CARBON'}) SET m2.name = 'ThinkPad X1 Carbon Gen 12'
        MERGE (m3:Model {code: 'THINKPHONE-24'}) SET m3.name = 'ThinkPhone by Motorola'
        MERGE (m4:Model {code: 'EDGE-50-PRO'}) SET m4.name = 'Motorola Edge 50 Pro'
        MERGE (m1)-[:IS_TYPE]->(dt_nb)
        MERGE (m2)-[:IS_TYPE]->(dt_nb)
        MERGE (m3)-[:IS_TYPE]->(dt_sp)
        MERGE (m4)-[:IS_TYPE]->(dt_sp)
        """,
        # 3. Batches
        """
        MERGE (b1:Batch {id: 'BATCH-2024-Q3-T14'}) SET b1.mfg_date = '2024-08-15'
        MERGE (b2:Batch {id: 'BATCH-2024-Q4-X1'}) SET b2.mfg_date = '2024-11-01'
        MERGE (b3:Batch {id: 'BATCH-2024-SP-TP'}) SET b3.mfg_date = '2024-09-10'
        WITH b1, b2, b3
        MATCH (m1:Model {code: 'T14-GEN5'})
        MATCH (m2:Model {code: 'X1-CARBON'})
        MATCH (m3:Model {code: 'THINKPHONE-24'})
        MERGE (b1)-[:OF_MODEL]->(m1)
        MERGE (b2)-[:OF_MODEL]->(m2)
        MERGE (b3)-[:OF_MODEL]->(m3)
        """,
        # 4. Firmwares
        """
        MERGE (fv1:FirmwareVersion {version: 'BIOS-1.42.0'}) SET fv1.release_date = '2024-09-20', fv1.has_known_defect = true
        MERGE (fv2:FirmwareVersion {version: 'BIOS-1.45.1'}) SET fv2.release_date = '2024-10-30', fv2.has_known_defect = false
        MERGE (fv3:FirmwareVersion {version: 'OS-14.1.0'}) SET fv3.release_date = '2024-08-01', fv3.has_known_defect = false
        WITH fv1, fv2, fv3
        MATCH (m1:Model {code: 'T14-GEN5'})
        MATCH (m3:Model {code: 'THINKPHONE-24'})
        MERGE (fv1)-[:TARGETS_MODEL]->(m1)
        MERGE (fv2)-[:TARGETS_MODEL]->(m1)
        MERGE (fv3)-[:TARGETS_MODEL]->(m3)
        """,
        # 5. Runbooks
        """
        MERGE (rb1:Runbook {id: 'RBK-BATT-01'})
        SET rb1.title = 'Substituição Proativa de Célula de Bateria',
            rb1.sla_target_hours = 4,
            rb1.steps = ['Validar telemetria', 'Despachar técnico N2', 'Troca física', 'Calibração'],
            rb1.requires_human_approval = false

        MERGE (rb2:Runbook {id: 'RBK-THERM-02'})
        SET rb2.title = 'Rollback Emergencial de BIOS e Limpeza de Duto Térmico',
            rb2.sla_target_hours = 2,
            rb2.steps = ['Executar rollback BIOS 1.41', 'Teste de estresse térmico', 'Limpeza de cooler'],
            rb2.requires_human_approval = false

        MERGE (rb3:Runbook {id: 'RBK-NVME-03'})
        SET rb3.title = 'Remapeamento S.M.A.R.T. e Clonagem Proativa de Imagem',
            rb3.sla_target_hours = 8,
            rb3.steps = ['Backup em nuvem', 'Aprovação de troca', 'Substituição física SSD', 'Restauração'],
            rb3.requires_human_approval = true

        MERGE (rb4:Runbook {id: 'RBK-SMARTPHONE-04'})
        SET rb4.title = 'Atualização Forçada de Firmware via MDM e Recalibração de Sensor',
            rb4.sla_target_hours = 6,
            rb4.steps = ['Push de update via MDM', 'Dump de log de kernel', 'Validação remota'],
            rb4.requires_human_approval = false
        """,
        # 6. Error Codes and Default Runbooks
        """
        MERGE (ec1:ErrorCode {code: 'ERR_BATT_CYCLE_EXCEEDED'}) SET ec1.subsystem = 'BATTERY_POWER', ec1.severity = 'HIGH'
        MERGE (ec2:ErrorCode {code: 'ERR_BATT_VOLTAGE_DROP'}) SET ec2.subsystem = 'BATTERY_POWER', ec2.severity = 'CRITICAL'
        MERGE (ec3:ErrorCode {code: 'ERR_THERMAL_THROTTLE_LOCK'}) SET ec3.subsystem = 'THERMAL_BOARD', ec3.severity = 'CRITICAL'
        MERGE (ec4:ErrorCode {code: 'ERR_NVME_TIMEOUT'}) SET ec4.subsystem = 'STORAGE_NVME', ec4.severity = 'HIGH'
        MERGE (ec5:ErrorCode {code: 'ERR_NVME_READ_FAILURE'}) SET ec5.subsystem = 'STORAGE_NVME', ec5.severity = 'CRITICAL'

        WITH ec1, ec2, ec3, ec4, ec5
        MATCH (rb1:Runbook {id: 'RBK-BATT-01'})
        MATCH (rb2:Runbook {id: 'RBK-THERM-02'})
        MATCH (rb3:Runbook {id: 'RBK-NVME-03'})
        MERGE (ec1)-[:DEFAULT_RUNBOOK]->(rb1)
        MERGE (ec2)-[:DEFAULT_RUNBOOK]->(rb1)
        MERGE (ec3)-[:DEFAULT_RUNBOOK]->(rb2)
        MERGE (ec4)-[:DEFAULT_RUNBOOK]->(rb3)
        MERGE (ec5)-[:DEFAULT_RUNBOOK]->(rb3)
        """,
        # 7. Tech Bulletins and Relationships
        """
        MERGE (tb1:TechBulletin {id: 'TB-2024-001'})
        SET tb1.title = 'Degradação Acelerada de Células de Bateria no Lote BATCH-2024-Q3-T14',
            tb1.severity = 'CRITICAL',
            tb1.summary = 'Baterias do fornecedor X apresentam queda prematura de tensão acima de 900 ciclos.',
            tb1.affected_batches = ['BATCH-2024-Q3-T14'],
            tb1.affected_firmwares = [],
            tb1.covered_errors = ['ERR_BATT_VOLTAGE_DROP', 'ERR_BATT_CYCLE_EXCEEDED']

        MERGE (tb2:TechBulletin {id: 'TB-2024-002'})
        SET tb2.title = 'Curva Agressiva de Throttling na BIOS-1.42.0',
            tb2.severity = 'HIGH',
            tb2.summary = 'BIOS trava clock da CPU permanentemente ao atingir 78C em ThinkPad T14.',
            tb2.affected_batches = [],
            tb2.affected_firmwares = ['BIOS-1.42.0'],
            tb2.covered_errors = ['ERR_THERMAL_THROTTLE_LOCK']

        MERGE (tb3:TechBulletin {id: 'TB-2024-003'})
        SET tb3.title = 'Timeouts de Armazenamento UFS/NVMe em Lote ThinkPhone',
            tb3.severity = 'MEDIUM',
            tb3.summary = 'Desgaste prematuro de blocos de armazenamento em smartphones.',
            tb3.affected_batches = ['BATCH-2024-SP-TP'],
            tb3.affected_firmwares = ['OS-14.1.0'],
            tb3.covered_errors = ['ERR_NVME_TIMEOUT']

        WITH tb1, tb2, tb3
        MATCH (rb1:Runbook {id: 'RBK-BATT-01'})
        MATCH (rb2:Runbook {id: 'RBK-THERM-02'})
        MATCH (rb4:Runbook {id: 'RBK-SMARTPHONE-04'})
        MERGE (tb1)-[:RECOMMENDS_RUNBOOK]->(rb1)
        MERGE (tb2)-[:RECOMMENDS_RUNBOOK]->(rb2)
        MERGE (tb3)-[:RECOMMENDS_RUNBOOK]->(rb4)
        """,
        # 8. Sample Devices for batch queries
        """
        MERGE (d1:Device {id: 'NB-2026-0042'}) SET d1.model = 'T14-GEN5'
        MERGE (d2:Device {id: 'NB-2026-0043'}) SET d2.model = 'T14-GEN5'
        MERGE (d3:Device {id: 'NB-2026-0044'}) SET d3.model = 'T14-GEN5'
        WITH d1, d2, d3
        MATCH (b:Batch {id: 'BATCH-2024-Q3-T14'})
        MERGE (d1)-[:BELONGS_TO_BATCH]->(b)
        MERGE (d2)-[:BELONGS_TO_BATCH]->(b)
        MERGE (d3)-[:BELONGS_TO_BATCH]->(b)
        """,
    ]

    executed = 0
    async with driver.session() as session:
        for q in queries:
            await session.run(q)
            executed += 1

    logger.info("Seeded Neo4j knowledge graph with %d queries successfully.", executed)
    return {"queries_executed": executed}


async def seed_tech_documents_pgvector(
    session: AsyncSession,
    vector_service: VectorService | None = None,
    embedding_service: EmbeddingService | None = None,
) -> int:
    """Populate PostgreSQL pgvector tech_documents table with embeddings."""
    v_service = vector_service or get_vector_service()
    e_service = embedding_service or get_embedding_service()

    count = 0
    for doc in TECH_DOCUMENTS_SEED:
        text_for_embed = f"{doc['title']}\n{doc['content']}"
        emb = await e_service.get_embedding(text_for_embed)
        await v_service.insert_document(
            session=session,
            doc_id=doc["doc_id"],
            title=doc["title"],
            doc_type=doc["doc_type"],
            device_type=doc["device_type"],
            subsystem=doc["subsystem"],
            content=doc["content"],
            doc_metadata=doc.get("doc_metadata", {}),
            embedding=emb,
        )
        count += 1

    logger.info("Seeded %d documents into PostgreSQL pgvector successfully.", count)
    return count
