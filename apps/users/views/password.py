"""Vues de gestion et réinitialisation de mot de passe pour l'application users."""

from __future__ import annotations

from typing import Any

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse, HttpResponseRedirect
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import FormView

from apps.users.forms import (
    ChangePasswordForm,
    ForgotPasswordForm,
    OTPVerificationForm,
    SetNewPasswordForm,
)
from apps.users.mixins import AnonymousRequiredMixin
from apps.users.services import (
    OtpCooldownError,
    PasswordResetError,
    confirm_password_reset,
    request_password_reset,
    verify_password_reset_otp,
)
from utils.enums import OTPPurposeEnum
from utils.otp import OtpTokenError, OtpTokenExpiredError


class ForgotPasswordView(AnonymousRequiredMixin, FormView):
    """Vue de demande d'oubli de mot de passe (anti-énumération)."""

    template_name = "users/forgot_password.html"
    form_class = ForgotPasswordForm
    success_url = reverse_lazy("users:password-reset-verify-otp")

    def form_valid(self, form: ForgotPasswordForm) -> HttpResponse:
        email = form.cleaned_data["email"]

        try:
            _, _, signed_token = request_password_reset(email)

            if signed_token:
                self.request.session["reset_signed_token"] = signed_token
                self.request.session["reset_email"] = email

            messages.info(
                self.request,
                _(
                    "Si un compte actif correspond à cet email, un code de réinitialisation vous a été envoyé par e-mail."
                ),
            )
        except OtpCooldownError as err:
            messages.warning(self.request, str(err))
            return HttpResponseRedirect(self.success_url)

        return super().form_valid(form)


class PasswordResetOTPVerifyView(AnonymousRequiredMixin, FormView):
    """Étape 1 : Saisie et validation du code OTP pour la réinitialisation de mot de passe."""

    template_name = "users/password_reset_otp_verify.html"
    form_class = OTPVerificationForm
    success_url = reverse_lazy("users:password-reset-confirm")

    def dispatch(self, request: Any, *args: Any, **kwargs: Any) -> HttpResponse:
        token = request.GET.get("token")
        if token:
            request.session["reset_signed_token"] = token

        if not request.session.get("reset_signed_token"):
            messages.info(
                request,
                _(
                    "Veuillez d'abord demander la réinitialisation de votre mot de passe."
                ),
            )
            return HttpResponseRedirect(reverse_lazy("users:forgot-password"))
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form: OTPVerificationForm) -> HttpResponse:
        signed_token = self.request.session.get("reset_signed_token", "")
        email = self.request.session.get("reset_email", "")
        code = form.cleaned_data["code"]

        is_valid = False
        if signed_token:
            try:
                is_valid = verify_password_reset_otp(signed_token, code)
            except (OtpTokenError, OtpTokenExpiredError, ValueError):
                is_valid = False

        if not is_valid and email:
            from apps.users.models import OTP, User
            from apps.users.services import verify_otp_by_user
            from utils.otp import create_otp_token

            user_obj = User.objects.filter(email__iexact=email).first()
            if user_obj and verify_otp_by_user(
                user_obj, code, OTPPurposeEnum.PASSWORD_RESET
            ):
                is_valid = True
                latest_otp = (
                    OTP.objects.filter(
                        user=user_obj,
                        purpose=OTPPurposeEnum.PASSWORD_RESET,
                        is_used=True,
                    )
                    .order_by("-updated_at")
                    .first()
                )
                if latest_otp:
                    signed_token = create_otp_token(
                        latest_otp.id, user_obj.id, OTPPurposeEnum.PASSWORD_RESET
                    )
                    self.request.session["reset_signed_token"] = signed_token

        if is_valid:
            from utils.otp import create_password_reset_ticket, validate_otp_token

            ticket = ""
            if signed_token:
                try:
                    payload = validate_otp_token(
                        signed_token, OTPPurposeEnum.PASSWORD_RESET
                    )
                    ticket = create_password_reset_ticket(
                        payload["otp_id"], payload["user_id"]
                    )
                except (OtpTokenError, ValueError):
                    pass

            if ticket:
                self.request.session["reset_auth_ticket"] = ticket
            self.request.session["reset_otp_verified"] = True
            messages.success(
                self.request,
                _(
                    "Code OTP vérifié avec succès ! Veuillez saisir votre nouveau mot de passe."
                ),
            )
            return HttpResponseRedirect(reverse_lazy("users:password-reset-confirm"))

        form.add_error("code", _("Le code saisi est invalide ou a expiré."))
        return self.form_invalid(form)


class PasswordResetConfirmView(AnonymousRequiredMixin, FormView):
    """Étape 2 : Saisie du nouveau mot de passe uniquement après validation de l'OTP."""

    template_name = "users/password_reset_confirm.html"
    form_class = SetNewPasswordForm
    fallback_url = "users:login"
    success_url = reverse_lazy("users:login")

    def dispatch(self, request: Any, *args: Any, **kwargs: Any) -> HttpResponse:
        if not request.session.get("reset_otp_verified"):
            messages.info(
                request,
                _("Veuillez d'abord valider votre code OTP de réinitialisation."),
            )
            if request.session.get("reset_signed_token"):
                return HttpResponseRedirect(
                    reverse_lazy("users:password-reset-verify-otp")
                )
            return HttpResponseRedirect(reverse_lazy("users:forgot-password"))
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form: SetNewPasswordForm) -> HttpResponse:
        signed_token = self.request.session.get("reset_signed_token", "")
        reset_ticket = self.request.session.get("reset_auth_ticket", "")
        new_password = form.cleaned_data["password1"]

        try:
            confirm_password_reset(
                signed_token,
                None,
                new_password,
                reset_ticket=reset_ticket,
            )
        except PasswordResetError as err:
            form.add_error(None, str(err))
            return self.form_invalid(form)

        self.request.session.pop("reset_signed_token", None)
        self.request.session.pop("reset_email", None)
        self.request.session.pop("reset_auth_ticket", None)
        self.request.session.pop("reset_otp_verified", None)

        messages.success(
            self.request,
            _(
                "Votre mot de passe a été réinitialisé avec succès. Vous pouvez vous connecter."
            ),
        )
        return super().form_valid(form)


class ChangePasswordView(LoginRequiredMixin, FormView):
    """Vue de modification du mot de passe pour utilisateur connecté."""

    template_name = "users/change_password.html"
    form_class = ChangePasswordForm
    success_url = reverse_lazy("users:profile")

    def get_form_kwargs(self) -> dict[str, Any]:
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form: ChangePasswordForm) -> HttpResponse:
        from django.contrib.auth import update_session_auth_hash

        new_password = form.cleaned_data["new_password1"]
        user = self.request.user
        user.set_password(new_password)
        user.save(update_fields=["password", "updated_at"])

        update_session_auth_hash(self.request, user)

        messages.success(
            self.request, _("Votre mot de passe a été modifié avec succès.")
        )
        return super().form_valid(form)
