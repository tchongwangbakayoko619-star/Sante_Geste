"""Service métier pour le module Caisse, la facturation et les règlements financiers."""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.patients.models import Facture
from apps.patients.models import Paiement
from apps.patients.models import Patient
from apps.patients.models import PrestationRealisee

if TYPE_CHECKING:
    from django.db.models import QuerySet

    from apps.users.models import User

logger = logging.getLogger(__name__)


class PaymentService:
    """Service centralisant la logique financière et les transactions de caisse."""

    @classmethod
    def generate_receipt_number(cls) -> str:
        """Génère un numéro de reçu unique au format REC-YYYYMMDD-XXXX."""
        today_str = timezone.now().strftime("%Y%m%d")
        prefix = f"REC-{today_str}-"

        with transaction.atomic():
            last_p = (
                Paiement.objects.filter(receipt_number__startswith=prefix)
                .order_by("-receipt_number")
                .first()
            )
            if last_p and last_p.receipt_number:
                try:
                    last_seq = int(last_p.receipt_number.split("-")[-1])
                    seq = last_seq + 1
                except ValueError:
                    seq = Paiement.objects.count() + 1
            else:
                seq = 1
            return f"{prefix}{seq:04d}"

    @classmethod
    def generate_invoice_number(cls) -> str:
        """Génère un numéro de facture unique au format FAC-YYYYMMDD-XXXX."""
        today_str = timezone.now().strftime("%Y%m%d")
        prefix = f"FAC-{today_str}-"

        with transaction.atomic():
            last_f = (
                Facture.objects.filter(invoice_number__startswith=prefix)
                .order_by("-invoice_number")
                .first()
            )
            if last_f and last_f.invoice_number:
                try:
                    last_seq = int(last_f.invoice_number.split("-")[-1])
                    seq = last_seq + 1
                except ValueError:
                    seq = Facture.objects.count() + 1
            else:
                seq = 1
            return f"{prefix}{seq:04d}"

    @classmethod
    def create_invoice(
        cls,
        *,
        patient: Patient,
        prestations: QuerySet[PrestationRealisee] | list[PrestationRealisee],
        cashier: User,
    ) -> Facture:
        """Crée une nouvelle facture pour des prestations en attente.

        Règle métier fondamentale :
        La facture créée a TOUJOURS le statut initial UNPAID et un montant payé de 0.
        Elle n'est JAMAIS automatiquement payée à la création.
        """
        if not prestations:
            msg = _("Aucune prestation fournie pour la facturation.")
            raise ValidationError(msg)

        with transaction.atomic():
            for item in prestations:
                if item.status != "EN_ATTENTE_CAISSE":
                    msg = _(
                        "La prestation %(name)s n'est plus en attente d'encaissement."
                    ) % {"name": item.prestation.name}
                    raise ValidationError(msg)

            total_sum = sum(item.total_price for item in prestations)
            invoice_num = cls.generate_invoice_number()

            first_consultation = getattr(prestations[0], "consultation", None)

            facture = Facture.objects.create(
                invoice_number=invoice_num,
                patient=patient,
                consultation=first_consultation,
                total_amount=total_sum,
                paid_amount=Decimal("0.00"),
                status="UNPAID",
                issued_by=cashier,
            )

            if isinstance(prestations, list):
                p_ids = [p.id for p in prestations]
                PrestationRealisee.objects.filter(id__in=p_ids).update(
                    status="FACTURE",
                    facture=facture,
                )
            else:
                prestations.update(status="FACTURE", facture=facture)

            logger.info(
                "Facture émise: N° %s | Patient: %s (ID %s) | Montant: %s | Agent: %s",
                facture.invoice_number,
                patient.full_name,
                patient.pk,
                total_sum,
                getattr(cashier, "email", str(cashier)),
            )

            return facture

    @classmethod
    def _validate_payment(
        cls,
        facture: Facture,
        amount: Decimal,
        payment_method: str,
    ) -> None:
        """Valide la cohérence des montants et des règles métier de caisse."""
        if facture.status == "CANCELLED":
            msg = _("Impossible d'encaisser un paiement sur une facture annulée.")
            raise ValidationError(msg)

        if facture.status == "PAID" or facture.remaining_amount <= 0:
            msg = _("Cette facture est déjà intégralement réglée.")
            raise ValidationError(msg)

        if amount <= 0:
            msg = _("Le montant reçu doit être strictement supérieur à zéro.")
            raise ValidationError(msg)

        if amount > facture.remaining_amount:
            msg = _(
                "Le montant reçu (%(amount)s FCFA) ne peut pas dépasser "
                "le reste à payer (%(remaining)s FCFA)."
            ) % {
                "amount": f"{amount:,.0f}",
                "remaining": f"{facture.remaining_amount:,.0f}",
            }
            raise ValidationError(msg)

        valid_methods = [code for code, _ in Paiement.PAYMENT_METHOD_CHOICES]
        if payment_method not in valid_methods:
            msg = _("Le mode de règlement sélectionné n'est pas valide.")
            raise ValidationError(msg)

    @classmethod
    def confirm_payment(
        cls,
        *,
        facture: Facture,
        amount: Decimal | float | str,
        payment_method: str,
        cashier: User,
        notes: str = "",
    ) -> Paiement:
        """Confirme et enregistre explicitement un paiement perçu par le Caissier."""
        try:
            if not isinstance(amount, Decimal):
                amount = Decimal(str(amount))
        except Exception as e:
            msg = _("Montant de règlement invalide.")
            raise ValidationError(msg) from e

        cls._validate_payment(facture, amount, payment_method)

        with transaction.atomic():
            facture_locked = Facture.objects.select_for_update().get(pk=facture.pk)

            if (
                facture_locked.status == "PAID"
                or facture_locked.remaining_amount < amount
            ):
                msg = _(
                    "Le solde restant de la facture a été modifié par une autre action."
                )
                raise ValidationError(msg)

            receipt_num = cls.generate_receipt_number()

            paiement = Paiement.objects.create(
                facture=facture_locked,
                cashier=cashier,
                amount=amount,
                payment_method=payment_method,
                notes=notes or "",
                receipt_number=receipt_num,
            )

            total_paid = sum(p.amount for p in facture_locked.paiements.all())
            facture_locked.paid_amount = total_paid

            if total_paid >= facture_locked.total_amount:
                facture_locked.status = "PAID"
                facture_locked.prestations_realisees.all().update(status="PAYE")
                if facture_locked.consultation:
                    facture_locked.consultation.prestations.all().update(status="PAYE")
            else:
                facture_locked.status = "PARTIALLY_PAID"

            facture_locked.save(update_fields=["paid_amount", "status", "updated_at"])

            logger.info(
                "ENCAISSEMENT CONFIRMÉ: Reçu N° %s | Facture N° %s | Montant: %s | "
                "Mode: %s | Caissier: %s | Statut: %s | Reste: %s",
                paiement.receipt_number,
                facture_locked.invoice_number,
                paiement.amount,
                paiement.payment_method,
                getattr(cashier, "email", str(cashier)),
                facture_locked.status,
                facture_locked.remaining_amount,
            )

            facture.paid_amount = facture_locked.paid_amount
            facture.status = facture_locked.status

            return paiement

    @classmethod
    def cancel_invoice(cls, *, facture: Facture, user: User) -> Facture:
        """Annule une facture non payée et libère les prestations."""
        if facture.status == "PAID" or facture.paid_amount > 0:
            msg = _(
                "Impossible d'annuler une facture ayant déjà fait l'objet "
                "d'un encaissement."
            )
            raise ValidationError(msg)

        if facture.status == "CANCELLED":
            msg = _("Cette facture est déjà annulée.")
            raise ValidationError(msg)

        with transaction.atomic():
            facture_locked = Facture.objects.select_for_update().get(pk=facture.pk)
            facture_locked.status = "CANCELLED"
            facture_locked.save(update_fields=["status", "updated_at"])

            facture_locked.prestations_realisees.all().update(
                status="EN_ATTENTE_CAISSE",
                facture=None,
            )
            if facture_locked.consultation:
                facture_locked.consultation.prestations.filter(
                    status="FACTURE"
                ).update(status="EN_ATTENTE_CAISSE")

            logger.info(
                "Facture annulée: N° %s | Patient: %s | Annulée par: %s (ID %s)",
                facture_locked.invoice_number,
                facture_locked.patient.full_name,
                getattr(user, "email", str(user)),
                user.pk,
            )

            facture.status = "CANCELLED"
            return facture_locked
