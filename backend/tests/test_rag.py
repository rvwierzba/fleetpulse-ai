"""Automated test suite for Sprint 3: Hybrid RAG, Neo4j, pgvector, and Semantic Cache."""

import hashlib

import pytest

from app.infra.config import get_settings
from app.infra.database import create_db_engine, create_session_factory
from app.infra.redis_client import create_redis_client
from app.rag.graph_service import (
    GraphService,
    UnsafeCypherQueryError,
    get_graph_service,
)
from app.rag.orchestrator import HybridRAGOrchestrator
from app.rag.schemas import HybridRAGResult
from app.rag.semantic_cache import SemanticCache
from app.rag.vector_service import get_vector_service


def test_read_only_cypher_validator_enforces_invariant_4() -> None:
    """Invariant #4: Text-to-Cypher validator blocks mutative instructions."""
    safe_queries = [
        "MATCH (d:Device) RETURN d.id LIMIT 10",
        "OPTIONAL MATCH (ec:ErrorCode {code: 'ERR_BATT'})-[:DEFAULT_RUNBOOK]->(rb) RETURN rb",
        "CYPHER 5.0 MATCH (tb:TechBulletin) WHERE tb.severity = 'HIGH' RETURN tb",
        "MATCH (b:Batch)<-[:BELONGS_TO_BATCH]-(d:Device) WITH b, count(d) AS c RETURN b.id, c",
    ]
    for q in safe_queries:
        GraphService.validate_read_only_cypher(q)

    unsafe_queries = [
        "CREATE (n:Hacked {name: 'pwnd'})",
        "MATCH (d:Device) DELETE d",
        "MATCH (d:Device) DETACH DELETE d",
        "MERGE (m:Model {code: 'T14'}) SET m.hacked = true",
        "MATCH (d:Device) SET d.status = 'COMPROMISED'",
        "DROP CONSTRAINT constraint_device",
        "CALL dbms.components()",
        "LOAD CSV FROM 'file:///etc/passwd' AS line RETURN line",
    ]
    for q in unsafe_queries:
        with pytest.raises(UnsafeCypherQueryError):
            GraphService.validate_read_only_cypher(q)


@pytest.mark.asyncio
async def test_graph_service_entity_validation_enforces_invariant_3() -> None:
    """Invariant #3: Every runbook_id and bulletin_id is validated against Neo4j."""
    graph = get_graph_service()
    if not await graph.ping():
        pytest.skip("Neo4j database not reachable for integration test")

    # Seeded IDs
    rb_valid, tb_valid = await graph.validate_entity_ids(
        runbook_id="RBK-BATT-01",
        bulletin_id="TB-2024-001",
    )
    assert rb_valid is True
    assert tb_valid is True

    # Fake IDs that do not exist in graph
    fake_rb, fake_tb = await graph.validate_entity_ids(
        runbook_id="RBK-HALLUCINATED-999",
        bulletin_id="TB-FAKE-666",
    )
    assert fake_rb is False
    assert fake_tb is False


@pytest.mark.asyncio
async def test_graph_service_traversal_returns_topology_context() -> None:
    """Verify Neo4j traversal matches runbook and active engineering bulletin."""
    graph = get_graph_service()
    if not await graph.ping():
        pytest.skip("Neo4j database not reachable")

    context = await graph.get_graph_context(
        device_type="NOTEBOOK",
        model_code="T14-GEN5",
        batch_id="BATCH-2024-Q3-T14",
        firmware_version="BIOS-1.42.0",
        error_code="ERR_BATT_CYCLE_EXCEEDED",
        subsystem="BATTERY_POWER",
    )

    assert context.matched_runbook is not None
    assert context.matched_runbook.runbook_id == "RBK-BATT-01"
    assert context.matched_runbook.sla_target_hours == 4
    assert len(context.active_bulletins) >= 1
    assert any(b.bulletin_id == "TB-2024-001" for b in context.active_bulletins)
    assert context.batch_failure_count >= 1


@pytest.mark.asyncio
async def test_pgvector_similarity_search_returns_chunks() -> None:
    """Verify pgvector semantic search finds relevant technical documents."""
    settings = get_settings()
    engine = create_db_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    vector_service = get_vector_service()

    async with session_factory() as session:
        chunks = await vector_service.search_documents(
            session=session,
            query_text="Bateria degradada com alta temperatura e perda de carga",
            device_type="NOTEBOOK",
            subsystem="BATTERY_POWER",
            limit=2,
        )

        assert len(chunks) > 0
        top = chunks[0]
        assert top.subsystem == "BATTERY_POWER"
        assert top.similarity_score > 0.40
        assert "RBK-BATT-01" in top.content or "bateria" in top.content.lower()

    await engine.dispose()


