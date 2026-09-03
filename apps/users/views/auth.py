"""Vues d'authentification (Connexion, Inscription, Déconnexion, OTP) pour l'application users."""

from __future__ import annotations

from typing import Any

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import FormView, View

from apps.users.forms import OTPVerificationForm, UserLoginForm, UserRegisterForm
from apps.users.mixins import AnonymousRequiredMixin, RedirectToNextOrReferrerMixin
from apps.users.services import OtpCooldownError, register_user, verify_otp_by_token
from utils.enums import OTPPurposeEnum



class UserRegisterView(AnonymousRequiredMixin, FormView):
    """Vue d'inscription d'un nouvel utilisateur SantéGeste."""

    template_name = "users/register.html"
    form_class = UserRegisterForm
    success_url = reverse_lazy("users:otp-verify")

    def form_valid(self, form: UserRegisterForm) -> HttpResponse:
        cleaned_data = form.cleaned_data
        try:
            user, raw_code, signed_token = register_user(
                email=cleaned_data["email"],
                password=cleaned_data["password1"],
                first_name=cleaned_data.get("first_name", ""),
                last_name=cleaned_data.get("last_name", ""),
                telephone=cleaned_data.get("telephone", ""),
                avatar=cleaned_data.get("avatar"),
            )
        except OtpCooldownError as err:
            messages.warning(self.request, str(err))
            return self.form_invalid(form)

        # Stocker le jeton signé d'OTP en session pour la deuxième étape de vérification
        self.request.session["otp_signed_token"] = signed_token
        self.request.session["otp_user_id"] = str(user.id)

        messages.success(
            self.request,
            _("Votre compte a été créé avec succès. Veuillez saisir le code OTP reçu pour le valider."),
        )
        return super().form_valid(form)


class UserLoginView(AnonymousRequiredMixin, RedirectToNextOrReferrerMixin, FormView):
    """Vue de connexion utilisateur avec redirection intelligente."""

    template_name = "users/login.html"
    form_class = UserLoginForm

    def form_valid(self, form: UserLoginForm) -> HttpResponse:
        if getattr(form, "inactive_user", None):
            user = form.inactive_user
            from apps.users.services import OtpCooldownError, request_otp
            from utils.enums import OTPPurposeEnum

            try:
                otp_obj, raw_code, signed_token = request_otp(user, OTPPurposeEnum.REGISTRATION)
                self.request.session["otp_signed_token"] = signed_token
                self.request.session["otp_user_id"] = str(user.id)
                messages.info(
                    self.request,
                    _("Votre compte n'est pas encore activé. Un nouveau code de vérification OTP a été envoyé par e-mail.")
                )
            except OtpCooldownError:
                messages.warning(
                    self.request,
                    _("Votre compte n'est pas encore activé. Veuillez saisir le code OTP déjà reçu.")
                )
            return HttpResponseRedirect(reverse_lazy("users:otp-verify"))

        user = form.get_user()
        if user is not None:
            login(self.request, user)
            messages.info(self.request, _("Bienvenue sur SantéGeste, %(name)s !") % {"name": user.full_name or user.email})
            redirect_url = self.get_redirect_url()
            return HttpResponseRedirect(redirect_url)
        return self.form_invalid(form)




class UserLogoutView(LoginRequiredMixin, View):
    """Vue de déconnexion sécurisée (POST uniquement)."""

    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        logout(request)
        messages.info(request, _("Vous avez été déconnecté avec succès."))
        return HttpResponseRedirect(reverse_lazy("home"))


class OTPVerificationView(FormView):
    """Vue de validation du code OTP soumis par l'utilisateur."""

    template_name = "users/otp_verify.html"
    form_class = OTPVerificationForm
    success_url = reverse_lazy("users:login")

    def dispatch(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        token = request.GET.get("token")
        if token:
            request.session["otp_signed_token"] = token

        if "otp_signed_token" not in request.session and "otp_user_id" not in request.session:
            messages.info(request, _("Veuillez vous connecter pour procéder à la vérification de votre compte."))
            return HttpResponseRedirect(reverse_lazy("users:login"))
        return super().dispatch(request, *args, **kwargs)


    def form_valid(self, form: OTPVerificationForm) -> HttpResponse:
        from apps.users.services import confirm_registration_otp

        signed_token = self.request.session.get("otp_signed_token", "")
        user_id = self.request.session.get("otp_user_id", "")
        code = form.cleaned_data["code"]

        is_valid, user_obj = confirm_registration_otp(signed_token, user_id, code)

        if is_valid:
            # Nettoyage des données temporaires de session
            self.request.session.pop("otp_signed_token", None)
            self.request.session.pop("otp_user_id", None)
            messages.success(
                self.request,
                _("Compte vérifié et activé avec succès ! Vous pouvez maintenant vous connecter."),
            )
            return super().form_valid(form)

        form.add_error("code", _("Le code saisi est invalide ou a expiré."))
        return self.form_invalid(form)


class OTPResendView(View):
    """Vue de renvoi d'un nouveau code OTP avec vérification du délai d'attente (cooldown, POST uniquement)."""

    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        user_id = request.session.get("otp_user_id")
        if not user_id:
            messages.error(request, _("Session expirée. Veuillez vous réinscrire."))
            return HttpResponseRedirect(reverse_lazy("users:register"))

        from apps.users.models import User
        from apps.users.services import OtpCooldownError, request_otp

        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            messages.error(request, _("Utilisateur introuvable."))
            return HttpResponseRedirect(reverse_lazy("users:register"))

        purpose = OTPPurposeEnum.REGISTRATION
        try:
            otp_obj, raw_code, signed_token = request_otp(user, purpose)
            request.session["otp_signed_token"] = signed_token
            messages.success(request, _("Un nouveau code OTP vous a été envoyé."))
        except OtpCooldownError as err:
            messages.warning(request, str(err))

        return HttpResponseRedirect(reverse_lazy("users:otp-verify"))



