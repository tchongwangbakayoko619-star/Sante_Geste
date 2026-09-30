"""Configuration des routes URL pour le module Dashboard."""

from django.urls import path

from apps.dashboard.views import DashboardApiView
from apps.dashboard.views import DashboardHomeView

app_name = "dashboard"

urlpatterns = [
    path("", DashboardHomeView.as_view(), name="home"),
    path("api/data/", DashboardApiView.as_view(), name="api_data"),
]
