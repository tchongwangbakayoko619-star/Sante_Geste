/**
 * CS² Health Design System - Alert & Toast Notification Controller
 *
 * Gère l'auto-disparition des alertes flash (cooldown, erreurs, succès),
 * les barres de progression temporelles, la mise en pause au survol,
 * et la fermeture fluide.
 */
(() => {
  'use strict';

  /**
   * Anime la disparition et suppression propre d'une alerte du DOM
   * @param {HTMLElement} alertEl
   */
  function dismissAlert(alertEl) {
    if (!alertEl || alertEl.dataset.isDismissing === 'true') return;
    alertEl.dataset.isDismissing = 'true';

    // Transition fluide : disparition douce puis affaissement de la hauteur
    alertEl.style.transition = 'opacity 0.25s ease, transform 0.25s ease, max-height 0.3s ease, margin 0.3s ease, padding 0.3s ease';
    alertEl.style.opacity = '0';
    alertEl.style.transform = 'translateY(-6px) scale(0.98)';

    setTimeout(() => {
      alertEl.style.maxHeight = '0px';
      alertEl.style.marginTop = '0px';
      alertEl.style.marginBottom = '0px';
      alertEl.style.paddingTop = '0px';
      alertEl.style.paddingBottom = '0px';
      alertEl.style.overflow = 'hidden';
      alertEl.style.borderWidth = '0px';

      setTimeout(() => {
        const parent = alertEl.parentElement;
        alertEl.remove();
        // Si le conteneur n'a plus d'alertes, le nettoyer
        if (parent && parent.classList.contains('flash-messages-container') && parent.children.length === 0) {
          parent.remove();
        }
      }, 300);
    }, 250);
  }

  /**
   * Initialise le comportement d'une alerte avec timer et barre de progression
   * @param {HTMLElement} alertEl
   */
  function initAlert(alertEl) {
    if (alertEl.dataset.alertInitialized === 'true') return;
    alertEl.dataset.alertInitialized = 'true';

    // Bouton de fermeture manuelle
    const closeBtn = alertEl.querySelector('[data-alert-close]');
    if (closeBtn) {
      closeBtn.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        dismissAlert(alertEl);
      });
    }

    // Gestion de l'auto-dismiss
    const autoDismissAttr = alertEl.getAttribute('data-auto-dismiss');
    const duration = autoDismissAttr ? parseInt(autoDismissAttr, 10) : 5000;

    if (duration <= 0) return; // Pas d'auto-dismiss si <= 0

    const progressBar = alertEl.querySelector('.flash-alert-progress-bar');
    let startTime = Date.now();
    let remainingTime = duration;
    let timerId = null;
    let isPaused = false;
    let animationFrameId = null;

    function updateProgress() {
      if (isPaused) return;

      const elapsed = Date.now() - startTime;
      const progressRatio = Math.max(0, 1 - (elapsed / duration));

      if (progressBar) {
        progressBar.style.transform = `scaleX(${progressRatio})`;
      }

      if (elapsed < duration) {
        animationFrameId = requestAnimationFrame(updateProgress);
      }
    }

    function startTimer() {
      startTime = Date.now() - (duration - remainingTime);
      isPaused = false;
      timerId = setTimeout(() => {
        dismissAlert(alertEl);
      }, remainingTime);
      animationFrameId = requestAnimationFrame(updateProgress);
    }

    function pauseTimer() {
      if (isPaused) return;
      isPaused = true;
      clearTimeout(timerId);
      cancelAnimationFrame(animationFrameId);
      remainingTime -= (Date.now() - startTime);
      if (remainingTime < 0) remainingTime = 0;
    }

    // Pause au survol pour permettre à l'utilisateur de lire tranquillement
    alertEl.addEventListener('mouseenter', pauseTimer);
    alertEl.addEventListener('mouseleave', () => {
      if (remainingTime > 0 && !alertEl.dataset.isDismissing) {
        startTimer();
      }
    });

    // Démarrage initial
    startTimer();
  }

  /**
   * Initialise toutes les alertes présentes sur la page
   */
  function initAllAlerts() {
    const alerts = document.querySelectorAll('[data-alert]');
    alerts.forEach(initAlert);
  }

  // Initialisation au chargement du DOM
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initAllAlerts);
  } else {
    initAllAlerts();
  }

  // Observer de mutations pour les alertes injectées dynamiquement (HTMX, fetch, etc.)
  const observer = new MutationObserver((mutations) => {
    for (const mutation of mutations) {
      for (const node of mutation.addedNodes) {
        if (node.nodeType === 1) { // Element node
          if (node.hasAttribute('data-alert')) {
            initAlert(node);
          } else if (node.querySelectorAll) {
            node.querySelectorAll('[data-alert]').forEach(initAlert);
          }
        }
      }
    }
  });

  observer.observe(document.body || document.documentElement, {
    childList: true,
    subtree: true,
  });

  // Exposer un helper global pour créer des toasts dynamiques
  window.showToast = function(message, type = 'info', duration = 5000) {
    let container = document.querySelector('.flash-messages-container');
    if (!container) {
      container = document.createElement('div');
      container.className = 'flash-messages-container fixed top-5 right-5 z-50 flex flex-col gap-3 max-w-sm sm:max-w-md w-[calc(100%-2.5rem)] pointer-events-none';
      container.setAttribute('role', 'region');
      container.setAttribute('aria-label', 'Notifications système');
      document.body.appendChild(container);
    }

    const variantStyles = {
      success: {
        bgClass: 'bg-emerald-950 border-emerald-400 text-emerald-200',
        iconSvg: '<svg class="w-5 h-5 text-emerald-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke-width="2.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="m4.5 12.75 6 6 9-13.5" /></svg>',
        btnHover: 'hover:bg-emerald-900/60 text-emerald-300',
        progressBar: 'bg-emerald-400'
      },
      warning: {
        bgClass: 'bg-amber-950 border-yellow-400 text-yellow-200',
        iconSvg: '<svg class="w-5 h-5 text-yellow-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke-width="1.75" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" /></svg>',
        btnHover: 'hover:bg-amber-900/60 text-yellow-300',
        progressBar: 'bg-yellow-400'
      },
      error: {
        bgClass: 'bg-red-950 border-red-500 text-red-200',
        iconSvg: '<svg class="w-5 h-5 text-red-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke-width="1.75" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M9.75 9.75l4.5 4.5m0-4.5l-4.5 4.5M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>',
        btnHover: 'hover:bg-red-900/60 text-red-300',
        progressBar: 'bg-red-500'
      },
      danger: {
        bgClass: 'bg-red-950 border-red-500 text-red-200',
        iconSvg: '<svg class="w-5 h-5 text-red-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke-width="1.75" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M9.75 9.75l4.5 4.5m0-4.5l-4.5 4.5M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>',
        btnHover: 'hover:bg-red-900/60 text-red-300',
        progressBar: 'bg-red-500'
      },
      info: {
        bgClass: 'bg-slate-900 border-blue-500 text-blue-200',
        iconSvg: '<svg class="w-5 h-5 text-blue-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke-width="1.75" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M11.25 11.25l.041-.02a.75.75 0 011.063.852l-.708 2.836a.75.75 0 001.063.853l.041-.021M21 12a9 9 0 11-18 0 9 9 0 0118 0zm-9-3.75h.008v.008H12V8.25z" /></svg>',
        btnHover: 'hover:bg-slate-800 text-blue-300',
        progressBar: 'bg-blue-500'
      }
    };

    const currentStyle = variantStyles[type] || variantStyles.info;

    const alert = document.createElement('div');
    alert.className = `flex items-center gap-3 border-l-4 px-5 py-4 text-sm font-medium border rounded-r-xl shadow-sm relative overflow-hidden transition-all duration-300 ease-out ${currentStyle.bgClass}`;
    alert.setAttribute('role', 'alert');
    alert.setAttribute('aria-live', type === 'error' || type === 'danger' ? 'assertive' : 'polite');
    alert.setAttribute('data-alert', '');
    alert.setAttribute('data-auto-dismiss', duration);

    alert.innerHTML = `
      <div class="shrink-0 flex items-center justify-center" aria-hidden="true">
        ${currentStyle.iconSvg}
      </div>
      <div class="flex-1 min-w-0 leading-snug">
        ${message}
      </div>
      <button type="button" class="shrink-0 -mr-1 p-1 rounded-lg opacity-70 hover:opacity-100 transition-all cursor-pointer focus:outline-none focus:ring-1 focus:ring-current ${currentStyle.btnHover}" data-alert-close aria-label="Fermer cette notification">
        <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" /></svg>
      </button>
      <div class="flash-alert-progress-track absolute bottom-0 left-0 right-0 h-1 bg-black/5 overflow-hidden">
        <div class="flash-alert-progress-bar h-full w-full origin-left ${currentStyle.progressBar}"></div>
      </div>
    `;

    container.appendChild(alert);
    initAlert(alert);
  };
})();
