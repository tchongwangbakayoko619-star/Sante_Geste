"""Vues du module Rapports, Statistiques et Exports (CSV, Excel, PDF) pour SantéGeste."""

from __future__ import annotations

import csv
from datetime import datetime
from io import BytesIO
from typing import Any

from django.contrib.auth import get_user_model
from django.db.models import Count
from django.db.models import Q
from django.db.models import Sum
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views import View

from apps.dashboard.services.dashboard_service import DashboardService
from apps.patients.models import Appointment
from apps.patients.models import Consultation
from apps.patients.models import Facture
from apps.patients.models import Paiement
from apps.patients.models import Patient
from apps.patients.models import PrestationRealisee
from apps.users.mixins import RoleRequiredMixin
from utils.enums import AppointmentStatusEnum
from utils.enums import UserRoleEnum

User = get_user_model()


class ReportsHomeView(RoleRequiredMixin, View):
    """Interface unifiée d'accès aux rapports selon les permissions et rôles RBAC."""

    required_roles = [
        UserRoleEnum.AGENT_ACCUEIL,
        UserRoleEnum.PERSONNEL_MEDICAL,
        UserRoleEnum.CAISSIER,
        UserRoleEnum.PROPRIETAIRE,
    ]
    require_all_roles = False

    def get(self, request: Any):
        user = request.user
        available_reports = []

        # 1. Rapports Administratifs & Accueil
        if user.is_agent_accueil or user.is_proprietaire or user.is_superuser:
            available_reports.append({
                "code": "rdv_admin",
                "title": _("Activité des Rendez-vous"),
                "category": _("Accueil & Administration"),
                "description": _("Statistiques globales des rendez-vous, réparties par praticien, service et statut (Planifiés, Honorés, Annulés, Absences)."),
                "icon": "calendar",
                "role_badge": _("Agent d'accueil"),
            })
            available_reports.append({
                "code": "patients_admin",
                "title": _("Admissions & Nouveaux Patients"),
                "category": _("Accueil & Administration"),
                "description": _("Evolution du recrutement des patients, nouveaux dossiers enregistrés et répartition démographique."),
                "icon": "users",
                "role_badge": _("Agent d'accueil"),
            })

        # 2. Rapports d'Activité Médicale
        if user.is_personnel_medical or user.is_proprietaire or user.is_superuser:
            available_reports.append({
                "code": "consultations_med",
                "title": _("Activité des Consultations"),
                "category": _("Médical & Soins"),
                "description": _("Synthèse des consultations réalisées, motifs fréquents et suivi du volume d'actes par période."),
                "icon": "clipboard-document-list",
                "role_badge": _("Personnel médical"),
            })
            available_reports.append({
                "code": "prestations_med",
                "title": _("Actes & Prestations Réalisés"),
                "category": _("Médical & Soins"),
                "description": _("Volume et détails des actes techniques et soins dispensés par les praticiens."),
                "icon": "sparkles",
                "role_badge": _("Personnel médical"),
            })

        # 3. Rapports Financiers & Caisse
        if user.is_caissier or user.is_proprietaire or user.is_superuser:
            available_reports.append({
                "code": "caisse_finances",
                "title": _("Facturation & Recettes Caisse"),
                "category": _("Finance & Caisse"),
                "description": _("Rapport financier d'encaissement, factures payées/impayées et ventilation par mode de règlement."),
                "icon": "banknotes",
                "role_badge": _("Caissier"),
            })

        context = {
            "reports": available_reports,
        }
        return render(request, "dashboard/reports_home.html", context)


