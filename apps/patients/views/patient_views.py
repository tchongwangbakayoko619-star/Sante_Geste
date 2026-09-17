"""Vues de gestion des dossiers patients (liste, détail 360°, création, édition)."""

from __future__ import annotations

from typing import Any

from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import QuerySet
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.generic import DetailView
from django.views.generic import ListView
from django.views.generic.edit import CreateView
from django.views.generic.edit import UpdateView

from apps.patients.forms import PatientAllergyForm
from apps.patients.forms import PatientForm
from apps.patients.forms import PatientMedicalUpdateForm
from apps.patients.forms import PatientSearchForm
from apps.patients.models import Allergen
from apps.patients.models import Patient
from apps.patients.models import PatientAllergy
from apps.patients.services import add_patient_allergy
from apps.patients.services import create_patient
from apps.patients.services import remove_patient_allergy
from apps.patients.services import search_patients
from apps.patients.services import update_patient
from apps.patients.services import update_patient_medical_record
from apps.users.mixins import AgentAccueilRequiredMixin
from apps.users.mixins import PatientManagementRequiredMixin
from apps.users.mixins import PersonnelMedicalRequiredMixin
from utils.enums import PatientStatusEnum


class PatientListView(PatientManagementRequiredMixin, ListView):
    """Liste paginée des patients avec recherche instantanée et indicateurs clés."""

    model = Patient
    template_name = "patients/patient_list.html"
    context_object_name = "patients"
    paginate_by = 15

    def get_queryset(self) -> QuerySet[Patient]:
        query = self.request.GET.get("q", "").strip()
        if query:
            return search_patients(query, active_only=False).order_by("-created_at")
        return Patient.objects.all().order_by("-created_at")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        query = self.request.GET.get("q", "").strip()
        context["search_form"] = PatientSearchForm(initial={"q": query})
        context["query"] = query

        # Métriques clés d'accueil
        now = timezone.now()
        thirty_days_ago = now - timezone.timedelta(days=30)
        context["total_patients"] = Patient.objects.count()
        context["active_patients"] = Patient.objects.filter(status=PatientStatusEnum.ACTIVE).count()
        context["new_this_month"] = Patient.objects.filter(created_at__gte=thirty_days_ago).count()
        return context

    def render_to_response(self, context: dict[str, Any], **response_kwargs: Any):
        # Support pour la recherche en temps réel via AJAX / JSON
        if self.request.headers.get("x-requested-with") == "XMLHttpRequest" or self.request.GET.get("format") == "json":
            patients_data = [
                {
                    "id": str(p.id),
                    "patient_number": p.patient_number,
                    "full_name": p.full_name,
                    "age": p.age,
                    "gender": p.get_gender_display(),
                    "status": p.status,
                    "status_display": p.get_status_display(),
                    "blood_group": p.blood_group,
                    "phone_number": p.phone_number,
                    "url": p.get_absolute_url(),
                    "has_critical_alerts": p.has_critical_alerts,
                }
                for p in context["patients"]
            ]
            return JsonResponse({"results": patients_data, "count": len(patients_data)})
        return super().render_to_response(context, **response_kwargs)


class PatientDetailView(PatientManagementRequiredMixin, DetailView):
    """Fiche détaillée 360° du patient avec historique, timeline et contrôle de confidentialité."""

    model = Patient
    template_name = "patients/patient_detail.html"
    context_object_name = "patient"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        user = self.request.user

        # Règle de confidentialité médicale : seuls les praticiens / personnel médical ou superusers voient les détails cliniques confidentiels
        can_view_medical_info = bool(
            getattr(user, "is_personnel_medical", False)
            or getattr(user, "is_superuser", False)
        )
        context["can_view_medical_info"] = can_view_medical_info

        # Rendez-vous du patient ordonnés du plus récent au plus ancien (optimisé select_related pour éviter N+1 queries)
        context["appointments"] = (
            self.object.appointments
            .select_related("doctor")
            .order_by("-scheduled_at")
        )
        context["upcoming_appointments"] = (
            self.object.appointments
            .select_related("doctor")
            .filter(scheduled_at__gte=timezone.now())
            .order_by("scheduled_at")
        )

        # Allergies codifiées avec détails pharmacologiques
        context["patient_allergies"] = (
            self.object.patient_allergies
            .select_related("allergen")
            .order_by("-criticality", "allergen__name")
        )

        return context


