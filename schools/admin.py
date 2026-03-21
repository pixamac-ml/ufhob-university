# schools/admin.py

from django.contrib import admin
from django.utils.html import format_html
from .models import School


@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
    list_display = [
        'short_name',
        'name',
        'display_color',
        'is_active',
        'programmes_count',
        'order'
    ]

    list_filter = ['is_active']

    search_fields = ['name', 'short_name', 'code']

    list_editable = ['order', 'is_active']

    prepopulated_fields = {'slug': ('short_name',)}

    readonly_fields = ['created_at', 'updated_at']

    fieldsets = (
        ('Identité', {
            'fields': ('name', 'short_name', 'code', 'slug')
        }),
        ('Description', {
            'fields': ('description', 'mission'),
            'classes': ('collapse',)
        }),
        ('Identité visuelle', {
            'fields': ('logo', 'cover_image', 'primary_color', 'secondary_color')
        }),
        ('Contact', {
            'fields': ('email', 'phone', 'address'),
            'classes': ('collapse',)
        }),
        ('Direction', {
            'fields': ('director',)
        }),
        ('Paramètres', {
            'fields': ('is_active', 'accepts_online_applications', 'order')
        }),
        ('Métadonnées', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def display_color(self, obj):
        return format_html(
            '<span style="background-color: {}; padding: 5px 15px; '
            'border-radius: 3px; color: white;">{}</span>',
            obj.primary_color,
            obj.primary_color
        )
    display_color.short_description = "Couleur"

    def programmes_count(self, obj):
        count = obj.programmes_count
        return format_html(
            '<span style="font-weight: bold;">{}</span>',
            count
        )
    programmes_count.short_description = "Programmes"