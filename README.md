# LangChain + Webfuse MCP

An AI research agent that browses multiple web pages, extracts data, and presents structured comparisons.

Built with [LangGraph](https://langchain-ai.github.io/langgraph/) (ReAct agent pattern) + [Webfuse Session MCP](https://dev.webfu.se/session-mcp-server/) for live browser control.

## Quick Start

```bash
cd agent
pip install -r requirements.txt
OPENAI_API_KEY=sk-... WEBFUSE_REST_KEY=rk_... uvicorn agent:app --port 8082
```

Deploy `extension/` to your Webfuse Space. See [SETUP.md](SETUP.md) for the full guide.

## What Makes This Different

The other demos (Claude Desktop, OpenAI, Vercel) work on a single page. This one crosses pages.

"Compare Amsterdam and Rotterdam" — the agent navigates to Amsterdam's Wikipedia page, reads the infobox, then navigates to Rotterdam's page, reads the same data, and writes a structured comparison. Multiple pages, one task, fully autonomous.

## Architecture

```
Extension Sidebar            Agent Server (Python)

  Research topic  --POST-->  /research
  "Compare X & Y"           
                             LangGraph ReAct Agent
  Live updates    <--SSE--   navigate → read → navigate → read
  (steps + tokens)           → compare → stream result
```

The agent uses `create_react_agent` from LangGraph with 7 async tool wrappers that call Webfuse MCP over HTTP. Each tool call shows as a step in the sidebar. The final comparison streams token-by-token.

## Example Topics

- "Compare Amsterdam and Rotterdam: population, area, and top attractions"
- "Compare the pricing pages of Notion and Confluence"
- "Research Python vs Rust for web backends: performance, ecosystem, learning curve"
- "Find the tallest buildings in New York and compare them to Dubai"

## Blog Post

Read the full write-up: [Build a Research Agent That Browses Multiple Pages](blog/draft.md)

## Links

- [Webfuse](https://webfuse.com) — The AI browser actuation platform
- [LangGraph Docs](https://langchain-ai.github.io/langgraph/) — Agent framework
- [Session MCP Server Docs](https://dev.webfu.se/session-mcp-server/) — Browser tool reference

## License

MIT
