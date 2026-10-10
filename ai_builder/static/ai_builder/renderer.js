(function (global) {
  'use strict';

  const icons = {
    activity: '◌',
    'badge-check': '✓',
    droplet: '◒',
    'flask-conical': '⚗',
    leaf: '⌁',
    'package-check': '▣',
    'shield-check': '◇',
    sparkles: '✦',
    truck: '▰',
    users: '♧',
    zap: 'ϟ'
  };

  function make(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined && text !== null) element.textContent = String(text);
    return element;
  }

  function editable(tag, className, text, sectionIndex, path, options) {
    const element = make(tag, className, text);
    const settings = options || {};
    if (settings.editable) {
      element.contentEditable = 'true';
      element.classList.add('inline-editable');
      element.dataset.sectionIndex = String(sectionIndex);
      element.dataset.fieldPath = path;
      element.setAttribute('role', 'textbox');
      element.setAttribute('aria-label', settings.label || 'Edit text');
      element.setAttribute('spellcheck', 'true');
    }
    return element;
  }

  function sectionRoot(section, options, className) {
    const root = make('section', `rendered-section ${className || ''}`.trim());
    root.dataset.sectionId = section.id;
    if (options.editable) {
      root.tabIndex = 0;
      root.setAttribute('aria-label', `${section.type.replace('_', ' ')} section`);
      root.addEventListener('click', function (event) {
        if (event.target.closest('[contenteditable="true"], button, a, input, select, textarea')) return;
        options.onSelect(section.id);
      });
    }
    if (options.selectedSectionId === section.id) root.classList.add('is-selected');
    return root;
  }

  function renderHero(section, index, options) {
    const root = sectionRoot(section, options, 'rendered-hero');
    const content = make('div', 'rendered-hero-content');
    content.append(
      editable('h1', '', section.headline, index, 'headline', { ...options, label: 'Hero headline' }),
      editable('p', '', section.subheadline, index, 'subheadline', { ...options, label: 'Hero subheadline' })
    );
    const button = make('button', 'rendered-cta', section.cta_text);
    button.type = 'button';
    button.disabled = Boolean(options.readOnly);
    if (options.readOnly) button.title = 'This action requires the live website workspace.';
    button.addEventListener('click', function () {
      if (section.cta_action === 'submit_b2b_inquiry') options.onAction('submit_b2b_inquiry');
      else if (section.cta_action === 'scroll_to_products') options.onAction('scroll_to_products');
      else options.onAction(section.cta_action);
    });
    content.append(button);
    root.append(content);
    return root;
  }

  function renderFeatures(section, index, options) {
    const root = sectionRoot(section, options, '');
    root.append(
      editable('h2', '', section.title, index, 'title', { ...options, label: 'Features title' }),
      editable('p', 'rendered-section-intro', section.subtitle, index, 'subtitle', { ...options, label: 'Features subtitle' })
    );
    const grid = make('div', 'rendered-features-grid');
    section.items.forEach(function (item, itemIndex) {
      const card = make('article', 'rendered-feature');
      card.append(
        make('span', 'rendered-feature-icon', icons[item.icon] || '•'),
        editable('h3', '', item.title, index, `items.${itemIndex}.title`, { ...options, label: 'Feature title' }),
        editable('p', '', item.description, index, `items.${itemIndex}.description`, { ...options, label: 'Feature description' })
      );
      grid.append(card);
    });
    root.append(grid);
    return root;
  }

  function renderProductGrid(section, index, options) {
    const root = sectionRoot(section, options, '');
    root.append(editable('h2', '', section.title, index, 'title', { ...options, label: 'Product grid title' }));
    const grid = make('div', 'rendered-products-grid');
    section.items.forEach(function (product, productIndex) {
      const productOptions = product.data_source === 'sample'
        ? options
        : Object.assign({}, options, { editable: false });
      const card = make('article', 'rendered-product');
      if (product.image_url) {
        const image = document.createElement('img');
        image.src = product.image_url;
        image.alt = product.name;
        image.loading = 'lazy';
        image.referrerPolicy = 'no-referrer';
        card.append(image);
      }
      card.append(editable('h3', '', product.name, index, `items.${productIndex}.name`, { ...productOptions, label: 'Product name' }));
      card.append(editable('p', '', product.capacity, index, `items.${productIndex}.capacity`, { ...productOptions, label: 'Product capacity' }));
      card.append(editable('p', '', product.description, index, `items.${productIndex}.description`, { ...productOptions, label: 'Product description' }));
      if (product.badge) {
        card.append(editable('span', 'rendered-badge', product.badge, index, `items.${productIndex}.badge`, { ...productOptions, label: 'Product badge' }));
      }
      if (product.data_source === 'sample') {
        card.append(make('span', 'sample-indicator', 'Sample content · not a live catalog item'));
      } else if (product.price && product.price.source === 'cheersthepure_database') {
        const amount = (product.price.amount_minor / 100).toLocaleString('en-IN', { minimumFractionDigits: 2 });
        card.append(make('p', 'rendered-price', `${product.price.currency} ${amount}`));
      }
      grid.append(card);
    });
    root.append(grid);
    return root;
  }

  function renderQuoteForm(section, index, options) {
    const root = sectionRoot(section, options, '');
    root.append(
      make('h2', '', section.title),
      make('p', 'rendered-section-intro', section.subtitle)
    );
    const form = make('form', 'rendered-quote-form');
    form.noValidate = false;
    section.fields.forEach(function (field) {
      const label = make('label', '', field.label);
      let input;
      if (field.name === 'capacity') {
        input = document.createElement('select');
        [['250 ml', '250 ml'], ['500 ml', '500 ml'], ['1000 ml', '1 L'], ['2 litres', '2 L']].forEach(function (pair) {
          const option = make('option', '', pair[1]);
          option.value = pair[0];
          input.append(option);
        });
      } else if (field.name === 'details') {
        input = document.createElement('textarea');
        input.maxLength = 2000;
        input.rows = 3;
      } else {
        input = document.createElement('input');
        input.type = field.name === 'email' ? 'email' : field.name === 'quantity' ? 'number' : 'text';
        if (field.name === 'quantity') {
          input.min = '1';
          input.max = '1000000';
          input.step = '1';
        }
      }
      input.name = field.name;
      input.required = field.required;
      input.autocomplete = ({ name: 'name', email: 'email', company: 'organization' })[field.name] || 'off';
      label.append(input);
      form.append(label);
    });
    const submit = make('button', 'rendered-cta', section.submit_button_text);
    submit.type = 'submit';
    form.append(submit);
    const status = make('p', 'quote-form-status');
    status.setAttribute('role', 'status');
    status.setAttribute('aria-live', 'polite');
    form.append(status);
    if (options.readOnly) {
      form.querySelectorAll('input, select, textarea, button').forEach(function (control) {
        control.disabled = true;
      });
      status.textContent = 'Inquiry submission requires the live, signed-in website workspace.';
      root.append(form);
      return root;
    }
    form.addEventListener('submit', function (event) {
      event.preventDefault();
      if (!form.reportValidity()) return;
      const values = Object.fromEntries(new FormData(form).entries());
      options.onAction('submit_b2b_inquiry', values, status, submit);
    });
    root.append(form);
    return root;
  }

  function renderFooter(section, index, options) {
    const root = sectionRoot(section, options, 'rendered-footer');
    root.append(
      editable('h2', '', section.company_name, index, 'company_name', { ...options, label: 'Footer company name' }),
      editable('p', '', section.copyright, index, 'copyright', { ...options, label: 'Footer copyright' })
    );
    section.links.forEach(function (link) {
      const anchor = make('a', '', link.label);
      anchor.href = link.url;
      if (!link.url.startsWith('/')) {
        anchor.target = '_blank';
        anchor.rel = 'noopener noreferrer';
      }
      root.append(anchor);
    });
    return root;
  }

  function renderTextBlock(section, index, options) {
    const root = sectionRoot(section, options, 'rendered-text-block');
    root.append(
      editable('h2', '', section.title, index, 'title', { ...options, label: 'Text section title' }),
      editable('p', '', section.body, index, 'body', { ...options, label: 'Text section body' })
    );
    return root;
  }

  function renderTestimonials(section, index, options) {
    const root = sectionRoot(section, options, '');
    root.append(editable('h2', '', section.title, index, 'title', { ...options, label: 'Testimonials title' }));
    const grid = make('div', 'rendered-testimonials-grid');
    section.items.forEach(function (item, itemIndex) {
      const card = make('article', 'rendered-testimonial');
      card.append(
        editable('blockquote', '', item.quote, index, `items.${itemIndex}.quote`, { ...options, label: 'Testimonial quote' }),
        editable('cite', '', item.attribution, index, `items.${itemIndex}.attribution`, { ...options, label: 'Testimonial attribution' })
      );
      if (item.content_status === 'sample') card.append(make('span', 'sample-indicator', 'Sample testimonial'));
      grid.append(card);
    });
    root.append(grid);
    return root;
  }

  const renderers = {
    hero: renderHero,
    features: renderFeatures,
    product_grid: renderProductGrid,
    quote_form: renderQuoteForm,
    footer: renderFooter,
    text_block: renderTextBlock,
    testimonials: renderTestimonials
  };

  function renderDocument(site, container, callbacks) {
    const options = Object.assign({ editable: false, selectedSectionId: null, onSelect: function () {}, onEdit: function () {}, onAction: function () {} }, callbacks || {});
    container.replaceChildren();
    const documentRoot = make('div', 'rendered-site');
    documentRoot.dataset.siteId = site.site_id;
    if (site.theme) {
      documentRoot.dataset.theme = site.theme.color;
      documentRoot.dataset.surface = site.theme.surface;
    }
    site.sections.forEach(function (section, index) {
      const renderer = renderers[section.type];
      if (renderer) documentRoot.append(renderer(section, index, options));
    });
    if (options.editable) {
      documentRoot.addEventListener('focusout', function (event) {
        const target = event.target.closest('[contenteditable="true"]');
        if (!target) return;
        options.onEdit(Number(target.dataset.sectionIndex), target.dataset.fieldPath, target.textContent);
      });
      documentRoot.addEventListener('keydown', function (event) {
        if (event.target.matches('[contenteditable="true"]') && event.key === 'Enter' && event.target.tagName !== 'P') {
          event.preventDefault();
          event.target.blur();
        }
      });
    }
    container.append(documentRoot);
    return documentRoot;
  }

  global.SaaSsumRenderer = {
    renderDocument: renderDocument,
    renderers: renderers
  };
})(window);