/**
 * Interactions du Dashboard Médical SantéGeste (Modèle Google Classroom)
 * - Navigation responsive : permanente sur desktop (expanded 280px / collapsed 80px), drawer sur mobile
 * - Mémorisation de l'état dans localStorage ('santegeste-sidebar-state')
 * - Sous-menus : accordéons inline en mode étendu, panneaux flyouts à droite en mode mini
 * - Tooltips flottants fluides en mode mini au survol et au focus clavier
 * - Raccourci clavier global ⌘K / Ctrl+K pour la recherche
 * - Dropdown du profil utilisateur
 */

// ==========================================================================
// 1. GESTION DES ÉTATS DE LA SIDEBAR
// ==========================================================================

const SIDEBAR_STORAGE_KEY = "santegeste-sidebar-state";

/**
 * Ouvre ou ferme le tiroir (drawer) sur mobile et tablette (< 1024px)
 */
function toggleSidebar(open) {
  const sidebar = document.getElementById("dashboard-sidebar");
  const backdrop = document.getElementById("sidebar-backdrop");
  if (!sidebar) return;

  if (open) {
    sidebar.classList.remove("-translate-x-full");
    if (backdrop) backdrop.classList.remove("hidden");
    document.body.classList.add("overflow-hidden");
  } else {
    sidebar.classList.add("-translate-x-full");
    if (backdrop) backdrop.classList.add("hidden");
    document.body.classList.remove("overflow-hidden");
  }
}

/**
 * Bascule entre état étendu (280px) et état réduit/mini (80px) sur Desktop (>= 1024px)
 * Reproduit le comportement de Google Classroom avec mémorisation localStorage
 */
function toggleDesktopSidebar() {
  const html = document.documentElement;
  const isCollapsed = html.classList.toggle("sidebar-collapsed");
  const collapseButton = document.querySelector("[data-sidebar-collapse]");

  // Fermer les flyouts ouverts lors de la transition
  closeAllFlyouts();
  hideSidebarTooltip();

  // Mémorisation dans localStorage
  try {
    localStorage.setItem(SIDEBAR_STORAGE_KEY, isCollapsed ? "collapsed" : "expanded");
  } catch (e) {
    console.warn("Impossible d'accéder au localStorage :", e);
  }

  // Accessibilité ARIA
  if (collapseButton) {
    collapseButton.setAttribute("aria-expanded", String(!isCollapsed));
    collapseButton.setAttribute("aria-label", isCollapsed ? "Agrandir le menu" : "Réduire le menu");
  }
}

// ==========================================================================
// 2. GESTION DES SOUS-MENUS (ACCORDÉONS & FLYOUTS)
// ==========================================================================

/**
 * Ferme un flyout individuel avec micro-transition de fade-out (80ms)
 */
function closeFlyout(flyout) {
  if (!flyout || flyout.classList.contains("hidden")) return;
  flyout.classList.add("is-closing");
  setTimeout(() => {
    flyout.classList.remove("is-closing");
    flyout.classList.add("hidden");
  }, 80);
}

/**
 * Ferme tous les panneaux flyout actifs avec animation fade-out
 */
function closeAllFlyouts(exceptFlyoutId = null) {
  document.querySelectorAll(".sidebar-flyout").forEach((flyout) => {
    if (flyout.id === exceptFlyoutId) return;
    if (!flyout.classList.contains("hidden") && !flyout.classList.contains("is-closing")) {
      closeFlyout(flyout);
    }
  });
  document.querySelectorAll("[data-flyout-target]").forEach((btn) => {
    const isCollapsed = document.documentElement.classList.contains("sidebar-collapsed");
    const targetId = btn.getAttribute("data-flyout-target");
    if (isCollapsed && targetId !== exceptFlyoutId) {
      btn.setAttribute("aria-expanded", "false");
    }
  });
}

/**
 * Ouvre un flyout spécifique aligné avec le bouton déclencheur
 */
function openFlyout(button, flyoutId) {
  closeAllFlyouts(flyoutId);
  hideSidebarTooltip();

  const flyout = document.getElementById(flyoutId);
  if (!flyout) return;

  flyout.classList.remove("is-closing", "hidden");

  const rect = button.getBoundingClientRect();
  const flyoutHeight = flyout.offsetHeight || 150;
  const maxTop = window.innerHeight - flyoutHeight - 16;
  const targetTop = Math.max(16, Math.min(rect.top, maxTop));

  flyout.style.top = `${targetTop}px`;
  button.setAttribute("aria-expanded", "true");
}

/**
 * Bascule un sous-menu :
 * - Si Desktop Collapsed : ouvre/ferme le flyout à droite
 * - Si Desktop Expanded ou Mobile : accordéon inline avec rotation du chevron
 */
function toggleMenu(menuId, button) {
  const isDesktop = window.innerWidth >= 1024;
  const isCollapsed = isDesktop && document.documentElement.classList.contains("sidebar-collapsed");

  if (isCollapsed) {
    // Mode Collapsed / Mini : Gestion du Flyout avec animation
    const flyoutId = button.getAttribute("data-flyout-target");
    if (!flyoutId) return;

    const flyout = document.getElementById(flyoutId);
    if (flyout && !flyout.classList.contains("hidden") && !flyout.classList.contains("is-closing")) {
      closeAllFlyouts();
    } else {
      openFlyout(button, flyoutId);
    }
    return;
  }

  // Mode Expanded ou Mobile : Accordéon classique inline
  const menu = document.getElementById(menuId);
  if (!menu) return;

  const isHidden = menu.classList.toggle("hidden");
  button.setAttribute("aria-expanded", String(!isHidden));

  // Rotation fluide du chevron
  const chevron = document.getElementById(menuId + "-chevron");
  if (chevron) {
    chevron.classList.toggle("rotate-180", !isHidden);
  }
}

