from . import server
import asyncio
import os
import subprocess

def main():
    """Main entry point for the package."""
    asyncio.run(server.main())

def inspect():
    """Run the MCP inspector for debugging."""
    project_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    subprocess.run([
        "npx",
        "@modelcontextprotocol/inspector",
        "uv",
        "--directory", project_dir,
        "run",
        "mcp-ankiconnect"
    ])

# Optionally expose other important items at package level
__all__ = ['main', 'server', 'inspect']
