/**
 * Gestion de l'État de Chargement & Spinners (CS² Health Design System)
 * Gère l'animation de chargement et le désengagement des boutons lors de la soumission.
 */
document.addEventListener('DOMContentLoaded', () => {
  const loadingForms = document.querySelectorAll('form[data-form-loading]');

  loadingForms.forEach((form) => {
    form.addEventListener('submit', (e) => {
      // Si la validation du navigateur ou de notre script échoue, ne pas lancer le spinner
      if (e.defaultPrevented) return;

      const submitButton = form.querySelector('button[type="submit"], input[type="submit"]');
      if (!submitButton || submitButton.disabled) return;

      // Activer l'état de chargement sur le bouton
      submitButton.disabled = true;

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
    });
  });
});
