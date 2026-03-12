const AGENT_URL = browser.webfuseSession.env.AGENT_URL || 'https://langchain-mcp.webfuse.it';
const logEl = document.getElementById('log');
const btn = document.getElementById('btn');
const topicEl = document.getElementById('topic');
const examplesEl = document.getElementById('examples');

function addEntry(cls, text) {
  const el = document.createElement('div');
  el.className = `entry ${cls}`;
  el.textContent = text;
  logEl.appendChild(el);
  logEl.scrollTop = logEl.scrollHeight;
  return el;
}

// Load example topics
async function loadExamples() {
  try {
    const resp = await fetch(`${AGENT_URL}/examples`);
    const { topics } = await resp.json();
    if (examplesEl && topics) {
      topics.forEach(t => {
        const btn = document.createElement('button');
        btn.className = 'example-btn';
        btn.textContent = t;
        btn.onclick = () => { topicEl.value = t; };
        examplesEl.appendChild(btn);
      });
    }
  } catch (_) {
    // Agent server might not be running yet
  }
}

async function startResearch() {
  btn.disabled = true;
  btn.textContent = '🔍 Researching...';
  logEl.innerHTML = '';

  let sessionId = '';
  try {
    const info = await browser.webfuseSession.getSessionInfo();
    sessionId = info.sessionId || info.session_id || '';
  } catch (e) {
    addEntry('status', '⚠️ No session ID (agent will use default)');
  }

  let resultEl = null;

  try {
    const resp = await fetch(`${AGENT_URL}/research`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, topic: topicEl.value }),
    });

    if (!resp.ok) {
      addEntry('error', `Server error: ${resp.status} ${resp.statusText}`);
      btn.disabled = false; btn.textContent = '🔍 Start Research';
      return;
    }

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop();
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        try {
          const event = JSON.parse(line.slice(6));
          switch (event.type) {
            case 'status':
              addEntry('status', event.text);
              break;
            case 'step':
              addEntry('step', `🔧 Step ${event.index}: ${event.text}`);
              break;
            case 'tool_done':
              addEntry('tool-done', `  ✓ ${event.tool}: ${event.preview || 'done'}`);
              break;
            case 'token':
              if (!resultEl) {
                addEntry('result-header', '📊 Results:');
                resultEl = addEntry('result', '');
              }
              resultEl.textContent += event.text;
              logEl.scrollTop = logEl.scrollHeight;
              break;
            case 'error':
              addEntry('error', `❌ ${event.text}`);
              break;
            case 'done':
              addEntry('done', `✅ Research complete (${event.steps || '?'} tool calls)`);
              break;
          }
        } catch {}
      }
    }
  } catch (e) {
    addEntry('error', '❌ ' + e.message);
  }

  btn.disabled = false;
  btn.textContent = '🔍 Research Again';
}

// Init
loadExamples();
browser.sidePanel.open();