class PatientCreateView(AgentAccueilRequiredMixin, SuccessMessageMixin, CreateView):
    """Enregistrement d'un nouveau dossier patient (réservé exclusivement à l'agent d'accueil)."""

    model = Patient
    form_class = PatientForm
    template_name = "patients/patient_form.html"

    def form_valid(self, form: PatientForm):
        patient = create_patient(
            data=form.cleaned_data,
            created_by=self.request.user,
        )
        self.object = patient
        messages.success(
            self.request,
            _("Le dossier patient %(number)s (%(name)s) a été créé avec succès.")
            % {"number": patient.patient_number, "name": patient.full_name},
        )
        return redirect(patient.get_absolute_url())

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["title"] = _("Nouveau dossier patient")
        context["action_text"] = _("Enregistrer le patient")
        return context


class PatientUpdateView(AgentAccueilRequiredMixin, SuccessMessageMixin, UpdateView):
    """Mise à jour des informations administratives du dossier patient (réservé à l'agent d'accueil)."""

    model = Patient
    form_class = PatientForm
    template_name = "patients/patient_form.html"

    def form_valid(self, form: PatientForm):
        patient = update_patient(
            patient=self.get_object(),
            data=form.cleaned_data,
            updated_by=self.request.user,
        )
        self.object = patient
        messages.success(
            self.request,
            _("Le dossier de %(name)s (%(number)s) a été mis à jour.")
            % {"name": patient.full_name, "number": patient.patient_number},
        )
        return redirect(patient.get_absolute_url())

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["title"] = _("Modifier le dossier de %(name)s") % {"name": self.object.full_name}
        context["action_text"] = _("Enregistrer les modifications")
        context["is_update"] = True
        return context


class PatientMedicalUpdateView(PersonnelMedicalRequiredMixin, SuccessMessageMixin, UpdateView):
    """Mise à jour des informations médicales et facteurs de risque (réservé au personnel soignant)."""

    model = Patient
    form_class = PatientMedicalUpdateForm
    template_name = "patients/patient_medical_form.html"

    def form_valid(self, form: PatientMedicalUpdateForm):
        patient = update_patient_medical_record(
            patient=self.get_object(),
            data=form.cleaned_data,
            updated_by=self.request.user,
        )
        self.object = patient
        messages.success(
            self.request,
            _("Le profil médical de %(name)s (%(number)s) a été mis à jour avec succès.")
            % {"name": patient.full_name, "number": patient.patient_number},
        )
        return redirect(patient.get_absolute_url())

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["title"] = _("Mise à jour du profil médical : %(name)s") % {"name": self.object.full_name}
        context["patient"] = self.object
        context["patient_allergies"] = (
            self.object.patient_allergies
            .select_related("allergen")
            .order_by("-criticality", "allergen__name")
        )
        context["allergy_form"] = PatientAllergyForm()
        return context


class PatientAllergyCreateView(PersonnelMedicalRequiredMixin, View):
    """Ajout d'une allergie codifiée au dossier patient via le service métier."""

    def post(self, request, pk, *args, **kwargs):
        patient = get_object_or_404(Patient, pk=pk)
        form = PatientAllergyForm(request.POST)
        if form.is_valid():
            cleaned = form.cleaned_data
            allergy = add_patient_allergy(
                patient=patient,
                allergen=cleaned["allergen"],
                criticality=cleaned["criticality"],
                verification_status=cleaned["verification_status"],
                reaction=cleaned.get("reaction", ""),
                diagnosed_date=cleaned.get("diagnosed_date"),
                notes=cleaned.get("notes", ""),
                created_by=request.user,
            )
            messages.success(
                request,
                _("L'allergie codifiée '%(allergen)s' a été ajoutée avec succès.")
                % {"allergen": allergy.allergen.name},
            )
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")

        next_url = request.POST.get("next") or reverse("patients:patient_medical_update", kwargs={"pk": patient.pk})
        return redirect(next_url)


class PatientAllergyDeleteView(PersonnelMedicalRequiredMixin, View):
    """Retrait d'une allergie codifiée du dossier patient via le service métier."""

    def post(self, request, pk, allergy_id, *args, **kwargs):
        patient = get_object_or_404(Patient, pk=pk)
        allergy = get_object_or_404(PatientAllergy, pk=allergy_id, patient=patient)
        allergen_name = allergy.allergen.name
        remove_patient_allergy(patient=patient, allergy_id=allergy_id)
        messages.success(
            request,
            _("L'allergie codifiée '%(allergen)s' a été supprimée du dossier.")
            % {"allergen": allergen_name},
        )
        next_url = request.POST.get("next") or reverse("patients:patient_medical_update", kwargs={"pk": patient.pk})
        return redirect(next_url)



