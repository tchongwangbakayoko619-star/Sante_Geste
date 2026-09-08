# Catalogue de Composants & Design System - CS² Health (SantéGeste)

Ce document sert de référence officielle pour l'architecture **Atomic Design**, la structure des composants et le guide d'utilisation des templates Django et scripts JavaScript dans le projet **SantéGeste**.

---

## 1. Architecture Atomic Design

Les templates sont organisés dans `santegeste/templates/components/` selon la méthodologie **Atomic Design** :

```text
santegeste/templates/
├── components/
│   ├── atoms/               # Éléments individuels indivisibles (boutons, inputs, badges, icônes)
│   │   ├── badge.html
│   │   ├── button.html
│   │   ├── checkbox.html
│   │   ├── icon.html
│   │   ├── input.html
│   │   ├── label.html
│   │   └── select.html
│   │
│   ├── molecules/           # Combinaisons d'atomes (champs de formulaire, alertes, lockup marque)
│   │   ├── alert.html
│   │   ├── brand-lockup.html
│   │   ├── flash-messages.html
│   │   ├── form-field.html
│   │   ├── password-field.html
│   │   └── select-field.html
│   │
│   └── organisms/           # Assemblages complexes prêts à l'emploi (formulaires complets, hero)
│       ├── auth-hero.html
│       ├── forgot-password-form.html
│       ├── login-form.html
│       ├── otp-form.html
│       ├── password-reset-confirm-form.html
│       └── register-form.html
│
└── layouts/                 # Structures de pages globales
    ├── base.html            # Layout principal de l'application (Navbar, Container, Footer)
    └── auth.html            # Layout split 50/50 pour les pages d'authentification
```

---

## 2. Guide d'utilisation des Atomes (`atoms/`)

### `button.html`
Bouton interactif ou lien stylisé avec support natif des icônes et du **spinner de chargement animé**.

**Paramètres (Props) :**
* `text` *(string)* : Texte du bouton.
* `type` *(string)* : `'submit'`, `'button'` ou `'a'` (défaut: `'submit'`).
* `href` *(string)* : URL si `type='a'`.
* `variant` *(string)* : `'primary'`, `'outline'`, `'secondary'`, `'link'` (défaut: `'primary'`).
* `full_width` *(bool)* : S'étend sur toute la largeur (`w-full`) si `True`.
* `icon_left` *(string)* : Nom de l'icône à gauche (ex: `'login'`, `'mail'`).
* `icon_right` *(string)* : Nom de l'icône à droite (ex: `'arrow-left'`).
* `disabled` *(bool)* : Désactive le bouton.
* `loading` *(bool)* : Affiche le spinner animé de chargement.

**Exemple d'utilisation :**
```django
{% include "components/atoms/button.html" with text="Se connecter" type="submit" variant="primary" full_width=True icon_left="login" %}
```

---

### `badge.html`
Badge sémantique (sécurité, statut, accentuation).

**Paramètres (Props) :**
* `text` *(string)* : Libellé du badge.
* `variant` *(string)* : `'secure'`, `'pill-highlight'`, `'success'`, `'neutral'` (défaut: `'secure'`).
* `icon_name` *(string)* : Nom de l'icône (ex: `'lock'`).

**Exemple d'utilisation :**
```django
{% include "components/atoms/badge.html" with variant="secure" text="Espace Sécurisé" icon_name="lock" %}
```

---

## 3. Guide d'utilisation des Molécules (`molecules/`)

### `form-field.html`
Champ de saisie standard regroupant le label, l'input et la gestion des erreurs/hints.

**Paramètres (Props) :**
* `id` *(string)* : Identifiant HTML.
* `name` *(string)* : Nom du champ dans le formulaire.
* `type` *(string)* : `'text'`, `'email'`, `'tel'`, etc.
* `label` *(string)* : Libellé du champ.
* `placeholder` *(string)* : Texte d'exemple.
* `value` *(string)* : Valeur courante.
* `required` *(bool)* : Champ obligatoire.
* `icon_left` *(string)* : Nom de l'icône (ex: `'mail'`, `'phone'`).
* `has_error` *(bool)* : Indique si le champ contient des erreurs.
* `error_message` *(string)* : Message d'erreur à afficher.

