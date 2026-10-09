function getCSRFCookie(name) {
  const value = `; ${document.cookie}`;
  const parts = value.split(`; ${name}=`);
  if (parts.length === 2) return parts.pop().split(';').shift();
  return '';
}

async function fetchJSON(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || 'Network response was not ok');
  }
  return response.json();
}

function renderProducts(products, container) {
  if (!products || products.length === 0) {
    container.innerHTML = '<p style="grid-column: 1 / -1; text-align: center; padding: 2rem;">No products available.</p>';
    return;
  }
  container.innerHTML = products
    .map(product => `
      <article class="product-card">
        ${product.image_url ? `<img class="product-card-image" src="${product.image_url}" alt="${product.name}" />` : ''}
        <h2>${product.name}</h2>
        <p class="product-meta">${product.capacity} • ${product.price === 'TBD' ? 'Price: TBD' : 'Price: ₹' + product.price} • ${product.tray_text || `Tray: ${product.tray_count} pcs`}</p>
        <p>${product.description}</p>
        <div class="product-card-actions">
          <a class="button" href="/order/${product.id}/">Request Quote</a>
          <a class="button button-secondary" href="/products/${product.id}/">View details</a>
        </div>
      </article>
    `)
    .join('');
}

function renderTestimonials(testimonials, container) {
  container.innerHTML = testimonials
    .map(item => `
      <article class="testimonial-card">
        <p class="quote">“${item.quote}”</p>
        <p class="testimonial-author">${item.name}, ${item.role}</p>
      </article>
    `)
    .join('');
}

function renderCategories(categories, container) {
  container.innerHTML = categories
    .map(category => `<li>${category.name}</li>`)
    .join('');
}

async function initApiSections() {
  const productGrid = document.querySelector('[data-api-products]');
  if (productGrid) {
    try {
      const data = await fetchJSON('/api/products/');
      renderProducts(data, productGrid);
    } catch (error) {
      productGrid.innerHTML = '<p>Unable to load products right now.</p>';
      console.error(error);
    }
  }

  const testimonialGrid = document.querySelector('[data-api-testimonials]');
  if (testimonialGrid) {
    try {
      const data = await fetchJSON('/api/testimonials/');
      renderTestimonials(data, testimonialGrid);
    } catch (error) {
      testimonialGrid.innerHTML = '<p>Unable to load testimonials right now.</p>';
      console.error(error);
    }
  }

  const categoryList = document.querySelector('[data-api-categories]');
  if (categoryList) {
    try {
      const data = await fetchJSON('/api/categories/');
      renderCategories(data, categoryList);
    } catch (error) {
      categoryList.innerHTML = '<li>Unable to load categories.</li>';
      console.error(error);
    }
  }
  const contactForm = document.querySelector('.contact-form[data-api-contact]');
  if (contactForm) {
    contactForm.addEventListener('submit', async event => {
      event.preventDefault();
      const formData = new FormData(contactForm);
      const payload = {
        name: formData.get('name'),
        email: formData.get('email'),
        subject: formData.get('subject'),
        message: formData.get('message'),
      };
      const feedback = document.querySelector('.contact-feedback');
      try {
        await fetchJSON('/api/contact/', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCSRFCookie('csrftoken'),
          },
          body: JSON.stringify(payload),
        });
        contactForm.reset();
        if (feedback) {
          feedback.textContent = 'Thanks! Your message has been sent.';
          feedback.className = 'contact-feedback success';
        }
      } catch (error) {
        if (feedback) {
          feedback.textContent = 'Unable to send the message. Please try again later.';
          feedback.className = 'contact-feedback error';
        }
        console.error(error);
      }
    });
  }

// Call immediately if DOM is already loaded, or wait for the event
document.addEventListener('DOMContentLoaded', function() {
  initApiSections();
});

// Also try to run immediately in case the event has already fired
if (document.readyState === 'complete' || document.readyState === 'interactive') {
  setTimeout(initApiSections, 0);
}
