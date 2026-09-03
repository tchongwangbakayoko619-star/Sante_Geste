"""Routage des URL (URLconf) pour l'application users de SantéGeste."""

from django.urls import path

from apps.users.views import (
    ChangePasswordView,
    ForgotPasswordView,
    MedicalProfileUpdateView,
    OTPResendView,
    OTPVerificationView,
    PasswordResetConfirmView,
    PasswordResetOTPVerifyView,
    UserLoginView,
    UserLogoutView,
    UserProfileDetailView,
    UserProfileUpdateView,
    UserRegisterView,
)

app_name = "users"

urlpatterns = [
    path("register/", UserRegisterView.as_view(), name="register"),
    path("login/", UserLoginView.as_view(), name="login"),
    path("logout/", UserLogoutView.as_view(), name="logout"),
    path("verify-otp/", OTPVerificationView.as_view(), name="otp-verify"),
    path("resend-otp/", OTPResendView.as_view(), name="otp-resend"),

    path("forgot-password/", ForgotPasswordView.as_view(), name="forgot-password"),
    path(
        "reset-password/verify-otp/",
        PasswordResetOTPVerifyView.as_view(),
        name="password-reset-verify-otp",
    ),
    path(
        "reset-password/confirm/",
        PasswordResetConfirmView.as_view(),
        name="password-reset-confirm",
    ),

    path("change-password/", ChangePasswordView.as_view(), name="change-password"),
    path("profile/", UserProfileDetailView.as_view(), name="profile"),
    path("profile/edit/", UserProfileUpdateView.as_view(), name="profile-edit"),
    path(
        "profile/medical/edit/",
        MedicalProfileUpdateView.as_view(),
        name="medical-profile-edit",
    ),
]
