"""
Framework module for MCP (Model Context Protocol) infrastructure.
Contains core server, client, and utility components.
"""

import sys
import os
root_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  
sys.path.append(root_path)
from logs.logger_utils import logger

__all__ = ['logger']

# Optional imports to avoid circular dependencies
try:
    from .mcp_server import mcp
    __all__.append('mcp')
except ImportError:
    pass

try:
    from .mcp_client import MCPClient
    __all__.append('MCPClient')
except ImportError:
    pass