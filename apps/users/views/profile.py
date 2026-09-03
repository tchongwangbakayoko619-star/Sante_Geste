"""Vues d'affichage et de mise à jour des profils utilisateur et médical."""

from __future__ import annotations

from typing import Any

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import FormView, TemplateView

from apps.users.forms import MedicalProfileForm, UserProfileUpdateForm
from apps.users.mixins import PersonnelMedicalRequiredMixin
from apps.users.services import update_medical_profile, update_user_profile


class UserProfileDetailView(LoginRequiredMixin, TemplateView):
    """Vue d'affichage du profil utilisateur et médical."""

    template_name = "users/profile_detail.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["user"] = self.request.user
        context["medical_profile"] = getattr(self.request.user, "medical_profile", None)
        return context


class UserProfileUpdateView(LoginRequiredMixin, FormView):
    """Vue d'édition des informations du profil utilisateur (nom, prénom, téléphone, photo)."""

    template_name = "users/profile_edit.html"
    form_class = UserProfileUpdateForm
    success_url = reverse_lazy("users:profile")

    def get_initial(self) -> dict[str, Any]:
        user = self.request.user
        return {
            "first_name": user.first_name,
            "last_name": user.last_name,
            "telephone": user.telephone,
            "avatar": user.avatar,
        }

    def form_valid(self, form: UserProfileUpdateForm) -> HttpResponse:
        cleaned_data = form.cleaned_data
        update_user_profile(
            user=self.request.user,
            first_name=cleaned_data.get("first_name"),
            last_name=cleaned_data.get("last_name"),
            telephone=cleaned_data.get("telephone"),
            avatar=cleaned_data.get("avatar"),
        )
        messages.success(self.request, _("Profil mis à jour avec succès."))
        return super().form_valid(form)


class MedicalProfileUpdateView(PersonnelMedicalRequiredMixin, FormView):
    """Vue d'édition du profil médical pour le personnel médical."""

    template_name = "users/medical_profile_edit.html"
    form_class = MedicalProfileForm
    success_url = reverse_lazy("users:profile")

    def get_initial(self) -> dict[str, Any]:
        medical_profile = getattr(self.request.user, "medical_profile", None)
        if medical_profile:
            return {
                "specialite": medical_profile.specialite,
                "numero_ordre": medical_profile.numero_ordre,
            }
        return {}

    def form_valid(self, form: MedicalProfileForm) -> HttpResponse:
        cleaned_data = form.cleaned_data
        update_medical_profile(
            user=self.request.user,
            specialite=cleaned_data.get("specialite"),
            numero_ordre=cleaned_data.get("numero_ordre"),
        )
        messages.success(self.request, _("Profil médical mis à jour avec succès."))
        return super().form_valid(form)
