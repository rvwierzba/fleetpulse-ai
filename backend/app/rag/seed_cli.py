"""Command-line script to bootstrap and seed Neo4j and pgvector knowledge bases."""

import asyncio
import logging

from app.infra.config import get_settings
from app.infra.database import create_db_engine, create_session_factory, init_db
from app.rag.graph_service import get_graph_service
from app.rag.seed_data import seed_neo4j_knowledge_graph, seed_tech_documents_pgvector

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("seed_cli")


async def main() -> None:
    settings = get_settings()
    logger.info("Connecting to PostgreSQL at %s ...", settings.database_url)
    engine = create_db_engine(settings.database_url)
    await init_db(engine)
    session_factory = create_session_factory(engine)

    logger.info("Seeding Neo4j Knowledge Graph...")
    graph = get_graph_service()
    neo_res = await seed_neo4j_knowledge_graph(graph)
    logger.info("Neo4j seeded successfully: %s", neo_res)

    logger.info("Seeding PostgreSQL pgvector technical documents...")
    async with session_factory() as session:
        doc_count = await seed_tech_documents_pgvector(session)
        logger.info("pgvector seeded successfully: %d documents", doc_count)

    await graph.close()
    await engine.dispose()
    logger.info("Bootstrap and seeding completed successfully!")


if __name__ == "__main__":
    asyncio.run(main())
