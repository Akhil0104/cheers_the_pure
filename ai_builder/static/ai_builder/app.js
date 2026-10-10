(function () {
  'use strict';

  const workspace = document.getElementById('saas-workspace');
  if (!workspace) return;

  const state = {
    site: null,
    prompt: '',
    selectedSectionId: null,
    previewMode: 'desktop',
    dirty: false,
    editRevision: 0,
    pendingEdits: [],
    inquiryIdempotencyKey: null,
    saving: false,
    refining: false,
    saveTimer: null,
    saveQueue: Promise.resolve()
  };
  const elements = {
    canvas: document.getElementById('site-canvas'),
    generateForm: document.getElementById('generate-form'),
    prompt: document.getElementById('site-prompt'),
    audience: document.getElementById('site-audience'),
    goal: document.getElementById('site-goal'),
    visualDirection: document.getElementById('site-visual-direction'),
    promptCount: document.getElementById('prompt-count'),
    samplePrompt: document.getElementById('sample-prompt-button'),
    retryButton: document.getElementById('retry-button'),
    generateButton: document.getElementById('generate-button'),
    progress: document.getElementById('generation-progress'),
    progressMessage: document.getElementById('generation-message'),
    sectionList: document.getElementById('section-list'),
    sectionCount: document.getElementById('section-count'),
    sectionSelector: document.getElementById('section-selector'),
    refineInstruction: document.getElementById('refine-instruction'),
    refineButton: document.getElementById('refine-button'),
    feedback: document.getElementById('feedback-message'),
    savedState: document.getElementById('saved-state'),
    unsavedIndicator: document.getElementById('unsaved-indicator'),
    projectName: document.getElementById('project-name'),
    saveButton: document.getElementById('save-button'),
    publishButton: document.getElementById('publish-button'),
    exportButton: document.getElementById('export-button'),
    reloadButton: document.getElementById('reload-sites-button'),
    savedDialog: document.getElementById('saved-sites-dialog'),
    savedList: document.getElementById('saved-sites-list'),
    quoteDialog: document.getElementById('quote-dialog'),
    quoteContent: document.getElementById('quote-dialog-content')
  };
  const typeLabels = {
    hero: 'Hero',
    features: 'Features',
    product_grid: 'Product grid',
    quote_form: 'Quote form',
    footer: 'Footer',
    text_block: 'Text block',
    testimonials: 'Testimonials'
  };

  function endpoint(template, siteId) {
    return template.replace('00000000-0000-0000-0000-000000000000', encodeURIComponent(siteId));
  }

  function csrfToken() {
    return workspace.dataset.csrfToken || '';
  }

  async function request(url, options) {
    const settings = Object.assign({ credentials: 'same-origin' }, options || {});
    settings.headers = Object.assign({ Accept: 'application/json' }, settings.headers || {});
    if (settings.body) {
      settings.headers['Content-Type'] = 'application/json';
      settings.headers['X-CSRFToken'] = csrfToken();
    }
    const response = await fetch(url, settings);
    if (response.redirected && response.url.includes('/login/')) {
      throw new Error('Your session has expired. Sign in again to continue.');
    }
    const contentType = response.headers.get('content-type') || '';
    const payload = contentType.includes('application/json') ? await response.json() : null;
    if (!response.ok || !payload || (payload.ok !== true && payload.success !== true)) {
      if (response.status === 401 || (response.redirected && response.url.includes('/login/'))) {
        throw new Error('Your session has expired. Sign in again to continue.');
      }
      const serverError = payload && payload.error;
      const error = new Error(typeof serverError === 'string' ? serverError : `The server could not complete this request (${response.status}).`);
      error.activity = payload && payload.activity ? payload.activity : [];
      throw error;
    }
    return payload;
  }

  function showMessage(message, isError) {
    elements.feedback.textContent = message;
    elements.feedback.classList.toggle('is-error', Boolean(isError));
  }

  function updatePromptCount() {
    elements.promptCount.textContent = `${elements.prompt.value.length} / 4000`;
  }

  function generationPayload() {
    return {
      prompt: elements.prompt.value.trim(),
      audience: elements.audience.value.trim(),
      goal: elements.goal.value.trim(),
      visual_direction: elements.visualDirection.value.trim()
    };
  }

  function showActivity(activity) {
    if (!Array.isArray(activity) || !activity.length) return;
    const latest = activity[activity.length - 1];
    if (latest && latest.summary) showMessage(latest.summary, latest.outcome === 'failed');
  }

  function markDirty(message) {
    state.editRevision += 1;
    state.dirty = true;
    elements.savedState.textContent = 'Unsaved changes';
    elements.unsavedIndicator.textContent = 'Unsaved changes';
    elements.unsavedIndicator.classList.add('has-changes');
    if (message) showMessage(message, false);
    scheduleSave();
  }

  function markSaved(message) {
    state.dirty = false;
    elements.savedState.textContent = 'Saved to your account';
    elements.unsavedIndicator.textContent = 'All changes saved';
    elements.unsavedIndicator.classList.remove('has-changes');
    if (message) showMessage(message, false);
  }

  function setBusy(button, busy, busyText) {
    if (busy) {
      button.dataset.originalText = button.querySelector('.button-label, span')?.textContent || button.textContent;
      button.disabled = true;
      const label = button.querySelector('.button-label, span');
      if (label && busyText) label.textContent = busyText;
    } else {
      button.disabled = false;
      const label = button.querySelector('.button-label, span');
      if (label && button.dataset.originalText) label.textContent = button.dataset.originalText;
    }
  }

  function updateControls() {
    const hasSite = Boolean(state.site);
    elements.saveButton.disabled = !hasSite || state.saving || state.refining;
    elements.publishButton.disabled = !hasSite || state.saving || state.refining;
    elements.exportButton.disabled = !hasSite || state.refining;
    elements.sectionSelector.disabled = !hasSite;
    elements.refineInstruction.disabled = !hasSite || !state.selectedSectionId || state.refining;
    elements.refineButton.disabled = !hasSite || !state.selectedSectionId || state.refining;
    if (state.site) {
      elements.projectName.textContent = state.site.site_name;
      document.title = `${state.site.site_name} · SaaSsum AI`;
    }
  }

  function renderSectionControls() {
    if (!state.site) return;
    elements.sectionCount.textContent = String(state.site.sections.length);
    elements.sectionList.replaceChildren();
    elements.sectionSelector.replaceChildren();
    state.site.sections.forEach(function (section, index) {
      const item = document.createElement('li');
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'section-row';
      button.setAttribute('aria-current', String(section.id === state.selectedSectionId));
      const number = document.createElement('span');
      number.className = 'section-index';
      number.textContent = String(index + 1).padStart(2, '0');
      const label = document.createElement('span');
      label.className = 'section-type';
      label.textContent = typeLabels[section.type] || section.type;
      const icon = document.createElement('i');
      icon.className = 'fa-solid fa-grip-lines';
      icon.setAttribute('aria-hidden', 'true');
      button.append(number, label, icon);
      button.addEventListener('click', function () {
        state.selectedSectionId = section.id;
        render();
      });
      item.append(button);
      elements.sectionList.append(item);

      const option = document.createElement('option');
      option.value = section.id;
      option.textContent = `${String(index + 1).padStart(2, '0')} · ${typeLabels[section.type] || section.type}`;
      elements.sectionSelector.append(option);
    });
    elements.sectionSelector.value = state.selectedSectionId || state.site.sections[0].id;
    elements.sectionSelector.disabled = false;
    elements.refineInstruction.disabled = !state.selectedSectionId || state.refining;
    elements.refineButton.disabled = !state.selectedSectionId || state.refining;
  }

  function render() {
    if (!state.site) return;
    SaaSsumRenderer.renderDocument(state.site, elements.canvas, {
      editable: true,
      selectedSectionId: state.selectedSectionId,
      onSelect: function (sectionId) {
        state.selectedSectionId = sectionId;
        render();
      },
      onEdit: handleInlineEdit,
      onAction: handleSiteAction
    });
    elements.canvas.classList.toggle('is-mobile', state.previewMode === 'mobile');
    document.getElementById('canvas-size-label').textContent = state.previewMode === 'mobile' ? 'Mobile · 390px' : 'Desktop · 100%';
    renderSectionControls();
    updateControls();
  }

  function getByPath(object, path) {
    return path.split('.').reduce(function (value, part) {
      return value && value[part] !== undefined ? value[part] : undefined;
    }, object);
  }

  function setByPath(object, path, value) {
    const parts = path.split('.');
    const final = parts.pop();
    const target = parts.reduce(function (current, part) {
      return current[part];
    }, object);
    target[final] = value;
  }

  function handleInlineEdit(sectionIndex, path, value) {
    const section = state.site && state.site.sections[sectionIndex];
    if (!section || getByPath(section, path) === undefined) return;
    const nextValue = value.trim();
    if (!nextValue) {
      showMessage('Text cannot be empty. Your previous value was restored.', true);
      render();
      return;
    }
    if (getByPath(section, path) === nextValue) return;
    setByPath(section, path, nextValue);
    state.pendingEdits.push({ sectionId: section.id, path: path, value: nextValue, revision: state.editRevision + 1 });
    state.selectedSectionId = section.id;
    markDirty('Text updated. Saving your changes…');
    render();
  }

  function handleSiteAction(action, values, status, submitButton) {
    if (action === 'submit_b2b_inquiry' && values) {
      submitInquiry(values, status, submitButton);
      return;
    }
    if (action === 'submit_b2b_inquiry') openQuoteDialog();
    if (action === 'scroll_to_products') {
      const productSection = elements.canvas.querySelector('[data-section-id][class*="rendered-section"]:has(.rendered-products-grid)');
      productSection?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
    if (action === 'contact_business' || action === 'learn_more') {
      showMessage('This action needs a destination configured by the site owner.', true);
    }
  }

  function openQuoteDialog() {
    const section = state.site.sections.find(function (item) { return item.type === 'quote_form'; });
    if (!section) {
      showMessage('This site does not have a quote form section.', true);
      return;
    }
    elements.quoteContent.replaceChildren();
    const title = document.createElement('h2');
    title.id = 'quote-dialog-title';
    title.textContent = section.title;
    const subtitle = document.createElement('p');
    subtitle.className = 'rendered-section-intro';
    subtitle.textContent = section.subtitle;
    const holder = document.createElement('div');
    SaaSsumRenderer.renderDocument({ site_id: state.site.site_id, sections: [section] }, holder, {
      editable: false,
      onAction: handleSiteAction
    });
    elements.quoteContent.append(title, subtitle, holder);
    elements.quoteDialog.hidden = false;
    elements.quoteDialog.querySelector('input')?.focus();
  }

  async function submitInquiry(values, status, submitButton) {
    submitButton.disabled = true;
    status.textContent = 'Sending inquiry…';
    try {
      if (!state.inquiryIdempotencyKey) {
        state.inquiryIdempotencyKey = crypto.randomUUID();
      }
      const response = await request(workspace.dataset.inquiryUrl, {
        method: 'POST',
        headers: { 'Idempotency-Key': state.inquiryIdempotencyKey },
        body: JSON.stringify(values)
      });
      if (!response.success || !response.quote_id) {
        throw new Error('The server did not confirm a saved inquiry. Please try again.');
      }
      state.inquiryIdempotencyKey = null;
      status.textContent = `${response.message}. Reference #${response.quote_id}. This is a pending inquiry, not an order.`;
      showMessage(`Quote request #${response.quote_id} received. The business team will review it.`, false);
    } catch (error) {
      status.textContent = error.message;
      showMessage(error.message, true);
    } finally {
      submitButton.disabled = false;
    }
  }

  elements.generateForm.addEventListener('submit', async function (event) {
    event.preventDefault();
    const prompt = elements.prompt.value.trim();
    if (!prompt) {
      elements.prompt.focus();
      return;
    }
    state.prompt = prompt;
    elements.generateButton.disabled = true;
    elements.retryButton.hidden = true;
    elements.progress.hidden = false;
    elements.progressMessage.textContent = 'Planning your page structure…';
    showMessage('Generating and validating your website.');
    const progressTimer = window.setTimeout(function () {
      elements.progressMessage.textContent = 'Checking sections, links, and content…';
    }, 1800);
    try {
      const result = await request(workspace.dataset.generateUrl, {
        method: 'POST',
        body: JSON.stringify(generationPayload())
      });
      window.clearTimeout(progressTimer);
      showActivity(result.activity);
      loadSavedSite(result.saved_site, prompt);
      markSaved('Website generated and saved to your account.');
    } catch (error) {
      window.clearTimeout(progressTimer);
      showActivity(error.activity);
      showMessage(error.message, true);
      elements.retryButton.hidden = false;
    } finally {
      elements.generateButton.disabled = false;
      elements.progress.hidden = true;
    }
  });

  elements.retryButton.addEventListener('click', function () {
    elements.generateForm.requestSubmit();
  });

  elements.samplePrompt.addEventListener('click', function () {
    elements.prompt.value = 'A clean wholesale website for a bottled water supplier serving hotels, restaurants, and retailers.';
    elements.audience.value = 'Hotels, restaurants, and retail distributors';
    elements.goal.value = 'Collect wholesale quote requests';
    elements.visualDirection.value = 'Calm, clear, and trustworthy';
    updatePromptCount();
    elements.prompt.focus();
    showMessage('Sample brief added. Edit it or generate when ready.');
  });

  elements.prompt.addEventListener('input', updatePromptCount);
  updatePromptCount();

  function loadSavedSite(savedSite, prompt) {
    state.site = savedSite.site;
    state.prompt = prompt !== undefined ? prompt : savedSite.prompt || '';
    state.siteId = savedSite.site_id;
    state.selectedSectionId = state.site.sections[0]?.id || null;
    state.dirty = false;
    state.pendingEdits = [];
    elements.prompt.value = state.prompt;
    render();
  }

  function scheduleSave() {
    window.clearTimeout(state.saveTimer);
    state.saveTimer = window.setTimeout(function () {
      if (state.refining) {
        scheduleSave();
        return;
      }
      state.saveQueue = state.saveQueue.then(saveSite).catch(function (error) {
        state.dirty = true;
        elements.savedState.textContent = 'Save failed';
        showMessage(error.message, true);
      });
    }, 700);
  }

  async function saveSite() {
    if (!state.site || !state.dirty || state.refining) return;
    const revision = state.editRevision;
    state.saving = true;
    updateControls();
    elements.savedState.textContent = 'Saving…';
    try {
      const isExisting = Boolean(state.siteId);
      const url = isExisting ? endpoint(workspace.dataset.detailUrlTemplate, state.siteId) : workspace.dataset.sitesUrl;
      const result = await request(url, {
        method: isExisting ? 'PUT' : 'POST',
        body: JSON.stringify({ site: state.site, prompt: state.prompt })
      });
      state.siteId = result.saved_site.site_id;
      if (revision === state.editRevision) {
        markSaved('Your edits are saved to your account.');
      } else {
        state.dirty = true;
        elements.savedState.textContent = 'Unsaved changes';
        scheduleSave();
      }
    } finally {
      state.saving = false;
      updateControls();
    }
  }

  elements.saveButton.addEventListener('click', function () {
    window.clearTimeout(state.saveTimer);
    state.saveQueue = state.saveQueue.then(saveSite).catch(function (error) {
      showMessage(error.message, true);
      elements.savedState.textContent = 'Save failed';
    });
  });

  elements.sectionSelector.addEventListener('change', function () {
    state.selectedSectionId = elements.sectionSelector.value;
    render();
  });

  elements.refineButton.addEventListener('click', async function () {
    if (!state.site || !state.selectedSectionId) return;
    const instruction = elements.refineInstruction.value.trim();
    if (!instruction) {
      elements.refineInstruction.focus();
      return;
    }
    elements.refineButton.disabled = true;
    elements.refineButton.querySelector('span').textContent = 'Updating section…';
    showMessage('Updating only the selected section…');
    try {
      window.clearTimeout(state.saveTimer);
      if (state.dirty) await saveSite();
      state.refining = true;
      updateControls();
      const refiningSectionId = state.selectedSectionId;
      const revision = state.editRevision;
      const result = await request(workspace.dataset.refineUrl, {
        method: 'POST',
        body: JSON.stringify({ site_id: state.siteId, section_id: refiningSectionId, instruction: instruction })
      });
      const index = state.site.sections.findIndex(function (item) { return item.id === refiningSectionId; });
      if (index < 0) throw new Error('The selected section no longer exists.');
      const refinedSection = result.section;
      state.pendingEdits
        .filter(function (edit) { return edit.sectionId === refinedSection.id && edit.revision > revision; })
        .forEach(function (edit) { setByPath(refinedSection, edit.path, edit.value); });
      state.site.sections[index] = refinedSection;
      render();
      if (revision === state.editRevision) {
        markSaved('Section updated and saved.');
      } else {
        state.dirty = true;
        elements.savedState.textContent = 'Unsaved changes';
        elements.unsavedIndicator.textContent = 'Unsaved changes';
        elements.unsavedIndicator.classList.add('has-changes');
      }
      elements.refineInstruction.value = '';
    } catch (error) {
      showMessage(error.message, true);
    } finally {
      state.refining = false;
      elements.refineButton.querySelector('span').textContent = 'Update section';
      updateControls();
      if (state.dirty) scheduleSave();
    }
  });

  document.querySelectorAll('[data-preview]').forEach(function (button) {
    button.addEventListener('click', function () {
      state.previewMode = button.dataset.preview;
      document.querySelectorAll('[data-preview]').forEach(function (item) {
        const active = item === button;
        item.classList.toggle('is-active', active);
        item.setAttribute('aria-pressed', String(active));
      });
      elements.canvas.classList.toggle('is-mobile', state.previewMode === 'mobile');
      document.getElementById('canvas-size-label').textContent = state.previewMode === 'mobile' ? 'Mobile · 390px' : 'Desktop · 100%';
    });
  });

  elements.reloadButton.addEventListener('click', openSavedSites);
  document.getElementById('close-sites-dialog').addEventListener('click', function () { elements.savedDialog.close(); });
  document.getElementById('close-quote').addEventListener('click', function () { elements.quoteDialog.hidden = true; });
  elements.quoteDialog.addEventListener('click', function (event) {
    if (event.target === elements.quoteDialog) elements.quoteDialog.hidden = true;
  });

  async function openSavedSites() {
    elements.savedList.replaceChildren();
    const loading = document.createElement('p');
    loading.textContent = 'Loading your websites…';
    elements.savedList.append(loading);
    elements.savedDialog.showModal();
    try {
      const result = await request(workspace.dataset.sitesUrl, { method: 'GET' });
      elements.savedList.replaceChildren();
      if (!result.sites.length) {
        const empty = document.createElement('p');
        empty.textContent = 'No saved websites yet. Generate your first website to see it here.';
        elements.savedList.append(empty);
        return;
      }
      result.sites.forEach(function (savedSite) {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'saved-site-item';
        const details = document.createElement('span');
        const name = document.createElement('span');
        name.className = 'saved-site-name';
        name.textContent = savedSite.site.site_name;
        const date = document.createElement('span');
        date.className = 'saved-site-date';
        date.textContent = new Date(savedSite.updated_at).toLocaleString();
        details.append(name, document.createElement('br'), date);
        const icon = document.createElement('i');
        icon.className = 'fa-solid fa-arrow-right';
        icon.setAttribute('aria-hidden', 'true');
        button.append(details, icon);
        button.addEventListener('click', function () {
          loadSavedSite(savedSite);
          markSaved('Saved website loaded.');
          elements.savedDialog.close();
        });
        elements.savedList.append(button);
      });
    } catch (error) {
      elements.savedList.replaceChildren();
      const message = document.createElement('p');
      message.textContent = error.message;
      message.setAttribute('role', 'alert');
      elements.savedList.append(message);
    }
  }

  elements.publishButton.addEventListener('click', async function () {
    if (state.dirty) {
      try { await saveSite(); } catch (error) { showMessage(error.message, true); return; }
    }
    if (!state.siteId) return;
    elements.publishButton.disabled = true;
    try {
      const result = await request(endpoint(workspace.dataset.publishUrlTemplate, state.siteId), { method: 'POST', body: '{}' });
      const shareUrl = new URL(result.saved_site.share_url, window.location.origin).href;
      try {
        await navigator.clipboard.writeText(shareUrl);
        showMessage('Published. Share link copied to your clipboard.');
      } catch (_clipboardError) {
        showMessage(`Published. Share this link: ${shareUrl}`);
      }
    } catch (error) {
      showMessage(error.message, true);
    } finally {
      updateControls();
    }
  });

  elements.exportButton.addEventListener('click', async function () {
    if (!state.site) return;
    try {
      const [styleResponse, rendererResponse] = await Promise.all([
        fetch('/static/ai_builder/builder.css', { credentials: 'same-origin' }),
        fetch('/static/ai_builder/renderer.js', { credentials: 'same-origin' })
      ]);
      if (!styleResponse.ok || !rendererResponse.ok) throw new Error('Could not load export styles or renderer.');
      const [styles, rendererSource] = await Promise.all([styleResponse.text(), rendererResponse.text()]);
      const jsonPayload = JSON.stringify(state.site)
        .replace(/</g, '\\u003c')
        .replace(/\u2028/g, '\\u2028')
        .replace(/\u2029/g, '\\u2029');
      const safeTitle = escapeHtml(state.site.site_name);
      const exported = `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${safeTitle}</title><link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Manrope:wght@500;600;700;800&display=swap" rel="stylesheet"><style>${styles}</style></head><body class="shared-site-body"><main class="shared-site-root" id="site-root"></main><script type="application/json" id="site-data">${jsonPayload}</script><script>${rendererSource}</script><script>window.SaaSsumRenderer.renderDocument(JSON.parse(document.getElementById('site-data').textContent),document.getElementById('site-root'),{editable:false,readOnly:true,onAction:function(){return false;}});<\/script></body></html>`;
      const blob = new Blob([exported], { type: 'text/html;charset=utf-8' });
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = `${state.site.site_name.toLowerCase().replace(/[^a-z0-9]+/g, '-') || 'saassum-site'}.html`;
      link.click();
      window.setTimeout(function () { URL.revokeObjectURL(link.href); }, 1000);
      showMessage('HTML exported. AI generation, saving, sharing, and quote submission require the live backend. Remote images/fonts require network access.');
    } catch (error) {
      showMessage(error.message, true);
    }
  });

  function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, function (character) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[character];
    });
  }

  window.addEventListener('beforeunload', function (event) {
    if (state.dirty) {
      event.preventDefault();
      event.returnValue = '';
    }
  });

  updateControls();
})();