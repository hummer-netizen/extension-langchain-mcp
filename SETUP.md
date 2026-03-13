# Setup Guide

## Prerequisites

- Python 3.10+
- OpenAI API key
- Webfuse account with a Space REST key

## 1. Install Dependencies

```bash
cd agent
pip install -r requirements.txt
```

## 2. Configure Environment

```bash
export OPENAI_API_KEY=sk-...
export WEBFUSE_REST_KEY=rk_...
```

Or create `agent/.env` and use `python-dotenv`.

## 3. Run the Agent Server

```bash
cd agent
uvicorn agent:app --port 8082
```

> **Note:** `uvicorn` doesn't auto-load `.env` files. Either export variables first (step 2) or add `python-dotenv` to your code. If you use a `.env` file, load it with: `export $(grep -v '^#' .env | grep -v '^$' | xargs) && uvicorn agent:app --port 8082`

Test it:
```bash
curl http://localhost:8082/health
# {"status":"ok"}
```

## 4. Deploy the Extension

Deploy the `extension/` directory to your Webfuse Space.

Set the `AGENT_URL` environment variable in the extension manifest to your agent server URL (e.g. `https://your-server.com` or use a tunnel like `ngrok http 8082`).

## 5. Try It

1. Open your Webfuse Space in a browser
2. The Research Agent sidebar will open
3. Enter a topic like: "Compare the populations of Tokyo and New York"
4. Click "Start Research"
5. Watch the agent navigate between Wikipedia pages and extract data

## How It Works

```
User enters topic
       ↓
Extension sidebar → POST /research → Agent server
       ↓
LangGraph ReAct agent (GPT-4o)
       ↓ ← tool calls via MCP
Webfuse browser session
  navigate → see_domSnapshot → navigate → see_domSnapshot
       ↓
Structured comparison streamed back to sidebar
```

The agent uses LangGraph's `create_react_agent` with async tool wrappers that call Webfuse MCP tools via HTTP. Each tool call is visible as a step in the sidebar, and the final response streams token-by-token.

## Customization

- **Change the LLM:** Swap `ChatOpenAI` for any LangChain-compatible model (Anthropic, Gemini, etc.)
- **Add more tools:** The agent has 7 tools by default. Add `see_guiSnapshot` for screenshots, or create custom tools
- **Adjust the system prompt:** Edit `SYSTEM_PROMPT` in `agent.py` to change research strategy
- **Increase max rounds:** LangGraph handles looping automatically — the agent runs until it's done
