# accounts/admin.py

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
from .models import Profile


class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False
    verbose_name_plural = 'Profil'
    fk_name = 'user'
    fields = [
        'avatar', 'bio', 'phone',
        'school', 'branch', 'role',  # NOUVEAU - school ajouté
        'badge_bronze', 'badge_silver', 'badge_gold'
    ]


class CustomUserAdmin(UserAdmin):
    inlines = [ProfileInline]
    list_display = [
        'username', 'email', 'first_name', 'last_name',
        'get_school', 'is_staff', 'is_active'  # NOUVEAU
    ]
    list_filter = [
        'is_staff', 'is_superuser', 'is_active',
        'profile__school'  # NOUVEAU - Filtre par école
    ]

    def get_school(self, obj):
        if hasattr(obj, 'profile') and obj.profile.school:
            return obj.profile.school.short_name
        return "-"
    get_school.short_description = "École"


# Réenregistre UserAdmin
admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'school', 'branch', 'role',]
    list_filter = ['school', 'branch', 'role']  # NOUVEAU
    search_fields = ['user__username', 'user__email', 'phone']
    autocomplete_fields = ['school', 'branch']