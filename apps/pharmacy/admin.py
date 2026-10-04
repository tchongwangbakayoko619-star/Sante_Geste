"""Administration Django pour le module Pharmacie."""

from django.contrib import admin
from apps.pharmacy.models import Batch, Category, Product, Sale, SaleItem, StockMovement, Supplier


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "created_at")
    search_fields = ("name",)


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ("name", "contact_person", "telephone", "email", "is_active")
    search_fields = ("name", "contact_person", "telephone")
    list_filter = ("is_active",)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("reference_code", "name", "dci", "category", "current_stock", "selling_price", "is_active")
    search_fields = ("reference_code", "name", "dci")
    list_filter = ("is_active", "category")


@admin.register(Batch)
class BatchAdmin(admin.ModelAdmin):
    list_display = ("batch_number", "product", "expiry_date", "current_quantity", "status")
    search_fields = ("batch_number", "product__name")
    list_filter = ("status",)


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ("movement_date", "product", "movement_type", "quantity", "previous_stock", "new_stock", "user", "reference_number")
    search_fields = ("product__name", "reference_number", "reason")
    list_filter = ("movement_type",)
    readonly_fields = ("movement_date", "product", "batch", "movement_type", "quantity", "previous_stock", "new_stock", "user", "reference_number", "reason")


class SaleItemInline(admin.TabularInline):
    model = SaleItem
    extra = 0
    readonly_fields = ("product", "batch", "quantity", "unit_price", "total_price")


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ("sale_number", "sale_date", "patient", "client_name", "seller", "total_amount", "status")
    search_fields = ("sale_number", "client_name", "patient__last_name", "patient__first_name")
    list_filter = ("status",)
    inlines = [SaleItemInline]
