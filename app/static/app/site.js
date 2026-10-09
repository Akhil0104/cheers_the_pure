// Consolidated site JS: robust API init, image fallbacks, intersection observer for animations
(function(){
  if (window.__siteInitDone) return;
  window.__siteInitDone = true;

  const defaults = {
    '250 ml': '/static/app/media/250ml.jpg',
    '500 ml': '/static/app/media/500ml.jpg',
    '1000 ml': '/static/app/media/1ltr.jpg',
    '1 ltr': '/static/app/media/1ltr.jpg',
    '2 litres': '/static/app/media/2ltr.jpg'
  };

  function safeFetchJSON(url){
    return fetch(url, {credentials:'same-origin'}).then(res => {
      if (!res.ok) throw new Error('Network response not ok ' + res.status);
      return res.json();
    });
  }

  function applyImageFallbacks(container){
    container.querySelectorAll('img').forEach(img=>{
      img.addEventListener('error', ()=>{
        // if image has data-capacity attribute use defaults
        const cap = img.getAttribute('data-capacity') || '';
        const key = (cap||'').toLowerCase();
        img.src = defaults[key] || '/static/app/media/500ml.jpg';
      });
    });
  }

  function renderProducts(products, container){
    if(!products || products.length===0){
      container.innerHTML = '<p style="grid-column:1/-1;text-align:center;padding:2rem">No products available.</p>';
      return;
    }

    container.innerHTML = products.map(p=>{
      const img = p.image_url ? `<img class="product-card-image" data-capacity="${p.capacity||''}" src="${p.image_url}" alt="${p.name}"/>` : '';
      return `
        <article class="product-card" data-id="${p.id}">
          ${img}
          <h2>${p.name}</h2>
          <p class="product-meta">${p.capacity} • ${p.price === 'TBD' ? 'Price: TBD' : 'Price: ₹' + p.price} • <span class="product-tray">${p.tray_text || `Tray: ${p.tray_count || 12} pcs`}</span></p>
          <p>${(p.description||'').substring(0,160)}</p>
          <div class="product-actions">
            <a class="button" href="/order/${p.id}/">Request Quote</a>
            <a class="button button-secondary" href="/products/${p.id}/">View details</a>
          </div>
        </article>`;
    }).join('');

    applyImageFallbacks(container);
    observeCards(container.querySelectorAll('.product-card'));
  }

  function renderTestimonials(items, container){
    container.innerHTML = (items||[]).map(t=>`<article class="testimonial-card"><p class="quote">“${t.quote}”</p><p class="testimonial-author">${t.name}, ${t.role||''}</p></article>`).join('');
    observeCards(container.querySelectorAll('.testimonial-card'));
  }

  function renderCategories(items, container){
    container.innerHTML = (items||[]).map(c=>`<li><a href="/categories/${c.id}/">${c.name}</a></li>`).join('');
  }

  // Intersection observer to add .visible and stagger children
  const obs = new IntersectionObserver((entries)=>{
    entries.forEach(e=>{
      if(e.isIntersecting){
        e.target.classList.add('visible');
        obs.unobserve(e.target);
      }
    });
  },{threshold:0.12,rootMargin:'0px 0px -40px 0px'});

  function observeCards(list){
    if(!list) return;
    list.forEach((el,idx)=>{
      el.style.transitionDelay = `${idx*60}ms`;
      obs.observe(el);
    });
  }

  async function initApiSections(){
    try{
      const productGrid = document.querySelector('[data-api-products]');
      if(productGrid){
        try{
          const data = await safeFetchJSON('/api/products/');
          renderProducts(data, productGrid);
        }catch(err){
          console.error('Products load failed',err);
          productGrid.innerHTML = '<p>Unable to load products right now.</p>';
        }
      }

      const testimonialGrid = document.querySelector('[data-api-testimonials]');
      if(testimonialGrid){
        try{
          const data = await safeFetchJSON('/api/testimonials/');
          renderTestimonials(data, testimonialGrid);
        }catch(err){
          console.error('Testimonials load failed',err);
          testimonialGrid.innerHTML = '<p>Unable to load testimonials right now.</p>';
        }
      }

      const categoryList = document.querySelector('[data-api-categories]');
      if(categoryList){
        try{
          const data = await safeFetchJSON('/api/categories/');
          renderCategories(data, categoryList);
        }catch(err){
          console.error('Categories load failed',err);
          categoryList.innerHTML = '<li>Unable to load categories.</li>';
        }
      }

      // Initialize dashboard chart
      initDashboardChart();
    }catch(e){
      console.error('initApiSections fatal',e);
    }
  }

  // Initialize dashboard chart if Chart.js is available
  function initDashboardChart(){
    const canvas = document.getElementById('dashboardChart');
    if(!canvas) return;

    // Load Chart.js from CDN if not already loaded
    if(!window.Chart){
      const script = document.createElement('script');
      script.src = 'https://cdn.jsdelivr.net/npm/chart.js';
      script.onload = renderChart;
      document.head.appendChild(script);
    } else {
      renderChart();
    }

    function renderChart(){
      try{
        const data = [
          parseInt(canvas.getAttribute('data-products')) || 0,
          parseInt(canvas.getAttribute('data-categories')) || 0,
          parseInt(canvas.getAttribute('data-testimonials')) || 0,
          parseInt(canvas.getAttribute('data-messages')) || 0,
          parseInt(canvas.getAttribute('data-quotes')) || 0,
          parseInt(canvas.getAttribute('data-users')) || 0
        ];
        const labels = ['Products','Categories','Testimonials','Messages','Quotes','Users'];
        const ctx = canvas.getContext('2d');
        new Chart(ctx, {
          type: 'doughnut',
          data: {
            labels: labels,
            datasets: [{
              data: data,
              backgroundColor: ['#2563EB','#10B981','#F59E0B','#EF4444','#8B5CF6','#059669'],
              borderColor: '#fff',
              borderWidth: 2,
              hoverOffset: 8
            }]
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              legend: { position: 'bottom', labels: { font: { size: 13 }, padding: 15 } },
              tooltip: { backgroundColor: 'rgba(15,23,42,0.8)', titleFont: { size: 14 }, bodyFont: { size: 13 } }
            }
          }
        });
      }catch(e){
        console.error('Dashboard chart error:', e);
      }
    }
  }

  /* Lightweight JavaScript water-ripple engine */
  document.addEventListener('click', function (e) {
    const target = e.target.closest('.button, .btn-add-cart, .btn-quote, .site-nav a, .footer-col a, .glass-card, .highlight-card, .about-card, .overview-card');
    if (!target) return;

    const ripple = document.createElement('div');
    ripple.className = 'water-ripple';
    
    const rect = target.getBoundingClientRect();
    const size = Math.max(rect.width, rect.height) * 2.5;
    
    ripple.style.width = size + 'px';
    ripple.style.height = size + 'px';
    ripple.style.left = (e.clientX - rect.left - size / 2) + 'px';
    ripple.style.top = (e.clientY - rect.top - size / 2) + 'px';

    const prevPos = window.getComputedStyle(target).position;
    if (prevPos !== 'relative' && prevPos !== 'absolute' && prevPos !== 'fixed') {
      target.style.position = 'relative';
    }
    
    target.style.overflow = 'hidden';
    target.appendChild(ripple);

    ripple.addEventListener('transitionend', function () {
      ripple.remove();
    });
    
    requestAnimationFrame(function () {
      ripple.classList.add('active');
    });
  });

  // Run on DOM ready
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded', initApiSections);
  else initApiSections();

  // Expose for debug
  window.__site = {initApiSections,renderProducts,initDashboardChart};
})();
