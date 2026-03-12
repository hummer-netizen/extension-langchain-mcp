const AGENT_URL = browser.webfuseSession.env.AGENT_URL || 'http://localhost:8082';
const logEl = document.getElementById('log');
const btn = document.getElementById('btn');
const topicEl = document.getElementById('topic');

function addEntry(cls, text) {
  const el = document.createElement('div');
  el.className = `entry ${cls}`;
  el.textContent = text;
  logEl.appendChild(el);
  logEl.scrollTop = logEl.scrollHeight;
  return el;
}

async function startResearch() {
  btn.disabled = true;
  btn.textContent = '🔍 Researching...';
  logEl.innerHTML = '';

  let sessionId;
  try {
    const info = await browser.webfuseSession.getSessionInfo();
    sessionId = info.sessionId;
  } catch (e) {
    addEntry('status', '❌ Could not get session: ' + e.message);
    btn.disabled = false; btn.textContent = '🔍 Start Research';
    return;
  }

  addEntry('status', `Session: ${sessionId.substring(0, 12)}...`);

  let resultEl = null;

  try {
    const resp = await fetch(`${AGENT_URL}/research`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, topic: topicEl.value }),
    });

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
          if (event.type === 'status') addEntry('status', event.text);
          if (event.type === 'step') addEntry('step', `Step ${event.index}: ${event.text}`);
          if (event.type === 'tools') addEntry('tools', `✓ ${event.tools}`);
          if (event.type === 'token') {
            // Stream tokens into a result entry
            if (!resultEl) resultEl = addEntry('result', '');
            resultEl.textContent += event.text;
            logEl.scrollTop = logEl.scrollHeight;
          }
          if (event.type === 'done') addEntry('done', '✅ Research complete');
        } catch {}
      }
    }
  } catch (e) {
    addEntry('status', '❌ ' + e.message);
  }

  btn.disabled = false;
  btn.textContent = '🔍 Research Again';
}

browser.sidePanel.open();
