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

# Max chars for DOM snapshots before truncation
MAX_SNAPSHOT_CHARS = 25000


# --- MCP tool wrappers ---

async def _mcp_call(tool_name: str, args: dict, rest_key: str, session_id: str = "") -> str:
    """Call a Webfuse MCP tool via Streamable HTTP."""
    async with httpx.AsyncClient(timeout=60) as client:
        try:
            base_headers = {
                "Authorization": f"Bearer {rest_key}",
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            }

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
                headers=base_headers,
            )

            mcp_sid = init_resp.headers.get("mcp-session-id", "")
            if mcp_sid:
                base_headers["mcp-session-id"] = mcp_sid

            await client.post(
                MCP_URL,
                json={"jsonrpc": "2.0", "method": "notifications/initialized"},
                headers=base_headers,
            )

            if session_id:
                args["session_id"] = session_id

            logger.info(f"MCP call: {tool_name} args={args}")

            resp = await client.post(
                MCP_URL,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {"name": tool_name, "arguments": args},
                },
                headers=base_headers,
            )

            data = None
            resp_text = resp.text
            for line in resp_text.split("\n"):
                if line.startswith("data:"):
                    try:
                        data = json.loads(line[5:].strip())
                    except json.JSONDecodeError:
                        continue

            if data is None:
                try:
                    data = resp.json()
                except:
                    return f"Error: Could not parse MCP response: {resp_text[:200]}"

            if "error" in data:
                return f"Error: {data['error'].get('message', 'unknown error')}"

            result = data.get("result", {})
            content_items = result.get("content", [])
            texts = [c.get("text", "") for c in content_items if c.get("type") == "text"]
            return "\n".join(texts) if texts else json.dumps(result)

        except httpx.TimeoutException:
            return "Error: MCP tool call timed out (60s). Try a more focused selector."
        except Exception as e:
            logger.error(f"MCP call failed: {e}")
            return f"Error: {str(e)}"


def _truncate_snapshot(text: str, root: str) -> str:
    """Truncate large snapshots and append guidance for the agent."""
    if len(text) <= MAX_SNAPSHOT_CHARS:
        return text

    truncated = text[:MAX_SNAPSHOT_CHARS]
    # Try to cut at last complete line
    last_newline = truncated.rfind('\n')
    if last_newline > MAX_SNAPSHOT_CHARS * 0.8:
        truncated = truncated[:last_newline]

    guidance = (
        f"\n\n--- TRUNCATED ({len(text):,} chars total, showing first {len(truncated):,}) ---\n"
        f"The snapshot for '{root}' is too large. To get the data you need:\n"
        f"1. Use see_accessibility_tree to find the right section heading or landmark\n"
        f"2. Then call see_dom_snapshot with a more specific CSS selector, e.g.:\n"
        f"   - 'table.wikitable' for data tables\n"
        f"   - '.infobox' for summary boxes\n"
        f"   - 'h2 + table' for a table after a specific heading\n"
        f"   - '#section-name' for a specific section\n"
    )
    return truncated + guidance


