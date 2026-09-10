/**
 * Composant de bascule de visibilité des mots de passe.
 * Gère l'affichage/masquage sécurisé des champs mot de passe.
 */
document.addEventListener("DOMContentLoaded", () => {
  const toggleButtons = document.querySelectorAll("[data-password-toggle]");

  toggleButtons.forEach((button) => {
    button.addEventListener("click", () => {
      const targetId = button.getAttribute("data-password-toggle");
      const input = document.getElementById(targetId);
      if (!input) return;

      const isPassword = input.type === "password";
      input.type = isPassword ? "text" : "password";

      const eyeIcon = button.querySelector(".icon-eye");
      const eyeOffIcon = button.querySelector(".icon-eye-off");

      if (eyeIcon && eyeOffIcon) {
        eyeIcon.classList.toggle("hidden", isPassword);
        eyeOffIcon.classList.toggle("hidden", !isPassword);
      }

      button.setAttribute("aria-label", isPassword ? "Masquer le mot de passe" : "Afficher le mot de passe");
    });
  });
});

