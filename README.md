# LangChain/LangGraph + Webfuse MCP, Research Agent

A multi-step research agent that compares data across web pages. Built with [LangGraph](https://langchain-ai.github.io/langgraph/) and [Webfuse MCP](https://webfuse.com).

## What It Does

Enter a research topic. The agent plans its approach, navigates to multiple web pages, extracts data with targeted CSS selectors, and delivers a structured comparison. You watch every step happen live in your browser.

**Example:** "Compare Amsterdam and Rotterdam: population, area, and top attractions"

The agent visits Wikipedia for each city, reads the infoboxes, extracts the numbers, and presents a side-by-side comparison.

## Quick Start

```bash
cd agent
pip install -r requirements.txt
cp ../.env.example .env  # Add OPENAI_API_KEY + WEBFUSE_REST_KEY
uvicorn agent:app --port 8082
```

Deploy `extension/` to your Webfuse Space. Set `AGENT_URL` to your server URL.

See [SETUP.md](SETUP.md) for the full guide.

## Architecture

```
Webfuse Extension (sidebar)     FastAPI Agent Server       Webfuse MCP

  Research topic    →POST→     /research                   
  Stream events     ←SSE←      LangGraph ReAct agent        
                                  ↓ tool calls              
                               navigate() ──────────→   session-mcp.webfu.se
                               see_dom_snapshot() ──→   13 browser tools
                               act_click() ─────────→   live browser session
```

The agent uses LangGraph's `create_react_agent` with async tool wrappers that call Webfuse MCP tools via Streamable HTTP. Each tool call streams as a progress event to the sidebar UI.

## What Makes This Different

Other integration demos show single-page interactions. This one is about **multi-page reasoning**:

- The agent plans which pages to visit
- Navigates between them, extracting comparable data
- Uses targeted CSS selectors (`.infobox`, `table.wikitable`) to avoid context overflow
- Presents a structured comparison with citations

This is the LangChain/LangGraph pattern: chains of reasoning with tool use. Webfuse makes the browser one of those tools.

## Example Research Topics

- "Compare Amsterdam and Rotterdam: population, area, and top attractions"
- "Compare the features of Next.js and Remix"
- "Research Python vs Rust for web backends: performance, ecosystem, learning curve"
- "Compare pricing and features of Notion vs Confluence"
- "Find the tallest buildings in New York and compare them to Dubai"

## The 7 Agent Tools

| Tool | MCP Tool | What it does |
|------|----------|-------------|
| `navigate` | `navigate` | Go to a URL |
| `see_dom_snapshot` | `see_domSnapshot` | Read page HTML (with CSS selector scoping) |
| `see_accessibility_tree` | `see_accessibilityTree` | Read page structure |
| `act_click` | `act_click` | Click an element |
| `act_scroll` | `act_scroll` | Scroll the page |
| `act_type` | `act_type` | Type into form fields |
| `act_key_press` | `act_keyPress` | Press keyboard keys |

The agent has 7 of the 13 available MCP tools, the ones needed for research workflows. Add more by extending `make_tools()` in `agent.py`.

## Swap the LLM

```python
# OpenAI (default)
from langchain_openai import ChatOpenAI
llm = ChatOpenAI(model="gpt-4o")

# Anthropic
from langchain_anthropic import ChatAnthropic
llm = ChatAnthropic(model="claude-sonnet-4-20250514")

# Google
from langchain_google_genai import ChatGoogleGenerativeAI
llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash")
```

Same Webfuse tools work across all providers.

## Links

- [Blog Post](blog/draft.md)
- [Webfuse](https://webfuse.com), AI browser actuation platform
- [LangGraph Docs](https://langchain-ai.github.io/langgraph/), Agent framework
- [Session MCP Server Docs](https://dev.webfu.se/session-mcp-server/), Full tool reference



## Other Webfuse Integrations

Webfuse MCP works with any AI framework:

- **[OpenAI Agents SDK](https://github.com/webfuse-com/extension-openai-agents-mcp)** - Python agent with browser control
- **[Claude Desktop / Cursor / VS Code](https://github.com/webfuse-com/extension-claude-mcp)** - Zero-code MCP config
- **[LangChain / LangGraph](https://github.com/webfuse-com/extension-langchain-mcp)** - Multi-page research agent
- **[Vercel AI SDK](https://github.com/webfuse-com/extension-vercel-ai-mcp)** - Next.js browsing assistant
- **[LiveKit Voice Agent](https://github.com/webfuse-com/extension-livekit-mcp)** - Voice-controlled browser
- **[ChatGPT GPT](https://github.com/webfuse-com/chatgpt-webfuse-mcp)** - Custom GPT with browser tools
- **[WebMCP Demo](https://github.com/webfuse-com/webfuse-webmcp-demo)** - Semantic tools on any website

## License

MIT
