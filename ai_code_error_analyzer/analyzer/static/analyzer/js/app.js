'use strict';

let user = null;
let lang = 'python';
let editor = null;
let lastAnal = null;
let lastOut = '';
let lastErr = '';
let lastRecordId = null;
let decorations = [];
let socket = null;
let currentSessionId = null;
let mentorHistory = [];

const CFG = document.body.dataset;

function looksLikeCode(text) {
    if (!text) return false;
    const t = String(text).trim();
    return /[\n{}();=]/.test(t) || /\b(print|input|def|class|public|static|int|Scanner|#include|printf|scanf)\b/.test(t);
}

function shouldShowFix(anal) {
    return !!(
        anal &&
        (anal.fix || anal.corrected_code) &&
        String(anal.fix || anal.corrected_code).trim() &&
        looksLikeCode(anal.fix || anal.corrected_code) &&
        (
            anal.hasError === true ||
            anal.is_code_correct === false
        )
    );
}

function pushMentorHistory(role, text) {
    mentorHistory.push({ role, text: String(text || '') });
    if (mentorHistory.length > 10) mentorHistory = mentorHistory.slice(-10);
}

const SAMPLES = {
    python: `# Python example
print("Enter your name:")
name = input()
print("Hello", name)
`,
    java: `import java.util.Scanner;
public class Main {
    public static void main(String[] args) {
        Scanner sc = new Scanner(System.in);
        System.out.println("Enter a number:");
        int n = sc.nextInt();
        System.out.println("Double = " + (n * 2));
    }
}`,
    c: `#include <stdio.h>

int main() {
    int n;
    printf("Enter a number:\\n");
    scanf("%d", &n);
    printf("Double = %d\\n", n * 2);
    return 0;
}`
};

function getCookie(name) {
    const cookieValue = document.cookie
        .split('; ')
        .find(row => row.startsWith(name + '='));
    return cookieValue ? decodeURIComponent(cookieValue.split('=')[1]) : '';
}

function getCsrfToken() {
    const metaToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
    return metaToken || getCookie('csrftoken') || '';
}

function api(url, method = 'GET', body = null) {
    const headers = { 'Content-Type': 'application/json' };
    if (!['GET', 'HEAD', 'OPTIONS', 'TRACE'].includes((method || 'GET').toUpperCase())) {
        const csrf = getCsrfToken();
        if (csrf) headers['X-CSRFToken'] = csrf;
    }

    return fetch(url, {
        method,
        headers,
        credentials: 'same-origin',
        body: body ? JSON.stringify(body) : null
    }).then(async (r) => {
        const data = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(data.message || 'Request failed');
        return data;
    });
}

async function initApp() {
    bindUpload();
    updateKeyIndicator();
    await checkSession();
}

async function checkSession() {
    try {
        const data = await api(CFG.sessionUrl);
        if (data.authenticated) {
            user = data.user;
            enterApp(false);
        }
    } catch (e) {
        console.log('Session check failed');
    }
}

function switchTab(t) {
    document.getElementById('tab-in').classList.toggle('on', t === 'in');
    document.getElementById('tab-up').classList.toggle('on', t === 'up');
    document.getElementById('f-in').style.display = t === 'in' ? '' : 'none';
    document.getElementById('f-up').style.display = t === 'up' ? '' : 'none';
}
window.switchTab = switchTab;

async function doLogin() {
    const e = document.getElementById('li-email').value.trim();
    const p = document.getElementById('li-pass').value;

    try {
        const data = await api(CFG.loginUrl, 'POST', { email: e, password: p });
        user = data.user;
        enterApp(true);
    } catch (err) {
        toast(err.message, 'err');
    }
}
window.doLogin = doLogin;

async function doSignup() {
    const n = document.getElementById('su-name').value.trim();
    const e = document.getElementById('su-email').value.trim();
    const p = document.getElementById('su-pass').value;

    try {
        const data = await api(CFG.signupUrl, 'POST', { name: n, email: e, password: p });
        user = data.user;
        enterApp(true);
    } catch (err) {
        toast(err.message, 'err');
    }
}
window.doSignup = doSignup;

function quickDemo() {
    switchTab('up');
    toast('Create a free account to start using the app.', 'inf');
}
window.quickDemo = quickDemo;

function enterApp(showToast = true) {
    updateKeyIndicator();
    document.getElementById('auth-screen').style.display = 'none';
    document.getElementById('app').classList.add('on');

    const displayName = (user?.name || user?.username || 'User');
    document.getElementById('uname').textContent = displayName.split(' ')[0];
    document.getElementById('uav').textContent = displayName
        .split(' ')
        .map(w => w[0])
        .join('')
        .slice(0, 2)
        .toUpperCase();

    gv('edit');

    setTimeout(() => {
        if (!editor) initMonaco();
        connectSocket();
    }, 100);

    if (showToast) toast('Welcome!', 'ok');
}

async function doLogout() {
    try {
        if (currentSessionId && socket && socket.readyState === WebSocket.OPEN) {
            socket.send(JSON.stringify({ action: 'stop' }));
        }
        await api(CFG.logoutUrl, 'POST', {});
    } catch (e) {}

    if (socket) {
        socket.close();
        socket = null;
    }

    currentSessionId = null;
    user = null;
    document.getElementById('auth-screen').style.display = '';
    document.getElementById('app').classList.remove('on');
}
window.doLogout = doLogout;

function gv(v) {
    document.querySelectorAll('.view').forEach(x => x.classList.remove('on'));
    document.querySelectorAll('.nav-btn').forEach(x => x.classList.remove('on'));

    const viewEl = document.getElementById('v-' + v);
    const navEl = document.getElementById('nb-' + v);

    if (viewEl) viewEl.classList.add('on');
    if (navEl) navEl.classList.add('on');

    if (v === 'edit') {
        if (!editor) initMonaco();
    }
    if (v === 'dash') loadDashboard();
    if (v === 'hist') loadHistory();
}
window.gv = gv;

function initMonaco() {
    require.config({
        paths: {
            vs: 'https://cdnjs.cloudflare.com/ajax/libs/monaco-editor/0.44.0/min/vs'
        }
    });

    require(['vs/editor/editor.main'], () => {
        if (editor) return;

        editor = monaco.editor.create(document.getElementById('mc'), {
            value: SAMPLES.python,
            language: 'python',
            theme: 'vs',
            fontSize: 13.5,
            fontFamily: '"Fira Code", monospace',
            fontLigatures: true,
            lineNumbers: 'on',
            minimap: { enabled: true },
            scrollBeyondLastLine: false,
            automaticLayout: true,
            padding: { top: 12 },
            renderLineHighlight: 'all',
            cursorBlinking: 'smooth',
            smoothScrolling: true,
            wordWrap: 'on'
        });

        editor.onDidChangeModelContent(() => {
            if (editor?.getModel()) {
                document.getElementById('lc').textContent = editor.getModel().getLineCount() + ' lines';
            }
        });

        document.getElementById('lc').textContent = editor.getModel().getLineCount() + ' lines';

        const s = document.createElement('style');
        s.textContent = '.errLine{background:rgba(225,29,72,.1)!important;border-left:3px solid #E11D48!important;}';
        document.head.appendChild(s);
    });
}

function setLang(l) {
    lang = l;

    document.querySelectorAll('.lb').forEach(b => {
        b.classList.toggle('on', b.dataset.l === l);
    });

    const dots = {
        python: 'var(--violet)',
        java: 'var(--orange)',
        c: 'var(--fuchsia)'
    };

    const names = {
        python: 'main.py',
        java: 'Main.java',
        c: 'program.c'
    };

    document.getElementById('lang-dot').style.background = dots[l];
    document.getElementById('fname').textContent = names[l];

    if (editor) {
        monaco.editor.setModelLanguage(
            editor.getModel(),
            l === 'c' ? 'c' : (l === 'java' ? 'java' : l)
        );
        editor.setValue(SAMPLES[l]);
    }

    if (l === 'java' || l === 'c') {
        toast(`${l.toUpperCase()} support is coming soon.`, 'inf');
    }
}
window.setLang = setLang;

function getWsUrl() {
    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const path = CFG.wsPath || '/ws/execute/';
    return `${protocol}://${window.location.host}${path}`;
}

function connectSocket() {
    if (!user) return;

    if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) {
        return;
    }

    socket = new WebSocket(getWsUrl());

    socket.onopen = () => {
        setStatus('ok', 'Connected');
        hideInputRowIfNeeded();
        addLine('WebSocket connected successfully', 'tl-ok');
    };

    socket.onmessage = (evt) => {
        try {
            const data = JSON.parse(evt.data);
            handleSocket(data);
        } catch (e) {
            console.error('Invalid socket message:', evt.data);
        }
    };

    socket.onerror = () => {
        setStatus('err', 'Connection error');
        addLine('WebSocket connection error', 'tl-err');
    };

    socket.onclose = () => {
        setStatus('err', 'Connection not ready');
        if (user) {
            setTimeout(() => connectSocket(), 1500);
        }
    };
}

