"""
LangGraph research agent — compares data across multiple web pages.
Persistent MCP session for fast tool calls.
"""

import os, json, httpx, asyncio, logging
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
MAX_SNAPSHOT_CHARS = 25000


class MCPSession:
    """Persistent MCP session — initialize once, reuse for all tool calls."""

    def __init__(self, rest_key: str, session_id: str):
        self.rest_key = rest_key
        self.session_id = session_id
        self.headers = {
            "Authorization": f"Bearer {rest_key}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        self.client = httpx.AsyncClient(timeout=60)
        self._initialized = False
        self._call_id = 0

    async def initialize(self):
        if self._initialized:
            return
        resp = await self.client.post(
            MCP_URL,
            json={
                "jsonrpc": "2.0", "id": 0, "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "langchain-agent", "version": "1.0"},
                },
            },
            headers=self.headers,
        )
        mcp_sid = resp.headers.get("mcp-session-id", "")
        if mcp_sid:
            self.headers["mcp-session-id"] = mcp_sid
        await self.client.post(
            MCP_URL,
            json={"jsonrpc": "2.0", "method": "notifications/initialized"},
            headers=self.headers,
        )
        self._initialized = True

    async def call(self, tool_name: str, args: dict) -> str:
        await self.initialize()
        if self.session_id:
            args["session_id"] = self.session_id

        self._call_id += 1
        try:
            resp = await self.client.post(
                MCP_URL,
                json={
                    "jsonrpc": "2.0", "id": self._call_id,
                    "method": "tools/call",
                    "params": {"name": tool_name, "arguments": args},
                },
                headers=self.headers,
            )

            data = None
            for line in resp.text.split("\n"):
                if line.startswith("data:"):
                    try:
                        data = json.loads(line[5:].strip())
                    except json.JSONDecodeError:
                        continue
            if data is None:
                try:
                    data = resp.json()
                except:
                    return f"Error: bad response: {resp.text[:200]}"

            if "error" in data:
                return f"Error: {data['error'].get('message', 'unknown')}"

            content = data.get("result", {}).get("content", [])
            texts = [c.get("text", "") for c in content if c.get("type") == "text"]
            return "\n".join(texts) if texts else json.dumps(data.get("result", {}))

        except httpx.TimeoutException:
            return "Error: timeout (60s). Use a narrower CSS selector."
        except Exception as e:
            return f"Error: {e}"

    async def close(self):
        await self.client.aclose()


def _truncate(text: str, label: str) -> str:
    if len(text) <= MAX_SNAPSHOT_CHARS:
        return text
    cut = text[:MAX_SNAPSHOT_CHARS]
    nl = cut.rfind('\n')
    if nl > MAX_SNAPSHOT_CHARS * 0.8:
        cut = cut[:nl]
    return (
        cut + f"\n\n--- TRUNCATED ({len(text):,} chars, showing {len(cut):,}) ---\n"
        f"'{label}' is too large. Use a narrower CSS selector:\n"
        f"  'table.wikitable', '.infobox', '#specific-id'\n"
    )


import re as _re

def _sanitize_selector(selector: str) -> str:
    """Strip CSS features unsupported by Webfuse: pseudo-selectors and sibling combinators."""
    s = _re.sub(r':{1,2}[a-zA-Z-]+(\([^)]*\))?', '', selector)
    s = _re.sub(r'\s*[~+]\s*', ' ', s)
    return s.strip() or 'body'


def make_tools(mcp: MCPSession):

    @tool
    async def navigate(url: str) -> str:
        """Navigate the browser to a URL."""
        return await mcp.call("navigate", {"url": url})


    @tool
    async def page_overview() -> str:
        """Get a compact overview of the current page: table of contents + infobox.
        ALWAYS call this FIRST on a new page before reading specific content."""
        toc = await mcp.call("see_domSnapshot", {"options": {"root": "#toc"}})
        if not toc or "Error" in toc or len(toc) < 30:
            # No TOC — fall back to low-quality body overview
            toc = await mcp.call("see_domSnapshot", {"options": {"root": "body", "quality": 0.1}})
        return _truncate(toc, "page-overview")

    @tool
    async def see_dom_snapshot(root: str = ".infobox") -> str:
        """Read page content scoped by a CSS selector.
        Always use a NARROW selector: '.infobox', 'table.wikitable', '#section-id'
        DO NOT use 'body' or 'main' — they overflow. No pseudo-selectors (:first-of-type etc)."""
        root = _sanitize_selector(root)
        result = await mcp.call("see_domSnapshot", {"options": {"root": root}})
        return _truncate(result, root)

    @tool
    async def act_click(target: str) -> str:
        """Click an element by CSS selector."""
        return await mcp.call("act_click", {"target": target})

    @tool
    async def act_scroll(target: str = "html", amount: int = 500) -> str:
        """Scroll by pixels. Positive=down, negative=up. Use 'html' for full page."""
        return await mcp.call("act_scroll", {"target": target, "amount": amount})

    @tool
    async def act_type(target: str, text: str) -> str:
        """Type text into a form field."""
        return await mcp.call("act_type", {"target": target, "text": text})

    @tool
    async def act_key_press(target: str, key: str) -> str:
        """Press a key (Enter, Tab, Escape, etc.)."""
        return await mcp.call("act_keyPress", {"target": target, "key": key})

    return [navigate, page_overview, see_dom_snapshot,
            act_click, act_scroll, act_type, act_key_press]


