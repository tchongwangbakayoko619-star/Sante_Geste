"""Formulaires du module d'utilisateurs SantéGeste."""

from apps.users.forms.auth import (
    ChangePasswordForm,
    ForgotPasswordForm,
    MedicalProfileForm,
    OTPVerificationForm,
    PasswordResetConfirmForm,
    SetNewPasswordForm,
    UserAdminChangeForm,
    UserAdminCreationForm,
    UserLoginForm,
    UserProfileUpdateForm,
    UserRegisterForm,
)
from apps.users.forms.mixins import PasswordConfirmationMixin

__all__ = [
    "ChangePasswordForm",
    "ForgotPasswordForm",
    "MedicalProfileForm",
    "OTPVerificationForm",
    "PasswordResetConfirmForm",
    "SetNewPasswordForm",
    "UserAdminChangeForm",
    "UserAdminCreationForm",
    "UserLoginForm",
    "UserProfileUpdateForm",
    "UserRegisterForm",
    "PasswordConfirmationMixin",
]
