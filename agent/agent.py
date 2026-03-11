"""
LangGraph research agent — compares data across multiple Wikipedia pages.

Connects to Webfuse Session MCP for browser control. The agent plans a
research strategy, visits multiple pages, extracts data, and writes a
comparison. Each step is visible in the user's browser.

Usage:
  OPENAI_API_KEY=sk-... WEBFUSE_REST_KEY=rk_... uvicorn agent:app --port 8082
"""

import os, json, httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

MCP_URL = "https://session-mcp.webfu.se/mcp"
OPENAI_URL = "https://api.openai.com/v1/responses"

class ResearchRequest(BaseModel):
    session_id: str
    topic: str = "Compare Amsterdam and Rotterdam: population, area, and top attractions"

SYSTEM = """You are a research agent with access to a live browser. You can navigate to pages,
read content, click links, and scroll. Your job is to research a topic by visiting multiple pages,
extracting specific data, and presenting a structured comparison.

Work step by step:
1. Navigate to the first subject's page
2. Extract the requested data points
3. Navigate to the second subject's page
4. Extract the same data points
5. Present a clear comparison

Be systematic. Read the relevant sections. Report facts, not guesses."""

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/research")
async def research(req: ResearchRequest):
    api_key = os.environ["OPENAI_API_KEY"]
    rest_key = os.environ["WEBFUSE_REST_KEY"]

    async def stream():
        yield f"data: {json.dumps({'type': 'status', 'text': 'Planning research...'})}\n\n"

        mcp_tool = {
            "type": "mcp",
            "server_label": "webfuse",
            "server_url": MCP_URL,
            "require_approval": "never",
            "headers": {"Authorization": f"Bearer {rest_key}"},
        }

        payload = {
            "model": "gpt-4o",
            "input": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": f"Session ID for all tools: {req.session_id}\n\n{req.topic}"},
            ],
            "tools": [mcp_tool],
            "truncation": "auto",
        }

        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

        step = 0
        max_rounds = 8

        async with httpx.AsyncClient(timeout=120) as client:
            for _ in range(max_rounds):
                step += 1
                yield f"data: {json.dumps({'type': 'step', 'index': step, 'text': f'Research step {step}...'})}\n\n"

                resp = await client.post(OPENAI_URL, json=payload, headers=headers)
                result = resp.json()

                # Extract tool calls and text from output
                tools_used = []
                final_text = ""
                for item in result.get("output", []):
                    if item.get("type") == "mcp_call":
                        tools_used.append(item.get("name", "?"))
                    if item.get("type") == "message":
                        for c in item.get("content", []):
                            if c.get("type") == "output_text":
                                final_text += c["text"]

                if tools_used:
                    yield f"data: {json.dumps({'type': 'tools', 'index': step, 'tools': ', '.join(tools_used)})}\n\n"

                # If model wants more tool calls, continue the conversation
                if result.get("status") == "incomplete":
                    payload["input"] = result["output"]
                    payload["previous_response_id"] = result["id"]
                    continue

                # Done
                if final_text:
                    yield f"data: {json.dumps({'type': 'result', 'text': final_text})}\n\n"
                break

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")
