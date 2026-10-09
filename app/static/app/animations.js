// 3D Interactive Animations JavaScript

// Mouse parallax effect
document.addEventListener('mousemove', (e) => {
  const cards = document.querySelectorAll('.product-card, .about-card, .highlight-card');
  
  cards.forEach(card => {
    const rect = card.getBoundingClientRect();
    const x = (e.clientX - rect.left) / rect.width;
    const y = (e.clientY - rect.top) / rect.height;
    
    // Calculate tilt angles based on mouse position
    const rotateX = (y - 0.5) * 10;
    const rotateY = (x - 0.5) * 10;
    
    // Apply subtle 3D tilt on hover
    if (e.clientX > rect.left && e.clientX < rect.right && e.clientY > rect.top && e.clientY < rect.bottom) {
      card.style.transform = `perspective(1000px) rotateX(${rotateX}deg) rotateY(${rotateY}deg) translateZ(20px)`;
    }
  });
});

// Reset tilt when mouse leaves
document.addEventListener('mouseleave', () => {
  const cards = document.querySelectorAll('.product-card, .about-card, .highlight-card');
  cards.forEach(card => {
    card.style.transform = '';
  });
});

// Scroll animation trigger
const observerOptions = {
  threshold: 0.1,
  rootMargin: '0px 0px -50px 0px'
};

const observer = new IntersectionObserver((entries) => {
  entries.forEach(entry => {
    if (entry.isIntersecting) {
      // add a visible class so CSS transitions handle the entrance
      entry.target.classList.add('visible');
      observer.unobserve(entry.target);
    }
  });
}, observerOptions);

// Observe all animated elements
document.addEventListener('DOMContentLoaded', () => {
  const animatedElements = document.querySelectorAll(
    '.product-card, .about-card, .testimonial-card, .highlight-card, .manufacturing-step'
  );
  
  animatedElements.forEach(el => {
    observer.observe(el);
  });

  // Add hover effects to buttons
  const buttons = document.querySelectorAll('.button');
  buttons.forEach(button => {
    button.addEventListener('mouseenter', function() {
      this.style.transform = 'perspective(1000px) rotateY(5deg) translateZ(10px) scale(1.02)';
    });
    
    button.addEventListener('mouseleave', function() {
      this.style.transform = '';
    });
  });

  // Add parallax effect to hero section
  const hero = document.querySelector('.hero');
  if (hero) {
    window.addEventListener('scroll', () => {
      const scrollY = window.scrollY;
      hero.style.transform = `perspective(1200px) rotateX(${scrollY * 0.02}deg) translateZ(0)`;
    });
  }

  // Animate numbers when they come into view
  const statCards = document.querySelectorAll('.hero-stat-grid div strong');
  statCards.forEach(card => {
    const observer = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting && !entry.target.classList.contains('animated')) {
          entry.target.classList.add('animated');
          const finalValue = parseInt(entry.target.textContent);
          const startValue = 0;
          const duration = 1500; // milliseconds
          const increment = finalValue / (duration / 16);
          let currentValue = startValue;

          const animateCounter = () => {
            currentValue += increment;
            if (currentValue >= finalValue) {
              entry.target.textContent = finalValue;
            } else {
              entry.target.textContent = Math.floor(currentValue);
              requestAnimationFrame(animateCounter);
            }
          };

          requestAnimationFrame(animateCounter);
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.5 });

    observer.observe(card);
  });

  // Add interactive feedback to form inputs
  const inputs = document.querySelectorAll('input, textarea');
  inputs.forEach(input => {
    input.addEventListener('focus', function() {
      this.style.transition = 'all 0.3s ease';
      this.style.boxShadow = '0 0 0 3px rgba(37, 99, 235, 0.1), 0 0 20px rgba(37, 99, 235, 0.3)';
    });

    input.addEventListener('blur', function() {
      this.style.boxShadow = '';
    });

    input.addEventListener('input', function() {
      this.style.transform = 'scale(1.02)';
      setTimeout(() => {
        this.style.transform = '';
      }, 100);
    });
  });

  // Add click ripple effect
  document.addEventListener('click', (e) => {
    if (e.target.closest('.button, .product-card a')) {
      const ripple = document.createElement('span');
      const button = e.target.closest('.button') || e.target;
      const rect = button.getBoundingClientRect();
      
      ripple.style.position = 'absolute';
      ripple.style.width = '10px';
      ripple.style.height = '10px';
      ripple.style.background = 'rgba(255, 255, 255, 0.5)';
      ripple.style.borderRadius = '50%';
      ripple.style.left = (e.clientX - rect.left) + 'px';
      ripple.style.top = (e.clientY - rect.top) + 'px';
      ripple.style.animation = 'ripple 0.6s ease-out';
      ripple.style.pointerEvents = 'none';
      ripple.style.transform = 'scale(0)';
      ripple.style.opacity = '1';

      button.style.position = 'relative';
      button.style.overflow = 'hidden';
      
      // Create ripple animation
      const keyframes = `
        @keyframes ripple {
          0% {
            transform: scale(0);
            opacity: 1;
          }
          100% {
            transform: scale(4);
            opacity: 0;
          }
        }
      `;
      
      if (!document.querySelector('style[data-ripple]')) {
        const style = document.createElement('style');
        style.setAttribute('data-ripple', 'true');
        style.textContent = keyframes;
        document.head.appendChild(style);
      }

      button.appendChild(ripple);
      setTimeout(() => ripple.remove(), 600);
    }
  });

  // Parallax effect for multiple layers
  const parallaxElements = document.querySelectorAll('[data-parallax]');
  if (parallaxElements.length > 0) {
    window.addEventListener('scroll', () => {
      parallaxElements.forEach(el => {
        const speed = el.getAttribute('data-parallax');
        const yPos = window.scrollY * speed;
        el.style.transform = `translateY(${yPos}px)`;
      });
    });
  }

  // Add element stagger animation
  const staggerElements = document.querySelectorAll('.product-grid .product-card');
  staggerElements.forEach((el, index) => {
    el.style.animationDelay = `${index * 0.1}s`;
  });

  // Smooth scroll links
  document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function (e) {
      const href = this.getAttribute('href');
      if (href !== '#') {
        e.preventDefault();
        const target = document.querySelector(href);
        if (target) {
          target.scrollIntoView({
            behavior: 'smooth',
            block: 'start'
          });
        }
      }
    });
  });

  // Add scroll-triggered animations
  const triggerAnimations = document.querySelectorAll('[data-animate]');
  const animationObserver = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        const animation = entry.target.getAttribute('data-animate');
        entry.target.style.animation = animation;
        animationObserver.unobserve(entry.target);
      }
    });
  }, { threshold: 0.1 });

  triggerAnimations.forEach(el => animationObserver.observe(el));
});

