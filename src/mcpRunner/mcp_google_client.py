import asyncio
import json
import logging
import httpx
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MCPGoogleClient:
    """
    A baseline MCP client for remote Google Workspace MCP servers.
    Supports SSE (Server-Sent Events) and Bearer Token authentication.
    """
    
    def __init__(self, base_url: str, access_token: str):
        self.base_url = base_url.rstrip('/')
        self.access_token = access_token
        self.client = httpx.AsyncClient(
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            },
            timeout=30.0
        )
        self.post_url: Optional[str] = None
        self.message_id = 1
        self.transport: Optional[str] = None
        self.session_id: Optional[str] = None

    async def connect(self):
        """
        Detect transport, establish the POST endpoint, and perform MCP initialization.
        """
        # 1. Check health to find transport
        try:
            logger.info(f"Checking server health at {self.base_url}...")
            health_resp = await self.client.get(self.base_url)
            if health_resp.status_code == 200:
                health_data = health_resp.json()
                self.transport = health_data.get("transport")
                logger.info(f"Detected transport: {self.transport}")
        except Exception as e:
            logger.warning(f"Could not reach health endpoint: {e}")

        # 2. Set endpoint URL
        if self.transport == "streamable-http":
            self.post_url = f"{self.base_url}/mcp"
            logger.info(f"Using Streamable HTTP endpoint: {self.post_url}")
        else:
            # Legacy SSE fallback
            self.post_url = f"{self.base_url}/mcp"
            logger.info(f"Defaulting to /mcp endpoint")

        # 3. MCP Initialization Handshake (required for streamable-http)
        await self._initialize()

    async def _initialize(self):
        """
        Perform the MCP initialize handshake to get a session ID.
        The server assigns a Mcp-Session-Id that must be included in all
        subsequent requests.
        """
        init_payload = {
            "jsonrpc": "2.0",
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "alfred-mcp-client", "version": "1.0"}
            },
            "id": self.message_id
        }
        self.message_id += 1

        logger.info("Performing MCP initialization handshake...")
        response = await self.client.post(self.post_url, json=init_payload)

        if response.status_code not in (200, 201):
            raise Exception(f"MCP initialization failed: {response.status_code} {response.text}")

        # Extract session ID from response headers
        self.session_id = response.headers.get("Mcp-Session-Id")
        if self.session_id:
            logger.info(f"Session established: {self.session_id[:12]}...")
            # Add session ID to all future requests
            self.client.headers.update({"Mcp-Session-Id": self.session_id})
        else:
            logger.warning("No session ID returned — server may not require one.")

        # Send initialized notification (required by MCP spec)
        notif_payload = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {}
        }
        await self.client.post(self.post_url, json=notif_payload)
        logger.info("MCP handshake complete.")

    def _parse_response(self, response) -> Any:
        """
        Parse a response that may be plain JSON or an SSE event stream.
        MCP streamable-http responses can be either format.
        """
        content_type = response.headers.get("content-type", "")
        raw = response.text.strip()

        if not raw:
            return {}

        # SSE format: lines starting with "data: "
        if "text/event-stream" in content_type or raw.startswith("data:"):
            for line in raw.splitlines():
                line = line.strip()
                if line.startswith("data:"):
                    data_str = line[5:].strip()
                    if data_str and data_str != "[DONE]":
                        return json.loads(data_str)
            return {}

        # Plain JSON
        return json.loads(raw)

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """
        Execute an MCP tool using JSON-RPC.
        """
        if not self.post_url:
            await self.connect()
            
        payload = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            },
            "id": self.message_id
        }
        self.message_id += 1
        
        logger.info(f"Calling tool: {tool_name} with args: {arguments}")
        response = await self.client.post(self.post_url, json=payload)
        
        if response.status_code not in (200, 202):
            logger.error(f"Tool call failed: {response.status_code} {response.text}")
            return {"error": response.text}
            
        result = self._parse_response(response)
        if "error" in result:
            logger.error(f"MCP Error: {result['error']}")
            return result["error"]
            
        return result.get("result", {})

    async def list_tools(self) -> List[Dict[str, Any]]:
        """
        List available tools from the MCP server.
        """
        if not self.post_url:
            await self.connect()
            
        payload = {
            "jsonrpc": "2.0",
            "method": "tools/list",
            "params": {},
            "id": self.message_id
        }
        self.message_id += 1
        
        response = await self.client.post(self.post_url, json=payload)
        if response.status_code not in (200, 202):
            raise Exception(f"Failed to list tools: {response.status_code} {response.text}")

        result = self._parse_response(response)
        return result.get("result", {}).get("tools", [])

    async def close(self):
        await self.client.aclose()

# Example usage for development/testing
if __name__ == "__main__":
    async def main():
        # Replace with a valid token for testing
        token = "YOUR_GOOGLE_ACCESS_TOKEN"
        url = "https://workspace-mcp-181562945855.asia-southeast2.run.app/"
        
        client = MCPGoogleClient(url, token)
        try:
            tools = await client.list_tools()
            print(f"Available tools: {[t['name'] for t in tools]}")
        finally:
            await client.close()
            
    # asyncio.run(main())