def make_tools(rest_key: str, session_id: str = ""):
    """Create LangChain tool wrappers for Webfuse MCP tools."""

    @tool
    async def navigate(url: str) -> str:
        """Navigate the browser to a URL. Use for visiting pages to research."""
        return await _mcp_call("navigate", {"url": url}, rest_key, session_id)

    @tool
    async def see_dom_snapshot(root: str = "body") -> str:
        """Read page content scoped by a CSS selector.
        IMPORTANT: Always start with a NARROW selector to avoid context overflow.
        Good: '.infobox', 'table.wikitable', '#specific-id', '.some-class'
        Bad: 'body', 'main', '#content' (these are usually too large)
        NOT supported: pseudo-selectors like :first-of-type, :nth-child, :contains
        If you're not sure which selector to use, call see_accessibility_tree FIRST."""
        result = await _mcp_call("see_domSnapshot", {"options": {"root": root}}, rest_key, session_id)
        return _truncate_snapshot(result, root)

    @tool
    async def page_overview() -> str:
        """Get a compact overview of the current page: all section headings (h2, h3) and the infobox if present.
        ALWAYS call this FIRST on a new page to understand the structure.
        Use the headings to identify which section contains the data you need,
        then call see_dom_snapshot with a targeted CSS selector."""
        parts = []
        
        # Try Table of Contents first (compact list of all sections)
        toc = await _mcp_call("see_domSnapshot", {"options": {"root": "#toc"}}, rest_key, session_id)
        if toc and "Error" not in toc and len(toc) > 20:
            parts.append("=== TABLE OF CONTENTS ===\n" + toc)
        
        # Try infobox (common on Wikipedia — has key facts)
        infobox = await _mcp_call("see_domSnapshot", {"options": {"root": ".infobox"}}, rest_key, session_id)
        if infobox and "Error" not in infobox and len(infobox) > 20:
            parts.append("=== INFOBOX ===\n" + infobox)
        
        # If no TOC found, get a low-quality snapshot of the whole page for structure
        if not parts:
            overview = await _mcp_call("see_domSnapshot", {"options": {"root": "body", "quality": 0.1}}, rest_key, session_id)
            parts.append("=== PAGE OVERVIEW (low detail) ===\n" + overview)
        
        result = "\n\n".join(parts)
        return _truncate_snapshot(result, "page-overview")

    @tool
    async def see_screenshot() -> str:
        """Take a screenshot of the current page. Returns a visual overview.
        Useful when DOM snapshots are too large or when you need to understand page layout."""
        return await _mcp_call("see_guiSnapshot", {"options": {"quality": 0.3}}, rest_key, session_id)

    @tool
    async def act_click(target: str) -> str:
        """Click an element by CSS selector or text content."""
        return await _mcp_call("act_click", {"target": target}, rest_key, session_id)

    @tool
    async def act_scroll(target: str = "html", amount: int = 500) -> str:
        """Scroll an element by pixel amount. Positive = down, negative = up. Use 'html' for full page."""
        return await _mcp_call("act_scroll", {"target": target, "amount": amount}, rest_key, session_id)

    @tool
    async def act_type(target: str, text: str) -> str:
        """Type text into a form field by CSS selector."""
        return await _mcp_call("act_type", {"target": target, "text": text}, rest_key, session_id)

    @tool
    async def act_key_press(target: str, key: str) -> str:
        """Press a keyboard key on a target element (Enter, Tab, Escape, etc.)."""
        return await _mcp_call("act_keyPress", {"target": target, "key": key}, rest_key, session_id)

    return [navigate, see_dom_snapshot, page_overview, see_screenshot,
            act_click, act_scroll, act_type, act_key_press]


SYSTEM_PROMPT = """You are a research agent with access to a live browser via Webfuse.
Your job: research a topic by visiting multiple web pages, extracting data, and comparing findings.

MANDATORY WORKFLOW for each page:
1. Navigate to the page
2. Call page_overview FIRST — this returns all section headings and the infobox (if any)
3. Identify which section contains the data you need based on the headings
4. Call see_dom_snapshot with a NARROW selector to get that specific section
5. If the snapshot is truncated, use an even narrower selector — never retry with the same one
6. Use see_screenshot if you need a visual overview of the page layout

SELECTOR STRATEGY (critical for avoiding context overflow):
- Wikipedia infoboxes: '.infobox' or '.infobox-data'
- Wikipedia data tables: 'table.wikitable'
- Specific sections: find the heading ID in the a11y tree, then use '#section-id' or nearby elements
- NEVER use 'body', 'main', or '#content' as your first attempt — these overflow on any real page
- DO NOT use CSS pseudo-selectors (:first-of-type, :nth-child, :contains, etc.) — they are not supported

RESEARCH RULES:
- Always cite which page each fact came from
- If data isn't available on a page, say so rather than guessing
- Navigate between pages rather than trying to open multiple tabs
- Present a STRUCTURED comparison with clear categories and data points
- Format results with markdown tables when comparing structured data
- When ranking or comparing items with a "Rank" column, ALWAYS sort the table by the most relevant numeric metric (height, population, revenue, etc.) in descending order. The rank should reflect the actual sorted order."""


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
        tools = make_tools(rest_key, req.session_id)
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
                    detail = ""
                    if "url" in tool_input:
                        detail = f" → {tool_input['url']}"
                    elif "root" in tool_input:
                        detail = f" → {tool_input['root']}"
                    elif "target" in tool_input:
                        detail = f" → {tool_input['target']}"
                    yield f"data: {json.dumps({'type': 'step', 'index': step, 'text': f'{tool_name}{detail}'})}\n\n"

                elif kind == "on_tool_end":
                    tool_name = event.get("name", "?")
                    output = event.get("data", {}).get("output", "")
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