function handleSocket(msg) {
    if (msg.type === 'status' && msg.message) {
        addLine(msg.message, 'tl-ok');
        return;
    }

    if (msg.type === 'output' && msg.message) {
        addLine(msg.message, 'tl-out');
        return;
    }

    if (msg.type === 'error' && msg.message) {
        addLine(msg.message, 'tl-err');
        toast(msg.message, 'err');
        return;
    }

    if (msg.event === 'started') {
        currentSessionId = msg.session_id || null;
        lastRecordId = msg.record_id || null;
        setStatus('run', 'Running');
        document.getElementById('run-btn').disabled = true;
        return;
    }

    if (msg.event === 'terminal') {
        addLine(msg.text || '', mapStream(msg.stream));
        return;
    }

    if (msg.event === 'modules') {
        showMods(msg.modules || [], msg.blocked_modules || [], msg.insights || []);
        return;
    }

    if (msg.event === 'waiting_input') {
        const row = document.getElementById('tin-row');
        row.classList.toggle('on', !!msg.value);

        if (msg.value) {
            setStatus('run', 'Waiting for input');
            setTimeout(() => {
                const ti = document.getElementById('ti');
                if (ti) ti.focus();
            }, 50);
        }
        return;
    }

    if (msg.event === 'complete') {
        document.getElementById('run-btn').disabled = false;
        currentSessionId = null;
        lastAnal = msg.analysis || {};
        lastRecordId = msg.record_id || lastRecordId;
        lastErr = msg.analysis?.raw || '';
        lastOut = msg.analysis?.output || '';

        renderAnalysis(msg.analysis || {});
        renderCompare(msg.analysis || {});
        highlightLine(msg.analysis?.line);
        loadDashboard();

        if (msg.status === 'success') {
            setStatus('ok', 'Success');
        } else if (msg.status === 'coming_soon') {
            setStatus('idle', 'Coming Soon');
        } else {
            setStatus('err', 'Completed with issues');
        }

        hideInputRowIfNeeded();
    }
}

