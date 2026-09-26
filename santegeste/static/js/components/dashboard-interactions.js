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
    document.body.classList.add("overflow-hidden");
  } else {
    sidebar.classList.add("-translate-x-full");
    if (backdrop) backdrop.classList.add("hidden");
    document.body.classList.remove("overflow-hidden");
  }
}

function toggleDesktopSidebar() {
  const sidebar = document.getElementById("dashboard-sidebar");
  const main = document.getElementById("dashboard-main-content");
  const collapseButton = document.querySelector("[data-sidebar-collapse]");
  const header = sidebar.querySelector("[data-sidebar-header]");
  if (!sidebar || !main) return;

  const collapsed = sidebar.classList.toggle("lg:w-20");
  sidebar.classList.toggle("lg:w-72", !collapsed);
  main.classList.toggle("lg:pl-20", collapsed);
  main.classList.toggle("lg:pl-72", !collapsed);
  sidebar.querySelectorAll("[data-sidebar-label], [data-sidebar-submenu]").forEach((element) => element.classList.toggle("lg:hidden", collapsed));
  header?.classList.toggle("lg:justify-center", false);
  header?.classList.toggle("lg:justify-start", collapsed);
  header?.classList.toggle("lg:pl-5", collapsed);
  collapseButton?.classList.toggle("lg:absolute", collapsed);
  collapseButton?.classList.toggle("lg:right-2", collapsed);
  if (collapseButton) {
    collapseButton.setAttribute("aria-pressed", String(collapsed));
    collapseButton.setAttribute("aria-label", collapsed ? "Agrandir le menu" : "Réduire le menu");
    collapseButton.querySelector("svg")?.classList.toggle("rotate-180", collapsed);
  }
}

function toggleMenu(menuId, button) {
  const menu = document.getElementById(menuId);
  const sidebar = document.getElementById("dashboard-sidebar");
  if (!menu) return;

  // In compact desktop mode, reveal the sidebar first so submenu links remain usable.
  if (sidebar?.classList.contains("lg:w-20")) {
    toggleDesktopSidebar();
    button.focus();
    return;
  }
  menu.classList.toggle("hidden");
  button.setAttribute("aria-expanded", String(!menu.classList.contains("hidden")));

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

  // 3. Initialisation des interactions des graphiques de statistiques
  initWeeklyChartInteractions();
  initDonutChartInteractions();
});

/**
 * 3. Interactions et animations du graphique d'activité hebdomadaire
 * - Ligne guide (crosshair) et infobulle riche flottante au survol des colonnes journalières
 * - Halos lumineux et mise en relief des points de données
 * - Légendes interactives avec bascule de visibilité (toggle) et survol isolé (hover highlight)
 */
