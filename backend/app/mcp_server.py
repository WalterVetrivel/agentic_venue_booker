"""MCP server at /mcp (Streamable HTTP, stateless), so Claude Desktop or any MCP client can use the
same tools as the in-app assistant.

Who is calling decides which tools are listed: send `Authorization: Bearer <token>` (from
GET /api/auth/mcp-token) to act as that staff member; without it you get the public, read-only
tools a student would get. Tools never change data: drafts and proposals come back as text with a
link to finish the step in the app.
"""

import json

import mcp_types as types
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPASGIApp, StreamableHTTPSessionManager

from app.agent import tools as registry
from app.auth import user_from_request
from app.db import session_for


def _request(ctx):
    request = getattr(ctx, "request", None)
    if request is None:
        raise RuntimeError("The MCP server only runs over HTTP")
    return request


def _tool_out(t: registry.Tool) -> types.Tool:
    return types.Tool(
        name=t.name,
        description=t.description,
        input_schema=t.schema(),
        annotations=types.ToolAnnotations(
            title=t.label, read_only_hint=True, destructive_hint=False, open_world_hint=False
        ),
    )


def _card_text(card: dict, base: str) -> str:
    lines = [card["title"], *card.get("lines", [])]
    if card.get("href"):
        lines.append(f"Open {base}{card['href']} to review and submit it.")
    else:
        lines.append(f"Confirm this in the app ({base}) to make the change.")
    return "\n".join(lines)


async def list_tools(ctx, params) -> types.ListToolsResult:
    request = _request(ctx)
    with session_for(request.app) as db:
        user = user_from_request(request, db)
        return types.ListToolsResult(tools=[_tool_out(t) for t in registry.tools_for(user)])


async def call_tool(ctx, params: types.CallToolRequestParams) -> types.CallToolResult:
    request = _request(ctx)
    with session_for(request.app) as db:
        user = user_from_request(request, db)
        try:
            result = registry.call(db, user, params.name, params.arguments or {})
        except registry.ToolError as e:
            return types.CallToolResult(
                content=[types.TextContent(type="text", text=str(e))], is_error=True
            )
        text = json.dumps(result.data, default=str, ensure_ascii=False, indent=1)
        content = [types.TextContent(type="text", text=text)]
        if result.card:
            base = str(request.base_url).rstrip("/")
            content.append(types.TextContent(type="text", text=_card_text(result.card, base)))
        return types.CallToolResult(content=content)


def make_session_manager() -> StreamableHTTPSessionManager:
    """A new manager per app: each can only be run once (in the app's lifespan)."""
    server = Server(
        "kiot-venue-booker",
        version="0.5.0",
        instructions=(
            "Venue booking for the CSE department at KIOT. Check availability with the tools "
            "instead of guessing; bookings and approvals are finished in the web app."
        ),
        on_list_tools=list_tools,
        on_call_tool=call_tool,
    )
    return StreamableHTTPSessionManager(app=server, stateless=True, json_response=True)


def asgi_app(manager: StreamableHTTPSessionManager) -> StreamableHTTPASGIApp:
    return StreamableHTTPASGIApp(manager)
