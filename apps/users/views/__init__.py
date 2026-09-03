"""Vues du module utilisateurs SantéGeste."""

from apps.users.views.auth import (
    OTPResendView,
    OTPVerificationView,
    UserLoginView,
    UserLogoutView,
    UserRegisterView,
)
from apps.users.views.password import (
    ChangePasswordView,
    ForgotPasswordView,
    PasswordResetConfirmView,
    PasswordResetOTPVerifyView,
)
from apps.users.views.profile import (
    MedicalProfileUpdateView,
    UserProfileDetailView,
    UserProfileUpdateView,
)

__all__ = [
    "ChangePasswordView",
    "ForgotPasswordView",
    "MedicalProfileForm",
    "MedicalProfileUpdateView",
    "OTPResendView",
    "OTPVerificationView",
    "PasswordResetConfirmView",
    "PasswordResetOTPVerifyView",
    "UserLoginView",
    "UserLogoutView",
    "UserProfileDetailView",
    "UserProfileUpdateView",
    "UserRegisterView",
]
