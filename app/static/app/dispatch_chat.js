/**
 * DispatchAI Chat System — dispatch_chat.js
 *
 * Provides a professional B2B conversational interface for DispatchAI.
 * Connects directly to the production API endpoint: POST /api/agent/chat
 *
 * Supports:
 * - Embedded dashboard console (#dispatch-dashboard-chat)
 * - Floating popup panel (#dispatch-panel)
 * - Suggested business prompt chips
 * - Real backend-driven indicators: "Memory used" & "Business data used"
 * - Action buttons for quote requests and order tracking
 * - CSRF authentication and error handling
 */

class DispatchAIChat {
  constructor(opts = {}) {
    this.apiEndpoint   = opts.apiEndpoint || '/api/agent/chat';
    this.sessionId     = opts.sessionId || null;
    this.isProcessing  = false;
    this.container     = null;
    this.messagesEl    = null;
    this.inputEl       = null;
    this.sendBtn       = null;
    this.promptsEl     = null;
    this.isEmbedded    = opts.isEmbedded || false;
    this.launcher      = null;
    this.panel         = null;
  }

  // ── Initialisation ─────────────────────────────────────────────────────
  init(containerEl) {
    if (containerEl) {
      this.container = containerEl;
    } else {
      this.container = document.getElementById('dispatch-dashboard-chat') ||
                       document.getElementById('dispatch-panel');
    }

    if (!this.container) return;

    this.messagesEl = this.container.querySelector('.dai-messages');
    this.inputEl    = this.container.querySelector('.dai-input');
    this.sendBtn    = this.container.querySelector('.dai-send-btn');
    this.promptsEl  = this.container.querySelector('.dai-prompts-container');
    this.launcher   = document.getElementById('dispatch-launcher');
    this.panel      = document.getElementById('dispatch-panel');

    this._bindEvents();

    // If messages area is empty, append default greeting
    if (this.messagesEl && this.messagesEl.children.length === 0) {
      this._appendWelcomeMessage();
    }
  }

  _appendWelcomeMessage() {
    const welcome = "👋 **Hello! I'm DispatchAI**, your B2B Supply & Distribution Assistant for **Cheers the Pure**.\n\n" +
      "I have real-time access to our wholesale catalog, tiered volume pricing, your order history, and remembered delivery constraints.\n\n" +
      "How can I assist your distribution business today?";
    this._appendMessage({
      role: 'assistant',
      content: welcome,
      timestamp: new Date().toISOString(),
      memory_used: false,
      sources: ['Cheers the Pure Authoritative Database Catalog'],
    });
  }