function initWeeklyChartInteractions() {
  const container = document.getElementById("weekly-chart-container");
  const svg = document.getElementById("weekly-activity-svg");
  const tooltip = document.getElementById("weekly-chart-tooltip");
  const crosshair = document.getElementById("chart-crosshair-line");

  if (!container || !svg || !tooltip || !crosshair) return;

  const tooltipDay = document.getElementById("tooltip-day");
  const tooltipRate = document.getElementById("tooltip-rate");
  const tooltipPlanned = document.getElementById("tooltip-planned");
  const tooltipCompleted = document.getElementById("tooltip-completed");

  const plannedCurve = document.getElementById("curve-planned");
  const plannedArea = document.getElementById("area-planned");
  const completedCurve = document.getElementById("curve-completed");
  const completedArea = document.getElementById("area-completed");

  const plannedBtn = document.getElementById("legend-btn-planned");
  const completedBtn = document.getElementById("legend-btn-completed");

  const activeDayCard = document.getElementById("weekly-active-day-card");
  const activeDayAvatar = document.getElementById("active-day-avatar");
  const activeDayName = document.getElementById("active-day-name");
  const activeDayPlanned = document.getElementById("active-day-planned");
  const activeDayCompleted = document.getElementById("active-day-completed");
  const activeDayRate = document.getElementById("active-day-rate");

  const initialAvatar = activeDayAvatar ? activeDayAvatar.textContent.trim() : "";
  const initialName = activeDayName ? activeDayName.textContent.trim() : "";
  const initialPlanned = activeDayPlanned ? activeDayPlanned.textContent.trim() : "0";
  const initialCompleted = activeDayCompleted ? activeDayCompleted.textContent.trim() : "0";
  const initialRate = activeDayRate ? activeDayRate.textContent.trim() : "0%";

  let plannedVisible = true;
  let completedVisible = true;

  // A. Gestion du survol des colonnes journalières
  const hoverCols = svg.querySelectorAll(".chart-hover-col");
  hoverCols.forEach((col) => {
    col.addEventListener("mouseenter", () => {
      const idx = col.getAttribute("data-idx");
      const day = col.getAttribute("data-day");
      const x = parseFloat(col.getAttribute("data-x"));
      const plannedY = parseFloat(col.getAttribute("data-planned-y"));
      const completedY = parseFloat(col.getAttribute("data-completed-y"));
      const planned = parseInt(col.getAttribute("data-planned") || "0", 10);
      const completed = parseInt(col.getAttribute("data-completed") || "0", 10);

      // 1. Positionnement et affichage du crosshair
      crosshair.setAttribute("x1", String(x));
      crosshair.setAttribute("x2", String(x));
      crosshair.style.opacity = "1";

      // 2. Halo lumineux sur les points correspondants
      const haloP = document.getElementById(`halo-planned-${idx}`);
      const dotP = document.getElementById(`dot-planned-${idx}`);
      const haloC = document.getElementById(`halo-completed-${idx}`);
      const dotC = document.getElementById(`dot-completed-${idx}`);

      if (haloP && plannedVisible) {
        haloP.style.opacity = "0.35";
        haloP.setAttribute("r", "10");
      }
      if (dotP && plannedVisible) {
        dotP.setAttribute("r", "6");
        dotP.setAttribute("stroke-width", "3");
      }

      if (haloC && completedVisible) {
        haloC.style.opacity = "0.45";
        haloC.setAttribute("r", "11");
      }
      if (dotC && completedVisible) {
        dotC.setAttribute("r", "6.5");
        dotC.setAttribute("stroke-width", "3");
      }

      // Mise en surbrillance du texte du jour sur l'axe X
      const dayLabel = document.getElementById(`label-day-${idx}`);
      if (dayLabel) {
        dayLabel.setAttribute("fill", "#14967F");
        dayLabel.setAttribute("font-weight", "800");
      }

      // 3. Mise à jour de la carte récapitulative du jour (haute lisibilité)
      if (activeDayAvatar && day) activeDayAvatar.textContent = day.charAt(0).toUpperCase();
      if (activeDayName) activeDayName.textContent = day;
      if (activeDayPlanned) activeDayPlanned.textContent = String(planned);
      if (activeDayCompleted) activeDayCompleted.textContent = String(completed);
      if (activeDayRate) {
        const ratePct = planned > 0 ? Math.round((completed / planned) * 100) : 0;
        activeDayRate.textContent = `${ratePct}%`;
      }
      if (activeDayCard) {
        activeDayCard.classList.add("bg-emerald-50/40", "border-[#14967F]/40");
        activeDayCard.classList.remove("bg-neutral-50/60", "border-neutral-200/80");
      }

      // 4. Remplissage et positionnement de l'infobulle flottante avec bridage anti-débordement
      if (tooltipDay) tooltipDay.textContent = day;
      if (tooltipPlanned) tooltipPlanned.textContent = String(planned);
      if (tooltipCompleted) tooltipCompleted.textContent = String(completed);

      if (tooltipRate) {
        if (planned > 0) {
          const rate = Math.round((completed / planned) * 100);
          tooltipRate.textContent = `${rate}% honorés`;
          tooltipRate.classList.remove("hidden");
        } else {
          tooltipRate.classList.add("hidden");
        }
      }

      // Coordonnées du tooltip relatives au conteneur avec bridage (aucun rognage à gauche/droite)
      const containerRect = container.getBoundingClientRect();
      const svgRect = svg.getBoundingClientRect();
      const scaleX = svgRect.width / 650;
      const scaleY = svgRect.height / 260;

      const posX = x * scaleX;
      const tooltipWidth = tooltip.offsetWidth || 224;
      const tooltipHeight = tooltip.offsetHeight || 100;

      let left = posX - (tooltipWidth / 2);
      const maxLeft = containerRect.width - tooltipWidth - 12;
      left = Math.max(12, Math.min(left, maxLeft));

      // Positionner au-dessus du point le plus haut, ou en-dessous si trop près du haut
      const highestY = Math.min(
        plannedVisible ? plannedY : 220,
        completedVisible ? completedY : 220
      );
      const posY = highestY * scaleY;
      let top = posY - tooltipHeight - 14;
      if (top < 10) {
        top = Math.min(containerRect.height - tooltipHeight - 10, posY + 22);
      }

      tooltip.style.left = `${left}px`;
      tooltip.style.top = `${top}px`;
      tooltip.style.opacity = "1";
    });

    col.addEventListener("mouseleave", () => {
      const idx = col.getAttribute("data-idx");
      crosshair.style.opacity = "0";

      const haloP = document.getElementById(`halo-planned-${idx}`);
      const dotP = document.getElementById(`dot-planned-${idx}`);
      const haloC = document.getElementById(`halo-completed-${idx}`);
      const dotC = document.getElementById(`dot-completed-${idx}`);

      if (haloP) {
        haloP.style.opacity = "0";
        haloP.setAttribute("r", "7");
      }
      if (dotP) {
        dotP.setAttribute("r", "4");
        dotP.setAttribute("stroke-width", "2");
      }

      if (haloC) {
        haloC.style.opacity = "0";
        haloC.setAttribute("r", "8");
      }
      if (dotC) {
        dotC.setAttribute("r", "4.5");
        dotC.setAttribute("stroke-width", "2");
      }

      const dayLabel = document.getElementById(`label-day-${idx}`);
      if (dayLabel) {
        dayLabel.setAttribute("fill", "#6B7280");
        dayLabel.setAttribute("font-weight", "600");
      }

      // Restauration de la carte récapitulative du jour actuel
      if (activeDayAvatar) activeDayAvatar.textContent = initialAvatar;
      if (activeDayName) activeDayName.textContent = initialName;
      if (activeDayPlanned) activeDayPlanned.textContent = initialPlanned;
      if (activeDayCompleted) activeDayCompleted.textContent = initialCompleted;
      if (activeDayRate) activeDayRate.textContent = initialRate;
      if (activeDayCard) {
        activeDayCard.classList.remove("bg-emerald-50/40", "border-[#14967F]/40");
        activeDayCard.classList.add("bg-neutral-50/60", "border-neutral-200/80");
      }

      tooltip.style.opacity = "0";
    });
  });

  // B. Interactions de la légende (Survol & Clic pour filtrer)
  if (plannedBtn) {
    // Survol : isoler la courbe planifiée
    plannedBtn.addEventListener("mouseenter", () => {
      if (!plannedVisible) return;
      if (completedCurve) completedCurve.style.opacity = "0.2";
      if (completedArea) completedArea.style.opacity = "0.1";
      svg.querySelectorAll('[id^="dot-completed-"]').forEach((d) => (d.style.opacity = "0.2"));
      if (plannedCurve) {
        plannedCurve.setAttribute("stroke-width", "4");
        plannedCurve.style.filter = "url(#glow-planned)";
      }
    });

    plannedBtn.addEventListener("mouseleave", () => {
      if (completedCurve && completedVisible) completedCurve.style.opacity = "1";
      if (completedArea && completedVisible) completedArea.style.opacity = "1";
      svg.querySelectorAll('[id^="dot-completed-"]').forEach((d) => (d.style.opacity = "1"));
      if (plannedCurve) {
        plannedCurve.setAttribute("stroke-width", "2.5");
        plannedCurve.style.filter = "none";
      }
    });

    // Clic : basculer l'affichage de la série
    plannedBtn.addEventListener("click", () => {
      plannedVisible = !plannedVisible;
      const targetOpacity = plannedVisible ? "1" : "0";
      if (plannedCurve) plannedCurve.style.opacity = targetOpacity;
      if (plannedArea) plannedArea.style.opacity = targetOpacity;
      svg.querySelectorAll('[id^="dot-planned-"]').forEach((d) => (d.style.opacity = targetOpacity));

      plannedBtn.classList.toggle("opacity-40", !plannedVisible);
      plannedBtn.classList.toggle("line-through", !plannedVisible);
      plannedBtn.classList.toggle("bg-neutral-100", !plannedVisible);
    });
  }

  if (completedBtn) {
    // Survol : isoler la courbe honorée
    completedBtn.addEventListener("mouseenter", () => {
      if (!completedVisible) return;
      if (plannedCurve) plannedCurve.style.opacity = "0.2";
      if (plannedArea) plannedArea.style.opacity = "0.1";
      svg.querySelectorAll('[id^="dot-planned-"]').forEach((d) => (d.style.opacity = "0.2"));
      if (completedCurve) {
        completedCurve.setAttribute("stroke-width", "4.5");
        completedCurve.style.filter = "url(#glow-completed)";
      }
    });

    completedBtn.addEventListener("mouseleave", () => {
      if (plannedCurve && plannedVisible) plannedCurve.style.opacity = "1";
      if (plannedArea && plannedVisible) plannedArea.style.opacity = "1";
      svg.querySelectorAll('[id^="dot-planned-"]').forEach((d) => (d.style.opacity = "1"));
      if (completedCurve) {
        completedCurve.setAttribute("stroke-width", "3");
        completedCurve.style.filter = "none";
      }
    });

    // Clic : basculer l'affichage de la série
    completedBtn.addEventListener("click", () => {
      completedVisible = !completedVisible;
      const targetOpacity = completedVisible ? "1" : "0";
      if (completedCurve) completedCurve.style.opacity = targetOpacity;
      if (completedArea) completedArea.style.opacity = targetOpacity;
      svg.querySelectorAll('[id^="dot-completed-"]').forEach((d) => (d.style.opacity = targetOpacity));

      completedBtn.classList.toggle("opacity-40", !completedVisible);
      completedBtn.classList.toggle("line-through", !completedVisible);
      completedBtn.classList.toggle("bg-neutral-100", !completedVisible);
    });
  }
}