function hideInputRowIfNeeded() {
    const row = document.getElementById('tin-row');
    if (row) row.classList.remove('on');
}

function mapStream(s) {
    return s === 'error'
        ? 'tl-err'
        : s === 'cmd'
            ? 'tl-cmd'
            : s === 'ok'
                ? 'tl-ok'
                : s === 'info'
                    ? 'tl-inf'
                    : 'tl-out';
}

function runCode() {
    if (!editor) {
        toast('Editor not ready', 'err');
        return;
    }

    if (lang === 'java' || lang === 'c') {
        clearRunPanels();
        clearTerminal();
        hideInputRowIfNeeded();

        const msg = `${lang.toUpperCase()} execution support is Coming Soon.`;

        addLine(msg, 'tl-inf');
        setStatus('idle', `${lang.toUpperCase()} coming soon`);

        lastAnal = {
            hasError: false,
            is_code_correct: true,
            type: '',
            line: null,
            raw: '',
            error: '',
            output: '',
            explain: msg,
            root_cause: '',
            fix: '',
            corrected_code: '',
            tips: [`${lang.toUpperCase()} execution will be available in a future update.`],
            optimizations: [],
            time: 'N/A',
            space: 'N/A',
            complexity_explanation: '',
            concepts: [`${lang.toUpperCase()} Support Coming Soon`],
            insights: [`${lang.toUpperCase()} execution is not enabled yet.`],
            steps: [],
            viva_answer: '',
            confidence: 'high',
            source: 'system'
        };

        renderAnalysis(lastAnal);
        renderCompare(lastAnal);

        return;
    }

    if (!socket || socket.readyState !== WebSocket.OPEN) {
        toast('Connection not ready', 'err');
        connectSocket();
        return;
    }

    clearRunPanels();
    clearTerminal();
    hideInputRowIfNeeded();

    socket.send(JSON.stringify({
        action: 'start',
        language: lang,
        code: editor.getValue()
    }));

    addLine(`Running ${lang} code...`, 'tl-cmd');
}
window.runCode = runCode;

function stopCode() {
    if (!socket || socket.readyState !== WebSocket.OPEN || !currentSessionId) {
        toast('No active execution', 'err');
        return;
    }

    socket.send(JSON.stringify({ action: 'stop' }));
    addLine('Execution stopped by user.', 'tl-err');
    currentSessionId = null;
    document.getElementById('run-btn').disabled = false;
    hideInputRowIfNeeded();
    setStatus('idle', 'Stopped');
}
window.stopCode = stopCode;

function sendInput() {
    const inp = document.getElementById('ti');
    if (!inp) return;

    const v = inp.value;
    if ((!v && v !== '') || !socket || socket.readyState !== WebSocket.OPEN) return;

    socket.send(JSON.stringify({
        action: 'input',
        text: v
    }));

    inp.value = '';
}
window.sendInput = sendInput;

function clearTerminal() {
    const tout = document.getElementById('tout');
    if (!tout) return;
    tout.innerHTML = '';
}

function addLine(text, cls = 'tl-out') {
    const tout = document.getElementById('tout');
    if (!tout || text === null || text === undefined) return;

    const d = document.createElement('div');
    d.className = `tl ${cls}`;
    d.textContent = String(text);
    tout.appendChild(d);
    tout.scrollTop = tout.scrollHeight;
}

