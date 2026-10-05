"""Service de gestion des ventes en pharmacie, délivrance d'ordonnances et intégration Caisse."""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.patients.models import Facture, Ordonnance, Patient
from apps.patients.services import PaymentService
from apps.pharmacy.models import Batch, Product, Sale, SaleItem, StockMovement
from apps.pharmacy.services.stock_service import StockService

if TYPE_CHECKING:
    from apps.users.models import User

logger = logging.getLogger(__name__)


class SaleService:
    """Service gérant le workflow complet de vente et la transmission à la Caisse."""

    @classmethod
    def generate_sale_number(cls) -> str:
        """Génère un numéro unique de vente au format VTE-YYYYMMDD-XXXX."""
        today_str = timezone.now().strftime("%Y%m%d")
        prefix = f"VTE-{today_str}-"
        with transaction.atomic():
            last = (
                Sale.objects.filter(sale_number__startswith=prefix)
                .order_by("-sale_number")
                .first()
            )
            if last and last.sale_number:
                try:
                    seq = int(last.sale_number.split("-")[-1]) + 1
                except ValueError:
                    seq = Sale.objects.count() + 1
            else:
                seq = 1
            return f"{prefix}{seq:04d}"

    @classmethod
    def create_sale(
        cls,
        *,
        seller: User,
        items_data: list[dict[str, Any]],
        patient: Patient | None = None,
        client_name: str = "",
        ordonnance: Ordonnance | None = None,
        discount_amount: Decimal = Decimal("0.00"),
        notes: str = "",
    ) -> Sale:
        """Crée et valide une vente de produits pharmaceutiques avec déstockage FEFO.

        `items_data`: list of {'product': Product, 'quantity': int, (optional)'unit_price': Decimal}
        
        Étapes transactionnelles :
        1. Vérification des stocks et calcul FEFO.
        2. Décrémentation atomique des lots et produits.
        3. Création des mouvements de stock (OUT_SALE ou OUT_DISPENSE).
        4. Création de la vente (PENDING_PAYMENT) et des lignes SaleItem.
        5. Émission de la Facture Caisse au statut initial UNPAID.
        6. Si ordonnance : mise à jour du statut en cours de délivrance.
        """
        if not items_data:
            raise ValidationError(_("La vente doit comporter au moins un produit."))

        if discount_amount < Decimal("0.00"):
            raise ValidationError(_("Le montant de remise ne peut pas être négatif."))

        with transaction.atomic():
            sale_num = cls.generate_sale_number()
            subtotal = Decimal("0.00")

            # 1. Préparation de la vente
            sale = Sale.objects.create(
                sale_number=sale_num,
                patient=patient,
                client_name=client_name.strip(),
                ordonnance=ordonnance,
                seller=seller,
                sale_date=timezone.now(),
                subtotal=Decimal("0.00"),
                discount_amount=discount_amount,
                total_amount=Decimal("0.00"),
                status="PENDING_PAYMENT",
                notes=notes.strip(),
                created_by=seller,
            )

            # 2. Traitement ligne par ligne avec déstockage FEFO
            for item in items_data:
                product: Product = item["product"]
                requested_qty = int(item["quantity"])
                if requested_qty <= 0:
                    raise ValidationError(_("La quantité pour '%(prod)s' doit être supérieure à 0.") % {"prod": product.name})

                # Verrouiller le produit en base
                prod_locked = Product.objects.select_for_update().get(pk=product.pk)
                unit_price = Decimal(str(item.get("unit_price") or prod_locked.selling_price))

                # Allocation par lots selon FEFO
                allocations = StockService.allocate_stock_fefo(prod_locked, requested_qty)

                for alloc in allocations:
                    batch: Batch = alloc["batch"]
                    qty_allocated = int(alloc["quantity"])
                    batch_locked = Batch.objects.select_for_update().get(pk=batch.pk)

                    # Décrémenter le lot
                    batch_locked.current_quantity -= qty_allocated
                    if batch_locked.current_quantity == 0:
                        batch_locked.status = "DEPLETED"
                    batch_locked.save(update_fields=["current_quantity", "status", "updated_at"])

                    # Décrémenter le produit global
                    prev_stock = prod_locked.current_stock
                    prod_locked.current_stock -= qty_allocated
                    prod_locked.save(update_fields=["current_stock", "updated_at"])

                    # Créer la ligne de vente pour cette portion de lot
                    line_price = unit_price * Decimal(qty_allocated)
                    SaleItem.objects.create(
                        sale=sale,
                        product=prod_locked,
                        batch=batch_locked,
                        quantity=qty_allocated,
                        unit_price=unit_price,
                        total_price=line_price,
                        created_by=seller,
                    )
                    subtotal += line_price

                    # Mouvement de stock traçable
                    mov_type = "OUT_DISPENSE" if ordonnance else "OUT_SALE"
                    StockMovement.objects.create(
                        product=prod_locked,
                        batch=batch_locked,
                        movement_type=mov_type,
                        quantity=-qty_allocated,
                        previous_stock=prev_stock,
                        new_stock=prod_locked.current_stock,
                        user=seller,
                        reference_number=sale_num,
                        reason=f"Vente pharmacie {sale_num}",
                        created_by=seller,
                    )

            if discount_amount > subtotal:
                raise ValidationError(_("La remise ne peut pas dépasser le montant total de la vente."))

            total_net = max(Decimal("0.00"), subtotal - discount_amount)
            sale.subtotal = subtotal
            sale.total_amount = total_net

            # 3. Émission de la facture Caisse (si patient identifié) ou liaison Caisse
            # Si le patient est enregistré, créer la Facture Caisse au statut UNPAID
            if patient:
                inv_num = PaymentService.generate_invoice_number()
                facture = Facture.objects.create(
                    invoice_number=inv_num,
                    patient=patient,
                    consultation=ordonnance.consultation if ordonnance else None,
                    total_amount=total_net,
                    paid_amount=Decimal("0.00"),
                    status="UNPAID",
                    issued_by=seller,
                    created_by=seller,
                )
                sale.facture = facture

            sale.save()

            # 4. Si ordonnance associée, marquer délivrée
            if ordonnance and ordonnance.status != "DELIVERED":
                ordonnance.status = "DELIVERED"
                ordonnance.delivered_at = timezone.now()
                ordonnance.delivered_by = seller
                ordonnance.save(update_fields=["status", "delivered_at", "delivered_by", "updated_at"])

            logger.info("Vente pharmacie créée : %s | Total: %s FCFA | Vendeur: %s", sale_num, total_net, seller.email)
            return sale

    @classmethod
    def cancel_sale(
        cls,
        *,
        sale: Sale,
        user: User,
        reason: str,
    ) -> Sale:
        """Annule une vente non encore réglée et réintègre le stock par mouvement RETURN.

        Réservé au Responsable Pharmacie.
        """
        if sale.status == "COMPLETED":
            raise ValidationError(_("Une vente déjà payée et clôturée ne peut pas être annulée directement."))

        if sale.status == "CANCELLED":
            raise ValidationError(_("Cette vente est déjà annulée."))

        with transaction.atomic():
            sale_locked = Sale.objects.select_for_update().get(pk=sale.pk)

            # Réintégrer le stock pour chaque ligne de vente
            for item in sale_locked.items.all():
                prod = Product.objects.select_for_update().get(pk=item.product.pk)
                prev_stock = prod.current_stock
                prod.current_stock += item.quantity
                prod.save(update_fields=["current_stock", "updated_at"])

                if item.batch:
                    batch = Batch.objects.select_for_update().get(pk=item.batch.pk)
                    batch.current_quantity += item.quantity
                    if batch.status == "DEPLETED" and batch.current_quantity > 0:
                        batch.status = "ACTIVE"
                    batch.save(update_fields=["current_quantity", "status", "updated_at"])

                StockMovement.objects.create(
                    product=prod,
                    batch=item.batch,
                    movement_type="RETURN",
                    quantity=item.quantity,
                    previous_stock=prev_stock,
                    new_stock=prod.current_stock,
                    user=user,
                    reference_number=f"ANNUL-{sale_locked.sale_number}",
                    reason=reason or f"Annulation vente {sale_locked.sale_number}",
                    created_by=user,
                )

            # Annuler la facture caisse associée si présente
            if sale_locked.facture and sale_locked.facture.status == "UNPAID":
                sale_locked.facture.status = "CANCELLED"
                sale_locked.facture.save(update_fields=["status", "updated_at"])

            sale_locked.status = "CANCELLED"
            sale_locked.notes = f"{sale_locked.notes}\n[Annulée le {timezone.now().strftime('%d/%m/%Y %H:%M')} par {user.full_name} : {reason}]".strip()
            sale_locked.save(update_fields=["status", "notes", "updated_at"])

            logger.info("Vente annulée : %s par %s | Motif: %s", sale_locked.sale_number, user.email, reason)
            return sale_locked
