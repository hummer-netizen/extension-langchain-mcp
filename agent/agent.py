"""
LangGraph research agent — compares data across multiple web pages.

Uses LangGraph's ReAct agent pattern with Webfuse Session MCP tools.
The agent plans research, visits pages, extracts data, and compares.

Usage:
  pip install -r requirements.txt
  OPENAI_API_KEY=sk-... WEBFUSE_REST_KEY=rk_... uvicorn agent:app --port 8082
"""

import os, json, httpx, asyncio
from typing import Any
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.prebuilt import create_react_agent

app = FastAPI()
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

MCP_URL = "https://session-mcp.webfu.se/mcp"


# --- MCP tool wrappers ---
# These wrap the Webfuse Session MCP tools as LangChain tools.

async def _mcp_call(tool_name: str, args: dict, rest_key: str) -> str:
    """Call a Webfuse MCP tool via HTTP."""
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            MCP_URL,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": tool_name, "arguments": args},
            },
            headers={
                "Authorization": f"Bearer {rest_key}",
                "Content-Type": "application/json",
            },
        )
        data = resp.json()
        result = data.get("result", {})
        # MCP returns content array
        content = result.get("content", [])
        texts = [c.get("text", "") for c in content if c.get("type") == "text"]
        return "\n".join(texts) if texts else json.dumps(result)


def make_tools(rest_key: str):
    """Create LangChain tool wrappers for Webfuse MCP tools."""

    @tool
    async def navigate(url: str) -> str:
        """Navigate the browser to a URL."""
        return await _mcp_call("navigate", {"url": url}, rest_key)

    @tool
    async def see_dom_snapshot(root: str = "body") -> str:
        """Read the page DOM structure. Use a CSS selector for `root` to scope (e.g. '.infobox', 'main', 'h1')."""
        return await _mcp_call("see_domSnapshot", {"root": root}, rest_key)

    @tool
    async def see_accessibility_tree() -> str:
        """Read the page accessibility tree for structured content."""
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
        """Type text into a form field specified by CSS selector."""
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
1. Navigate to the first subject's page (e.g. Wikipedia)
2. Use see_dom_snapshot with a focused CSS selector (like '.infobox' or 'main') to read key data
3. Navigate to the next subject's page
4. Extract the same data points
5. Present a clear, structured comparison

Tips:
- Use focused CSS selectors to avoid huge DOM dumps. Start with '.infobox' or 'h1' before reading 'body'.
- Be systematic: extract the same data points from each page.
- If a page is too large, scroll and read sections incrementally.
- Report facts from the pages, not guesses."""


class ResearchRequest(BaseModel):
    session_id: str
    topic: str = "Compare Amsterdam and Rotterdam: population, area, and top attractions"


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/research")
async def research(req: ResearchRequest):
    rest_key = os.environ["WEBFUSE_REST_KEY"]

    async def stream():
        yield f"data: {json.dumps({'type': 'status', 'text': 'Setting up agent...'})}\n\n"

        llm = ChatOpenAI(model="gpt-4o", temperature=0)
        tools = make_tools(rest_key)
        agent = create_react_agent(llm, tools)

        yield f"data: {json.dumps({'type': 'status', 'text': 'Starting research...'})}\n\n"

        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=req.topic),
        ]

        step = 0
        async for event in agent.astream_events(
            {"messages": messages}, version="v2"
        ):
            kind = event.get("event", "")

            if kind == "on_tool_start":
                step += 1
                tool_name = event.get("name", "?")
                yield f"data: {json.dumps({'type': 'step', 'index': step, 'text': f'Using {tool_name}...'})}\n\n"

            elif kind == "on_tool_end":
                tool_name = event.get("name", "?")
                yield f"data: {json.dumps({'type': 'tools', 'index': step, 'tools': tool_name})}\n\n"

            elif kind == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk")
                if chunk and hasattr(chunk, "content") and isinstance(chunk.content, str) and chunk.content:
                    yield f"data: {json.dumps({'type': 'token', 'text': chunk.content})}\n\n"

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")