function renderAnalysis(anal) {
    let h = '';

    const sourceMap = {
        ollama: 'Ollama',
        system: 'System',
        rules: 'Rule-based fallback'
    };

    const source = sourceMap[anal.source] || 'Rule-based fallback';
    const confidence = anal.confidence || 'low';
    const highlightedLine = anal.line || anal.line_focus || '';

    h += `
        <div class="insights-row">
            <div class="ins-chip"><span>🧠</span><span>${esc(source)}</span></div>
            <div class="ins-chip"><span>📊</span><span>Confidence: ${esc(confidence)}</span></div>
            <div class="ins-chip"><span>🎯</span><span>${highlightedLine ? `Check line ${esc(String(highlightedLine))} first` : 'No exact line detected'}</span></div>
            <div class="ins-chip"><span>🎤</span><span>${anal.viva_answer ? 'Viva answer ready' : 'Generate viva answer after AI analysis'}</span></div>
        </div>
    `;

    if ((anal.insights || []).length) {
        h += '<div class="insights-row">' +
            anal.insights.map(x => `
                <div class="ins-chip">
                    <span>💡</span>
                    <span>${esc(x)}</span>
                </div>
            `).join('') +
            '</div>';
    }

    h += `
        <div class="cx-row">
            <div class="cx-chip">
                <div class="cx-lbl">Time Complexity</div>
                <div class="cx-val">${esc(anal.time || anal.complexity?.time || 'O(1)')}</div>
            </div>
            <div class="cx-chip">
                <div class="cx-lbl">Space Complexity</div>
                <div class="cx-val">${esc(anal.space || anal.complexity?.space || 'O(1)')}</div>
            </div>
        </div>
    `;

    if (anal.complexity_explanation || anal.complexity?.explanation) {
        h += `
            <div class="a-info">
                <div class="card-title ct-cyan">📈 Complexity Explanation</div>
                <div class="explain-txt">${esc(anal.complexity_explanation || anal.complexity?.explanation || '')}</div>
            </div>
        `;
    }

    if (anal.raw) {
        h += `
            <div class="a-error">
                <div class="card-title ct-red">🔴 Error - ${esc(anal.type || 'Error')}</div>
                <div class="raw-block rb-red">${esc(anal.raw)}</div>
            </div>
        `;
    }

    h += `
        <div class="a-explain">
            <div class="card-title ct-blue">🤖 Explanation</div>
            <div class="explain-txt">${esc(anal.explain || 'No explanation')}</div>
        </div>
    `;

    if (anal.root_cause) {
        h += `
            <div class="a-info">
                <div class="card-title ct-purple">🧩 Root Cause</div>
                <div class="explain-txt">${esc(anal.root_cause)}</div>
            </div>
        `;
    }

    if ((anal.steps || []).length) {
        h += `
            <div class="a-info">
                <div class="card-title ct-cyan">🪜 Step-by-Step Debugger</div>
                <div class="step-list">${anal.steps.map((s, i) => `<div class="step-item"><span class="step-num">${i + 1}</span><span>${esc(s)}</span></div>`).join('')}</div>
            </div>
        `;
    }

    if (shouldShowFix(anal)) {
        h += `
            <div class="a-fix">
                <div class="card-title ct-green">✅ Corrected Code</div>
                <div class="raw-block rb-green">${esc(anal.fix || anal.corrected_code)}</div>
                <div class="copy-row">
                    <button class="cbtn cbtn-green" onclick="copyFix()">📋 Copy Code</button>
                    <button class="cbtn cbtn-blue" onclick="applyFix()">⚡ Apply to Editor</button>
                </div>
            </div>
        `;
    }

    if ((anal.tips || []).length) {
        h += `
            <div class="a-suggest">
                <div class="card-title ct-purple">💡 Suggestions</div>
                ${anal.tips.map(t => `<div class="suggest-item">• ${esc(t)}</div>`).join('')}
            </div>
        `;
    }

    if ((anal.optimizations || []).length) {
        h += `
            <div class="a-suggest">
                <div class="card-title ct-green">🚀 Optimization Ideas</div>
                ${anal.optimizations.map(t => `<div class="suggest-item">• ${esc(t)}</div>`).join('')}
            </div>
        `;
    }

    if (anal.viva_answer) {
        h += `
            <div class="a-info">
                <div class="card-title ct-blue">🎤 Viva Answer</div>
                <div class="raw-block">${esc(anal.viva_answer)}</div>
                <div class="copy-row">
                    <button class="cbtn cbtn-blue" onclick="copyVivaAnswer()">📋 Copy Viva Answer</button>
                    <button class="cbtn cbtn-green" onclick="useVivaAnswer()">✨ Send to Mentor Chat</button>
                </div>
            </div>
        `;
    }

    if ((anal.concepts || []).length) {
        h += `
            <div class="a-info">
                <div class="card-title ct-cyan">📚 Concepts</div>
                <div class="mod-chips">
                    ${anal.concepts.map(c => `<span class="mc-safe">${esc(c)}</span>`).join('')}
                </div>
            </div>
        `;
    }

    document.getElementById('anal-ph').style.display = 'none';
    document.getElementById('anal-body').style.display = 'block';
    document.getElementById('anal-body').innerHTML = h;
}

