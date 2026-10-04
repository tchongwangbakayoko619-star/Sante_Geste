"""Configuration des routes URL de l'application Pharmacie."""

from django.urls import path

from apps.pharmacy.views import (
    CategoryCreateView,
    CategoryListView,
    PharmacyDashboardView,
    ProductCreateView,
    ProductDetailView,
    ProductListView,
    ProductUpdateView,
    SaleCancelView,
    SaleCreateView,
    SaleDetailView,
    SaleListView,
    StockAdjustmentView,
    StockEntryView,
    StockMovementListView,
    SupplierCreateView,
    SupplierListView,
    BatchListView,
    PharmacyReportView,
    PharmacySettingsView,
)

app_name = "pharmacy"

urlpatterns = [
    # Tableau de bord principal
    path("", PharmacyDashboardView.as_view(), name="dashboard"),

    # Catalogue & Produits
    path("produits/", ProductListView.as_view(), name="product_list"),
    path("produits/nouveau/", ProductCreateView.as_view(), name="product_create"),
    path("produits/<uuid:pk>/", ProductDetailView.as_view(), name="product_detail"),
    path("produits/<uuid:pk>/modifier/", ProductUpdateView.as_view(), name="product_update"),

    # Stock & Mouvements
    path("stock/entree/", StockEntryView.as_view(), name="stock_entry"),
    path("stock/ajustement/", StockAdjustmentView.as_view(), name="stock_adjustment"),
    path("stock/mouvements/", StockMovementListView.as_view(), name="movement_list"),

    # Ventes & Délivrances
    path("ventes/", SaleListView.as_view(), name="sale_list"),
    path("ventes/nouvelle/", SaleCreateView.as_view(), name="sale_create"),
    path("ventes/<uuid:pk>/", SaleDetailView.as_view(), name="sale_detail"),
    path("ventes/<uuid:pk>/annuler/", SaleCancelView.as_view(), name="sale_cancel"),

    # Fournisseurs & Catégories
    path("fournisseurs/", SupplierListView.as_view(), name="supplier_list"),
    path("fournisseurs/nouveau/", SupplierCreateView.as_view(), name="supplier_create"),
    path("categories/", CategoryListView.as_view(), name="category_list"),
    path("categories/nouvelle/", CategoryCreateView.as_view(), name="category_create"),

    # Lots, Inventaire, Rapports & Paramètres
    path("stock/lots/", BatchListView.as_view(), name="batch_list"),
    path("rapports/", PharmacyReportView.as_view(), name="reports"),
    path("parametres/", PharmacySettingsView.as_view(), name="settings"),
]
