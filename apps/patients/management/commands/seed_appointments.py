"""Commande Django de génération de rendez-vous médicaux de test pour le tableau de bord."""

from __future__ import annotations

from datetime import datetime
from datetime import time
from datetime import timedelta
import random

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.patients.models import Appointment
from apps.patients.models import Patient
from utils.enums import AppointmentStatusEnum

User = get_user_model()


class Command(BaseCommand):
    help = "Génère des rendez-vous médicaux de démonstration réalistes pour les patients existants."

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Supprime tous les rendez-vous existants avant de générer les nouveaux.",
        )

    def handle(self, *args, **options):
        if options["clear"]:
            deleted_count, _ = Appointment.objects.all().delete()
            self.stdout.write(
                self.style.WARNING(f"Suppression de {deleted_count} rendez-vous existants.")
            )

        # 1. Récupération ou activation des médecins
        doctors = list(
            User.objects.filter(is_personnel_medical=True, is_active=True).order_by("email")
        )

        # S'assurer que le compte administrateur est habilité médicalement si présent
        admin_user = User.objects.filter(email="tchongwangbakayoko619@gmail.com").first()
        if admin_user and not admin_user.is_personnel_medical:
            admin_user.is_personnel_medical = True
            admin_user.save(update_fields=["is_personnel_medical"])
            if admin_user not in doctors:
                doctors.append(admin_user)

        if not doctors:
            doctor = User.objects.filter(is_superuser=True).first()
            if doctor:
                doctor.is_personnel_medical = True
                doctor.save(update_fields=["is_personnel_medical"])
                doctors.append(doctor)
            else:
                self.stdout.write(
                    self.style.ERROR("Aucun médecin ni superuser trouvé pour assigner les RDV.")
                )
                return

        self.stdout.write(
            self.style.SUCCESS(
                f"Médecins affectés ({len(doctors)}) : {', '.join([d.email for d in doctors])}"
            )
        )

        # 2. Récupération des patients
        patients = list(
            Patient.objects.filter(is_deleted=False, status="active").order_by("patient_number")
        )
        if not patients:
            self.stdout.write(
                self.style.ERROR("Aucun patient actif trouvé. Veuillez d'abord créer des patients.")
            )
            return

        self.stdout.write(f"Patients disponibles : {len(patients)}")

        # 3. Base temporelle : Aujourd'hui et la semaine courante
        now = timezone.now()
        local_now = timezone.localtime(now)
        today = local_now.date()
        monday = today - timedelta(days=today.weekday())

        reasons = [
            ("Consultation de routine / Bilan de santé", "Examen clinique complet et prise de constantes."),
            ("Suivi hypertension artérielle", "Contrôle tensionnel et adaptation posologique ARA2."),
            ("Suivi diabète de type 2", "Vérification carnet glycémique et HbA1c."),
            ("Renouvellement ordonnance asthme", "Évaluation débit expiratoire de pointe et contrôle ventoline."),
            ("Douleurs abdominales aiguës", "Palpation fosse iliaque, prescription échographie abdominale."),
            ("Céphalées et migraines récurrentes", "Examen neurologique normal, bilan ophtalmologique demandé."),
            ("Infection respiratoire fébrile", "Auscultation pulmonaire, prescription traitement symptomatique."),
            ("Certificat médical d'aptitude sportive", "ECG de repos conforme, apte aux sports collectifs."),
            ("Lecture de résultats d'analyses", "NFS et bilan lipidique commentés avec le patient."),
            ("Contrôle post-opératoire", "Bonne cicatrisation, ablation des fils programmée."),
            ("Palpitations et essoufflement à l'effort", "Prescription Holter ECG et bilan thyroïdien."),
            ("Lombalgie et sciatalgie droite", "Prescription antalgiques palier 2 et 10 séances de kiné."),
            ("Vaccination et rappel voyage", "Administration vaccin hépatite A et conseils prophylactiques."),
            ("Avis dermatologique - Lésion cutanée", "Dermoscopie rassurante, surveillance annuelle préconisée."),
            ("Consultation pédiatrique de croissance", "Courbes staturo-pondérales régulières et conformes."),
        ]

        # Définition des créneaux de la semaine
        # Jour de la semaine (0 = Lundi ... 6 = Dimanche)
        weekly_schedule = [
            # Lundi
            {
                "day_offset": 0,
                "slots": [
                    (time(8, 30), AppointmentStatusEnum.COMPLETED),
                    (time(9, 30), AppointmentStatusEnum.COMPLETED),
                    (time(11, 0), AppointmentStatusEnum.COMPLETED),
                    (time(14, 30), AppointmentStatusEnum.COMPLETED),
                    (time(16, 0), AppointmentStatusEnum.CANCELLED),
                ],
            },
            # Mardi
            {
                "day_offset": 1,
                "slots": [
                    (time(9, 0), AppointmentStatusEnum.COMPLETED),
                    (time(10, 15), AppointmentStatusEnum.COMPLETED),
                    (time(11, 30), AppointmentStatusEnum.COMPLETED),
                    (time(15, 0), AppointmentStatusEnum.COMPLETED),
                    (time(16, 30), AppointmentStatusEnum.COMPLETED),
                    (time(17, 30), AppointmentStatusEnum.CANCELLED),
                ],
            },
            # Mercredi
            {
                "day_offset": 2,
                "slots": [
                    (time(8, 30), AppointmentStatusEnum.COMPLETED),
                    (time(9, 45), AppointmentStatusEnum.COMPLETED),
                    (time(11, 0), AppointmentStatusEnum.COMPLETED),
                    (time(14, 0), AppointmentStatusEnum.COMPLETED),
                    (time(15, 30), AppointmentStatusEnum.COMPLETED),
                ],
            },
            # Jeudi
            {
                "day_offset": 3,
                "slots": [
                    (time(8, 45), AppointmentStatusEnum.COMPLETED),
                    (time(10, 0), AppointmentStatusEnum.COMPLETED),
                    (time(11, 15), AppointmentStatusEnum.COMPLETED),
                    (time(14, 30), AppointmentStatusEnum.COMPLETED),
                    (time(15, 45), AppointmentStatusEnum.COMPLETED),
                    (time(17, 0), AppointmentStatusEnum.CANCELLED),
                ],
            },
            # Vendredi
            {
                "day_offset": 4,
                "slots": [
                    (time(8, 30), AppointmentStatusEnum.COMPLETED),
                    (time(9, 30), AppointmentStatusEnum.COMPLETED),
                    (time(10, 45), AppointmentStatusEnum.COMPLETED),
                    (time(14, 0), AppointmentStatusEnum.COMPLETED),
                    (time(15, 15), AppointmentStatusEnum.COMPLETED),
                    (time(16, 30), AppointmentStatusEnum.COMPLETED),
                    (time(17, 30), AppointmentStatusEnum.COMPLETED),
                ],
            },
            # Samedi (Aujourd'hui ou week-end)
            {
                "day_offset": 5,
                "slots": [
                    (time(8, 0), AppointmentStatusEnum.COMPLETED),
                    (time(8, 45), AppointmentStatusEnum.COMPLETED),
                    (time(9, 30), AppointmentStatusEnum.IN_CONSULTATION),
                    (time(10, 15), AppointmentStatusEnum.WAITING),
                    (time(11, 0), AppointmentStatusEnum.SCHEDULED),
                    (time(11, 45), AppointmentStatusEnum.CANCELLED),
                    (time(14, 0), AppointmentStatusEnum.SCHEDULED),
                    (time(15, 0), AppointmentStatusEnum.SCHEDULED),
                    (time(16, 0), AppointmentStatusEnum.SCHEDULED),
                ],
            },
            # Dimanche (Permanence)
            {
                "day_offset": 6,
                "slots": [
                    (time(9, 30), AppointmentStatusEnum.SCHEDULED),
                    (time(11, 0), AppointmentStatusEnum.SCHEDULED),
                    (time(14, 30), AppointmentStatusEnum.SCHEDULED),
                ],
            },
        ]

        created_count = 0
        patient_idx = 0

        # 4. Création des rendez-vous de la semaine courante
        for day_plan in weekly_schedule:
            target_date = monday + timedelta(days=day_plan["day_offset"])
            for slot_time, status in day_plan["slots"]:
                scheduled_dt = timezone.make_aware(
                    datetime.combine(target_date, slot_time),
                    timezone.get_current_timezone(),
                )

                patient = patients[patient_idx % len(patients)]
                patient_idx += 1
                doctor = doctors[(patient_idx) % len(doctors)]
                reason, notes = reasons[(patient_idx) % len(reasons)]

                # Éviter de recréer si un RDV existe déjà sur ce créneau exact pour ce médecin
                existing = Appointment.objects.filter(
                    doctor=doctor,
                    scheduled_at=scheduled_dt,
                ).first()
                if existing:
                    continue

                appt = Appointment(
                    patient=patient,
                    doctor=doctor,
                    scheduled_at=scheduled_dt,
                    estimated_duration_minutes=30,
                    reason=reason,
                    status=status,
                    notes=notes,
                )
                appt.save()
                created_count += 1

        # 5. Ajout de quelques rendez-vous sur la semaine précédente pour un mois bien garni
        last_week_monday = monday - timedelta(days=7)
        for offset in range(5):
            target_date = last_week_monday + timedelta(days=offset)
            for slot_time in [time(9, 0), time(11, 30), time(14, 15)]:
                scheduled_dt = timezone.make_aware(
                    datetime.combine(target_date, slot_time),
                    timezone.get_current_timezone(),
                )
                patient = patients[patient_idx % len(patients)]
                patient_idx += 1
                doctor = doctors[patient_idx % len(doctors)]
                reason, notes = reasons[patient_idx % len(reasons)]

                if not Appointment.objects.filter(doctor=doctor, scheduled_at=scheduled_dt).exists():
                    appt = Appointment(
                        patient=patient,
                        doctor=doctor,
                        scheduled_at=scheduled_dt,
                        estimated_duration_minutes=30,
                        reason=reason,
                        status=AppointmentStatusEnum.COMPLETED,
                        notes=notes,
                    )
                    appt.save()
                    created_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Succès ! {created_count} rendez-vous de démonstration ont été créés avec succès."
            )
        )
