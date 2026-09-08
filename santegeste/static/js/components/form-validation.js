/**
 * Validation Côté Client en Temps Réel (CS² Health Design System)
 * Gère la validation dynamique des formulaires et l'accessibilité ARIA (email, téléphone, confirmation de mot de passe, champs obligatoires).
 */
document.addEventListener('DOMContentLoaded', () => {
  const forms = document.querySelectorAll('form[data-form-validate]');

  forms.forEach((form) => {
    const inputs = form.querySelectorAll('input, select, textarea');

    // Validation lors de la saisie (input) et lors de la perte de focus (blur)
    inputs.forEach((input) => {
      input.addEventListener('blur', () => validateField(input, form));
      input.addEventListener('input', () => {
        if (input.classList.contains('input-error')) {
          validateField(input, form);
        }
      });
    });

    // Validation globale lors de la soumission (submit)
    form.addEventListener('submit', (e) => {
      let isValid = true;
      inputs.forEach((input) => {
        if (!validateField(input, form)) {
          isValid = false;
        }
      });

      if (!isValid) {
        e.preventDefault();
        e.stopPropagation();

        // Focus sur le premier champ en erreur
        const firstErrorField = form.querySelector('.input-error');
        if (firstErrorField) {
          firstErrorField.focus();
        }
      }
    });
  });

  /**
   * Valide un champ individuel et met à jour l'affichage de l'erreur.
   */
  function validateField(field, form) {
    // Ignorer les champs masqués ou désactivés
    if (field.type === 'hidden' || field.disabled) return true;

    let errorMessage = '';

    // 1. Champ obligatoire
    if (field.hasAttribute('required') && !field.value.trim()) {
      errorMessage = 'Ce champ est obligatoire.';
    }
    // 2. Format Email
    else if (field.type === 'email' && field.value.trim()) {
      const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
      if (!emailRegex.test(field.value.trim())) {
        errorMessage = 'Veuillez saisir une adresse e-mail valide.';
      }
    }
    // 3. Format Téléphone (si renseigné)
    else if (field.type === 'tel' && field.value.trim()) {
      const phoneRegex = /^(\+237|00237|237)?[236][0-9\s.-]{8,15}$/;
      if (!phoneRegex.test(field.value.trim())) {
        errorMessage = 'Veuillez saisir un numéro de téléphone valide (ex : 6XX XX XX XX).';
      }
    }
    // 4. Confirmation du mot de passe
    else if (field.name === 'password2') {
      const pass1 = form.querySelector('input[name="password1"]');
      if (pass1 && field.value !== pass1.value) {
        errorMessage = 'Les mots de passe ne correspondent pas.';
      }
    }

    // Affichage ou suppression du message d'erreur
    setFieldError(field, errorMessage);
    return !errorMessage;
  }

  /**
   * Met à jour le DOM pour afficher/masquer le message d'erreur du champ et synchroniser les attributs ARIA.
   */
  function setFieldError(field, message) {
    const parentGroup = field.closest('.form-group') || field.parentElement;
    let errorElement = parentGroup.querySelector('.form-error-text');
    const fieldId = field.id || field.name;
    const errorId = fieldId ? `${fieldId}-error` : null;

    if (message) {
      field.classList.add('input-error');
      field.setAttribute('aria-invalid', 'true');

      if (!errorElement) {
        errorElement = document.createElement('p');
        errorElement.className = 'form-error-text';
        if (errorId) errorElement.id = errorId;
        errorElement.setAttribute('role', 'alert');
        errorElement.setAttribute('aria-live', 'assertive');
        errorElement.innerHTML = `
          <svg class="w-3.5 h-3.5 shrink-0" fill="currentColor" viewBox="0 0 20 20">
            <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clip-rule="evenodd"/>
          </svg>
          <span>${message}</span>
        `;
        parentGroup.appendChild(errorElement);
      } else {
        const span = errorElement.querySelector('span') || errorElement;
        span.textContent = message;
      }

      if (errorId) {
        field.setAttribute('aria-describedby', errorId);
      }
    } else {
      field.classList.remove('input-error');
      field.setAttribute('aria-invalid', 'false');

      if (errorElement) {
        errorElement.remove();
      }
    }
  }
});
