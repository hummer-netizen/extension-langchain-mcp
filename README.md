# LangChain + Webfuse MCP

An AI research agent that compares data across multiple web pages.

Give it a research topic. It navigates to different pages, extracts specific data points, and presents a structured comparison. You watch the research happen in your browser.

## Quick Start

```bash
cd agent
pip install fastapi uvicorn httpx
OPENAI_API_KEY=sk-... WEBFUSE_REST_KEY=rk_... uvicorn agent:app --port 8082
```

Deploy `extension/` to your Webfuse Space.

## What Makes This Different

The other demos (OpenAI, Claude, Vercel) work on a single page. This one crosses pages.

"Compare Amsterdam and Rotterdam" — the agent navigates to Amsterdam's Wikipedia page, reads the infobox, then navigates to Rotterdam's page, reads the same data, and writes a comparison. Multiple pages, one task.

## Architecture

```
Extension Sidebar          Agent Server (Python)

  Research topic  --POST-->  /research
  "Compare X & Y"           
                             OpenAI API + MCP
  Live updates    <--SSE--   Navigate → Read → Navigate → Read
  per step                   → Compare → Report
```

## Links

- [Blog Post](/blog/build-a-research-agent-with-langchain-and-webfuse)
- [Webfuse](https://webfuse.com)
- [Session MCP Server Docs](https://dev.webfu.se/session-mcp-server/)
