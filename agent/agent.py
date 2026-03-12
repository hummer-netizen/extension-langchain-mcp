"""
LangGraph research agent — compares data across multiple web pages.

Uses LangGraph's ReAct agent pattern with Webfuse Session MCP tools.
The agent plans research, visits pages, extracts data, and compares.

Usage:
  pip install -r requirements.txt
  cp ../.env.example .env  # fill in keys
  uvicorn agent:app --port 8082
"""

import os, json, httpx, asyncio, logging
from typing import Any, Optional
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.prebuilt import create_react_agent

logger = logging.getLogger("research-agent")

app = FastAPI()
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

MCP_URL = "https://session-mcp.webfu.se/mcp"


# --- MCP tool wrappers ---

async def _mcp_call(tool_name: str, args: dict, rest_key: str) -> str:
    """Call a Webfuse MCP tool via Streamable HTTP."""
    async with httpx.AsyncClient(timeout=60) as client:
        try:
            # Initialize MCP session
            init_resp = await client.post(
                MCP_URL,
                json={
                    "jsonrpc": "2.0",
                    "id": 0,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-03-26",
                        "capabilities": {},
                        "clientInfo": {"name": "langchain-research-agent", "version": "1.0"},
                    },
                },
                headers={
                    "Authorization": f"Bearer {rest_key}",
                    "Content-Type": "application/json",
                    "Accept": "application/json, text/event-stream",
                },
            )

            # Extract session ID from response header
            session_id = init_resp.headers.get("mcp-session-id", "")
            headers = {
                "Authorization": f"Bearer {rest_key}",
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            }
            if session_id:
                headers["mcp-session-id"] = session_id

            # Send initialized notification
            await client.post(
                MCP_URL,
                json={
                    "jsonrpc": "2.0",
                    "method": "notifications/initialized",
                },
                headers=headers,
            )

            # Call the tool
            resp = await client.post(
                MCP_URL,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {"name": tool_name, "arguments": args},
                },
                headers=headers,
            )

            data = resp.json()

            if "error" in data:
                return f"Error: {data['error'].get('message', 'unknown error')}"

            result = data.get("result", {})
            content = result.get("content", [])
            texts = [c.get("text", "") for c in content if c.get("type") == "text"]
            return "\n".join(texts) if texts else json.dumps(result)

        except httpx.TimeoutException:
            return "Error: MCP tool call timed out (60s). Try a more focused selector."
        except Exception as e:
            logger.error(f"MCP call failed: {e}")
            return f"Error: {str(e)}"


def make_tools(rest_key: str):
    """Create LangChain tool wrappers for Webfuse MCP tools."""

    @tool
    async def navigate(url: str) -> str:
        """Navigate the browser to a URL. Use for visiting pages to research."""
        return await _mcp_call("navigate", {"url": url}, rest_key)

    @tool
    async def see_dom_snapshot(root: str = "body") -> str:
        """Read the page DOM. Use a CSS selector for `root` to scope results and avoid huge responses.
        Good selectors: '.infobox', 'main', 'h1', '#content', 'table.wikitable'.
        Start narrow (e.g. '.infobox') before trying broader selectors."""
        return await _mcp_call("see_domSnapshot", {"root": root}, rest_key)

    @tool
    async def see_accessibility_tree() -> str:
        """Read the page accessibility tree. Good for understanding page structure before using CSS selectors."""
        return await _mcp_call("see_accessibilityTree", {}, rest_key)

    @tool
    async def act_click(selector: str) -> str:
        """Click an element by CSS selector."""
        return await _mcp_call("act_click", {"selector": selector}, rest_key)

    @tool
    async def act_scroll(direction: str = "down", amount: int = 3) -> str:
        """Scroll the page. Direction: 'up' or 'down'. Amount in viewport fractions."""
        return await _mcp_call("act_scroll", {"direction": direction, "amount": amount}, rest_key)

    @tool
    async def act_type(selector: str, text: str) -> str:
        """Type text into a form field by CSS selector."""
        return await _mcp_call("act_type", {"selector": selector, "text": text}, rest_key)

    @tool
    async def act_key_press(key: str) -> str:
        """Press a keyboard key (Enter, Tab, Escape, etc.)."""
        return await _mcp_call("act_keyPress", {"key": key}, rest_key)

    return [navigate, see_dom_snapshot, see_accessibility_tree,
            act_click, act_scroll, act_type, act_key_press]


