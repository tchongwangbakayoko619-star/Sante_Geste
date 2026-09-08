from debug_toolbar.panels import Panel
from django.urls import reverse
from django.utils.translation import gettext_lazy as _


class UserLogoutPanel(Panel):
    """Custom Django Debug Toolbar panel providing user authentication information and a quick logout button."""

    panel_id = "UserLogoutPanel"
    has_content = True
    template = "debug_toolbar/panels/user_logout.html"
    _request = None

    @property
    def request(self):
        if self._request is not None:
            return self._request
        if hasattr(self, "toolbar") and getattr(self.toolbar, "request", None):
            return self.toolbar.request
        return None

    @request.setter
    def request(self, value):
        self._request = value

    def process_request(self, request):
        self.request = request
        return super().process_request(request)

    @property
    def nav_title(self) -> str:
        return str(_("Utilisateur / Auth"))

    @property
    def title(self) -> str:
        return str(_("Utilisateur & Déconnexion"))

    @property
    def nav_subtitle(self) -> str:
        req = self.request
        if req and hasattr(req, "user") and getattr(req.user, "is_authenticated", False):
            return str(getattr(req.user, "email", _("Connecté")))
        return str(_("Déconnecté"))

    def generate_stats(self, request, response) -> None:
        self.request = request
        user = getattr(request, "user", None)
        is_authenticated = bool(user and getattr(user, "is_authenticated", False))
        self.record_stats(
            {
                "user": user,
                "is_authenticated": is_authenticated,
                "logout_url": reverse("users:logout"),
                "login_url": reverse("users:login"),
            }
        )
