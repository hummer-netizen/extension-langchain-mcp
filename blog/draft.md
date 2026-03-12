---
title: "How to Connect LangChain to a Live Browser with Webfuse MCP"
description: "Give your LangChain agent a real browser. Connect LangGraph to Webfuse via MCP for human-in-the-loop web automation. Python tutorial with full source code."
shortTitle: "LangChain + Webfuse MCP"
created: 2026-03-11
category: ai-agents
authorId: nicholas-piel
tags: ["langchain", "langgraph", "mcp", "browser-automation", "webfuse", "python", "human-in-the-loop", "ai-agent"]
featurePriority: 0
relatedLinks:
  - text: "OpenAI Agent + Webfuse"
    href: "/blog/build-an-ai-agent-that-controls-a-live-browser"
    description: "Same concept with the OpenAI Agents SDK."
  - text: "Vercel AI SDK + Webfuse"
    href: "/blog/build-a-browsing-assistant-with-vercel-ai-sdk-and-webfuse"
    description: "TypeScript version for Next.js apps."
  - text: "Claude Desktop + Webfuse"
    href: "/blog/connect-claude-to-a-live-browser-with-webfuse-mcp"
    description: "Zero-code setup with Claude Desktop."
  - text: "Session MCP Server Docs"
    href: "https://dev.webfu.se/session-mcp-server/"
    description: "Full reference for the 13 browser tools."
faqs:
  - question: "Does the user need to install anything?"
    answer: "No. The browser runs inside a Webfuse session. Users open a link and get a full browser with your agent's sidebar. Nothing to install."
  - question: "Can I use LangChain without LangGraph?"
    answer: "Yes. The MCP tools are regular LangChain tools. You can use them with any LangChain agent setup or even just call them directly."
  - question: "Does the agent see the user's real browser?"
    answer: "Yes. Webfuse sessions run in the user's live browser with their cookies, auth, and state. The agent sees exactly what the user sees."
  - question: "What about authentication and security?"
    answer: "Each Webfuse session is isolated. The agent can only control the tab it's connected to. REST key auth keeps your MCP endpoint private."
  - question: "Can the user intervene while the agent works?"
    answer: "Yes. The user watches the agent browse in real time. They can scroll, click, or navigate at any point. That's the human-in-the-loop."
---

LangChain is great at reasoning. But when your agent needs to interact with a website, you're stuck stitching together Playwright scripts, managing headless browsers, and hoping nothing breaks.

What if you could give your LangChain agent a real browser in three lines of code?

<TldrBox title="TL;DR">

**Connect LangChain to a live browser via Webfuse MCP.** Your agent gets tools to navigate, read pages, click, type, and scroll. The user watches it happen. Human-in-the-loop by default.

