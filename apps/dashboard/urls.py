"""Configuration des routes URL pour le module Dashboard."""

from django.urls import path

from apps.dashboard.report_views import ReportDetailView
from apps.dashboard.report_views import ReportExportView
from apps.dashboard.report_views import ReportsHomeView
from apps.dashboard.views import DashboardApiView
from apps.dashboard.views import DashboardHomeView

app_name = "dashboard"

urlpatterns = [
    path("", DashboardHomeView.as_view(), name="home"),
    path("api/data/", DashboardApiView.as_view(), name="api_data"),
    path("rapports/", ReportsHomeView.as_view(), name="reports_home"),
    path("rapports/<str:report_code>/", ReportDetailView.as_view(), name="report_detail"),
    path("rapports/<str:report_code>/export/<str:fmt>/", ReportExportView.as_view(), name="report_export"),
]