// Request animation frame for smooth animations
function animationFrame(callback) {
  if (window.requestAnimationFrame) {
    requestAnimationFrame(callback);
  } else {
    setTimeout(callback, 1000 / 60);
  }
}

// Utility function to add 3D tilt to any element
function add3DTilt(element) {
  element.addEventListener('mousemove', (e) => {
    const rect = element.getBoundingClientRect();
    const x = (e.clientX - rect.left) / rect.width;
    const y = (e.clientY - rect.top) / rect.height;
    
    const rotateX = (y - 0.5) * 20;
    const rotateY = (x - 0.5) * 20;
    
    element.style.transform = `perspective(1000px) rotateX(${rotateX}deg) rotateY(${rotateY}deg) scale(1.02)`;
    element.style.transition = 'none';
  });

  element.addEventListener('mouseleave', () => {
    element.style.transform = 'perspective(1000px) rotateX(0deg) rotateY(0deg) scale(1)';
    element.style.transition = 'all 0.3s ease';
  });
}

// Apply 3D tilt to all product cards
document.addEventListener('DOMContentLoaded', () => {
  const productCards = document.querySelectorAll('.product-card');
  productCards.forEach(card => add3DTilt(card));
});

// Mouse wheel parallax enhancement
let mouseX = 0, mouseY = 0;
document.addEventListener('mousemove', (e) => {
  mouseX = (e.clientX / window.innerWidth) * 2 - 1;
  mouseY = (e.clientY / window.innerHeight) * 2 - 1;
});

// Performance optimization - use RAF for smooth animations
let ticking = false;
window.addEventListener('scroll', () => {
  if (!ticking) {
    window.requestAnimationFrame(() => {
      const parallaxElements = document.querySelectorAll('[data-parallax-speed]');
      parallaxElements.forEach(el => {
        const speed = parseFloat(el.getAttribute('data-parallax-speed')) || 0.5;
        el.style.transform = `translateY(${window.scrollY * speed}px)`;
      });
      ticking = false;
    });
    ticking = true;
  }
});

// Export functions for use in other scripts
window.add3DTilt = add3DTilt;
window.animationFrame = animationFrame;
