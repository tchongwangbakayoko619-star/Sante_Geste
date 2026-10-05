"""Services de gestion des stocks, des réceptions de lots et de la stratégie FEFO."""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.pharmacy.models import Batch, Product, StockMovement, Supplier

if TYPE_CHECKING:
    from apps.users.models import User

logger = logging.getLogger(__name__)


class StockService:
    """Service métier centralisant les opérations de stock, la traçabilité et le FEFO."""

    @classmethod
    def receive_batch(
        cls,
        *,
        product: Product,
        batch_number: str,
        expiry_date: date,
        quantity: int,
        purchase_price: Decimal,
        user: User,
        supplier: Supplier | None = None,
        selling_price: Decimal | None = None,
        notes: str = "",
    ) -> Batch:
        """Enregistre une réception de stock fournisseur (création/mise à jour d'un lot).

        - Vérifie la cohérence de date de péremption et de quantité (> 0).
        - Met à jour le stock du produit.
        - Crée le mouvement de stock inaltérable (IN_PURCHASE).
        """
        if quantity <= 0:
            raise ValidationError(_("La quantité reçue doit être strictement supérieure à 0."))

        if expiry_date <= date.today():
            raise ValidationError(_("Impossible de réceptionner un lot dont la date de péremption est antérieure ou égale à aujourd'hui."))

        clean_batch_number = batch_number.strip().upper()

        with transaction.atomic():
            # Verrouille le produit pour éviter les conditions de concurrence
            prod = Product.objects.select_for_update().get(pk=product.pk)
            prev_stock = prod.current_stock

            # Mettre à jour le prix de vente si spécifié
            if selling_price and selling_price > Decimal("0.00"):
                prod.selling_price = selling_price

            prod.purchase_price = purchase_price
            prod.current_stock = prev_stock + quantity
            prod.save(update_fields=["current_stock", "purchase_price", "selling_price", "updated_at"])

            # Créer ou mettre à jour le lot correspondant
            batch, created = Batch.objects.get_or_create(
                product=prod,
                batch_number=clean_batch_number,
                defaults={
                    "supplier": supplier,
                    "expiry_date": expiry_date,
                    "initial_quantity": quantity,
                    "current_quantity": quantity,
                    "purchase_price": purchase_price,
                    "entry_date": date.today(),
                    "status": "ACTIVE",
                    "created_by": user,
                },
            )
            if not created:
                batch.current_quantity += quantity
                batch.initial_quantity += quantity
                batch.expiry_date = expiry_date
                batch.purchase_price = purchase_price
                if supplier:
                    batch.supplier = supplier
                if batch.status != "ACTIVE":
                    batch.status = "ACTIVE"
                batch.updated_by = user
                batch.save()

            # Mouvement de stock d'entrée
            StockMovement.objects.create(
                product=prod,
                batch=batch,
                movement_type="IN_PURCHASE",
                quantity=quantity,
                previous_stock=prev_stock,
                new_stock=prod.current_stock,
                user=user,
                reference_number=f"RECEPT-{clean_batch_number}",
                reason=notes or _("Réception fournisseur de %(qty)d unités") % {"qty": quantity},
                created_by=user,
            )

            logger.info(
                "Stock réceptionné : %s (+%d) | Nouveau stock: %d | Opérateur: %s",
                prod.name,
                quantity,
                prod.current_stock,
                user.email,
            )
            return batch

    @classmethod
    def get_available_batches_fefo(cls, product: Product) -> list[Batch]:
        """Retourne la liste des lots disponibles ordonnée selon FEFO (First Expired, First Out).

        Exclut les lots dont la quantité est nulle et les lots expirés.
        """
        today = date.today()
        return list(
            Batch.objects.filter(
                product=product,
                current_quantity__gt=0,
                status="ACTIVE",
                expiry_date__gt=today,
            ).order_by("expiry_date", "entry_date")
        )

    @classmethod
    def allocate_stock_fefo(
        cls,
        product: Product,
        requested_quantity: int,
    ) -> list[dict[str, Any]]:
        """Calcule la répartition de déstockage sur les lots actifs selon la règle FEFO.

        Retourne une liste de dict : [{'batch': Batch, 'quantity': int}, ...]
        Lève une ValidationError si le stock actif non périmé est insuffisant.
        """
        if requested_quantity <= 0:
            raise ValidationError(_("La quantité demandée doit être supérieure à 0."))

        batches = cls.get_available_batches_fefo(product)
        total_available = sum(b.current_quantity for b in batches)

        if total_available < requested_quantity:
            raise ValidationError(
                _("Stock insuffisant pour '%(product)s'. Disponible non périmé : %(avail)d, demandé : %(req)d.")
                % {
                    "product": product.name,
                    "avail": total_available,
                    "req": requested_quantity,
                }
            )

        allocations: list[dict[str, Any]] = []
        remaining = requested_quantity

        for batch in batches:
            if remaining <= 0:
                break
            allocated = min(batch.current_quantity, remaining)
            allocations.append({"batch": batch, "quantity": allocated})
            remaining -= allocated

        return allocations

    @classmethod
    def adjust_stock(
        cls,
        *,
        product: Product,
        new_quantity: int,
        user: User,
        reason: str,
        batch: Batch | None = None,
    ) -> StockMovement:
        """Effectue un ajustement d'inventaire (positif ou négatif).

        Réservé au Responsable Pharmacie.
        """
        if new_quantity < 0:
            raise ValidationError(_("La nouvelle quantité de stock ne peut pas être négative."))

        if not reason.strip():
            raise ValidationError(_("Un motif d'ajustement est obligatoire pour justifier l'inventaire."))

        with transaction.atomic():
            prod = Product.objects.select_for_update().get(pk=product.pk)
            prev_stock = prod.current_stock
            diff = new_quantity - prev_stock

            if diff == 0:
                raise ValidationError(_("Le stock indiqué est identique au stock actuel."))

            movement_type = "POS_ADJUST" if diff > 0 else "NEG_ADJUST"
            prod.current_stock = new_quantity
            prod.save(update_fields=["current_stock", "updated_at"])

            if batch:
                target_batch = Batch.objects.select_for_update().get(pk=batch.pk)
                new_batch_qty = target_batch.current_quantity + diff
                if new_batch_qty < 0:
                    raise ValidationError(_("L'ajustement rendrait la quantité du lot '%(batch)s' négative.") % {"batch": target_batch.batch_number})
                target_batch.current_quantity = new_batch_qty
                if target_batch.current_quantity == 0:
                    target_batch.status = "DEPLETED"
                elif target_batch.status == "DEPLETED" and target_batch.current_quantity > 0:
                    target_batch.status = "ACTIVE"
                target_batch.save(update_fields=["current_quantity", "status", "updated_at"])

            movement = StockMovement.objects.create(
                product=prod,
                batch=batch,
                movement_type=movement_type,
                quantity=diff,
                previous_stock=prev_stock,
                new_stock=new_quantity,
                user=user,
                reference_number=f"INVENT-{timezone.now().strftime('%Y%m%d%H%M')}",
                reason=reason.strip(),
                created_by=user,
            )

            logger.info(
                "Ajustement stock: %s (%+d) -> %d par %s [Motif: %s]",
                prod.name,
                diff,
                new_quantity,
                user.email,
                reason,
            )
            return movement

    @classmethod
    def discard_expired_batch(
        cls,
        *,
        batch: Batch,
        user: User,
        reason: str = "",
    ) -> StockMovement:
        """Met au rebut un lot périmé ou impropre à la consommation."""
        with transaction.atomic():
            b = Batch.objects.select_for_update().get(pk=batch.pk)
            qty_to_discard = b.current_quantity
            if qty_to_discard <= 0:
                raise ValidationError(_("Ce lot ne contient plus d'unités en stock."))

            prod = Product.objects.select_for_update().get(pk=b.product.pk)
            prev_stock = prod.current_stock

            prod.current_stock = max(0, prev_stock - qty_to_discard)
            prod.save(update_fields=["current_stock", "updated_at"])

            b.current_quantity = 0
            b.status = "EXPIRED"
            b.save(update_fields=["current_quantity", "status", "updated_at"])

            movement = StockMovement.objects.create(
                product=prod,
                batch=b,
                movement_type="EXPIRED",
                quantity=-qty_to_discard,
                previous_stock=prev_stock,
                new_stock=prod.current_stock,
                user=user,
                reference_number=f"REBUT-{b.batch_number}",
                reason=reason or _("Mise au rebut pour péremption du lot %(lot)s") % {"lot": b.batch_number},
                created_by=user,
            )
            return movement
