"""Module des formulaires de l'application users."""

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
    "PasswordConfirmationMixin",
    "PasswordResetConfirmForm",
    "SetNewPasswordForm",
    "UserAdminChangeForm",
    "UserAdminCreationForm",
    "UserLoginForm",
    "UserProfileUpdateForm",
    "UserRegisterForm",
]


