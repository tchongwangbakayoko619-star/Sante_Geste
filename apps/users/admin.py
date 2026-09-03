"""Admin panel registration for users application."""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from apps.users.forms import UserAdminChangeForm
from apps.users.forms import UserAdminCreationForm
from apps.users.models import MedicalProfile
from apps.users.models import User


class MedicalProfileInline(admin.StackedInline):
    """Inline configuration for MedicalProfile in UserAdmin."""

    model = MedicalProfile
    can_delete = False
    verbose_name_plural = "Profil Médical"
    fk_name = "user"


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Admin configuration for User model."""

    add_form = UserAdminCreationForm
    form = UserAdminChangeForm
    inlines = [MedicalProfileInline]
    list_display = (
        "email",
        "first_name",
        "last_name",
        "is_staff",
        "is_personnel_medical",
    )
    search_fields = ("email", "first_name", "last_name")
    ordering = ("email",)




@admin.register(MedicalProfile)
class MedicalProfileAdmin(admin.ModelAdmin):
    """Admin configuration for MedicalProfile model."""

    list_display = ("user", "specialite", "numero_ordre")
    search_fields = ("user__email", "specialite", "numero_ordre")