Source: [github.com/hummer-netizen/extension-langchain-mcp](https://github.com/hummer-netizen/extension-langchain-mcp)

Live demo: [webfu.se/+langchain-mcp/](https://webfu.se/+langchain-mcp/)

</TldrBox>

## Why Webfuse MCP Instead of Playwright?

Playwright runs a headless browser on your server. The user can't see what's happening. If something goes wrong, you find out from logs.

Webfuse runs in the **user's live browser**. The agent browses, and the user watches. Real cookies. Real auth. Real state. If the agent takes a wrong turn, the user just says so.

That's not a nice-to-have. For any web journey that involves real accounts (booking, shopping, admin tasks), headless browsers don't work because they don't have the user's session. Webfuse does.

## The Connection: MCP

Your LangChain agent connects to Webfuse through the [Session MCP Server](https://dev.webfu.se/session-mcp-server/). MCP (Model Context Protocol) is an open standard for connecting AI to tools. Webfuse exposes 13 browser tools through it:

- **navigate** — go to a URL
- **see_domSnapshot** — read page content by CSS selector
- **act_click**, **act_type**, **act_keyPress** — interact with elements
- **act_scroll** — scroll the page
- And more (screenshots, accessibility info, waiting)

Your agent calls these tools through MCP. Webfuse executes them in the user's browser. You never touch a browser binary.

## Connecting LangChain to Webfuse MCP

Here's the core pattern. Three things: an MCP client, LangChain tools that wrap it, and an agent.

### Step 1: MCP Client

The MCP client handles the connection to Webfuse:

```python
import httpx, json

MCP_URL = "https://session-mcp.webfu.se/mcp"

class MCPSession:
    def __init__(self, rest_key: str, session_id: str):
        self.session_id = session_id
        self.headers = {
            "Authorization": f"Bearer {rest_key}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        self.client = httpx.AsyncClient(timeout=60)

    async def initialize(self):
        """Handshake with the MCP server."""
        resp = await self.client.post(MCP_URL, json={
            "jsonrpc": "2.0", "id": 0, "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "my-agent", "version": "1.0"},
            },
        }, headers=self.headers)

        # Store the session ID for subsequent calls
        mcp_sid = resp.headers.get("mcp-session-id", "")
        if mcp_sid:
            self.headers["mcp-session-id"] = mcp_sid

    async def call(self, tool_name: str, args: dict) -> str:
        """Call any MCP tool and return the text result."""
        args["session_id"] = self.session_id
        resp = await self.client.post(MCP_URL, json={
            "jsonrpc": "2.0", "id": 1,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": args},
        }, headers=self.headers)

        # Parse the result
        data = resp.json()
        content = data.get("result", {}).get("content", [])
        return "\n".join(c["text"] for c in content if c.get("type") == "text")
```

The `session_id` ties every tool call to the user's specific browser tab. That's how the agent knows which browser to control.

### Step 2: LangChain Tools

Wrap the MCP calls as LangChain tools. Each tool is a thin wrapper:

```python
from langchain_core.tools import tool

def make_tools(mcp: MCPSession):

    @tool
    async def navigate(url: str) -> str:
        """Navigate the browser to a URL."""
        return await mcp.call("navigate", {"url": url})

    @tool
    async def read_page(root: str = "body") -> str:
        """Read page content. Use a CSS selector: '.infobox', '#pricing', 'h1'."""
        return await mcp.call("see_domSnapshot", {"options": {"root": root}})

    @tool
    async def click(target: str) -> str:
        """Click an element by CSS selector."""
        return await mcp.call("act_click", {"target": target})

    @tool
    async def type_text(target: str, text: str) -> str:
        """Type text into a form field."""
        return await mcp.call("act_type", {"target": target, "text": text})

    return [navigate, read_page, click, type_text]
```

You choose which MCP tools to expose to your agent. Expose all 13 for a general-purpose browser agent, or just 2-3 for a focused automation.

### Step 3: The Agent

Plug the tools into a LangGraph ReAct agent:

```python
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.prebuilt import create_react_agent

llm = ChatOpenAI(model="gpt-4o", temperature=0)
tools = make_tools(mcp)
agent = create_react_agent(llm, tools)

result = await agent.ainvoke({
    "messages": [
        SystemMessage(content="You are a browsing assistant."),
        HumanMessage(content="What is on this page?"),
    ]
})
```

That's it. The agent decides when to navigate, what to read, what to click. LangGraph handles the tool call loop. Webfuse executes in the browser.

## Human-in-the-Loop: Built In, Not Bolted On

Most agent frameworks treat human-in-the-loop as an advanced feature you opt into. With Webfuse, it's the default.

The user sees everything the agent does because the agent is working in **their browser**. Navigate to a page? The user sees it load. Click a button? The user sees the click. Read a table? The user can read along.

This changes the trust equation. Users don't need to blindly trust agent output. They watch the work happen and can course-correct in real time.

For web journeys that matter (booking, purchasing, filling forms), this isn't optional. You need the human watching.

## Production Tips

A few things we learned building the demo that'll save you time:

**Truncate tool results.** Web pages can be huge. A full Wikipedia article returns 700K+ tokens of HTML. Cap your tool results at 15-25K characters and tell the agent to use narrower CSS selectors.

```python
MAX_CHARS = 25000

def truncate(text, label):
    if len(text) <= MAX_CHARS:
        return text
    return text[:MAX_CHARS] + f"\n[Truncated. Use a narrower selector than '{label}'.]"
```

**Sanitize CSS selectors.** LLMs love pseudo-selectors (`:nth-child`, `:first-of-type`). The Webfuse CSS parser doesn't support them. Strip them before they hit the MCP server:

```python
import re

def sanitize_selector(selector):
    s = re.sub(r':{1,2}[a-zA-Z-]+(\([^)]*\))?', '', selector)  # :pseudo
    s = re.sub(r'\s*[~+]\s*', ' ', s)  # sibling combinators
    return s.strip() or 'body'
```

**Disable parallel tool calls.** Your agent controls one browser tab. Parallel `navigate` calls will cancel each other. Force sequential execution:

```python
llm = ChatOpenAI(
    model="gpt-4o",
    model_kwargs={"parallel_tool_calls": False}
)
```

**Stream progress to the user.** Long research tasks need feedback. Use LangGraph's `astream_events` to send step-by-step updates:

```python
async for event in agent.astream_events(messages, version="v2"):
    if event["event"] == "on_tool_start":
        yield f"🔧 {event['name']}"
    elif event["event"] == "on_tool_end":
        yield f"✓ {event['name']} done"
```

## Beyond the Demo

The research agent demo compares Wikipedia pages. But the pattern works for any web journey:

- **Internal tools.** "Check our Salesforce dashboard and summarize this week's pipeline."
- **Authenticated flows.** "Log into our supplier portal and check delivery status for order #4521."
- **Multi-step forms.** "Fill out this insurance quote form with these details."
- **Competitive research.** "Visit these three competitor pricing pages and compare them."

Same tools. Same pattern. The agent uses `navigate`, `read_page`, `click`, and `type_text`. Your system prompt defines the journey.

::ArticleSignupCta
---
heading: "Give your LangChain agent a browser"
subtitle: "Webfuse connects LangChain to live web sessions via MCP. Build browser agents that work in the user's real browser."
---
::

## Full Source Code

Everything is on GitHub: [hummer-netizen/extension-langchain-mcp](https://github.com/hummer-netizen/extension-langchain-mcp)

- `agent/agent.py` — FastAPI server with MCP client, tools, and LangGraph agent
- `extension/` — Webfuse sidebar extension (research UI)
- `blog/` — This blog post

Try the live demo at [webfu.se/+langchain-mcp/](https://webfu.se/+langchain-mcp/) — type a research topic, watch the agent browse.