function showMods(mods, blocked = [], insights = []) {
    document.getElementById('mods-ph').style.display = 'none';
    document.getElementById('mods-body').style.display = 'block';

    let h = '';

    if (blocked.length) {
        h += `<div class="mod-warn">⛔ Blocked module(s): <strong>${esc(blocked.join(', '))}</strong></div>`;
    }

    h += `
        <div class="mod-card">
            <div class="card-title ct-purple">📦 Detected Imports</div>
            <div class="mod-chips">
                ${
                    mods.map(m => `
                        <span class="${blocked.includes(m) ? 'mc-block' : 'mc-safe'}">
                            ${blocked.includes(m) ? '⛔' : '✓'} ${esc(m)}
                        </span>
                    `).join('') || '<span class="mc-safe">No imports detected</span>'
                }
            </div>
        </div>
    `;

    if (insights.length) {
        h += '<div class="mod-info-list">' +
            insights.map(x => `
                <div class="mod-info-item">
                    <div>📌</div>
                    <div>
                        <div class="mi-name">Insight</div>
                        <div class="mi-desc">${esc(x)}</div>
                    </div>
                </div>
            `).join('') +
            '</div>';
    }

    document.getElementById('mods-body').innerHTML = h;
}

function renderCompare(anal) {
    document.getElementById('cmp-ph').style.display = 'none';
    document.getElementById('cmp-body').style.display = 'block';

    document.getElementById('cmp-body').innerHTML = `
        <div class="cmp-grid">
            <div>
                <div class="cmp-title" style="color:var(--rose)">⚠ Original</div>
                <div class="cmp-code" style="color:#FDA4AF">${esc(editor ? editor.getValue() : '')}</div>
            </div>
            <div>
                <div class="cmp-title" style="color:var(--emerald)">✅ Fixed</div>
                <div class="cmp-code" style="color:#6EE7B7">${esc(shouldShowFix(anal) ? (anal.fix || anal.corrected_code) : (editor ? editor.getValue() : ''))}</div>
            </div>
        </div>
    `;
}

function highlightLine(line) {
    if (!editor || !window.monaco) return;

    if (decorations.length) {
        decorations = editor.deltaDecorations(decorations, []);
    }

    if (line) {
        decorations = editor.deltaDecorations([], [{
            range: new monaco.Range(line, 1, line, 1),
            options: {
                isWholeLine: true,
                className: 'errLine'
            }
        }]);
    }
}

function clearRunPanels() {
    ['anal', 'mods', 'cmp'].forEach(x => {
        document.getElementById(x + '-ph').style.display = 'block';
        document.getElementById(x + '-body').style.display = 'none';
    });

    lastAnal = null;
    lastErr = '';
    lastOut = '';
}

function clearAll() {
    if (editor) editor.setValue(SAMPLES[lang]);

    clearTerminal();
    addLine('// Terminal cleared', 'tl-inf');
    clearRunPanels();
    hideInputRowIfNeeded();
    setStatus('idle', 'Ready');
}
window.clearAll = clearAll;

function bindUpload() {
    const el = document.getElementById('fu');
    if (!el) return;
    el.addEventListener('change', uploadFile);
}

function uploadFile(ev) {
    const f = ev.target.files?.[0];
    if (!f) return;

    const ext = f.name.split('.').pop().toLowerCase();
    const map = { py: 'python', java: 'java', c: 'c' };

    if (!map[ext]) {
        toast('Unsupported file type', 'err');
        return;
    }

    setLang(map[ext]);

    const r = new FileReader();
    r.onload = e => {
        if (editor) editor.setValue(e.target.result);
    };
    r.readAsText(f);
}
window.uploadFile = uploadFile;

function sotab(t) {
    const ids = ['term', 'anal', 'mods', 'cmp'];

    document.querySelectorAll('.otab').forEach((el, i) => {
        el.classList.toggle('on', ids[i] === t);
    });

    ids.forEach(id => {
        document.getElementById('oc-' + id).classList.toggle('on', id === t);
    });
}
window.sotab = sotab;

function setStatus(s, t) {
    document.getElementById('sdot').className = 'sdot s-' + s;
    document.getElementById('stxt').textContent = t;
}

