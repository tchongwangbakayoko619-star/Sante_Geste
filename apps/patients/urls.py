"""Configuration des routes URL pour le module patients et rendez-vous."""

from django.urls import path

from apps.patients.views import AppointmentCreateView
from apps.patients.views import AppointmentListView
from apps.patients.views import AppointmentStatusUpdateView
from apps.patients.views import PatientCreateView
from apps.patients.views import PatientDetailView
from apps.patients.views import PatientListView
from apps.patients.views import PatientUpdateView

app_name = "patients"

urlpatterns = [
    # Gestion des patients
    path("", PatientListView.as_view(), name="patient_list"),
    path("nouveau/", PatientCreateView.as_view(), name="patient_create"),
    path("<uuid:pk>/", PatientDetailView.as_view(), name="patient_detail"),
    path("<uuid:pk>/modifier/", PatientUpdateView.as_view(), name="patient_update"),

    # Rendez-vous et agenda médical
    path("rendez-vous/", AppointmentListView.as_view(), name="appointment_list"),
    path("rendez-vous/planifier/", AppointmentCreateView.as_view(), name="appointment_create"),
    path("rendez-vous/<uuid:pk>/statut/", AppointmentStatusUpdateView.as_view(), name="appointment_status_update"),
]