**Exemple d'utilisation :**
```django
{% include "components/molecules/form-field.html" with id="email" name="email" type="email" label="Adresse e-mail *" placeholder="dr.valois@cs2-health.org" value=form.email.value required=True icon_left="mail" has_error=form.email.errors error_message=form.email.errors.0 %}
```

---

### `password-field.html`
Champ mot de passe sécurisé incluant l'icône cadenas, le bouton d'affichage/masquage de mot de passe (œil) et le lien "Mot de passe oublié".

**Exemple d'utilisation :**
```django
{% include "components/molecules/password-field.html" with id="password" name="password" label="Mot de passe *" placeholder="••••••••" required=True forgot_password_url=forgot_url has_error=form.password.errors error_message=form.password.errors.0 %}
```

---

### `alert.html`
Notification / Alerte avec gestion des variantes d'état (`success`, `warning`, `error`, `danger`, `info`) et auto-fermeture.

**Exemple d'utilisation :**
```django
{% include "components/molecules/alert.html" with variant="error" message="Identifiants incorrects." dismissible=True auto_dismiss=5000 %}
```

---

## 4. Guide d'utilisation des Organismes (`organisms/`)

Les organismes sont 100% configurables et ne contiennent aucune URL codée en dur.

### `login-form.html`
Formulaire de connexion complet.

**Props principales :**
* `form` : Objet `Form` Django.
* `action_url` : URL de la vue POST.
* `forgot_password_url` : URL vers mot de passe oublié.
* `register_url` : URL vers l'inscription.
* `title` & `subtitle` : Personnalisation des titres.
* `submit_text` : Libellé du bouton.

**Exemple d'utilisation dans une page :**
```django
{% url 'users:forgot-password' as forgot_url %}
{% url 'users:register' as register_url %}
{% include "components/organisms/login-form.html" with form=form forgot_password_url=forgot_url register_url=register_url %}
```

---

### `register-form.html`
Formulaire de création de compte professionnel soignant.

**Exemple d'utilisation :**
```django
{% url 'users:login' as login_url %}
{% include "components/organisms/register-form.html" with form=form login_url=login_url %}
```

---

### `otp-form.html`
Formulaire de saisie du code OTP à 6 chiffres avec bouton de renvoi du code et bouton de retour.

**Exemple d'utilisation :**
```django
{% url 'users:resend-otp' as resend_url %}
{% url 'users:register' as back_url %}
{% include "components/organisms/otp-form.html" with form=form resend_url=resend_url back_url=back_url back_text="Retour à l'inscription" title="Validation du compte" %}
```

---

## 5. Scripts JavaScript d'Interaction UI

Les scripts sont situés dans `santegeste/static/js/components/` et s'activent automatiquement grâce aux attributs HTML `data-*` :

| Script | Attribut déclencheur | Rôle |
| :--- | :--- | :--- |
| `form-validation.js` | `data-form-validate` | Validation côté client en direct (format email, téléphone, concordance des mots de passe `password1`/`password2`). |
| `form-loading.js` | `data-form-loading` | Désactivation du bouton lors du clic et affichage du spinner de chargement animé. |
| `password-toggle.js` | `data-password-toggle="id"` | Bascule de l'affichage du mot de passe (icône œil ouvert/fermé). |
| `alerts.js` | `data-alert`, `data-auto-dismiss="5000"` | Gestion de la fermeture manuelle et automatique des toasts d'alertes. |

---

## 6. Structure des Styles CSS (Tailwind v4)

Les styles de composants sont définis dans `santegeste/static/css/components/` sous la directive `@layer components` :

* `auth.css` : Layouts et conteneurs d'authentification (`.auth-layout`, `.auth-hero`, `.auth-content`, `.auth-glow`, `.auth-pattern`).
* `buttons.css` : Variantes de boutons (`.btn`, `.btn-primary`, `.btn-outline`, `.btn-secondary`, `.btn-link`).
* `forms.css` : Champs de saisie (`.input-base`, `.input-with-icon`, `.input-error`, `.form-group`, `.form-error-text`).
* `alerts.css` : Alertes (`.flash-messages-container`, `.alert-base`, `.alert-error`, `.alert-success`).
* `badges.css` : Badges (`.badge-base`, `.badge-secure`, `.brand-lockup-logo`).
