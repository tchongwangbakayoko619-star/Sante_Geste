"""Configuration des routes URL pour le module patients et rendez-vous."""

from django.urls import path

from apps.patients.views import AppointmentCancelView
from apps.patients.views import AppointmentCreateView
from apps.patients.views import AppointmentListView
from apps.patients.views import AppointmentStatusUpdateView
from apps.patients.views import CaissePendingListView
from apps.patients.views import ConsultationCreateView
from apps.patients.views import ConsultationDetailView
from apps.patients.views import ConsultationListView
from apps.patients.views import ConsultationUpdateView
from apps.patients.views import DoctorAppointmentListView
from apps.patients.views import FactureCancelView
from apps.patients.views import FactureCreateView
from apps.patients.views import FactureDetailView
from apps.patients.views import FactureListView
from apps.patients.views import FacturePrintView
from apps.patients.views import FactureUpdateView
from apps.patients.views import OrdonnanceCreateView
from apps.patients.views import OrdonnanceDetailPrintView
from apps.patients.views import OrdonnanceUpdateView
from apps.patients.views import PaiementCreateView
from apps.patients.views import PaiementReceiptView
from apps.patients.views import PatientAllergyCreateView
from apps.patients.views import PatientAllergyDeleteView
from apps.patients.views import PatientCreateView
from apps.patients.views import PatientDetailView
from apps.patients.views import PatientListView
from apps.patients.views import PatientMedicalUpdateView
from apps.patients.views import PatientUpdateView
from apps.patients.views import PharmacyOrdonnanceDispenseView
from apps.patients.views import PharmacyOrdonnanceListView
from apps.patients.views import PrestationRealiseeCreateView
from apps.patients.views import PrestationRealiseeDeleteView

app_name = "patients"

urlpatterns = [
    # Gestion des patients
    path("", PatientListView.as_view(), name="patient_list"),
    path("nouveau/", PatientCreateView.as_view(), name="patient_create"),
    path("<uuid:pk>/", PatientDetailView.as_view(), name="patient_detail"),
    path("<uuid:pk>/modifier/", PatientUpdateView.as_view(), name="patient_update"),
    path("<uuid:pk>/medical/", PatientMedicalUpdateView.as_view(), name="patient_medical_update"),
    path("<uuid:pk>/allergies/ajouter/", PatientAllergyCreateView.as_view(), name="patient_allergy_create"),
    path("<uuid:pk>/allergies/<uuid:allergy_id>/supprimer/", PatientAllergyDeleteView.as_view(), name="patient_allergy_delete"),

    # Rendez-vous et agenda médical
    path("rendez-vous/", AppointmentListView.as_view(), name="appointment_list"),
    path("mes-rendez-vous/", DoctorAppointmentListView.as_view(), name="my_appointments"),
    path("rendez-vous/planifier/", AppointmentCreateView.as_view(), name="appointment_create"),
    path("rendez-vous/<uuid:pk>/statut/", AppointmentStatusUpdateView.as_view(), name="appointment_status_update"),
    path("rendez-vous/<uuid:pk>/annuler/", AppointmentCancelView.as_view(), name="appointment_cancel"),

    # Consultations Médicales & Prescriptions
    path("consultations/", ConsultationListView.as_view(), name="consultation_list"),
    path("consultations/nouvelle/", ConsultationCreateView.as_view(), name="consultation_create"),
    path("consultations/<uuid:pk>/", ConsultationDetailView.as_view(), name="consultation_detail"),
    path("consultations/<uuid:pk>/modifier/", ConsultationUpdateView.as_view(), name="consultation_update"),
    path("consultations/<uuid:pk>/prestation/ajouter/", PrestationRealiseeCreateView.as_view(), name="prestation_realisee_create"),
    path("consultations/<uuid:pk>/prestation/<uuid:prestation_id>/supprimer/", PrestationRealiseeDeleteView.as_view(), name="prestation_realisee_delete"),
    path("consultations/<uuid:pk>/ordonnance/creer/", OrdonnanceCreateView.as_view(), name="ordonnance_create"),
    path("ordonnances/<uuid:pk>/modifier/", OrdonnanceUpdateView.as_view(), name="ordonnance_update"),
    path("ordonnances/<uuid:pk>/imprimer/", OrdonnanceDetailPrintView.as_view(), name="ordonnance_print"),

    # Module Caisse & Facturation
    path("caisse/en-attente/", CaissePendingListView.as_view(), name="caisse_pending_list"),
    path("caisse/factures/", FactureListView.as_view(), name="facture_list"),
    path("caisse/facturer/<uuid:patient_id>/", FactureCreateView.as_view(), name="facture_create"),
    path("caisse/factures/<uuid:pk>/", FactureDetailView.as_view(), name="facture_detail"),
    path("caisse/factures/<uuid:pk>/modifier/", FactureUpdateView.as_view(), name="facture_update"),
    path("caisse/factures/<uuid:pk>/annuler/", FactureCancelView.as_view(), name="facture_cancel"),
    path("caisse/factures/<uuid:pk>/imprimer/", FacturePrintView.as_view(), name="facture_print"),
    path("caisse/factures/<uuid:pk>/payer/", PaiementCreateView.as_view(), name="paiement_create"),
    path("caisse/paiements/<uuid:pk>/recu/", PaiementReceiptView.as_view(), name="paiement_receipt"),

    # Module Pharmacie & Délivrance
    path("pharmacie/ordonnances/", PharmacyOrdonnanceListView.as_view(), name="pharmacy_ordonnance_list"),
    path("pharmacie/ordonnances/<uuid:pk>/delivrer/", PharmacyOrdonnanceDispenseView.as_view(), name="pharmacy_ordonnance_dispense"),
]


