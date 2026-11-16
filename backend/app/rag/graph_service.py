"""Async Neo4j service: fleet topology, knowledge graph traversal, and read-only Cypher validation."""

import asyncio
import logging
import re
from typing import Any

from neo4j import AsyncDriver, AsyncGraphDatabase

from app.infra.config import get_settings
from app.rag.schemas import GraphContext, RunbookSummary, TechBulletinSummary

logger = logging.getLogger(__name__)

FORBIDDEN_CYPHER_KEYWORDS = re.compile(
    r"\b(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|ALTER|TRUNCATE|CALL\s+dbms|LOAD\s+CSV)\b",
    re.IGNORECASE,
)


class UnsafeCypherQueryError(ValueError):
    """Raised when a Cypher query violates Architectural Invariant #4 (Read-Only)."""


class GraphService:
    """Async Neo4j graph repository managing topology and technical runbooks."""

    def __init__(
        self,
        uri: str | None = None,
        user: str | None = None,
        password: str | None = None,
    ) -> None:
        settings = get_settings()
        self.uri = uri or settings.neo4j_uri
        self.user = user or settings.neo4j_user
        self.password = password or settings.neo4j_password
        self._driver: AsyncDriver | None = None

    def get_driver(self) -> AsyncDriver:
        """Return or lazily initialize the async Neo4j driver tied to the running event loop."""
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None

        if self._driver is None or getattr(self, "_loop", None) is not current_loop:
            self._driver = AsyncGraphDatabase.driver(
                self.uri,
                auth=(self.user, self.password),
            )
            self._loop = current_loop
        return self._driver

    async def close(self) -> None:
        """Close driver connections cleanly."""
        if self._driver is not None:
            await self._driver.close()
            self._driver = None

    async def ping(self) -> bool:
        """Check Neo4j database availability."""
        try:
            driver = self.get_driver()
            async with driver.session() as session:
                result = await session.run("RETURN 1 AS alive")
                record = await result.single()
                return bool(record and record["alive"] == 1)
        except Exception as exc:
            logger.warning("Neo4j ping failed: %s", exc)
            return False

    @staticmethod
    def validate_read_only_cypher(query: str) -> None:
        """Enforce Architectural Invariant #4: block any mutative Cypher instructions."""
        cleaned = query.strip()
        if not cleaned:
            raise UnsafeCypherQueryError("Empty Cypher query.")

        match = FORBIDDEN_CYPHER_KEYWORDS.search(cleaned)
        if match:
            forbidden = match.group(0).upper()
            raise UnsafeCypherQueryError(
                f"Forbidden mutative Cypher keyword '{forbidden}' detected. "
                "Text-to-Cypher queries must be strictly read-only (MATCH / RETURN)."
            )

        # Must start with allowed read statements
        first_token = cleaned.split()[0].upper()
        allowed_starts = {"MATCH", "OPTIONAL", "RETURN", "WITH", "CYPHER"}
        if first_token not in allowed_starts:
            raise UnsafeCypherQueryError(
                f"Cypher query must begin with read operation ({', '.join(allowed_starts)}), "
                f"got '{first_token}'."
            )

    async def execute_read_only_query(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Validate read-only safety then execute Cypher query against Neo4j."""
        self.validate_read_only_cypher(query)
        driver = self.get_driver()
        async with driver.session() as session:
            result = await session.run(query, parameters or {})
            records = await result.data()
            return records

    async def validate_entity_ids(
        self,
        runbook_id: str | None = None,
        bulletin_id: str | None = None,
    ) -> tuple[bool, bool]:
        """Enforce Architectural Invariant #3: check if runbook_id and bulletin_id exist in graph."""
        rb_valid = False
        tb_valid = False
        driver = self.get_driver()
        async with driver.session() as session:
            if runbook_id:
                res = await session.run(
                    "MATCH (rb:Runbook {id: $id}) RETURN count(rb) AS cnt",
                    {"id": runbook_id},
                )
                rec = await res.single()
                rb_valid = bool(rec and rec["cnt"] > 0)

            if bulletin_id:
                res = await session.run(
                    "MATCH (tb:TechBulletin {id: $id}) RETURN count(tb) AS cnt",
                    {"id": bulletin_id},
                )
                rec = await res.single()
                tb_valid = bool(rec and rec["cnt"] > 0)

        return rb_valid, tb_valid

    async def get_graph_context(
        self,
        device_type: str,
        model_code: str,
        batch_id: str,
        firmware_version: str,
        error_code: str,
        subsystem: str,
    ) -> GraphContext:
        """Traverse graph to retrieve applicable runbook, active bulletins, and batch impact."""
        driver = self.get_driver()
        runbook_summary: RunbookSummary | None = None
        active_bulletins: list[TechBulletinSummary] = []
        batch_failure_count = 0

        async with driver.session() as session:
            # 1. Fetch matching Runbook for error_code
            rb_res = await session.run(
                """
                MATCH (ec:ErrorCode {code: $error_code})-[:DEFAULT_RUNBOOK|RECOMMENDS_RUNBOOK]->(rb:Runbook)
                RETURN rb.id AS id, rb.title AS title, rb.sla_target_hours AS sla,
                       rb.steps AS steps, rb.requires_human_approval AS req_approval
                LIMIT 1
                """,
                {"error_code": error_code},
            )
            rb_rec = await rb_res.single()
            if rb_rec:
                runbook_summary = RunbookSummary(
                    runbook_id=rb_rec["id"],
                    title=rb_rec["title"],
                    sla_target_hours=rb_rec["sla"] or 4,
                    steps=rb_rec["steps"] or [],
                    requires_human_approval=bool(rb_rec["req_approval"]),
                )

            # 2. Fetch Tech Bulletins covering batch_id, firmware_version, or error_code
            tb_res = await session.run(
                """
                MATCH (tb:TechBulletin)
                WHERE ($batch_id IN tb.affected_batches)
                   OR ($firmware_version IN tb.affected_firmwares)
                   OR ($error_code IN tb.covered_errors)
                RETURN tb.id AS id, tb.title AS title, tb.severity AS severity,
                       tb.summary AS summary, tb.affected_batches AS batches,
                       tb.affected_firmwares AS firmwares
                LIMIT 5
                """,
                {
                    "batch_id": batch_id,
                    "firmware_version": firmware_version,
                    "error_code": error_code,
                },
            )
            tb_data = await tb_res.data()
            for row in tb_data:
                active_bulletins.append(
                    TechBulletinSummary(
                        bulletin_id=row["id"],
                        title=row["title"],
                        severity=row["severity"] or "MEDIUM",
                        summary=row["summary"] or "",
                        affected_batches=row["batches"] or [],
                        affected_firmwares=row["firmwares"] or [],
                    )
                )

            # If no direct runbook from error_code, check if a bulletin recommends a runbook
            if runbook_summary is None and active_bulletins:
                first_tb_id = active_bulletins[0].bulletin_id
                rec_res = await session.run(
                    """
                    MATCH (tb:TechBulletin {id: $tb_id})-[:RECOMMENDS_RUNBOOK]->(rb:Runbook)
                    RETURN rb.id AS id, rb.title AS title, rb.sla_target_hours AS sla,
                           rb.steps AS steps, rb.requires_human_approval AS req_approval
                    LIMIT 1
                    """,
                    {"tb_id": first_tb_id},
                )
                rec_rec = await rec_res.single()
                if rec_rec:
                    runbook_summary = RunbookSummary(
                        runbook_id=rec_rec["id"],
                        title=rec_rec["title"],
                        sla_target_hours=rec_rec["sla"] or 4,
                        steps=rec_rec["steps"] or [],
                        requires_human_approval=bool(rec_rec["req_approval"]),
                    )

            # 3. Count correlated devices/incidents in batch
            batch_res = await session.run(
                """
                MATCH (b:Batch {id: $batch_id})<-[:BELONGS_TO_BATCH]-(d:Device)
                RETURN count(d) AS total_devices
                """,
                {"batch_id": batch_id},
            )
            batch_rec = await batch_res.single()
            if batch_rec:
                batch_failure_count = batch_rec["total_devices"]

        return GraphContext(
            device_type=device_type,
            model_code=model_code,
            batch_id=batch_id,
            firmware_version=firmware_version,
            error_code=error_code,
            subsystem=subsystem,
            matched_runbook=runbook_summary,
            active_bulletins=active_bulletins,
            batch_failure_count=batch_failure_count,
        )


_graph_service: GraphService | None = None


def get_graph_service() -> GraphService:
    """Return singleton GraphService."""
    global _graph_service
    if _graph_service is None:
        _graph_service = GraphService()
    return _graph_service
