"""
AI Agent Immune System - Main Entry Point

A system that treats AI agents as living entities with an immune system that:
- Learns normal behavior
- Detects infections (abnormal behavior)
- Quarantines unhealthy agents
- Heals them with progressive actions
- Remembers which healing actions work (adaptive immunity)
"""
import asyncio
import sys
from agents import create_agent_pool
from orchestrator import ImmuneSystemOrchestrator
from web_dashboard import WebDashboard
from logging_config import setup_logging, get_logger

logger = get_logger(__name__)


async def main():
    """Main entry point with web dashboard"""
    setup_logging()

    logger.info("Starting AI Agent Immune System")
    # Create pool of 15 diverse agents
    agents = create_agent_pool(15)
    logger.info("Created %d agents", len(agents))
    
    # Create immune system orchestrator
    orchestrator = ImmuneSystemOrchestrator(agents)

    # Start web dashboard (pass loop so approve-healing can schedule heal from Flask thread)
    dashboard = WebDashboard(orchestrator, port=8090)
    dashboard.set_loop(asyncio.get_running_loop())
    dashboard.start()

    # Run for 1200 seconds - adjust as needed
    await orchestrator.run(duration_seconds=1200)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutdown requested by user")
        sys.exit(0)
