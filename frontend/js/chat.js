// RAG-Chat — © 2026 David Dülle
// https://duelle.org

/**
 * Chat module: SSE streaming, message rendering, markdown, sources,
 * localStorage chat history (FE-04)
 *
 * History format in localStorage('rag-chat-history'):
 * [
 *   { id, title, created, messages: [{role, content, sources?, stats?}] },
 *   ...
 * ]
 */

const Chat = (() => {

    const STORAGE_KEY = 'rag-chat-history';
    const MAX_CHATS = 50;

    let _abortController = null;
    let _isStreaming = false;
    let _conversations = [];     // all chats
    let _activeId = null;        // current chat id

    // ===================================================================
    // History persistence
    // ===================================================================

    function _loadHistory() {
        try {
            _conversations = JSON.parse(localStorage.getItem(STORAGE_KEY)) || [];
        } catch (_) {
            _conversations = [];
        }
    }

    function _saveHistory() {
        // Trim to MAX_CHATS
        if (_conversations.length > MAX_CHATS) {
            _conversations = _conversations.slice(0, MAX_CHATS);
        }
        try {
            localStorage.setItem(STORAGE_KEY, JSON.stringify(_conversations));
        } catch (_) {
            // localStorage full — silently drop oldest
            _conversations.pop();
            try { localStorage.setItem(STORAGE_KEY, JSON.stringify(_conversations)); }
            catch (_) { /* give up */ }
        }
    }

    function _getChat(id) {
        return _conversations.find(c => c.id === id) || null;
    }

    function _createChat() {
        const chat = {
            id: crypto.randomUUID ? crypto.randomUUID() : Date.now().toString(36) + Math.random().toString(36).slice(2),
            title: 'Neuer Chat',
            created: new Date().toISOString(),
            messages: [],
        };
        _conversations.unshift(chat);
        _saveHistory();
        return chat;
    }

    function _deleteChat(id) {
        _conversations = _conversations.filter(c => c.id !== id);
        _saveHistory();
        if (_activeId === id) {
            _activeId = null;
            _showWelcome();
        }
        _renderChatList();
    }

    function _addMessageToHistory(role, content, sources, stats) {
        if (!_activeId) return;
        const chat = _getChat(_activeId);
        if (!chat) return;
        const msg = { role, content };
        if (sources && sources.length) msg.sources = sources;
        if (stats) msg.stats = stats;
        chat.messages.push(msg);
        // Update title from first user message
        if (chat.messages.length === 1 && role === 'user') {
            chat.title = content.slice(0, 60) + (content.length > 60 ? '…' : '');
        }
        _saveHistory();
        _renderChatList();
    }

    // ===================================================================
    // Sidebar chat list
    // ===================================================================

    function _renderChatList() {
        const list = document.getElementById('chat-list');
        if (!list) return;
        list.innerHTML = '';

        for (const chat of _conversations) {
            const item = document.createElement('div');
            item.className = 'chat-item' + (chat.id === _activeId ? ' active' : '');
            item.dataset.id = chat.id;

            const title = document.createElement('span');
            title.className = 'chat-item-title';
            title.textContent = chat.title;
            title.title = chat.title;

            const del = document.createElement('button');
            del.className = 'chat-item-delete';
            del.innerHTML = '&times;';
            del.title = 'Chat löschen';
            del.addEventListener('click', (e) => {
                e.stopPropagation();
                _deleteChat(chat.id);
            });

            item.appendChild(title);
            item.appendChild(del);

            item.addEventListener('click', () => _switchToChat(chat.id));
            list.appendChild(item);
        }
    }

    function _switchToChat(id) {
        if (_isStreaming) return;
        _activeId = id;
        const chat = _getChat(id);
        if (!chat) return;

        _renderChatList();
        _clearMessages();

        // Re-render all messages
        for (const msg of chat.messages) {
            if (msg.role === 'user') {
                addMessage('user', msg.content);
            } else {
                const contentDiv = addMessage('bot', msg.content);
                if (msg.sources) renderSources(contentDiv, msg.sources, msg.stats);
            }
        }
    }

    // ===================================================================
    // Markdown
    // ===================================================================

    function initMarked() {
        if (typeof marked !== 'undefined') {
            marked.setOptions({
                breaks: true,
                gfm: true,
                highlight: (code, lang) => {
                    if (typeof hljs !== 'undefined' && lang && hljs.getLanguage(lang)) {
                        try { return hljs.highlight(code, { language: lang }).value; }
                        catch (_) { /* fallback */ }
                    }
                    return code;
                },
            });
        }
    }

    function renderMarkdown(text) {
        if (typeof marked !== 'undefined') {
            return marked.parse(text);
        }
        return text
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/\n/g, '<br>');
    }

    // ===================================================================
    // Message DOM
    // ===================================================================

    function _showWelcome() {
        const messages = document.getElementById('messages');
        messages.innerHTML = `
            <div id="welcome" class="welcome-msg">
                <h2>Willkommen bei RAG-Chat</h2>
                <p>Stelle eine Frage zu deinen Dokumenten oder lade eine Datei hoch.</p>
            </div>`;
    }

    function _clearMessages() {
        document.getElementById('messages').innerHTML = '';
    }

    function addMessage(role, content) {
        const welcome = document.getElementById('welcome');
        if (welcome) welcome.remove();

        const messages = document.getElementById('messages');
        const div = document.createElement('div');
        div.className = `message ${role}`;

        const avatar = document.createElement('div');
        avatar.className = 'msg-avatar';
        avatar.textContent = role === 'user' ? 'Du' : 'AI';

        const contentDiv = document.createElement('div');
        contentDiv.className = 'msg-content';

        if (role === 'user') {
            contentDiv.textContent = content;
        } else {
            contentDiv.innerHTML = renderMarkdown(content);
        }

        div.appendChild(avatar);
        div.appendChild(contentDiv);
        messages.appendChild(div);
        UI.scrollToBottom(messages, true);
        return contentDiv;
    }

    function addErrorMessage(text) {
        const messages = document.getElementById('messages');
        const div = document.createElement('div');
        div.className = 'message error';

        const avatar = document.createElement('div');
        avatar.className = 'msg-avatar';
        avatar.textContent = '!';

        const contentDiv = document.createElement('div');
        contentDiv.className = 'msg-content';
        contentDiv.textContent = text;

        div.appendChild(avatar);
        div.appendChild(contentDiv);
        messages.appendChild(div);
        UI.scrollToBottom(messages, true);
    }

    // ===================================================================
    // Sources (FE-03)
    // ===================================================================

    function renderSources(contentDiv, sources, stats) {
        if (!sources || sources.length === 0) return;

        const container = document.createElement('div');
        container.className = 'sources-container';

        const toggle = document.createElement('button');
        toggle.className = 'sources-toggle';
        toggle.innerHTML = `<span class="arrow">▶</span> ${sources.length} Quelle${sources.length > 1 ? 'n' : ''}`;
        toggle.addEventListener('click', () => {
            toggle.classList.toggle('open');
            list.classList.toggle('open');
        });

        const list = document.createElement('div');
        list.className = 'sources-list';

        for (const src of sources) {
            const card = document.createElement('div');
            card.className = 'source-card';
            const pct = Math.round((src.score || 0) * 100);
            card.innerHTML = `
                <div class="source-header">
                    <span class="source-file" title="${_escHtml(src.file)}">${_escHtml(src.file)}</span>
                    <span class="source-score">${pct}%</span>
                </div>
                <div class="score-bar"><div class="score-bar-fill" style="width: ${pct}%"></div></div>
                <div class="source-preview">${_escHtml(src.preview || '')}</div>`;
            list.appendChild(card);
        }

        container.appendChild(toggle);
        container.appendChild(list);

        if (stats) {
            const statsEl = document.createElement('div');
            statsEl.className = 'stats-line';
            const parts = [];
            if (stats.tokens_per_second) parts.push(`${stats.tokens_per_second} Tokens/s`);
            if (stats.total_duration_ms) parts.push(`${(stats.total_duration_ms / 1000).toFixed(1)}s`);
            if (parts.length) statsEl.textContent = parts.join(' · ');
            container.appendChild(statsEl);
        }

        contentDiv.appendChild(container);
    }

    function _escHtml(str) {
        const d = document.createElement('div');
        d.textContent = str;
        return d.innerHTML;
    }

    // ===================================================================
    // SSE Streaming (FE-02)
    // ===================================================================

    async function sendMessage(text) {
        if (_isStreaming || !text.trim()) return;

        // Ensure we have an active chat
        if (!_activeId) {
            const chat = _createChat();
            _activeId = chat.id;
            _clearMessages();
            _renderChatList();
        }

        _isStreaming = true;
        _abortController = new AbortController();

        const sendBtn = document.getElementById('send-btn');
        const stopBtn = document.getElementById('stop-btn');
        sendBtn.classList.add('hidden');
        stopBtn.classList.remove('hidden');

        addMessage('user', text);
        _addMessageToHistory('user', text);

        UI.showTyping(true);

        const body = { message: text };
        const sessionId = Upload.getSessionId();
        if (sessionId) body.session_id = sessionId;

        let contentDiv = null;
        let fullText = '';
        let thinkingText = '';
        let thinkingDiv = null;
        let isThinking = false;
        let lastSources = null;
        let lastStats = null;
        const messages = document.getElementById('messages');

        try {
            const resp = await fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
                signal: _abortController.signal,
            });

            if (!resp.ok) {
                const err = await resp.json().catch(() => ({}));
                throw new Error(err.detail || `Fehler ${resp.status}`);
            }

            const reader = resp.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop() || '';

                for (const line of lines) {
                    if (!line.startsWith('data: ')) continue;

                    let event;
                    try { event = JSON.parse(line.slice(6)); }
                    catch (_) { continue; }

                    if (event.type === 'thinking_start') {
                        // Create message container + collapsible thinking block
                        if (!contentDiv) {
                            UI.showTyping(false);
                            contentDiv = addMessage('bot', '');
                        }
                        isThinking = true;
                        thinkingText = '';
                        thinkingDiv = document.createElement('details');
                        thinkingDiv.className = 'thinking-block';
                        thinkingDiv.innerHTML = '<summary class="thinking-summary">Denkprozess</summary><div class="thinking-content"></div>';
                        thinkingDiv.open = true;
                        contentDiv.appendChild(thinkingDiv);
                        UI.scrollToBottom(messages);

                    } else if (event.type === 'thinking') {
                        thinkingText += event.content;
                        if (thinkingDiv) {
                            const tc = thinkingDiv.querySelector('.thinking-content');
                            if (tc) tc.innerHTML = renderMarkdown(thinkingText);
                        }
                        UI.scrollToBottom(messages);

                    } else if (event.type === 'thinking_end') {
                        isThinking = false;
                        if (thinkingDiv) {
                            // Collapse thinking block, show final content
                            thinkingDiv.open = false;
                            const summary = thinkingDiv.querySelector('.thinking-summary');
                            if (summary) summary.textContent = 'Denkprozess anzeigen';
                        }

                    } else if (event.type === 'token') {
                        if (!contentDiv) {
                            UI.showTyping(false);
                            contentDiv = addMessage('bot', '');
                        }
                        fullText += event.content;
                        // Render answer after the thinking block
                        let answerDiv = contentDiv.querySelector('.answer-content');
                        if (!answerDiv && thinkingDiv) {
                            answerDiv = document.createElement('div');
                            answerDiv.className = 'answer-content';
                            contentDiv.appendChild(answerDiv);
                        }
                        const target = answerDiv || contentDiv;
                        target.innerHTML = renderMarkdown(fullText);
                        if (typeof hljs !== 'undefined') {
                            target.querySelectorAll('pre code').forEach((block) => {
                                if (!block.dataset.highlighted) {
                                    hljs.highlightElement(block);
                                    block.dataset.highlighted = 'true';
                                }
                            });
                        }
                        UI.scrollToBottom(messages);

                    } else if (event.type === 'sources') {
                        lastSources = event.sources;
                        lastStats = event.stats;
                        if (!contentDiv) {
                            UI.showTyping(false);
                            contentDiv = addMessage('bot', '');
                        }
                        renderSources(contentDiv, event.sources, event.stats);

                    } else if (event.type === 'error') {
                        UI.showTyping(false);
                        addErrorMessage(event.message);

                    } else if (event.type === 'done') {
                        // Save bot response to history
                        _addMessageToHistory('bot', fullText, lastSources, lastStats);
                    }
                }
            }

        } catch (e) {
            UI.showTyping(false);
            if (e.name === 'AbortError') {
                if (contentDiv && fullText) {
                    fullText += '\n\n*(Abgebrochen)*';
                    contentDiv.innerHTML = renderMarkdown(fullText);
                    _addMessageToHistory('bot', fullText);
                }
            } else {
                addErrorMessage(e.message || 'Verbindungsfehler');
            }
        } finally {
            _isStreaming = false;
            _abortController = null;
            sendBtn.classList.remove('hidden');
            stopBtn.classList.add('hidden');
            document.getElementById('message-input')?.focus();
        }
    }

    function stopStreaming() {
        if (_abortController) _abortController.abort();
    }

    // ===================================================================
    // Export chat as .txt
    // ===================================================================

    function exportChat(id) {
        const chat = _getChat(id || _activeId);
        if (!chat || !chat.messages.length) return;

        let text = `# ${chat.title}\n# ${chat.created}\n\n`;
        for (const msg of chat.messages) {
            const label = msg.role === 'user' ? 'Du' : 'AI';
            text += `--- ${label} ---\n${msg.content}\n\n`;
        }

        const blob = new Blob([text], { type: 'text/plain' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `chat-${chat.title.slice(0, 30).replace(/[^a-zA-Z0-9äöü]/gi, '_')}.txt`;
        a.click();
        URL.revokeObjectURL(url);
    }

    // ===================================================================
    // Init
    // ===================================================================

    function init() {
        initMarked();
        _loadHistory();
        _renderChatList();

        const form = document.getElementById('chat-form');
        const input = document.getElementById('message-input');

        form?.addEventListener('submit', (e) => {
            e.preventDefault();
            const text = input.value.trim();
            if (text) {
                input.value = '';
                input.style.height = 'auto';
                sendMessage(text);
            }
        });

        document.getElementById('stop-btn')?.addEventListener('click', stopStreaming);

        document.getElementById('new-chat-btn')?.addEventListener('click', () => {
            if (_isStreaming) return;
            _activeId = null;
            Upload.clearSession();
            _showWelcome();
            _renderChatList();
            input.value = '';
            input.focus();
        });
    }

    return { init, sendMessage, stopStreaming, exportChat };

})();

document.addEventListener('DOMContentLoaded', Chat.init);
