"""
Quick demo of AI Agent Immune System (30 seconds) with Web Dashboard
"""
import asyncio
import sys
from agents import create_agent_pool
from orchestrator import ImmuneSystemOrchestrator
from web_dashboard import WebDashboard
from logging_config import setup_logging, get_logger

logger = get_logger(__name__)


async def main():
    """Run a quick 30-second demo with web dashboard"""
    setup_logging()

    logger.info("Starting AI Agent Immune System Demo")
    
    # Create pool of 10 agents
    agents = create_agent_pool(10)
    logger.info("Created %d agents", len(agents))
    
    # Create immune system orchestrator
    orchestrator = ImmuneSystemOrchestrator(agents)
    
    # Start web dashboard
    dashboard = WebDashboard(orchestrator, port=8090)
    dashboard.start()
    
    # Run immune system (30 seconds)
    await orchestrator.run(duration_seconds=30)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Demo interrupted by user")
        sys.exit(0)
