/**
 * SantéGeste - Module des Graphiques Interactifs du Tableau de Bord (Chart.js)
 * - Graphique linéaire dynamique avec double courbe lissée (Planifiés vs Honorés)
 * - Donut Chart des statuts avec compteur central interactif et synchronisation des légendes
 * - Effets d'animation de chargement fluides (loading animations) et dégradés émeraude
 */

(function () {
  'use strict';

  function initCharts() {
    const dataElement = document.getElementById('dashboard-charts-data');
    if (!dataElement) return;

    let chartData = {};
    const rawContent = (dataElement.textContent || '{}').trim();
    try {
      chartData = JSON.parse(rawContent);
    } catch (e) {
      try {
        // Nettoyage de secours au cas où des virgules de localisation ont été rendues (ex: 33,3 -> 33.3)
        const sanitized = rawContent.replace(/:\s*([0-9]+),([0-9]+)/g, ': $1.$2');
        chartData = JSON.parse(sanitized);
      } catch (err) {
        console.error('Erreur lors du parsing des données de graphiques SantéGeste:', err);
        return;
      }
    }

    if (typeof Chart === 'undefined') {
      // Si Chart.js est en cours de chargement asynchrone, réessayer dans 50ms
      setTimeout(initCharts, 50);
      return;
    }

    // Configuration globale Chart.js pour respecter le Design System SantéGeste
    Chart.defaults.font.family = "Outfit, system-ui, -apple-system, sans-serif";
    Chart.defaults.color = '#64748B';

    initActivityLineChart(chartData.activity || {});
    initStatusDonutChart(chartData.status_breakdown || {});
  }

  /**
   * 1. Graphique d'Activité & Prise en Charge (Courbes Splines Dégradées)
   */
  function initActivityLineChart(activity) {
    const canvas = document.getElementById('activityChartCanvas');
    if (!canvas || !activity.has_data) return;

    const ctx = canvas.getContext('2d');
    const parentContainer = document.getElementById('activity-chart-container');
    const height = parentContainer ? parentContainer.clientHeight || 270 : 270;

    // Création des gradients de fond vert émeraude
    const gradientPlanned = ctx.createLinearGradient(0, 0, 0, height);
    gradientPlanned.addColorStop(0, 'rgba(11, 87, 70, 0.22)');
    gradientPlanned.addColorStop(1, 'rgba(11, 87, 70, 0.01)');

    const gradientCompleted = ctx.createLinearGradient(0, 0, 0, height);
    gradientCompleted.addColorStop(0, 'rgba(20, 150, 127, 0.32)');
    gradientCompleted.addColorStop(1, 'rgba(20, 150, 127, 0.02)');

    // Éléments de la carte récapitulative
    const activeDayAvatar = document.getElementById('active-day-avatar');
    const activeDayName = document.getElementById('active-day-name');
    const activeDayPlanned = document.getElementById('active-day-planned');
    const activeDayCompleted = document.getElementById('active-day-completed');
    const activeDayRate = document.getElementById('active-day-rate');
    const activeDayCard = document.getElementById('weekly-active-day-card');

    const initialAvatar = activeDayAvatar ? activeDayAvatar.textContent.trim() : '';
    const initialName = activeDayName ? activeDayName.textContent.trim() : '';
    const initialPlanned = activeDayPlanned ? activeDayPlanned.textContent.trim() : '0';
    const initialCompleted = activeDayCompleted ? activeDayCompleted.textContent.trim() : '0';
    const initialRate = activeDayRate ? activeDayRate.textContent.trim() : '0%';

    const chart = new Chart(ctx, {
      type: 'line',
      data: {
        labels: activity.labels || [],
        datasets: [
          {
            label: 'RDV Planifiés',
            data: activity.planned || [],
            borderColor: '#0B5746',
            backgroundColor: gradientPlanned,
            borderWidth: 2.5,
            fill: true,
            tension: 0.38,
            pointBackgroundColor: '#0B5746',
            pointBorderColor: '#ffffff',
            pointBorderWidth: 2,
            pointRadius: 4,
            pointHoverRadius: 7,
            pointHoverBackgroundColor: '#0B5746',
            pointHoverBorderColor: '#ffffff',
            pointHoverBorderWidth: 3,
          },
          {
            label: 'Honorés / Prise en charge',
            data: activity.completed || [],
            borderColor: '#14967F',
            backgroundColor: gradientCompleted,
            borderWidth: 3,
            fill: true,
            tension: 0.38,
            pointBackgroundColor: '#14967F',
            pointBorderColor: '#ffffff',
            pointBorderWidth: 2,
            pointRadius: 4.5,
            pointHoverRadius: 8,
            pointHoverBackgroundColor: '#14967F',
            pointHoverBorderColor: '#ffffff',
            pointHoverBorderWidth: 3,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: {
          duration: 1200,
          easing: 'easeInOutQuart',
        },
        interaction: {
          mode: 'index',
          intersect: false,
        },
        plugins: {
          legend: {
            display: false, // Légende externe sur-mesure pour un design 100% harmonieux
          },
          tooltip: {
            enabled: true,
            backgroundColor: 'rgba(255, 255, 255, 0.98)',
            titleColor: '#0F172A',
            bodyColor: '#334155',
            borderColor: '#E2E8F0',
            borderWidth: 1,
            padding: 12,
            cornerRadius: 14,
            boxPadding: 6,
            usePointStyle: true,
            titleFont: {
              size: 13,
              weight: 'bold',
            },
            bodyFont: {
              size: 12,
              weight: '600',
            },
            callbacks: {
              afterBody: function (items) {
                if (!items || items.length < 2) return '';
                const plannedVal = items[0]?.raw || 0;
                const completedVal = items[1]?.raw || 0;
                if (plannedVal > 0) {
                  const rate = Math.round((completedVal / plannedVal) * 100);
                  return `\nTaux de réalisation : ${rate}%`;
                }
                return '';
              },
            },
          },
        },
        scales: {
          x: {
            grid: {
              display: false,
            },
            ticks: {
              color: '#64748B',
              font: {
                size: 11,
                weight: '600',
              },
              maxRotation: 0,
              autoSkip: true,
              maxTicksLimit: 12,
            },
          },
          y: {
            beginAtZero: true,
            grid: {
              color: '#F1F5F9',
              borderDash: [4, 4],
            },
            ticks: {
              color: '#64748B',
              font: {
                size: 11,
                weight: 'bold',
              },
              precision: 0,
            },
          },
        },
        onHover: function (event, elements) {
          if (elements && elements.length > 0) {
            const idx = elements[0].index;
            const dayLabel = activity.labels[idx] || '';
            const plannedVal = activity.planned[idx] || 0;
            const completedVal = activity.completed[idx] || 0;
            const rateVal = plannedVal > 0 ? Math.round((completedVal / plannedVal) * 100) : 0;

            if (activeDayAvatar && dayLabel) activeDayAvatar.textContent = dayLabel.charAt(0).toUpperCase();
            if (activeDayName) activeDayName.textContent = dayLabel;
            if (activeDayPlanned) activeDayPlanned.textContent = String(plannedVal);
            if (activeDayCompleted) activeDayCompleted.textContent = String(completedVal);
            if (activeDayRate) activeDayRate.textContent = `${rateVal}%`;

            if (activeDayCard) {
              activeDayCard.classList.add('bg-emerald-50/40', 'border-[#14967F]/40');
              activeDayCard.classList.remove('bg-neutral-50/60', 'border-neutral-200/80');
            }
          }
        },
      },
    });

    // Remise à l'état initial quand le curseur quitte le graphique
    canvas.addEventListener('mouseleave', () => {
      if (activeDayAvatar) activeDayAvatar.textContent = initialAvatar;
      if (activeDayName) activeDayName.textContent = initialName;
      if (activeDayPlanned) activeDayPlanned.textContent = initialPlanned;
      if (activeDayCompleted) activeDayCompleted.textContent = initialCompleted;
      if (activeDayRate) activeDayRate.textContent = initialRate;
      if (activeDayCard) {
        activeDayCard.classList.remove('bg-emerald-50/40', 'border-[#14967F]/40');
        activeDayCard.classList.add('bg-neutral-50/60', 'border-neutral-200/80');
      }
    });

    // Synchronisation interactive des boutons de légende
    const plannedBtn = document.getElementById('legend-btn-planned');
    const completedBtn = document.getElementById('legend-btn-completed');

    if (plannedBtn) {
      plannedBtn.addEventListener('click', () => {
        const isVisible = chart.isDatasetVisible(0);
        chart.setDatasetVisibility(0, !isVisible);
        plannedBtn.classList.toggle('opacity-50', isVisible);
        chart.update();
      });
    }

    if (completedBtn) {
      completedBtn.addEventListener('click', () => {
        const isVisible = chart.isDatasetVisible(1);
        chart.setDatasetVisibility(1, !isVisible);
        completedBtn.classList.toggle('opacity-50', isVisible);
        chart.update();
      });
    }
  }

  /**
   * 2. Graphique Donut de Répartition des Statuts
   */
  function initStatusDonutChart(statusBreakdown) {
    const canvas = document.getElementById('statusDonutCanvas');
    if (!canvas || !statusBreakdown.has_data) return;

    const ctx = canvas.getContext('2d');
    const counts = statusBreakdown.counts || {};
    const percentages = statusBreakdown.percentages || {};

    const centerValue = document.getElementById('donut-center-value');
    const centerLabel = document.getElementById('donut-center-label');
    const centerPct = document.getElementById('donut-center-pct');

    const totalCount = statusBreakdown.total || 0;

    const donutChart = new Chart(ctx, {
      type: 'doughnut',
      data: {
        labels: ['Honorés', 'En attente', 'Annulés', 'Planifiés'],
        datasets: [
          {
            data: [
              counts.confirmed || 0,
              counts.waiting || 0,
              counts.cancelled || 0,
              counts.scheduled || 0,
            ],
            backgroundColor: [
              '#14967F', // Vert émeraude SantéGeste
              '#F59E0B', // Ambre / Orange
              '#EF4444', // Rouge rose
              '#3B82F6', // Bleu
            ],
            hoverBackgroundColor: [
              '#0E705F',
              '#D97706',
              '#DC2626',
              '#2563EB',
            ],
            borderWidth: 3,
            borderColor: '#FFFFFF',
            hoverOffset: 6,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: '72%',
        animation: {
          animateRotate: true,
          animateScale: true,
          duration: 1200,
          easing: 'easeOutQuart',
        },
        plugins: {
          legend: {
            display: false, // Légende externe détaillée via les cartes-pills
          },
          tooltip: {
            enabled: true,
            backgroundColor: 'rgba(255, 255, 255, 0.98)',
            titleColor: '#0F172A',
            bodyColor: '#334155',
            borderColor: '#E2E8F0',
            borderWidth: 1,
            padding: 10,
            cornerRadius: 12,
            boxPadding: 4,
            usePointStyle: true,
            callbacks: {
              label: function (context) {
                const val = context.raw || 0;
                const pct = totalCount > 0 ? Math.round((val / totalCount) * 100) : 0;
                return ` ${context.label}: ${val} (${pct}%)`;
              },
            },
          },
        },
        onHover: function (event, elements) {
          if (elements && elements.length > 0) {
            const idx = elements[0].index;
            const labels = ['Honorés', 'En attente', 'Annulés', 'Planifiés'];
            const keys = ['confirmed', 'waiting', 'cancelled', 'scheduled'];
            const key = keys[idx];
            const val = counts[key] || 0;
            const pct = percentages[key] || 0;

            if (centerValue) centerValue.textContent = String(val);
            if (centerLabel) centerLabel.textContent = labels[idx].toUpperCase();
            if (centerPct) {
              centerPct.textContent = `${pct}%`;
              centerPct.classList.remove('hidden');
            }
          }
        },
      },
    });

    // Restauration du centre quand la souris quitte le donut
    canvas.addEventListener('mouseleave', () => {
      if (centerValue) centerValue.textContent = String(totalCount);
      if (centerLabel) centerLabel.textContent = 'TOTAL RDV';
      if (centerPct) centerPct.classList.add('hidden');
    });

    // Synchronisation interactive des 4 cartes de statuts
    const legendPills = document.querySelectorAll('[data-donut-target]');
    const statusMap = {
      confirmed: 0,
      waiting: 1,
      cancelled: 2,
      scheduled: 3,
    };

    legendPills.forEach((pill) => {
      const target = pill.getAttribute('data-donut-target');
      const datasetIndex = statusMap[target];

      pill.addEventListener('mouseenter', () => {
        if (typeof datasetIndex === 'number' && donutChart) {
          donutChart.setActiveElements([
            {
              datasetIndex: 0,
              index: datasetIndex,
            },
          ]);
          donutChart.tooltip.setActiveElements(
            [
              {
                datasetIndex: 0,
                index: datasetIndex,
              },
            ],
            { x: 0, y: 0 }
          );
          donutChart.update();

          const labels = ['Honorés', 'En attente', 'Annulés', 'Planifiés'];
          const keys = ['confirmed', 'waiting', 'cancelled', 'scheduled'];
          const val = counts[target] || 0;
          const pct = percentages[target] || 0;

          if (centerValue) centerValue.textContent = String(val);
          if (centerLabel) centerLabel.textContent = labels[datasetIndex].toUpperCase();
          if (centerPct) {
            centerPct.textContent = `${pct}%`;
            centerPct.classList.remove('hidden');
          }
        }
      });

      pill.addEventListener('mouseleave', () => {
        if (donutChart) {
          donutChart.setActiveElements([]);
          donutChart.tooltip.setActiveElements([], { x: 0, y: 0 });
          donutChart.update();

          if (centerValue) centerValue.textContent = String(totalCount);
          if (centerLabel) centerLabel.textContent = 'TOTAL RDV';
          if (centerPct) centerPct.classList.add('hidden');
        }
      });
    });
  }

  // Lancement dès que le DOM est prêt
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initCharts);
  } else {
    initCharts();
  }
})();
