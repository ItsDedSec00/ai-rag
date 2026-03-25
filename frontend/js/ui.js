// RAG-Chat — © 2026 David Dülle
// https://duelle.org

/**
 * UI module: Theme toggle, sidebar, textarea auto-resize, scroll behavior
 */

const UI = (() => {

    // --- Theme ---

    function initTheme() {
        const saved = localStorage.getItem('rag-chat-theme');
        if (saved) {
            document.documentElement.setAttribute('data-theme', saved);
        }
        // Standard: Light-Mode (kein Auto-Dark über prefers-color-scheme)
        _updateThemeIcons();
    }

    function toggleTheme() {
        const current = document.documentElement.getAttribute('data-theme');
        const next = current === 'dark' ? 'light' : 'dark';
        document.documentElement.setAttribute('data-theme', next);
        localStorage.setItem('rag-chat-theme', next);
        _updateThemeIcons();
    }

    function _updateThemeIcons() {
        const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
        const moon = document.getElementById('icon-moon');
        const sun = document.getElementById('icon-sun');
        if (moon) moon.classList.toggle('hidden', isDark);
        if (sun) sun.classList.toggle('hidden', !isDark);
    }

    // --- Sidebar ---

    function initSidebar() {
        const sidebar = document.getElementById('sidebar');
        const backdrop = document.getElementById('sidebar-backdrop');
        const isMobile = window.innerWidth <= 768;
        if (isMobile) {
            sidebar.classList.remove('open');
        } else {
            const saved = localStorage.getItem('rag-chat-sidebar');
            if (saved === 'collapsed') sidebar.classList.add('collapsed');
        }

        // Close sidebar when clicking backdrop (mobile)
        backdrop?.addEventListener('click', () => {
            sidebar.classList.remove('open');
            backdrop.classList.remove('visible');
        });
    }

    function toggleSidebar() {
        const sidebar = document.getElementById('sidebar');
        const backdrop = document.getElementById('sidebar-backdrop');
        const isMobile = window.innerWidth <= 768;
        if (isMobile) {
            const opening = !sidebar.classList.contains('open');
            sidebar.classList.toggle('open');
            backdrop?.classList.toggle('visible', opening);
        } else {
            sidebar.classList.toggle('collapsed');
            localStorage.setItem(
                'rag-chat-sidebar',
                sidebar.classList.contains('collapsed') ? 'collapsed' : 'open'
            );
        }
    }

    // --- Textarea auto-resize ---

    function initTextarea() {
        const textarea = document.getElementById('message-input');
        if (!textarea) return;

        textarea.addEventListener('input', () => {
            textarea.style.height = 'auto';
            textarea.style.height = Math.min(textarea.scrollHeight, 150) + 'px';
        });

        textarea.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                document.getElementById('chat-form').dispatchEvent(new Event('submit'));
            }
        });
    }

    // --- Smart scroll ---

    function isNearBottom(el, threshold = 80) {
        return el.scrollHeight - el.scrollTop - el.clientHeight < threshold;
    }

    function scrollToBottom(el, force = false) {
        if (force || isNearBottom(el)) {
            el.scrollTop = el.scrollHeight;
        }
    }

    // --- Thinking indicator (Claude-style rotating words) ---

    const _thinkingPhrases = [
        'Nachdenken…',
        'Kontext durchsuchen…',
        'Dokumente analysieren…',
        'Zusammenhänge finden…',
        'Antwort formulieren…',
        'Quellen prüfen…',
        'Informationen verknüpfen…',
    ];
    let _thinkingInterval = null;
    let _thinkingIndex = 0;

    function showTyping(show) {
        const el = document.getElementById('thinking-indicator');
        if (!el) return;

        if (show) {
            el.classList.remove('hidden');
            _thinkingIndex = 0;
            _updateThinkingWord();
            _thinkingInterval = setInterval(() => {
                _thinkingIndex = (_thinkingIndex + 1) % _thinkingPhrases.length;
                _updateThinkingWord();
            }, 2000);
            scrollToBottom(document.getElementById('messages'), true);
        } else {
            el.classList.add('hidden');
            if (_thinkingInterval) {
                clearInterval(_thinkingInterval);
                _thinkingInterval = null;
            }
        }
    }

    function _updateThinkingWord() {
        const textEl = document.querySelector('.thinking-text');
        if (!textEl) return;
        const word = document.createElement('span');
        word.className = 'thinking-word';
        word.textContent = _thinkingPhrases[_thinkingIndex];
        textEl.innerHTML = '';
        textEl.appendChild(word);
    }

    // --- Init ---

    function init() {
        initTheme();
        initSidebar();
        initTextarea();

        document.getElementById('theme-toggle')?.addEventListener('click', toggleTheme);
        document.getElementById('sidebar-toggle')?.addEventListener('click', toggleSidebar);
    }

    return { init, scrollToBottom, isNearBottom, showTyping, toggleTheme, toggleSidebar };

})();

document.addEventListener('DOMContentLoaded', UI.init);
