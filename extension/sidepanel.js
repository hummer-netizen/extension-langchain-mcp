const AGENT_URL = browser.webfuseSession.env.AGENT_URL || 'https://langchain-mcp.webfuse.it';
const logEl = document.getElementById('log');
const btn = document.getElementById('btn');
const topicEl = document.getElementById('topic');
const examplesEl = document.getElementById('examples');

// Open external links via window.open to bypass CSP
document.querySelectorAll('a[data-href]').forEach(a => {
  a.addEventListener('click', (e) => {
    e.preventDefault();
    window.open(a.dataset.href, '_blank');
  });
});

// Simple markdown to HTML renderer
function mdToHtml(md) {
  // Tables
  md = md.replace(/^(\|.+\|)\n(\|[\s:|-]+\|)\n((?:\|.+\|\n?)+)/gm, (_, header, sep, rows) => {
    const ths = header.split('|').filter(c => c.trim()).map(c => `<th>${c.trim()}</th>`).join('');
    const trs = rows.trim().split('\n').map(row => {
      const tds = row.split('|').filter(c => c.trim()).map(c => `<td>${c.trim()}</td>`).join('');
      return `<tr>${tds}</tr>`;
    }).join('');
    return `<table><thead><tr>${ths}</tr></thead><tbody>${trs}</tbody></table>`;
  });

  // Headers
  md = md.replace(/^### (.+)$/gm, '<h3>$1</h3>');
  md = md.replace(/^## (.+)$/gm, '<h2>$1</h2>');
  md = md.replace(/^# (.+)$/gm, '<h1>$1</h1>');

  // Bold
  md = md.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');

  // Unordered lists
  md = md.replace(/^((?:- .+\n?)+)/gm, (match) => {
    const items = match.trim().split('\n').map(l => `<li>${l.replace(/^- /, '')}</li>`).join('');
    return `<ul>${items}</ul>`;
  });

  // Ordered lists
  md = md.replace(/^((?:\d+\. .+\n?)+)/gm, (match) => {
    const items = match.trim().split('\n').map(l => `<li>${l.replace(/^\d+\. /, '')}</li>`).join('');
    return `<ol>${items}</ol>`;
  });

  // Paragraphs (lines not already wrapped)
  md = md.replace(/^(?!<[a-z])((?!$).+)$/gm, '<p>$1</p>');

  // Clean up empty paragraphs
  md = md.replace(/<p>\s*<\/p>/g, '');

  return md;
}

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
  } catch (_) {}
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
  let resultMd = '';

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

    // Read full response (proxy may buffer/close streaming connections)
    var fullText = await resp.text();
    
    // Parse SSE events
    var dataLines = fullText.split("data: ").slice(1).map(function(s) { var end = s.indexOf("\n"); return end > 0 ? s.slice(0, end) : s.trim(); });
    for (var i = 0; i < dataLines.length; i++) {
      try {
        var event = JSON.parse(dataLines[i]);
        switch (event.type) {
          case "status":
            addEntry("status", event.text);
            break;
          case "step":
            addEntry("step", "🔧 Step " + event.index + ": " + event.text);
            break;
          case "tool_done":
            addEntry("tool-done", "  ✓ " + event.tool + ": " + (event.preview || "done"));
            break;
          case "token":
            if (!resultEl) {
              addEntry("result-header", "📊 Results:");
              resultEl = addEntry("result", "");
            }
            resultMd += event.text;
            break;
          case "error":
            addEntry("error", "❌ " + event.text);
            break;
          case "done":
            addEntry("done", "✅ Research complete (" + (event.steps || "?") + " tool calls)");
            break;
        }
      } catch (parseErr) {}
    }
    
    // Final render
    if (resultEl && resultMd) {
      resultEl.innerHTML = mdToHtml(resultMd);
    }
    addEntry('error', '❌ ' + e.message);
  }

  btn.disabled = false;
  btn.textContent = '🔍 Research Again';
}

// Init
loadExamples();
browser.sidePanel.open();