// ==========================================================================
// 3. TOOLTIPS FLOTTANTS EN MODE MINI
// ==========================================================================

let tooltipTimeout = null;

function showSidebarTooltip(target) {
  const isDesktop = window.innerWidth >= 1024;
  const isCollapsed = isDesktop && document.documentElement.classList.contains("sidebar-collapsed");
  if (!isCollapsed) return;

  // Ne pas afficher de tooltip si un flyout est actuellement ouvert pour ce bouton
  const flyoutId = target.getAttribute("data-flyout-target");
  if (flyoutId) {
    const flyout = document.getElementById(flyoutId);
    if (flyout && !flyout.classList.contains("hidden") && !flyout.classList.contains("is-closing")) return;
  }

  const tooltipText = target.getAttribute("data-sidebar-tooltip");
  if (!tooltipText) return;

  const tooltip = document.getElementById("sidebar-floating-tooltip");
  if (!tooltip) return;

  clearTimeout(tooltipTimeout);
  tooltipTimeout = setTimeout(() => {
    tooltip.textContent = tooltipText;
    const rect = target.getBoundingClientRect();
    const top = rect.top + rect.height / 2;
    tooltip.style.top = `${top}px`;
    tooltip.style.left = "88px";
    tooltip.classList.add("visible");
  }, 60); // Délai très court et discret
}

function hideSidebarTooltip() {
  clearTimeout(tooltipTimeout);
  const tooltip = document.getElementById("sidebar-floating-tooltip");
  if (tooltip) {
    tooltip.classList.remove("visible");
  }
}

// ==========================================================================
// 4. INITIALISATION AU CHARGEMENT DU DOM
// ==========================================================================

document.addEventListener("DOMContentLoaded", () => {
  // A. Synchronisation initiale de l'état Desktop et des attributs ARIA
  const collapseButton = document.querySelector("[data-sidebar-collapse]");
  const isDesktop = window.innerWidth >= 1024;

  if (isDesktop) {
    try {
      const savedState = localStorage.getItem(SIDEBAR_STORAGE_KEY);
      if (savedState === "collapsed") {
        document.documentElement.classList.add("sidebar-collapsed");
      } else if (savedState === "expanded") {
        document.documentElement.classList.remove("sidebar-collapsed");
      }
    } catch (e) {
      console.warn("Erreur lecture localStorage :", e);
    }

    const currentlyCollapsed = document.documentElement.classList.contains("sidebar-collapsed");
    if (collapseButton) {
      collapseButton.setAttribute("aria-expanded", String(!currentlyCollapsed));
      collapseButton.setAttribute("aria-label", currentlyCollapsed ? "Agrandir le menu" : "Réduire le menu");
    }
  }

  // B. Fermeture des flyouts au clic extérieur
  document.addEventListener("click", (e) => {
    const isInsideFlyout = e.target.closest(".sidebar-flyout");
    const isFlyoutTrigger = e.target.closest("[data-flyout-target]");

    if (!isInsideFlyout && !isFlyoutTrigger) {
      closeAllFlyouts();
    }
  });

  // C. Accessibilité Clavier : Touche Escape pour fermer Flyout ou Drawer Mobile
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      closeAllFlyouts();
      hideSidebarTooltip();
      toggleSidebar(false);
    }
  });

  // D. Délégation d'événements pour les Tooltips de la Sidebar (Survol & Focus Clavier)
  const sidebar = document.getElementById("dashboard-sidebar");
  if (sidebar) {
    sidebar.addEventListener("mouseover", (e) => {
      const tooltipEl = e.target.closest("[data-sidebar-tooltip]");
      if (tooltipEl && sidebar.contains(tooltipEl)) {
        showSidebarTooltip(tooltipEl);
      }
    });

    sidebar.addEventListener("mouseout", (e) => {
      const tooltipEl = e.target.closest("[data-sidebar-tooltip]");
      if (tooltipEl) {
        hideSidebarTooltip();
      }
    });

    sidebar.addEventListener("focusin", (e) => {
      const tooltipEl = e.target.closest("[data-sidebar-tooltip]");
      if (tooltipEl && sidebar.contains(tooltipEl)) {
        showSidebarTooltip(tooltipEl);
      }
    });

    sidebar.addEventListener("focusout", (e) => {
      const tooltipEl = e.target.closest("[data-sidebar-tooltip]");
      if (tooltipEl) {
        hideSidebarTooltip();
      }
    });
  }

  // E. Raccourci Clavier Global ⌘K / Ctrl+K pour la recherche
  document.addEventListener("keydown", (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
      e.preventDefault();
      const searchInput = document.getElementById("global-search-input");
      if (searchInput) {
        searchInput.focus();
        searchInput.select();
      }
    }
  });

  // F. Dropdown du Profil Utilisateur Topbar
  const userButton = document.getElementById("user-menu-button");
  const userDropdown = document.getElementById("user-dropdown-menu");

  if (userButton && userDropdown) {
    userButton.addEventListener("click", (e) => {
      e.stopPropagation();
      const isExpanded = userButton.getAttribute("aria-expanded") === "true";
      userButton.setAttribute("aria-expanded", String(!isExpanded));
      userDropdown.classList.toggle("hidden");
    });

    document.addEventListener("click", (e) => {
      if (!userDropdown.contains(e.target) && !userButton.contains(e.target)) {
        userDropdown.classList.add("hidden");
        userButton.setAttribute("aria-expanded", "false");
      }
    });
  }
});
