"""MCP service types. Ported from services/mcp/types.ts"""
from __future__ import annotations
from typing import Any, Dict, List, Literal, Optional, Union
from dataclasses import dataclass, field


@dataclass
class MCPServerConfig:
    name: str
    transport: str  # 'stdio' | 'sse' | 'http'
    command: Optional[str] = None
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    url: Optional[str] = None
    headers: Dict[str, str] = field(default_factory=dict)
    enabled: bool = True


@dataclass
class MCPTool:
    name: str
    description: str
    input_schema: dict
    server_name: str


@dataclass
class MCPResource:
    uri: str
    name: str
    description: Optional[str] = None
    mime_type: Optional[str] = None


@dataclass
class MCPConnectionStatus:
    server_name: str
    status: Literal["connected", "connecting", "disconnected", "error"]
    error: Optional[str] = None
    tools: List[MCPTool] = field(default_factory=list)
    resources: List[MCPResource] = field(default_factory=list)