function esc(s) {
    return String(s || '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

function copyFix() {
    const fixedCode = lastAnal?.fix || lastAnal?.corrected_code || '';
    if (fixedCode) {
        navigator.clipboard.writeText(fixedCode).then(() => toast('Corrected code copied', 'ok'));
    } else {
        toast('No corrected code available', 'err');
    }
}
window.copyFix = copyFix;

function applyFix() {
    const fixedCode = lastAnal?.fix || lastAnal?.corrected_code || '';
    if (fixedCode && editor) {
        editor.setValue(fixedCode);
        toast('Corrected code applied to editor', 'ok');
    } else {
        toast('No corrected code available', 'err');
    }
}
window.applyFix = applyFix;

async function loadDashboard() {
    try {
        const data = await api(CFG.dashboardUrl);

        document.getElementById('st-exec').textContent = data.stats.executions;
        document.getElementById('st-err').textContent = data.stats.errors;
        document.getElementById('st-fix').textContent = data.stats.fixes;
        document.getElementById('st-lang').textContent = data.stats.languages_used;

        document.getElementById('bp').style.width = data.language_breakdown.python + '%';
        document.getElementById('pp').textContent = data.language_breakdown.python + '%';

        document.getElementById('bj').style.width = data.language_breakdown.java + '%';
        document.getElementById('pj').textContent = data.language_breakdown.java + '%';

        document.getElementById('bc').style.width = data.language_breakdown.c + '%';
        document.getElementById('pc').textContent = data.language_breakdown.c + '%';

        const al = document.getElementById('act-list');

        if (!data.recent_activity.length) {
            al.innerHTML = '<div class="empty-ph"><span class="ep-ico">💻</span>No activity yet. Run some code!</div>';
        } else {
            al.innerHTML = data.recent_activity.map(r => `
                <div class="act-item" onclick="loadHistoryRecord(${r.id})">
                    <span class="lang-tag t-${r.language}">${r.language}</span>
                    <span style="font-family:var(--mono);font-size:12px">${esc(r.error_type)}</span>
                    <span style="color:var(--muted);font-size:11px;margin-left:auto">${esc(r.created_at)}</span>
                    <span class="badge ${r.status === 'success' ? 'bd-ok' : 'bd-err'}">${esc(r.status)}</span>
                </div>
            `).join('');
        }
    } catch (e) {
        console.log('Dashboard load failed');
    }
}

async function loadHistory() {
    try {
        const data = await api(CFG.historyUrl);
        const tb = document.getElementById('hist-body');

        if (!data.items.length) {
            tb.innerHTML = '<tr><td colspan="6" class="empty-ph" style="padding:40px">No history yet.</td></tr>';
            return;
        }

        tb.innerHTML = data.items.map(r => `
            <tr>
                <td style="font-family:var(--mono);font-size:11px;color:var(--muted)">${esc(r.date)}</td>
                <td><span class="lang-tag t-${r.language}">${r.language}</span></td>
                <td style="font-family:var(--mono);font-size:11px;color:var(--muted);max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(r.code_preview)}</td>
                <td style="font-size:12px;color:var(--muted2)">${esc(r.error_type)}</td>
                <td><span class="badge ${r.status === 'success' ? 'bd-ok' : 'bd-err'}">${esc(r.status)}</span></td>
                <td><button class="btn-hv" onclick="loadHistoryRecord(${r.id})">View</button></td>
            </tr>
        `).join('');
    } catch (err) {
        toast(err.message, 'err');
    }
}

async function loadHistoryRecord(id) {
    try {
        const r = await api(CFG.historyUrl + id + '/');
        gv('edit');
        setLang(r.language);

        setTimeout(() => {
            if (editor) editor.setValue(r.code);
        }, 100);

        lastAnal = {
            raw: r.raw_error,
            type: r.error_type,
            explain: r.explanation,
            root_cause: r.root_cause,
            fix: r.corrected_code,
            corrected_code: r.corrected_code,
            hasError: !!r.raw_error,
            is_code_correct: !r.raw_error,
            tips: r.suggestions,
            optimizations: r.optimizations || [],
            concepts: r.concepts,
            time: r.complexity?.time || 'O(1)',
            space: r.complexity?.space || 'O(1)',
            complexity_explanation: r.complexity?.explanation || '',
            line: r.line_number,
            output: r.output,
            insights: r.insights,
            steps: r.steps || [],
            viva_answer: r.viva_answer || '',
            source: r.source || 'rules',
            confidence: r.confidence || 'medium'
        };

        lastRecordId = id;
        lastErr = r.raw_error || '';
        lastOut = r.output || '';

        renderAnalysis(lastAnal);
        renderCompare(lastAnal);
        showMods(r.modules || [], r.blocked_modules || [], r.insights || []);
        highlightLine(r.line_number);
    } catch (err) {
        toast(err.message, 'err');
    }
}
window.loadHistoryRecord = loadHistoryRecord;

function openReport() {
    if (!lastRecordId && !lastAnal) {
        toast('Run code first', 'err');
        return;
    }

    document.getElementById('r-ts').textContent = lastRecordId ? 'Generated from record #' + lastRecordId : 'Generated from current analysis';
    document.getElementById('r-orig').textContent = editor ? editor.getValue() : '—';
    document.getElementById('r-err').textContent = lastErr || 'None';
    document.getElementById('r-expl').textContent = lastAnal?.explain || '—';
    document.getElementById('r-fix').textContent = (lastAnal?.fix || lastAnal?.corrected_code || '—') + (lastAnal?.viva_answer ? `\n\nViva Answer:\n${lastAnal.viva_answer}` : '') + ((lastAnal?.steps || []).length ? `\n\nDebug Steps:\n- ${lastAnal.steps.join('\n- ')}` : '');
    document.getElementById('r-out').textContent = lastOut || '—';

    document.getElementById('report-modal').classList.add('on');
}
window.openReport = openReport;

function closeReport() {
    document.getElementById('report-modal').classList.remove('on');
}
window.closeReport = closeReport;

async function dlReport(type) {
    if (lastRecordId) {
        window.location.href = `/api/report/${lastRecordId}/${type}/`;
        return;
    }

    const timestamp = document.getElementById('r-ts').innerText || '—';
    const original = document.getElementById('r-orig').innerText || '—';
    const error = document.getElementById('r-err').innerText || '—';
    const explanation = document.getElementById('r-expl').innerText || '—';
    const fix = document.getElementById('r-fix').innerText || '—';
    const output = document.getElementById('r-out').innerText || '—';

    const reportText = `AI CODE ERROR ANALYZER REPORT
==============================

Timestamp:
${timestamp}

------------------------------
ORIGINAL CODE
------------------------------
${original}

------------------------------
ERROR
------------------------------
${error}

------------------------------
EXPLANATION
------------------------------
${explanation}

------------------------------
SUGGESTED FIX
------------------------------
${fix}

------------------------------
PROGRAM OUTPUT
------------------------------
${output}
`;

    if (type === 'txt') {
        const blob = new Blob([reportText], { type: 'text/plain' });
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'codesage_report.txt';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);
        return;
    }

    toast('Run the code first to create a saved record before downloading PDF.', 'inf');
}
window.dlReport = dlReport;

function openSettings() {
    document.getElementById('settings-modal').classList.add('on');
}
window.openSettings = openSettings;

function closeSettings() {
    document.getElementById('settings-modal').classList.remove('on');
}
window.closeSettings = closeSettings;

function toggleKeyVis() {
    const input = document.getElementById('sk-input');
    if (!input) return;
    input.type = input.type === 'password' ? 'text' : 'password';
}
window.toggleKeyVis = toggleKeyVis;

function saveKey() {
    const key = document.getElementById('sk-input').value.trim();
    localStorage.setItem('codesage_chat_name', key);
    toast('Mentor name saved locally', 'ok');
}
window.saveKey = saveKey;

function removeKey() {
    document.getElementById('sk-input').value = '';
    localStorage.removeItem('codesage_chat_name');
    toast('Mentor name removed', 'ok');
}
window.removeKey = removeKey;

function updateKeyIndicator() {
    const mentorName = localStorage.getItem('codesage_chat_name');
    const btn = document.getElementById('key-btn');
    const label = document.getElementById('key-label');
    const input = document.getElementById('sk-input');
    if (!btn || !label) return;

    btn.classList.toggle('active', !!mentorName);
    label.textContent = mentorName ? `Mentor: ${mentorName}` : 'Chat Settings';
    if (input && mentorName) input.value = mentorName;
}
window.updateKeyIndicator = updateKeyIndicator;

function appendChatMessage(role, text) {
    pushMentorHistory(role, text);
    const wrap = document.getElementById('chat-msgs');
    const empty = document.getElementById('chat-empty');
    if (empty) empty.style.display = 'none';
    const div = document.createElement('div');
    div.className = `chat-bubble ${role === 'user' ? 'cb-user' : 'cb-ai'}`;
    div.innerHTML = `<div class="cb-role">${role === 'user' ? 'You' : (localStorage.getItem('codesage_chat_name') || 'Code Mentor')}</div><div class="cb-text">${esc(text).replace(/\n/g, '<br>')}</div>`;
    wrap.appendChild(div);
    wrap.scrollTop = wrap.scrollHeight;
}

function buildMentorReply(question) {
    const q = question.toLowerCase();
    const tips = [];
    const code = editor ? editor.getValue() : '';
    if (lastAnal?.type) tips.push(`Current issue: ${lastAnal.type}. ${lastAnal.explain || ''}`);
    if (lastAnal?.line) tips.push(`Focus on line ${lastAnal.line} first.`);
    if (lastAnal?.steps?.length) tips.push(`First debug step: ${lastAnal.steps[0]}`);
    if (lastAnal?.optimizations?.length) tips.push(`Optimization idea: ${lastAnal.optimizations[0]}`);
    if (lastAnal?.concepts?.length) tips.push(`Main concepts in this code: ${lastAnal.concepts.join(', ')}.`);

    if (q.includes('viva')) {
        return lastAnal?.viva_answer || 'Run the code first so I can create a viva-ready explanation.';
    }
    if (q.includes('step') || q.includes('debug')) {
        return lastAnal?.steps?.length
            ? `Step-by-step debugger:\n- ${lastAnal.steps.join('\n- ')}`
            : 'Run the code first so I can generate step-by-step debugging guidance.';
    }
    if (q.includes('optimiz') || q.includes('improve')) {
        return lastAnal?.optimizations?.length
            ? `Optimization ideas:\n- ${lastAnal.optimizations.join('\n- ')}`
            : 'Run the code first so I can suggest targeted optimizations.';
    }
    if (q.includes('fix') || q.includes('correct')) {
        return (lastAnal?.fix || lastAnal?.corrected_code)
            ? `Try this suggested version and compare it carefully with your original code:\n\n${lastAnal.fix || lastAnal.corrected_code}`
            : 'Run the code first so I can inspect the latest error.';
    }
    if (q.includes('error') || q.includes('why')) {
        return lastAnal?.type
            ? `${lastAnal.type}: ${lastAnal.explain || 'The runtime/compiler found a problem.'}`
            : 'Run the code first and I will explain the latest error in simple words.';
    }
    if (q.includes('input')) {
        return 'If your program uses input(), Scanner, or scanf, run it and then type values in the terminal input box below the terminal output.';
    }
    if (q.includes('code')) {
        const lines = code ? code.split('\n').length : 0;
        return `Your editor currently has ${lines} lines. ${tips[0] || 'Run it to get a deeper review.'}`;
    }
    return tips.length
        ? `Here is a mentor summary:\n- ${tips.join('\n- ')}`
        : 'I can help explain errors, fixes, step-by-step debugging, optimization ideas, and viva answers. Run the program first for a more accurate answer.';
}

function askAIAboutCode() {
    gv('chat');
    const starter = lastAnal?.type
        ? `Explain this ${lastAnal.type} error in simple words and tell me how to fix it.`
        : 'Review my current code and tell me what to improve.';
    document.getElementById('chat-input').value = starter;
    sendChat();
}
window.askAIAboutCode = askAIAboutCode;

function copyVivaAnswer() {
    const textToCopy = lastAnal?.viva_answer || '';
    if (!textToCopy) {
        toast('No viva answer available yet', 'err');
        return;
    }
    navigator.clipboard.writeText(textToCopy).then(() => toast('Viva answer copied', 'ok'));
}
window.copyVivaAnswer = copyVivaAnswer;

function useVivaAnswer() {
    gv('chat');
    const starter = lastAnal?.viva_answer
        ? `Use this viva answer and improve it if needed:\n\n${lastAnal.viva_answer}`
        : 'Give me a viva-ready explanation for my current program and the latest error.';
    document.getElementById('chat-input').value = starter;
    sendChat();
}
window.useVivaAnswer = useVivaAnswer;

async function sendChat() {
    const input = document.getElementById('chat-input');
    const question = input.value.trim();
    if (!question) return;

    appendChatMessage('user', question);
    input.value = '';
    input.style.height = 'auto';

    const fallbackReply = buildMentorReply(question);

    if (!CFG.mentorChatUrl) {
        appendChatMessage('ai', fallbackReply);
        return;
    }

    try {
        const data = await api(CFG.mentorChatUrl, 'POST', {
            question,
            language: lang,
            code: editor ? editor.getValue() : '',
            analysis: lastAnal || {},
            output: lastOut || '',
            error: lastErr || '',
            history: mentorHistory
        });
        appendChatMessage('ai', data.reply || fallbackReply);
    } catch (err) {
        appendChatMessage('ai', fallbackReply);
        toast(err.message || 'AI chat failed. Using fallback mentor reply.', 'inf');
    }
}
window.sendChat = sendChat;

function chatStarter(msg) {
    document.getElementById('chat-input').value = msg;
}
window.chatStarter = chatStarter;

async function clearHistory() {
    try {
        const data = await api(CFG.historyClearUrl || (CFG.historyUrl + 'clear/'), 'POST', {});
        lastRecordId = null;
        lastAnal = null;
        lastErr = '';
        lastOut = '';
        loadHistory();
        loadDashboard();
        toast(`History cleared (${data.deleted || 0} records)`, 'ok');
    } catch (err) {
        toast(err.message, 'err');
    }
}
window.clearHistory = clearHistory;

function toast(msg, type = 'inf') {
    const t = document.createElement('div');
    t.className = `toast t-${type}`;
    t.innerHTML = `<span>${({ ok: '✓', err: '✗', inf: 'ℹ' })[type] || 'ℹ'}</span><span>${esc(msg)}</span>`;
    document.getElementById('toasts').appendChild(t);
    setTimeout(() => t.remove(), 3000);
}

window.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        closeSettings();
        closeReport();
    }

    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        e.preventDefault();
        if (document.getElementById('v-edit').classList.contains('on')) runCode();
    }

    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        if (document.getElementById('v-edit').classList.contains('on')) stopCode();
    }
});

window.addEventListener('load', initApp);