/**
 * 4. Interactions et animations du Donut Chart des statuts
 * - Survol des pilules de légende qui anime et agrandit l'arc correspondant
 * - Mise à jour du texte central (chiffre animé, pourcentage et intitulé)
 * - Survol direct des arcs SVG synchronisé avec les pilules
 */
function initDonutChartInteractions() {
  const donutSvg = document.getElementById("status-donut-svg");
  const centerValue = document.getElementById("donut-center-value");
  const centerLabel = document.getElementById("donut-center-label");
  const centerPct = document.getElementById("donut-center-pct");

  if (!donutSvg || !centerValue || !centerLabel || !centerPct) return;

  const defaultTotal = centerValue.textContent.trim();
  const defaultLabel = centerLabel.textContent.trim();

  const segments = donutSvg.querySelectorAll(".donut-segment");
  const pills = document.querySelectorAll(".donut-legend-pill");

  function highlightStatus(statusKey) {
    const targetSegment = document.getElementById(`donut-seg-${statusKey}`);
    if (!targetSegment) return;

    const count = targetSegment.getAttribute("data-count") || "0";
    const label = targetSegment.getAttribute("data-label") || "";
    const pct = targetSegment.getAttribute("data-pct") || "0";
    const color = targetSegment.getAttribute("data-color") || "#14967F";

    // 1. Mettre en valeur l'arc SVG et estomper les autres
    segments.forEach((seg) => {
      if (seg === targetSegment) {
        seg.setAttribute("stroke-width", "27");
        seg.style.opacity = "1";
        seg.style.filter = "drop-shadow(0 2px 8px rgba(0, 0, 0, 0.25))";
      } else {
        seg.setAttribute("stroke-width", "18");
        seg.style.opacity = "0.25";
        seg.style.filter = "none";
      }
    });

    // 2. Mettre à jour le centre du Donut
    centerValue.textContent = count;
    centerValue.style.color = color;
    centerLabel.textContent = label;
    centerPct.textContent = `${pct}%`;
    centerPct.style.color = color;
    centerPct.classList.remove("hidden");
    centerPct.style.opacity = "1";

    // 3. Activer visuellement la pilule correspondante
    pills.forEach((pill) => {
      const isTarget = pill.getAttribute("data-donut-target") === statusKey;
      pill.classList.toggle("ring-2", isTarget);
      pill.classList.toggle("ring-[#14967F]/40", isTarget);
      pill.classList.toggle("shadow-xs", isTarget);
      pill.classList.toggle("-translate-y-0.5", isTarget);
    });
  }

  function resetStatus() {
    segments.forEach((seg) => {
      seg.setAttribute("stroke-width", "20");
      seg.style.opacity = "1";
      seg.style.filter = "none";
    });

    centerValue.textContent = defaultTotal;
    centerValue.style.color = "#0F172A";
    centerLabel.textContent = defaultLabel;
    centerPct.classList.add("hidden");
    centerPct.style.opacity = "0";

    pills.forEach((pill) => {
      pill.classList.remove("ring-2", "ring-[#14967F]/40", "shadow-xs", "-translate-y-0.5");
    });
  }

  // Événements sur les pilules de légende
  pills.forEach((pill) => {
    const statusKey = pill.getAttribute("data-donut-target");
    if (!statusKey) return;

    pill.addEventListener("mouseenter", () => highlightStatus(statusKey));
    pill.addEventListener("mouseleave", resetStatus);
    pill.addEventListener("focus", () => highlightStatus(statusKey));
    pill.addEventListener("blur", resetStatus);
  });

  // Événements sur les arcs SVG du Donut
  segments.forEach((seg) => {
    const statusKey = seg.getAttribute("data-status");
    if (!statusKey) return;

    seg.addEventListener("mouseenter", () => highlightStatus(statusKey));
    seg.addEventListener("mouseleave", resetStatus);
  });
}

