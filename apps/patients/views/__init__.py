"""Vues pour la gestion des patients, des rendez-vous et du tableau de bord."""

from .appointment_views import AppointmentCancelView
from .appointment_views import AppointmentCreateView
from .appointment_views import AppointmentListView
from .appointment_views import AppointmentStatusUpdateView
from .caisse_views import CaissePendingListView
from .caisse_views import FactureCreateView
from .caisse_views import FactureDetailView
from .caisse_views import FactureListView
from .caisse_views import PaiementCreateView
from .consultation_views import ConsultationCreateView
from .consultation_views import ConsultationDetailView
from .consultation_views import ConsultationListView
from .consultation_views import DoctorAppointmentListView
from .consultation_views import OrdonnanceCreateView
from .consultation_views import PrestationRealiseeCreateView
from .dashboard_views import DashboardHomeView
from .patient_views import PatientAllergyCreateView
from .patient_views import PatientAllergyDeleteView
from .patient_views import PatientCreateView
from .patient_views import PatientDetailView
from .patient_views import PatientListView
from .patient_views import PatientMedicalUpdateView
from .patient_views import PatientUpdateView

from .caisse_views import FacturePrintView
from .consultation_views import OrdonnanceDetailPrintView
from .pharmacy_views import PharmacyOrdonnanceDispenseView
from .pharmacy_views import PharmacyOrdonnanceListView

__all__ = [
    "AppointmentCancelView",
    "AppointmentCreateView",
    "AppointmentListView",
    "AppointmentStatusUpdateView",
    "CaissePendingListView",
    "ConsultationCreateView",
    "ConsultationDetailView",
    "ConsultationListView",
    "DashboardHomeView",
    "DoctorAppointmentListView",
    "FactureCreateView",
    "FactureDetailView",
    "FactureListView",
    "FacturePrintView",
    "OrdonnanceCreateView",
    "OrdonnanceDetailPrintView",
    "PaiementCreateView",
    "PatientAllergyCreateView",
    "PatientAllergyDeleteView",
    "PatientCreateView",
    "PatientDetailView",
    "PatientListView",
    "PatientMedicalUpdateView",
    "PatientUpdateView",
    "PharmacyOrdonnanceDispenseView",
    "PharmacyOrdonnanceListView",
    "PrestationRealiseeCreateView",
]

