import logging
from mcp_ankiconnect.server import mcp

logger = logging.getLogger(__name__)

def main():
    """Main entry point for the package."""
    logger.info("Starting MCP-AnkiConnect server")
    mcp.run()

if __name__ == "__main__":
    main()