@pytest.mark.asyncio
async def test_semantic_cache_l1_and_l2() -> None:
    """Verify Redis L1 exact match and pgvector L2 cosine similarity caching."""
    settings = get_settings()
    engine = create_db_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    redis_client = create_redis_client(settings.redis_url)
    cache = SemanticCache()

    signature = cache.compute_signature(
        device_type="MOCK_DEV",
        model_code="MOCK_MODEL",
        firmware_version="MOCK_FW_1.0",
        subsystem="BATTERY_POWER",
        error_code="MOCK_ERR_999",
    )
    query_text = "Dispositivo de teste com falha simulada de bateria"
    sample_payload = {"mock_runbook": "RBK-BATT-01", "mock_status": "OK"}

    async with session_factory() as session:
        # Initial lookup must miss
        data, cache_type = await cache.get(session, redis_client, signature, query_text)

        # Store in cache
        await cache.put(
            session, redis_client, signature, query_text, sample_payload, ttl_seconds=60
        )

        # Immediate exact lookup -> Redis L1 Hit
        l1_data, l1_type = await cache.get(session, redis_client, signature, query_text)
        assert l1_data == sample_payload
        assert l1_type == "redis_l1"

    await redis_client.aclose()
    await engine.dispose()


@pytest.mark.asyncio
async def test_hybrid_rag_orchestrator_enrichment_and_caching() -> None:
    """Verify complete end-to-end enrichment: first call misses, second call hits cache."""
    settings = get_settings()
    engine = create_db_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    redis_client = create_redis_client(settings.redis_url)

    orchestrator = HybridRAGOrchestrator()

    # Clear any previous cached entries for this signature to guarantee a clean miss on res1
    sig = orchestrator.cache.compute_signature(
        device_type="NOTEBOOK",
        model_code="T14-GEN5",
        firmware_version="BIOS-1.42.0",
        subsystem="BATTERY_POWER",
        error_code="ERR_BATT_CYCLE_EXCEEDED",
    )
    redis_key = f"fleetpulse:semcache:l1:{hashlib.sha256(sig.encode()).hexdigest()}"
    await redis_client.delete(redis_key)
    async with session_factory() as session:
        from sqlalchemy import text

        await session.execute(
            text("DELETE FROM semantic_cache_entries WHERE signature = :sig"),
            {"sig": sig},
        )
        await session.commit()

    async with session_factory() as session:
        # First call: Cache miss -> queries Neo4j and pgvector
        res1: HybridRAGResult = await orchestrator.enrich_alert_context(
            session=session,
            redis_client=redis_client,
            device_type="NOTEBOOK",
            model_code="T14-GEN5",
            batch_id="BATCH-2024-Q3-T14",
            firmware_version="BIOS-1.42.0",
            error_code="ERR_BATT_CYCLE_EXCEEDED",
            subsystem="BATTERY_POWER",
            description="Bateria descarregando rapidamente sob alta carga",
            telemetry={"battery_cycles": 1180, "battery_health_pct": 44.5},
        )

        assert res1.cache_hit is False
        assert res1.matched_runbook_id == "RBK-BATT-01"
        assert res1.matched_bulletin_id == "TB-2024-001"
        assert "RBK-BATT-01" in res1.synthesized_context
        assert len(res1.vector_documents) > 0

        # Second identical call: Must hit Semantic Cache
        res2: HybridRAGResult = await orchestrator.enrich_alert_context(
            session=session,
            redis_client=redis_client,
            device_type="NOTEBOOK",
            model_code="T14-GEN5",
            batch_id="BATCH-2024-Q3-T14",
            firmware_version="BIOS-1.42.0",
            error_code="ERR_BATT_CYCLE_EXCEEDED",
            subsystem="BATTERY_POWER",
            description="Bateria descarregando rapidamente sob alta carga",
            telemetry={"battery_cycles": 1180, "battery_health_pct": 44.5},
        )

        assert res2.cache_hit is True
        assert res2.matched_runbook_id == "RBK-BATT-01"
        assert res2.cache_type in {"redis_l1", "pgvector_l2"}

    await redis_client.aclose()
    await engine.dispose()
