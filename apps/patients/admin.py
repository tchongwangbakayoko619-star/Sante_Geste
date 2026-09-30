"""Administration Django pour les modèles du module patients."""

from django.contrib import admin

from apps.patients.models import Allergen
from apps.patients.models import Appointment
from apps.patients.models import Patient
from apps.patients.models import PatientAllergy


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = [
        "patient_number",
        "last_name",
        "first_name",
        "phone_number",
        "gender",
        "blood_group",
        "status",
        "is_active",
        "created_at",
    ]
    search_fields = [
        "patient_number",
        "last_name",
        "first_name",
        "phone_number",
        "email",
    ]
    list_filter = ["status", "gender", "blood_group", "created_at"]
    readonly_fields = [
        "id",
        "patient_number",
        "created_at",
        "updated_at",
        "deleted_at",
        "created_by",
        "updated_by",
    ]


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = [
        "patient",
        "doctor",
        "scheduled_at",
        "status",
        "estimated_duration_minutes",
        "reason",
    ]
    search_fields = [
        "patient__last_name",
        "patient__first_name",
        "patient__patient_number",
        "doctor__last_name",
        "doctor__first_name",
        "reason",
    ]
    list_filter = ["status", "scheduled_at", "doctor"]
    readonly_fields = [
        "id",
        "created_at",
        "updated_at",
        "deleted_at",
        "created_by",
        "updated_by",
    ]


@admin.register(Allergen)
class AllergenAdmin(admin.ModelAdmin):
    list_display = ["name", "category", "atc_code", "cross_reactivity_group", "created_at"]
    search_fields = ["name", "atc_code", "cross_reactivity_group", "description"]
    list_filter = ["category", "created_at"]
    readonly_fields = ["id", "created_at", "updated_at", "created_by", "updated_by"]


@admin.register(PatientAllergy)
class PatientAllergyAdmin(admin.ModelAdmin):
    list_display = ["patient", "allergen", "criticality", "verification_status", "reaction", "diagnosed_date"]
    search_fields = ["patient__last_name", "patient__first_name", "allergen__name", "reaction"]
    list_filter = ["criticality", "verification_status", "allergen__category"]
    readonly_fields = ["id", "created_at", "updated_at", "created_by", "updated_by"]