SYSTEM_PROMPT = """You are a research agent with access to a live browser via Webfuse.
Your job: research a topic by visiting multiple web pages, extracting data, and comparing findings.

Strategy:
1. Plan which pages to visit for each subject
2. Navigate to the first subject's page (Wikipedia is a good starting point)
3. Use see_dom_snapshot with a FOCUSED CSS selector to read key data
   - Start narrow: '.infobox', '.mw-parser-output > p:first-of-type', 'table.wikitable'
   - Only use 'body' as a last resort — large pages will overflow context
4. Navigate to the next subject's page
5. Extract the SAME data points for fair comparison
6. Present a clear, structured comparison with data from both pages

Rules:
- Always cite which page each fact came from
- If data isn't available on a page, say so rather than guessing
- Use focused CSS selectors — '.infobox' is almost always better than 'body'
- Navigate between pages rather than trying to open multiple tabs
- Keep the final comparison well-structured with clear categories"""


EXAMPLE_TOPICS = [
    "Compare Amsterdam and Rotterdam: population, area, and top attractions",
    "Compare the features of Next.js and Remix",
    "Research Python vs Rust for web backends: performance, ecosystem, learning curve",
    "Compare pricing and features of Notion vs Confluence",
    "Find the tallest buildings in New York and compare them to Dubai",
]


class ResearchRequest(BaseModel):
    session_id: str = ""
    topic: str = EXAMPLE_TOPICS[0]


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/examples")
def examples():
    return {"topics": EXAMPLE_TOPICS}


@app.post("/research")
async def research(req: ResearchRequest):
    rest_key = os.environ["WEBFUSE_REST_KEY"]

    async def stream():
        yield f"data: {json.dumps({'type': 'status', 'text': 'Setting up research agent...'})}\n\n"

        llm = ChatOpenAI(model="gpt-4o", temperature=0, max_tokens=4096)
        tools = make_tools(rest_key)
        agent = create_react_agent(llm, tools)

        yield f"data: {json.dumps({'type': 'status', 'text': f'Researching: {req.topic}'})}\n\n"

        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=req.topic),
        ]

        step = 0
        try:
            async for event in agent.astream_events(
                {"messages": messages}, version="v2"
            ):
                kind = event.get("event", "")

                if kind == "on_tool_start":
                    step += 1
                    tool_name = event.get("name", "?")
                    tool_input = event.get("data", {}).get("input", {})
                    # Show what the agent is doing
                    detail = ""
                    if "url" in tool_input:
                        detail = f" → {tool_input['url']}"
                    elif "root" in tool_input:
                        detail = f" → {tool_input['root']}"
                    elif "selector" in tool_input:
                        detail = f" → {tool_input['selector']}"
                    yield f"data: {json.dumps({'type': 'step', 'index': step, 'text': f'{tool_name}{detail}'})}\n\n"

                elif kind == "on_tool_end":
                    tool_name = event.get("name", "?")
                    output = event.get("data", {}).get("output", "")
                    # Truncate long outputs in the log
                    preview = str(output)[:100] + "..." if len(str(output)) > 100 else str(output)
                    yield f"data: {json.dumps({'type': 'tool_done', 'index': step, 'tool': tool_name, 'preview': preview})}\n\n"

                elif kind == "on_chat_model_stream":
                    chunk = event.get("data", {}).get("chunk")
                    if chunk and hasattr(chunk, "content") and isinstance(chunk.content, str) and chunk.content:
                        yield f"data: {json.dumps({'type': 'token', 'text': chunk.content})}\n\n"

        except Exception as e:
            logger.error(f"Agent error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'text': str(e)})}\n\n"

        yield f"data: {json.dumps({'type': 'done', 'steps': step})}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")
