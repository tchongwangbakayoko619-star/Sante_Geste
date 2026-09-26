/**
 * CS² Health Design System - Searchable Select Component (Combobox)
 * Transforme n'importe quel <select data-searchable="true"> ou <select class="searchable-select">
 * en un champ de recherche filtrable avec autocomplétion, recherche insensible à la casse et aux accents,
 * navigation complète au clavier et synchronisation bidirectionnelle avec l'élément <select> natif.
 */

(function () {
  'use strict';

  /**
   * Normalise une chaîne pour une recherche insensible aux accents et à la casse.
   */
  function normalize(str) {
    return (str || '')
      .toLowerCase()
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .trim();
  }

  /**
   * Échappe les caractères HTML dangereux.
   */
  function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text || '';
    return div.innerHTML;
  }

  /**
   * Initialise un select enrichi en Combobox accessible.
   */
  function initSearchableSelect(select) {
    if (select.dataset.searchableInitialized === 'true') {
      return;
    }
    select.dataset.searchableInitialized = 'true';

    const selectId = select.id || 'select_' + Math.random().toString(36).substring(2, 9);
    select.id = selectId;

    const placeholder =
      select.dataset.placeholder ||
      (select.options.length > 0 && !select.options[0].value ? select.options[0].text : 'Rechercher...');

    // Création du conteneur wrapper
    const wrapper = document.createElement('div');
    wrapper.className = 'relative w-full searchable-select-wrapper';
    wrapper.dataset.targetSelect = selectId;

    // Masquage du select natif (conservé dans le DOM pour la soumission du formulaire et validation Django)
    select.style.position = 'absolute';
    select.style.opacity = '0';
    select.style.pointerEvents = 'none';
    select.style.width = '1px';
    select.style.height = '1px';
    select.style.margin = '-1px';
    select.setAttribute('tabindex', '-1');
    select.setAttribute('aria-hidden', 'true');

    // Insertion du wrapper avant le select
    select.parentNode.insertBefore(wrapper, select);
    wrapper.appendChild(select);

    // Champ de saisie interactif (Input Combobox)
    const inputWrapper = document.createElement('div');
    inputWrapper.className = 'relative flex items-center';

    const input = document.createElement('input');
    input.type = 'text';
    input.autocomplete = 'off';
    input.spellcheck = false;
    input.className =
      'w-full pl-10 pr-16 py-2.5 rounded-xl border border-neutral-300 focus:outline-none focus:ring-2 focus:ring-[#14967F] focus:border-[#14967F] text-sm text-neutral-800 transition-colors bg-white placeholder:text-neutral-400';
    input.placeholder = placeholder;
    input.setAttribute('role', 'combobox');
    input.setAttribute('aria-expanded', 'false');
    input.setAttribute('aria-autocomplete', 'list');
    input.setAttribute('aria-controls', `${selectId}_dropdown`);

    // Icône de recherche à gauche
    const leftIcon = document.createElement('div');
    leftIcon.className = 'absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-neutral-400';
    leftIcon.innerHTML = `
      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/>
      </svg>
    `;

    // Boutons à droite (Clear + Chevron)
    const rightActions = document.createElement('div');
    rightActions.className = 'absolute inset-y-0 right-0 pr-2.5 flex items-center gap-1';

    const clearBtn = document.createElement('button');
    clearBtn.type = 'button';
    clearBtn.title = 'Effacer la sélection';
    clearBtn.className =
      'p-1 text-neutral-400 hover:text-neutral-600 rounded-lg hover:bg-neutral-100 transition-colors cursor-pointer hidden focus:outline-none';
    clearBtn.innerHTML = `
      <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
      </svg>
    `;

    const chevronBtn = document.createElement('button');
    chevronBtn.type = 'button';
    chevronBtn.tabIndex = -1;
    chevronBtn.title = 'Afficher la liste';
    chevronBtn.className = 'p-1 text-neutral-400 hover:text-neutral-600 transition-transform cursor-pointer focus:outline-none';
    chevronBtn.innerHTML = `
      <svg class="w-4 h-4 transition-transform duration-200 transform" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/>
      </svg>
    `;

    rightActions.appendChild(clearBtn);
    rightActions.appendChild(chevronBtn);

    inputWrapper.appendChild(leftIcon);
    inputWrapper.appendChild(input);
    inputWrapper.appendChild(rightActions);
    wrapper.appendChild(inputWrapper);

    // Menu déroulant des options
    const dropdown = document.createElement('div');
    dropdown.id = `${selectId}_dropdown`;
    dropdown.className =
      'hidden absolute z-50 left-0 right-0 mt-1.5 bg-white border border-neutral-200/90 rounded-2xl shadow-xl max-h-64 overflow-y-auto p-1.5 space-y-0.5';
    dropdown.setAttribute('role', 'listbox');
    wrapper.appendChild(dropdown);

    let highlightedIndex = -1;
    let visibleOptions = [];

    // Récupération des options réelles
    function getOptionsData() {
      const items = [];
      for (let i = 0; i < select.options.length; i++) {
        const opt = select.options[i];
        if (!opt.value) continue; // Ignore le séparateur ou option vide par défaut
        items.push({
          value: opt.value,
          text: opt.text.trim(),
          normalized: normalize(opt.text),
        });
      }
      return items;
    }

    /**
     * Rendu HTML formaté pour une option (Badge NUP pour patient, Dr pour médecin).
     */
    function formatOptionHtml(text) {
      // Détection format Patient : "PAT-2026-0003 - BAKAYOKO Tchongwang"
      const dashIdx = text.indexOf(' - ');
      if (dashIdx !== -1) {
        const code = text.substring(0, dashIdx).trim();
        const name = text.substring(dashIdx + 3).trim();
        return `
          <div class="flex items-center gap-2.5 truncate">
            <span class="font-mono text-[11px] px-2 py-0.5 rounded-md bg-neutral-100 text-neutral-700 border border-neutral-200 shrink-0 font-semibold group-hover:bg-emerald-100 group-hover:text-emerald-800 transition-colors">${escapeHtml(code)}</span>
            <span class="font-bold text-neutral-900 group-hover:text-[#14967F] truncate">${escapeHtml(name)}</span>
          </div>
        `;
      }

      // Détection format Médecin : "Dr. Traoré Ibrahim"
      if (text.startsWith('Dr.') || text.startsWith('Dr ')) {
        return `
          <div class="flex items-center gap-2.5 truncate">
            <span class="w-6 h-6 rounded-full bg-teal-50 text-[#14967F] flex items-center justify-center shrink-0 text-[11px] font-black border border-teal-100">Dr</span>
            <span class="font-bold text-neutral-900 group-hover:text-[#14967F] truncate">${escapeHtml(text)}</span>
          </div>
        `;
      }

      return `<span class="font-medium text-neutral-800 group-hover:text-[#14967F] truncate">${escapeHtml(text)}</span>`;
    }

    /**
     * Affiche ou filtre les options dans le menu déroulant.
     */
    function renderDropdown(filterQuery = '') {
      const q = normalize(filterQuery);
      const allOptions = getOptionsData();

      visibleOptions = q ? allOptions.filter((opt) => opt.normalized.includes(q)) : allOptions;

      dropdown.innerHTML = '';
      highlightedIndex = -1;

      if (visibleOptions.length === 0) {
        const emptyMsg = document.createElement('div');
        emptyMsg.className = 'py-4 px-3 text-center text-xs text-neutral-400 space-y-1';
        emptyMsg.innerHTML = `
          <p class="font-semibold text-neutral-500">Aucun résultat trouvé</p>
          <p class="text-[11px] text-neutral-400">Aucune correspondance pour « ${escapeHtml(filterQuery)} »</p>
        `;
        dropdown.appendChild(emptyMsg);
        return;
      }

      visibleOptions.forEach((opt, idx) => {
        const itemBtn = document.createElement('button');
        itemBtn.type = 'button';
        itemBtn.setAttribute('role', 'option');
        itemBtn.setAttribute('data-index', idx);
        itemBtn.setAttribute('data-value', opt.value);

        const isSelected = select.value === opt.value;
        itemBtn.setAttribute('aria-selected', isSelected ? 'true' : 'false');

        itemBtn.className = `w-full text-left px-3 py-2 rounded-xl text-xs sm:text-sm font-medium transition-colors flex items-center justify-between group cursor-pointer ${
          isSelected
            ? 'bg-teal-50 text-[#14967F] font-bold'
            : 'text-neutral-700 hover:bg-neutral-50 hover:text-neutral-900'
        }`;

        itemBtn.innerHTML = `
          <div class="flex-1 truncate mr-2">
            ${formatOptionHtml(opt.text)}
          </div>
          ${
            isSelected
              ? `<svg class="w-4 h-4 text-[#14967F] shrink-0" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd"/></svg>`
              : ''
          }
        `;

        itemBtn.addEventListener('click', (e) => {
          e.preventDefault();
          selectOption(opt.value, opt.text);
        });

        dropdown.appendChild(itemBtn);
      });
    }

    /**
     * Sélectionne une option et synchronise avec le select natif.
     */
    function selectOption(value, text) {
      select.value = value;
      input.value = text;
      clearBtn.classList.toggle('hidden', !value);
      closeDropdown();

      // Déclenche l'événement change sur le select natif pour les scripts dépendants
      select.dispatchEvent(new Event('change', { bubbles: true }));
    }

    /**
     * Ouvre le menu déroulant.
     */
    function openDropdown() {
      renderDropdown(input.value);
      dropdown.classList.remove('hidden');
      input.setAttribute('aria-expanded', 'true');
      chevronBtn.querySelector('svg').classList.add('rotate-180');
    }

    /**
     * Ferme le menu déroulant.
     */
    function closeDropdown() {
      dropdown.classList.add('hidden');
      input.setAttribute('aria-expanded', 'false');
      chevronBtn.querySelector('svg').classList.remove('rotate-180');
      highlightedIndex = -1;
    }

    /**
     * Synchronise le champ avec l'option courante du select.
     */
    function syncFromSelect() {
      const selectedOpt = select.options[select.selectedIndex];
      if (selectedOpt && selectedOpt.value) {
        input.value = selectedOpt.text.trim();
        clearBtn.classList.remove('hidden');
      } else {
        input.value = '';
        clearBtn.classList.add('hidden');
      }
    }

    // Initialisation valeur initiale si déjà présélectionnée
    syncFromSelect();

    // Écoute des changements sur le select d'origine (ex: reset de formulaire)
    select.addEventListener('change', syncFromSelect);

    // Événements sur l'input
    input.addEventListener('focus', () => {
      openDropdown();
    });

    input.addEventListener('input', () => {
      openDropdown();
      renderDropdown(input.value);
      clearBtn.classList.toggle('hidden', !input.value);
    });

    // Clic sur l'input sélectionne tout le texte pour faciliter la recherche rapide
    input.addEventListener('click', () => {
      if (dropdown.classList.contains('hidden')) {
        openDropdown();
      }
    });

    // Clic sur le chevron pour basculer l'ouverture
    chevronBtn.addEventListener('click', (e) => {
      e.preventDefault();
      if (dropdown.classList.contains('hidden')) {
        input.focus();
        openDropdown();
      } else {
        closeDropdown();
      }
    });

    // Clic sur le bouton d'effacement
    clearBtn.addEventListener('click', (e) => {
      e.preventDefault();
      select.value = '';
      input.value = '';
      clearBtn.classList.add('hidden');
      select.dispatchEvent(new Event('change', { bubbles: true }));
      input.focus();
      renderDropdown('');
      openDropdown();
    });

    // Navigation au clavier (Flèches, Entrée, Échap, Tab)
    input.addEventListener('keydown', (e) => {
      const items = dropdown.querySelectorAll('[role="option"]');
      if (!items || items.length === 0) return;

      if (e.key === 'ArrowDown') {
        e.preventDefault();
        if (dropdown.classList.contains('hidden')) {
          openDropdown();
          return;
        }
        highlightedIndex = (highlightedIndex + 1) % items.length;
        updateHighlight(items);
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        if (dropdown.classList.contains('hidden')) {
          openDropdown();
          return;
        }
        highlightedIndex = (highlightedIndex - 1 + items.length) % items.length;
        updateHighlight(items);
      } else if (e.key === 'Enter') {
        if (!dropdown.classList.contains('hidden') && highlightedIndex >= 0 && items[highlightedIndex]) {
          e.preventDefault();
          items[highlightedIndex].click();
        }
      } else if (e.key === 'Escape') {
        closeDropdown();
      } else if (e.key === 'Tab') {
        closeDropdown();
      }
    });

    function updateHighlight(items) {
      items.forEach((item, idx) => {
        if (idx === highlightedIndex) {
          item.classList.add('bg-neutral-100', 'text-neutral-900', 'ring-1', 'ring-neutral-200');
          item.scrollIntoView({ block: 'nearest' });
        } else {
          item.classList.remove('bg-neutral-100', 'text-neutral-900', 'ring-1', 'ring-neutral-200');
        }
      });
    }

    // Gestion de la perte de focus (Blur)
    input.addEventListener('blur', () => {
      // Temporisation pour permettre au clic sur une option d'aboutir
      setTimeout(() => {
        closeDropdown();
        // Si l'utilisateur a tapé un texte sans cliquer sur une option
        const currentText = input.value.trim();
        const allOptions = getOptionsData();
        const exactMatch = allOptions.find(
          (opt) => normalize(opt.text) === normalize(currentText)
        );

        if (exactMatch) {
          selectOption(exactMatch.value, exactMatch.text);
        } else if (!select.value) {
          // Rien de sélectionné
          input.value = '';
          clearBtn.classList.add('hidden');
        } else {
          // Rétablir le libellé de l'option actuellement sélectionnée
          syncFromSelect();
        }
      }, 200);
    });

    // Fermeture si clic à l'extérieur
    document.addEventListener('click', (e) => {
      if (!wrapper.contains(e.target)) {
        closeDropdown();
      }
    });
  }

  // Initialisation automatique sur le DOM
  function initAll() {
    const selects = document.querySelectorAll('select[data-searchable="true"], select.searchable-select');
    selects.forEach(initSearchableSelect);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initAll);
  } else {
    initAll();
  }

  // Expose globalement pour réinitialisation dynamique si besoin (AJAX / modales)
  window.initSearchableSelect = initSearchableSelect;
  window.initAllSearchableSelects = initAll;
})();
