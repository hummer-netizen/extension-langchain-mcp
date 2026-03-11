---
title: "Build a Research Agent That Browses Multiple Pages (LangChain + Webfuse)"
description: "An AI agent that navigates between web pages, extracts data, and presents structured comparisons. LangChain + Webfuse MCP. Watch the research happen live."
shortTitle: "LangChain Research Agent + Webfuse"
created: 2026-03-11
category: ai-agents
authorId: nicholas-piel
tags: ["langchain", "langgraph", "mcp", "browser-automation", "webfuse", "research"]
featurePriority: 0
relatedLinks:
  - text: "OpenAI Agent + Webfuse"
    href: "/blog/build-an-ai-agent-that-controls-a-live-browser"
    description: "Guided journey demo with the OpenAI Agents SDK."
  - text: "Claude Desktop + Webfuse"
    href: "/blog/connect-claude-to-a-live-browser-with-webfuse-mcp"
    description: "Zero-code setup with Claude Desktop."
  - text: "Session MCP Server Docs"
    href: "https://dev.webfu.se/session-mcp-server/"
    description: "Full reference for the 13 browser tools."
faqs:
  - question: "Does the agent decide which pages to visit?"
    answer: "Yes. You give it a research topic. It plans the approach, picks the pages, and navigates there itself."
  - question: "Can it handle more than two pages?"
    answer: "Yes. Set max_rounds higher and the agent will visit as many pages as it needs."
  - question: "What if the agent goes to the wrong page?"
    answer: "The user watches it happen live. They can intervene, or the agent self-corrects on the next step."
---

Most browser agents work on one page. Open a URL, read it, maybe click something. Done.

But real research means going places. Visiting multiple pages. Comparing what you find. Following links and coming back with answers.

This agent does that.

<TldrBox title="TL;DR">

**A research agent that navigates between pages, extracts data, and writes structured comparisons.** Give it a topic like "Compare Amsterdam and Rotterdam." Watch it visit both Wikipedia pages, read the infoboxes, and present the results.

Source: [github.com/hummer-netizen/extension-langchain-mcp](https://github.com/hummer-netizen/extension-langchain-mcp)

</TldrBox>

## The Demo

Type a research topic: "Compare Amsterdam and Rotterdam: population, area, and top attractions."

The agent:

1. Plans its approach (which pages to visit, what to look for)
2. Navigates to Amsterdam's Wikipedia page
3. Reads the infobox and relevant sections
4. Navigates to Rotterdam's Wikipedia page
5. Reads the same data points
6. Presents a structured comparison

You watch it happen. The browser navigates, scrolls, reads. When the agent switches from Amsterdam to Rotterdam, you see the page change. Real browsing, real research.

## Why Multi-Page Matters

Single-page agents are impressive demos. But most real tasks require crossing pages.

"Find me the best deal" means visiting multiple stores. "Research these competitors" means reading multiple sites. "Plan my trip" means checking flights, hotels, and activities across different platforms.

The moment your agent can navigate between pages, the number of useful tasks explodes.

## The Agent

The server is a single Python file. One endpoint. The agent gets a topic and a browser session, plans its research, and executes step by step.

```python
SYSTEM = """You are a research agent with access to a live browser.
Work step by step:
1. Navigate to the first subject's page
2. Extract the requested data points
3. Navigate to the second subject's page
4. Extract the same data points
5. Present a clear comparison"""
```

The rest is the MCP connection (same 5 lines as every other integration) and a loop that lets the agent chain tool calls until it's done.

The agent decides which tools to use, which pages to visit, and when it has enough data. You just give it a topic.

::ArticleSignupCta
---
heading: "Build agents that research across the web"
subtitle: "Webfuse gives your AI agent a real browser. Navigate, read, compare — across any number of pages."
---
::

## What Users See

A sidebar with a text field and a research log. Type a topic. Hit "Start Research." Watch the entries appear as the agent works:

```
Step 1: Planning research...
Step 2: Tools: navigate, see_domSnapshot
Step 3: Tools: see_domSnapshot
Step 4: Tools: navigate, see_domSnapshot
...
✅ Research complete

Amsterdam vs Rotterdam:
Population: 933,680 vs 664,311
Area: 219.32 km² vs 325.79 km²
...
```

Each step shows which tools the agent called. The browser moves in real time. When the research is done, you get a clean comparison.

## Beyond Wikipedia

The demo uses Wikipedia because it's clean and public. But the pattern works for anything:

- **Product research.** "Compare the pricing pages of Slack, Discord, and Teams."
- **Job hunting.** "Find Python developer roles at these five companies."
- **Market research.** "What do these three competitors say about their enterprise plan?"
- **Travel planning.** "Check flight prices from Amsterdam to Barcelona on these airlines."

Same agent. Same MCP tools. Different pages.

## Source Code

Everything is on GitHub: [hummer-netizen/extension-langchain-mcp](https://github.com/hummer-netizen/extension-langchain-mcp)

- `agent/agent.py` -- Research agent server
- `extension/` -- Webfuse sidebar extension
- `blog/` -- This blog post