class ReportDetailView(RoleRequiredMixin, View):
    """Consultation d'un rapport spécifique avec filtres temporels et agrégations."""

    required_roles = [
        UserRoleEnum.AGENT_ACCUEIL,
        UserRoleEnum.PERSONNEL_MEDICAL,
        UserRoleEnum.CAISSIER,
        UserRoleEnum.PROPRIETAIRE,
    ]
    require_all_roles = False

    def get(self, request: Any, report_code: str):
        user = request.user
        period = request.GET.get("period", "month")
        start_date_str = request.GET.get("start_date")
        end_date_str = request.GET.get("end_date")

        # Résolution de la plage temporelle
        local_now = timezone.localtime(timezone.now())
        start_date, end_date = DashboardService._resolve_period_range(
            period=period,
            local_now=local_now,
            custom_start=datetime.strptime(start_date_str, "%Y-%m-%d") if start_date_str else None,
            custom_end=datetime.strptime(end_date_str, "%Y-%m-%d") if end_date_str else None,
        )

        context: dict[str, Any] = {
            "report_code": report_code,
            "period": period,
            "start_date": start_date,
            "end_date": end_date,
            "start_date_formatted": start_date.strftime("%Y-%m-%d"),
            "end_date_formatted": end_date.strftime("%Y-%m-%d"),
        }

        if report_code == "rdv_admin":
            if not (user.is_agent_accueil or user.is_proprietaire or user.is_superuser):
                raise PermissionDenied()
            qs = Appointment.objects.filter(scheduled_at__gte=start_date, scheduled_at__lte=end_date)
            context["title"] = _("Rapport des Rendez-vous & Agenda")
            context["kpis"] = [
                {"label": _("Total Rendez-vous"), "value": qs.count()},
                {"label": _("Honorés / Terminés"), "value": qs.filter(status=AppointmentStatusEnum.COMPLETED).count()},
                {"label": _("En attente / En cours"), "value": qs.filter(status__in=[AppointmentStatusEnum.WAITING, AppointmentStatusEnum.IN_CONSULTATION]).count()},
                {"label": _("Annulés"), "value": qs.filter(status=AppointmentStatusEnum.CANCELLED).count()},
            ]
            context["items"] = qs.select_related("patient", "doctor").order_by("scheduled_at")[:100]

        elif report_code == "patients_admin":
            if not (user.is_agent_accueil or user.is_proprietaire or user.is_superuser):
                raise PermissionDenied()
            qs = Patient.objects.filter(created_at__gte=start_date, created_at__lte=end_date)
            context["title"] = _("Rapport des Admissions & Nouveaux Patients")
            context["kpis"] = [
                {"label": _("Nouveaux Dossiers"), "value": qs.count()},
                {"label": _("Total Patients Actifs"), "value": Patient.objects.filter(is_deleted=False).count()},
            ]
            context["items"] = qs.order_by("-created_at")[:100]

        elif report_code == "consultations_med":
            if not (user.is_personnel_medical or user.is_proprietaire or user.is_superuser):
                raise PermissionDenied()
            qs = Consultation.objects.filter(consultation_date__gte=start_date, consultation_date__lte=end_date)
            if user.is_personnel_medical and not (user.is_superuser or user.is_proprietaire):
                qs = qs.filter(doctor=user)
            context["title"] = _("Rapport d'Activité des Consultations Médicales")
            context["kpis"] = [
                {"label": _("Consultations Réalisées"), "value": qs.count()},
            ]
            context["items"] = qs.select_related("patient", "doctor").order_by("-consultation_date")[:100]

        elif report_code == "prestations_med":
            if not (user.is_personnel_medical or user.is_proprietaire or user.is_superuser):
                raise PermissionDenied()
            qs = PrestationRealisee.objects.filter(created_at__gte=start_date, created_at__lte=end_date)
            if user.is_personnel_medical and not (user.is_superuser or user.is_proprietaire):
                qs = qs.filter(doctor=user)
            context["title"] = _("Rapport des Actes & Prestations Réalisés")
            context["kpis"] = [
                {"label": _("Total Actes Réalisés"), "value": qs.count()},
                {"label": _("Montant Total Généré"), "value": f"{sum(p.total_price for p in qs):,.0f} FCFA"},
            ]
            context["items"] = qs.select_related("patient", "doctor", "prestation").order_by("-created_at")[:100]

        elif report_code == "caisse_finances":
            if not (user.is_caissier or user.is_proprietaire or user.is_superuser):
                raise PermissionDenied()
            factures = Facture.objects.filter(issued_at__gte=start_date, issued_at__lte=end_date)
            paiements = Paiement.objects.filter(paid_at__gte=start_date, paid_at__lte=end_date)

            tot_emitted = sum(f.total_amount for f in factures)
            tot_collected = sum(p.amount for p in paiements)

            context["title"] = _("Rapport Financier & Encaisser de Caisse")
            context["kpis"] = [
                {"label": _("Factures Émises"), "value": factures.count()},
                {"label": _("Montant Total Facturé"), "value": f"{tot_emitted:,.0f} FCFA"},
                {"label": _("Encaissements Reçus"), "value": f"{tot_collected:,.0f} FCFA"},
                {"label": _("Reste à Recouvrer"), "value": f"{max(0, tot_emitted - tot_collected):,.0f} FCFA"},
            ]
            context["items"] = factures.select_related("patient", "issued_by").order_by("-issued_at")[:100]
        else:
            raise PermissionDenied(_("Rapport inconnu."))

        return render(request, "dashboard/report_detail.html", context)


