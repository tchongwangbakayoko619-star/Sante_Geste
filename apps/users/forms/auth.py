"""Formulaires d'authentification, de profil et d'OTP pour l'application users."""
from __future__ import annotations

from typing import Any

from django import forms
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.forms import UserChangeForm as BaseUserChangeForm
from django.contrib.auth.forms import UserCreationForm as BaseUserCreationForm
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from apps.users.forms.mixins import PasswordConfirmationMixin
from apps.users.models import MedicalProfile
from utils.constants.otp import OTP_CODE_LENGTH
from utils.phone import normalize_phone_number, validate_phone_number


User = get_user_model()


def _password_field(label: str, autocomplete: str) -> forms.CharField:
    return forms.CharField(
        label=label,
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": autocomplete}),
    )


# --- Authentification --------------------------------------------------

from utils.enums import UserRoleEnum


class UserRegisterForm(PasswordConfirmationMixin, forms.ModelForm):
    ROLE_CHOICES = [("", _("Sélectionnez votre rôle *"))] + list(UserRoleEnum.choices)

    role = forms.ChoiceField(
        label=_("Rôle professionnel"),
        choices=ROLE_CHOICES,
        required=True,
        error_messages={
            "required": _("Le choix d'un rôle est obligatoire."),
            "invalid_choice": _("Veuillez sélectionner un rôle valide."),
        },
    )
    password1 = _password_field(_("Mot de passe"), "new-password")
    password2 = _password_field(_("Confirmation du mot de passe"), "new-password")
    telephone = forms.CharField(max_length=20, required=False, validators=[validate_phone_number])

    class Meta:
        model = User
        fields = (
            "email",
            "first_name",
            "last_name",
            "telephone",
            "role",
            "avatar",
            "password1",
            "password2",
        )

    def clean_email(self) -> str:
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError(_("Un compte existe déjà avec cette adresse email."))
        return email

    def clean_first_name(self) -> str:
        return self.cleaned_data.get("first_name", "").strip()

    def clean_last_name(self) -> str:
        return self.cleaned_data.get("last_name", "").strip()

    def clean_telephone(self) -> str:
        telephone = self.cleaned_data.get("telephone", "").strip()
        if not telephone:
            return ""
        return normalize_phone_number(telephone)

    def clean_role(self) -> str:
        role = self.cleaned_data.get("role", "").strip()
        if not role:
            raise ValidationError(_("Le choix d'un rôle est obligatoire."))
        if role not in UserRoleEnum.values:
            raise ValidationError(_("Rôle sélectionné invalide."))
        return role

    def clean(self) -> dict[str, Any]:
        cleaned_data = super().clean()
        self.clean_passwords(cleaned_data)
        return cleaned_data

    def save(self, commit: bool = True) -> User:
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        user.set_password(self.cleaned_data["password1"])
        user.is_verified = False

        # Attribution du rôle obligatoire
        role = self.cleaned_data["role"]
        user.is_proprietaire = (role == UserRoleEnum.PROPRIETAIRE)
        user.is_personnel_medical = (role == UserRoleEnum.PERSONNEL_MEDICAL)
        user.is_responsable_pharmacie = (role == UserRoleEnum.RESPONSABLE_PHARMACIE)
        user.is_vendeur_pharmacie = (role == UserRoleEnum.VENDEUR_PHARMACIE)
        user.is_caissier = (role == UserRoleEnum.CAISSIER)
        user.is_agent_accueil = (role == UserRoleEnum.AGENT_ACCUEIL)

        if commit:
            user.save()
            if user.is_personnel_medical:
                MedicalProfile.objects.get_or_create(user=user)
        return user