SYSTEM_PROMPT = """You are a research agent with a live browser via Webfuse.
Research topics by visiting pages, extracting data, and comparing findings.

CRITICAL: You control ONE browser tab. All tools act on the CURRENT page only.
When comparing multiple subjects, research them ONE AT A TIME:
  1. Navigate to page A, read all needed data, note the facts
  2. Navigate to page B, read all needed data, note the facts
  3. Write your comparison from the collected facts
NEVER call navigate twice in parallel - the second call cancels the first.
NEVER call tools for different pages in the same step.

WORKFLOW for each page:
1. navigate to the page
2. page_overview - get TOC + structure
3. see_dom_snapshot('.infobox') - usually has population, area, key facts
4. Extract what you need from the result and MOVE ON
Do NOT read individual table rows one by one. Read the whole .infobox ONCE.
If it is truncated, that is OK - extract what you can and proceed.
Budget: max 5-6 tool calls per page, then navigate to the next.

SELECTOR RULES:
- Good: '.infobox', 'table.wikitable', '#section-id', '#toc'
- Bad: 'body', 'main' (too large, will be truncated)
- No pseudo-selectors (:first-of-type, :nth-child) - not supported
- No sibling combinators (~ +) - not supported

OUTPUT:
- Cite which page each fact came from
- Use markdown tables for comparisons
- Sort ranked tables by the relevant metric descending
- If data is not available, say so"""


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
    mcp = MCPSession(rest_key, req.session_id)

    async def stream():
        try:
            yield f"data: {json.dumps({'type': 'status', 'text': 'Setting up research agent...'})}\n\n"

            llm = ChatOpenAI(model="gpt-4o", temperature=0, max_tokens=4096, model_kwargs={"parallel_tool_calls": False})
            tools = make_tools(mcp)
            agent = create_react_agent(llm, tools)

            yield f"data: {json.dumps({'type': 'status', 'text': f'Researching: {req.topic}'})}\n\n"

            messages = [
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(content=req.topic),
            ]

            step = 0
            async for event in agent.astream_events(
                {"messages": messages},
                {"recursion_limit": 50},
                version="v2",
            ):
                kind = event.get("event", "")

                if kind == "on_tool_start":
                    step += 1
                    name = event.get("name", "?")
                    inp = event.get("data", {}).get("input", {})
                    detail = ""
                    if "url" in inp: detail = f" → {inp['url']}"
                    elif "root" in inp: detail = f" → {inp['root']}"
                    elif "target" in inp: detail = f" → {inp['target']}"
                    yield f"data: {json.dumps({'type': 'step', 'index': step, 'text': f'{name}{detail}'})}\n\n"

                elif kind == "on_tool_end":
                    name = event.get("name", "?")
                    out = str(event.get("data", {}).get("output", ""))
                    preview = out[:80] + "..." if len(out) > 80 else out
                    yield f"data: {json.dumps({'type': 'tool_done', 'index': step, 'tool': name, 'preview': preview})}\n\n"

                elif kind == "on_chat_model_stream":
                    chunk = event.get("data", {}).get("chunk")
                    if chunk and hasattr(chunk, "content") and isinstance(chunk.content, str) and chunk.content:
                        yield f"data: {json.dumps({'type': 'token', 'text': chunk.content})}\n\n"

        except Exception as e:
            logger.error(f"Agent error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'text': str(e)})}\n\n"
        finally:
            await mcp.close()

        yield f"data: {json.dumps({'type': 'done', 'steps': step})}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")