  _bindEvents() {
    // Send button click
    if (this.sendBtn) {
      this.sendBtn.addEventListener('click', () => this.sendMessage());
    }

    // Input keyboard handling (Enter to send, Shift+Enter for newline)
    if (this.inputEl) {
      this.inputEl.addEventListener('input', () => {
        this._autoResize(this.inputEl);
        this._updateSendButtonState();
      });

      this.inputEl.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault();
          if (!this.sendBtn || !this.sendBtn.disabled) {
            this.sendMessage();
          }
        }
      });
    }

    // Suggested prompt chips
    if (this.container) {
      const promptChips = this.container.querySelectorAll('.dai-prompt-chip');
      promptChips.forEach(chip => {
        chip.addEventListener('click', (e) => {
          e.preventDefault();
          const promptText = chip.getAttribute('data-prompt') || chip.textContent.trim();
          this.sendMessage(promptText);
        });
      });

      // Clear / Reset conversation button
      const resetBtn = this.container.querySelector('.dai-reset-btn');
      if (resetBtn) {
        resetBtn.addEventListener('click', (e) => {
          e.preventDefault();
          this.resetConversation();
        });
      }

      // Close button on floating panel
      const closeBtn = this.container.querySelector('.dai-header-close');
      if (closeBtn) {
        closeBtn.addEventListener('click', (e) => {
          e.preventDefault();
          this.close();
        });
      }
    }

    // Launcher button for floating panel
    if (this.launcher) {
      this.launcher.addEventListener('click', () => this.toggle());
    }
  }

  // ── Floating Panel Controls ────────────────────────────────────────────
  toggle() {
    if (!this.panel) return;
    this.panel.classList.contains('open') ? this.close() : this.open();
  }

  open() {
    if (!this.panel) return;
    this.panel.classList.add('open');
    this.panel.setAttribute('aria-hidden', 'false');
    if (this.launcher) this.launcher.classList.add('open');
    setTimeout(() => this.inputEl && this.inputEl.focus(), 250);
  }

  close() {
    if (!this.panel) return;
    this.panel.classList.remove('open');
    this.panel.setAttribute('aria-hidden', 'true');
    if (this.launcher) this.launcher.classList.remove('open');
  }

  resetConversation() {
    this.sessionId = null;
    if (this.messagesEl) {
      this.messagesEl.innerHTML = '';
      this._appendWelcomeMessage();
    }
    if (this.inputEl) {
      this.inputEl.value = '';
      this._autoResize(this.inputEl);
      this._updateSendButtonState();
    }
  }

  // ── Message Transmission ───────────────────────────────────────────────
  async sendMessage(customText = null) {
    if (this.isProcessing) return;

    const text = (customText !== null ? customText : (this.inputEl ? this.inputEl.value : '')).trim();
    if (!text) return;

    // Clear input
    if (this.inputEl && customText === null) {
      this.inputEl.value = '';
      this._autoResize(this.inputEl);
      this._updateSendButtonState();
    }

    // 1. Render user message bubble
    this._appendMessage({
      role: 'user',
      content: text,
      timestamp: new Date().toISOString(),
    });

    // 2. Render loading typing indicator
    this.isProcessing = true;
    this._setLoadingState(true);
    this._showTypingIndicator();

    try {
      // 3. POST to /api/agent/chat
      const response = await fetch(this.apiEndpoint, {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json',
          'X-CSRFToken': this._getCsrfToken(),
        },
        body: JSON.stringify({
          message: text,
          session_id: this.sessionId,
        }),
      });

      this._hideTypingIndicator();

      const data = await response.json();

      if (!response.ok || data.success === false) {
        const errorMsg = data.error || data.reply || 'An error occurred while connecting to DispatchAI. Please try again.';
        this._appendErrorMessage(errorMsg, text);
        return;
      }

      // 4. Update session ID for multi-turn conversational context
      if (data.session_id) {
        this.sessionId = data.session_id;
      }

      // 5. Render agent response with real backend badges & actions
      this._appendMessage({
        role: 'assistant',
        content: data.reply || 'No response received from agent.',
        timestamp: new Date().toISOString(),
        memory_used: !!data.memory_used,
        memory_summary: data.memory_summary || '',
        sources: Array.isArray(data.sources) ? data.sources : [],
        actions: Array.isArray(data.actions) ? data.actions : [],
      });

    } catch (err) {
      console.error('[DispatchAI UI] Network error:', err);
      this._hideTypingIndicator();
      this._appendErrorMessage('Unable to connect to DispatchAI server. Please check your network connection and try again.', text);
    } finally {
      this.isProcessing = false;
      this._setLoadingState(false);
      this._updateSendButtonState();
      if (this.inputEl) this.inputEl.focus();
    }
  }

  // ── DOM Rendering Helpers ──────────────────────────────────────────────
  _appendMessage({ role, content, timestamp, memory_used, memory_summary, sources, actions }) {
    if (!this.messagesEl) return;

    const msgRow = document.createElement('div');
    msgRow.className = `dai-msg-row dai-msg-${role}`;

    // Avatar
    const avatar = document.createElement('div');
    avatar.className = 'dai-msg-avatar';
    avatar.innerHTML = role === 'user' ? '👤' : '🤖';
    msgRow.appendChild(avatar);

    // Body container
    const body = document.createElement('div');
    body.className = 'dai-msg-body';

    // Bubble
    const bubble = document.createElement('div');
    bubble.className = 'dai-bubble';
    bubble.innerHTML = this._formatMarkdown(content);
    body.appendChild(bubble);

    // Badges Container (Only for Assistant responses with REAL backend flags)
    if (role === 'assistant') {
      const badgesContainer = document.createElement('div');
      badgesContainer.className = 'dai-badges-row';

      // 1. "Memory used" badge (Strictly when memory_used is true)
      if (memory_used) {
        const memoryBadge = document.createElement('span');
        memoryBadge.className = 'dai-badge-pill dai-badge-memory';
        memoryBadge.title = memory_summary || 'Hindsight persistent memory was retrieved for this answer.';
        memoryBadge.innerHTML = '<span class="dai-badge-icon">🧠</span> Memory used';
        badgesContainer.appendChild(memoryBadge);
      }

      // 2. "Business data used" badge (Strictly when sources include catalog/database/rules)
      if (sources && sources.length > 0) {
        const businessBadge = document.createElement('span');
        businessBadge.className = 'dai-badge-pill dai-badge-business';
        businessBadge.title = `Authoritative data sources: ${sources.join(', ')}`;
        businessBadge.innerHTML = '<span class="dai-badge-icon">📊</span> Business data used';
        badgesContainer.appendChild(businessBadge);
      }

      if (badgesContainer.children.length > 0) {
        body.appendChild(badgesContainer);
      }

      // 3. Quick Action Buttons (e.g. Request Quote, Track Order)
      if (actions && actions.length > 0) {
        const actionsContainer = document.createElement('div');
        actionsContainer.className = 'dai-actions-row';
        actions.forEach(action => {
          if (action.url && action.label) {
            const btn = document.createElement('a');
            btn.className = 'dai-action-btn';
            btn.href = action.url;
            btn.textContent = `${action.label} →`;
            actionsContainer.appendChild(btn);
          }
        });
        body.appendChild(actionsContainer);
      }
    }

    // Timestamp
    if (timestamp) {
      const timeEl = document.createElement('div');
      timeEl.className = 'dai-msg-time';
      const timeStr = new Date(timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      timeEl.textContent = `${role === 'user' ? 'You' : 'DispatchAI'} • ${timeStr}`;
      body.appendChild(timeEl);
    }

    msgRow.appendChild(body);
    this.messagesEl.appendChild(msgRow);
    this._scrollToBottom();
  }

  _appendErrorMessage(errorText, originalPrompt = null) {
    if (!this.messagesEl) return;

    const errorRow = document.createElement('div');
    errorRow.className = 'dai-msg-row dai-msg-assistant dai-msg-error';

    const avatar = document.createElement('div');
    avatar.className = 'dai-msg-avatar';
    avatar.innerHTML = '⚠️';
    errorRow.appendChild(avatar);

    const body = document.createElement('div');
    body.className = 'dai-msg-body';

    const bubble = document.createElement('div');
    bubble.className = 'dai-bubble dai-bubble-error';
    bubble.textContent = errorText;
    body.appendChild(bubble);

    if (originalPrompt) {
      const retryBtn = document.createElement('button');
      retryBtn.className = 'dai-retry-btn';
      retryBtn.type = 'button';
      retryBtn.innerHTML = '↻ Retry message';
      retryBtn.addEventListener('click', () => {
        errorRow.remove();
        this.sendMessage(originalPrompt);
      });
      body.appendChild(retryBtn);
    }

    errorRow.appendChild(body);
    this.messagesEl.appendChild(errorRow);
    this._scrollToBottom();
  }

  _showTypingIndicator() {
    this._hideTypingIndicator();
    if (!this.messagesEl) return;

    const typingRow = document.createElement('div');
    typingRow.className = 'dai-msg-row dai-msg-assistant dai-typing-row';
    typingRow.id = 'dai-typing-indicator';

    const avatar = document.createElement('div');
    avatar.className = 'dai-msg-avatar';
    avatar.innerHTML = '🤖';
    typingRow.appendChild(avatar);

    const body = document.createElement('div');
    body.className = 'dai-msg-body';

    const bubble = document.createElement('div');
    bubble.className = 'dai-bubble dai-typing-bubble';
    bubble.innerHTML = `
      <div class="dai-typing-dots">
        <span></span><span></span><span></span>
      </div>
      <span class="dai-typing-text">DispatchAI is analyzing catalog & memory...</span>
    `;
    body.appendChild(bubble);

    typingRow.appendChild(body);
    this.messagesEl.appendChild(typingRow);
    this._scrollToBottom();
  }

  _hideTypingIndicator() {
    const el = document.getElementById('dai-typing-indicator');
    if (el) el.remove();
  }

  _setLoadingState(isLoading) {
    if (this.sendBtn) {
      this.sendBtn.disabled = isLoading;
      if (isLoading) {
        this.sendBtn.classList.add('loading');
      } else {
        this.sendBtn.classList.remove('loading');
      }
    }
    if (this.inputEl) {
      this.inputEl.disabled = isLoading;
    }
  }

  _updateSendButtonState() {
    if (!this.sendBtn || !this.inputEl) return;
    const hasText = this.inputEl.value.trim().length > 0;
    this.sendBtn.disabled = !hasText || this.isProcessing;
  }

  _autoResize(el) {
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 120) + 'px';
  }

  _scrollToBottom() {
    if (this.messagesEl) {
      this.messagesEl.scrollTop = this.messagesEl.scrollHeight;
    }
  }

  _formatMarkdown(text) {
    if (!text) return '';
    // Basic safe markdown parser for formatting
    let html = text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');

    // Bold
    html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    // Italic
    html = html.replace(/\*(.*?)\*/g, '<em>$1</em>');
    // Code blocks / inline code
    html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
    // Bullet lists
    html = html.replace(/^\s*[-•]\s+(.*)$/gm, '<li>$1</li>');
    html = html.replace(/(<li>.*<\/li>)/gs, '<ul>$1</ul>');
    // Paragraph breaks
    html = html.replace(/\n\n/g, '<br><br>');
    html = html.replace(/\n/g, '<br>');

    return html;
  }

  _getCsrfToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    if (meta) return meta.getAttribute('content');
    const input = document.querySelector('input[name="csrfmiddlewaretoken"]');
    if (input) return input.value;
    const match = document.cookie.match(/csrftoken=([^;]+)/);
    return match ? match[1] : '';
  }
}

// ── Auto Initialization on DOM Ready ──────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  // 1. Check for embedded console on B2B dashboard
  const embeddedConsole = document.getElementById('dispatch-dashboard-chat');
  if (embeddedConsole) {
    window.dispatchAIDashboard = new DispatchAIChat({
      apiEndpoint: '/api/agent/chat',
      isEmbedded: true,
    });
    window.dispatchAIDashboard.init(embeddedConsole);
  }

  // 2. Check for floating panel
  const floatingPanel = document.getElementById('dispatch-panel');
  if (floatingPanel) {
    window.dispatchAI = new DispatchAIChat({
      apiEndpoint: '/api/agent/chat',
      isEmbedded: false,
    });
    window.dispatchAI.init(floatingPanel);
  }
});