class UserLoginForm(forms.Form):
    email = forms.EmailField(widget=forms.EmailInput(attrs={"autocomplete": "email"}))
    password = _password_field(_("Mot de passe"), "current-password")

    def __init__(self, *args: Any, request=None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.request = request
        self.user_cache: User | None = None
        self.inactive_user: User | None = None

    def clean(self) -> dict[str, Any]:
        """Même message pour email inconnu / mot de passe incorrect (anti-énumération) avec rate-limiting."""
        cleaned_data = super().clean()
        email, password = cleaned_data.get("email"), cleaned_data.get("password")
        if not email or not password:
            return cleaned_data

        email_clean = email.strip().lower()

        if self.request:
            from utils.rate_limit import check_login_rate_limit, record_failed_login

            is_locked, remaining = check_login_rate_limit(self.request, email=email_clean)
            if is_locked:
                minutes = max(1, (remaining + 59) // 60)
                raise ValidationError(
                    _(
                        "Trop de tentatives de connexion infructueuses. "
                        "Veuillez patienter %(minutes)d minute(s) avant de réessayer."
                    )
                    % {"minutes": minutes}
                )

        user_candidate = User.objects.filter(email__iexact=email_clean).first()
        if user_candidate and not user_candidate.is_active and user_candidate.check_password(password):
            self.inactive_user = user_candidate
            return cleaned_data

        self.user_cache = authenticate(self.request, email=email_clean, password=password)
        if self.user_cache is None or not self.user_cache.is_active:
            if self.request:
                from utils.rate_limit import record_failed_login

                record_failed_login(self.request, email=email_clean)
            raise ValidationError(_("Adresse email ou mot de passe incorrect."))
        return cleaned_data

    def get_user(self) -> User | None:
        return self.user_cache



# --- OTP -----------------------------------------------------------------

class OTPVerificationForm(forms.Form):
    code = forms.CharField(min_length=OTP_CODE_LENGTH, max_length=OTP_CODE_LENGTH)

    def clean_code(self) -> str:
        code = self.cleaned_data["code"]
        if not code.isdigit():
            raise ValidationError(_("Le code doit contenir uniquement des chiffres."))
        return code


# --- Mot de passe ----------------------------------------------------------

class ForgotPasswordForm(forms.Form):
    email = forms.EmailField()

    def clean_email(self) -> str:
        return self.cleaned_data["email"].strip().lower()


class SetNewPasswordForm(PasswordConfirmationMixin, forms.Form):
    """Formulaire de saisie du nouveau mot de passe (Étape 2 après vérification OTP)."""

    password1 = _password_field(_("Nouveau mot de passe"), "new-password")
    password2 = _password_field(_("Confirmation du mot de passe"), "new-password")

    def __init__(self, *args: Any, user=None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.user = user

    def clean(self) -> dict[str, Any]:
        cleaned_data = super().clean()
        self.clean_passwords(cleaned_data, user=self.user)
        return cleaned_data


class PasswordResetConfirmForm(PasswordConfirmationMixin, forms.Form):
    """Formulaire unifié de réinitialisation de mot de passe."""

    email = forms.EmailField(widget=forms.HiddenInput(), required=False)
    code = forms.CharField(
        min_length=OTP_CODE_LENGTH,
        max_length=OTP_CODE_LENGTH,
        required=False,
    )
    password1 = _password_field(_("Nouveau mot de passe"), "new-password")
    password2 = _password_field(_("Confirmation"), "new-password")

    def __init__(self, *args: Any, user=None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.user = user

    def clean_code(self) -> str:
        code = self.cleaned_data.get("code", "").strip()
        if code and not code.isdigit():
            raise ValidationError(_("Le code doit contenir uniquement des chiffres."))
        return code

    def clean(self) -> dict[str, Any]:
        cleaned_data = super().clean()
        self.clean_passwords(cleaned_data, user=self.user)
        return cleaned_data



class ChangePasswordForm(PasswordConfirmationMixin, forms.Form):
    password1_field = "new_password1"
    password2_field = "new_password2"

    current_password = _password_field(_("Mot de passe actuel"), "current-password")
    new_password1 = _password_field(_("Nouveau mot de passe"), "new-password")
    new_password2 = _password_field(_("Confirmation"), "new-password")

    def __init__(self, *args: Any, user=None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.user = user

    def clean_current_password(self) -> str:
        password = self.cleaned_data["current_password"]
        if self.user is None or not self.user.check_password(password):
            raise ValidationError(_("Le mot de passe actuel est incorrect."))
        return password

    def clean(self) -> dict[str, Any]:
        cleaned_data = super().clean()
        self.clean_passwords(cleaned_data, user=self.user)
        return cleaned_data


# --- Profil utilisateur / Admin -------------------------------------------------

class UserProfileUpdateForm(forms.ModelForm):
    """Formulaire de mise à jour du profil utilisateur (nom, prénom, téléphone, photo)."""

    class Meta:
        model = User
        fields = ("first_name", "last_name", "telephone", "avatar")
        widgets = {
            "first_name": forms.TextInput(attrs={"placeholder": _("Prénom")}),
            "last_name": forms.TextInput(attrs={"placeholder": _("Nom")}),
            "telephone": forms.TextInput(attrs={"placeholder": "+237 6XX XX XX XX"}),
            "avatar": forms.FileInput(attrs={"accept": "image/*"}),
        }

    def clean_telephone(self) -> str:
        telephone = self.cleaned_data.get("telephone", "").strip()
        if not telephone:
            return ""
        return normalize_phone_number(telephone)


class MedicalProfileForm(forms.ModelForm):
    class Meta:
        model = MedicalProfile
        fields = ("specialite", "numero_ordre")


class UserAdminCreationForm(BaseUserCreationForm):
    class Meta:
        model = User
        fields = (
            "email",
            "first_name",
            "last_name",
            "telephone",
            "avatar",
            "is_proprietaire",
            "is_personnel_medical",
            "is_responsable_pharmacie",
            "is_vendeur_pharmacie",
            "is_caissier",
            "is_agent_accueil",
        )


class UserAdminChangeForm(BaseUserChangeForm):
    class Meta:
        model = User
        fields = "__all__"