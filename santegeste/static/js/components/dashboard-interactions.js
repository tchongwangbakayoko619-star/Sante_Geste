/**
 * Interactions du Dashboard Médical SantéGeste
 * - Bascule de la sidebar mobile
 * - Menus déroulants accordéons de navigation
 * - Raccourci clavier global ⌘K / Ctrl+K pour la recherche
 * - Dropdown du profil utilisateur
 */
function toggleSidebar(open) {
  const sidebar = document.getElementById("dashboard-sidebar");
  const backdrop = document.getElementById("sidebar-backdrop");
  if (!sidebar) return;

  if (open) {
    sidebar.classList.remove("-translate-x-full");
    if (backdrop) backdrop.classList.remove("hidden");
  } else {
    sidebar.classList.add("-translate-x-full");
    if (backdrop) backdrop.classList.add("hidden");
  }
}

function toggleMenu(menuId, button) {
  const menu = document.getElementById(menuId);
  if (!menu) return;
  menu.classList.toggle("hidden");

  // Rotate chevron if present
  const chevron = document.getElementById(menuId + "-chevron");
  if (chevron) {
    chevron.classList.toggle("rotate-180");
  }
}

document.addEventListener("DOMContentLoaded", () => {
  // 1. Raccourci Clavier Global ⌘K / Ctrl+K
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

  // 2. Dropdown du Profil Utilisateur
  const userButton = document.getElementById("user-menu-button");
  const userDropdown = document.getElementById("user-dropdown-menu");

  if (userButton && userDropdown) {
    userButton.addEventListener("click", (e) => {
      e.stopPropagation();
      const isExpanded = userButton.getAttribute("aria-expanded") === "true";
      userButton.setAttribute("aria-expanded", !isExpanded);
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