class ReportExportView(RoleRequiredMixin, View):
    """Génération et téléchargement d'exports CSV, Excel ou PDF à la demande."""

    required_roles = [
        UserRoleEnum.AGENT_ACCUEIL,
        UserRoleEnum.PERSONNEL_MEDICAL,
        UserRoleEnum.CAISSIER,
        UserRoleEnum.PROPRIETAIRE,
    ]

    def get(self, request: Any, report_code: str, fmt: str):
        user = request.user
        filename = f"rapport_{report_code}_{timezone.now().strftime('%Y%m%d_%H%M')}"

        if fmt not in ["csv", "excel", "pdf"]:
            return HttpResponse(_("Format d'export non supporté."), status=400)

        # Extraction des filtres
        period = request.GET.get("period", "month")
        start_date, end_date = DashboardService._resolve_period_range(
            period=period,
            local_now=timezone.localtime(timezone.now()),
        )

        rows = []
        headers = []

        if report_code == "rdv_admin":
            qs = Appointment.objects.filter(scheduled_at__gte=start_date, scheduled_at__lte=end_date).select_related("patient", "doctor")
            headers = ["Date & Heure", "N° Patient", "Nom Patient", "Médecin", "Motif", "Statut"]
            for rdv in qs:
                rows.append([
                    timezone.localtime(rdv.scheduled_at).strftime("%d/%m/%Y %H:%M"),
                    rdv.patient.patient_number,
                    rdv.patient.full_name,
                    rdv.doctor.full_name,
                    rdv.reason,
                    rdv.get_status_display(),
                ])

        elif report_code == "patients_admin":
            qs = Patient.objects.filter(created_at__gte=start_date, created_at__lte=end_date)
            headers = ["N° Patient", "Nom Complet", "Sexe", "Téléphone", "Date de Naissance", "Date d'admission"]
            for p in qs:
                rows.append([
                    p.patient_number,
                    p.full_name,
                    p.get_gender_display(),
                    p.phone_number,
                    p.date_of_birth.strftime("%d/%m/%Y") if p.date_of_birth else "-",
                    p.created_at.strftime("%d/%m/%Y"),
                ])

        elif report_code == "consultations_med":
            qs = Consultation.objects.filter(consultation_date__gte=start_date, consultation_date__lte=end_date).select_related("patient", "doctor")
            headers = ["Date & Heure", "N° Patient", "Patient", "Médecin", "Motif", "Diagnostic"]
            for c in qs:
                rows.append([
                    timezone.localtime(c.consultation_date).strftime("%d/%m/%Y %H:%M"),
                    c.patient.patient_number,
                    c.patient.full_name,
                    c.doctor.full_name,
                    c.reason,
                    c.diagnosis,
                ])

        elif report_code == "caisse_finances":
            qs = Facture.objects.filter(issued_at__gte=start_date, issued_at__lte=end_date).select_related("patient", "issued_by")
            headers = ["N° Facture", "Date Émission", "Patient", "Montant Total", "Montant Payé", "Statut"]
            for f in qs:
                rows.append([
                    f.invoice_number,
                    timezone.localtime(f.issued_at).strftime("%d/%m/%Y %H:%M"),
                    f.patient.full_name,
                    f"{f.total_amount:,.0f} FCFA",
                    f"{f.paid_amount:,.0f} FCFA",
                    f.get_status_display(),
                ])

        # Formats d'export
        if fmt == "csv":
            response = HttpResponse(content_type="text/csv; charset=utf-8")
            response["Content-Disposition"] = f'attachment; filename="{filename}.csv"'
            response.write("\ufeff".encode("utf8"))  # BOM UTF-8 pour Excel
            writer = csv.writer(response, delimiter=";")
            writer.writerow(headers)
            for r in rows:
                writer.writerow(r)
            return response

        elif fmt == "excel":
            response = HttpResponse(content_type="application/vnd.ms-excel")
            response["Content-Disposition"] = f'attachment; filename="{filename}.xls"'
            # Génération HTML/XML compatible MS Excel
            content = f"<table><tr>{''.join(f'<th>{h}</th>' for h in headers)}</tr>"
            for r in rows:
                content += f"<tr>{''.join(f'<td>{val}</td>' for val in r)}</tr>"
            content += "</table>"
            response.write(content.encode("utf-8"))
            return response

        elif fmt == "pdf":
            # Impression optimisée PDF / HTML Print
            context = {
                "report_code": report_code,
                "headers": headers,
                "rows": rows,
                "title": f"Rapport {report_code.upper()}",
                "printed_at": timezone.now().strftime("%d/%m/%Y %H:%M"),
                "printed_by": user.full_name,
            }
            return render(request, "dashboard/report_pdf_print.html", context)

        return HttpResponse(_("Erreur d'exportation."), status=400)
