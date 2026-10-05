"""Services métier de l'application Pharmacie."""

from apps.pharmacy.services.sale_service import SaleService
from apps.pharmacy.services.stock_service import StockService

__all__ = ["StockService", "SaleService"]
