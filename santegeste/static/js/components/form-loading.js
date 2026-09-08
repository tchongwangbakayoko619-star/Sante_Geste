/**
 * Gestion de l'État de Chargement & Spinners (CS² Health Design System)
 * Gère l'animation de chargement, le désengagement des boutons et la vocalisation ARIA lors de la soumission.
 */
document.addEventListener('DOMContentLoaded', () => {
  const loadingForms = document.querySelectorAll('form[data-form-loading]');

  loadingForms.forEach((form) => {
    form.addEventListener('submit', (e) => {
      // Si la validation du navigateur ou de notre script empêche l'envoi, ne pas basculer en loading
      if (e.defaultPrevented) return;

      const submitButton = form.querySelector('button[type="submit"], input[type="submit"]');
      if (!submitButton || submitButton.disabled) return;

      // Basculer le formulaire en état aria-busy
      form.setAttribute('aria-busy', 'true');

      // Activer l'état de chargement et d'accessibilité sur le bouton
      submitButton.disabled = true;
      submitButton.setAttribute('aria-disabled', 'true');
      submitButton.setAttribute('aria-busy', 'true');

      const spinner = submitButton.querySelector('.btn-spinner');
      const icons = submitButton.querySelectorAll('.btn-icon-left, .btn-icon-right');
      const btnText = submitButton.querySelector('.btn-text');

      if (spinner) {
        spinner.classList.remove('hidden');
      }

      icons.forEach((icon) => icon.classList.add('hidden'));

      if (btnText) {
        btnText.setAttribute('data-original-text', btnText.textContent);
        btnText.textContent = 'Traitement en cours...';
      }

      // Sécurité : restauration au bout de 15 secondes en cas d'interruption réseau
      setTimeout(() => {
        if (form.getAttribute('aria-busy') === 'true') {
          form.removeAttribute('aria-busy');
          submitButton.disabled = false;
          submitButton.removeAttribute('aria-disabled');
          submitButton.removeAttribute('aria-busy');
          if (spinner) spinner.classList.add('hidden');
          icons.forEach((icon) => icon.classList.remove('hidden'));
          if (btnText && btnText.hasAttribute('data-original-text')) {
            btnText.textContent = btnText.getAttribute('data-original-text');
          }
        }
      }, 15000);
    });
  });
});
