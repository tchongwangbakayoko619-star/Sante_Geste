"""Administration Django pour les modèles du module patients."""

from django.contrib import admin

from apps.patients.models import Appointment
from apps.patients.models import Patient


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = [
        "patient_number",
        "last_name",
        "first_name",
        "phone_number",
        "gender",
        "blood_group",
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
    list_filter = ["is_active", "gender", "blood_group", "created_at"]
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
