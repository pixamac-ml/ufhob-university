# formations/admin.py

from django.contrib import admin
from django.utils.html import format_html

from .models import (
    Cycle, Diploma, Filiere, Programme, ProgrammeYear, Fee,
    ProgrammeQuickFact, ProgrammeTab, ProgrammeSection,
    CompetenceBlock, CompetenceItem, RequiredDocument, ProgrammeRequiredDocument
)


# ==================================================
# INLINES
# ==================================================

class ProgrammeYearInline(admin.TabularInline):
    model = ProgrammeYear
    extra = 1


class FeeInline(admin.TabularInline):
    model = Fee
    extra = 1


class ProgrammeQuickFactInline(admin.TabularInline):
    model = ProgrammeQuickFact
    extra = 1


class ProgrammeRequiredDocumentInline(admin.TabularInline):
    model = ProgrammeRequiredDocument
    extra = 1


class CompetenceItemInline(admin.TabularInline):
    model = CompetenceItem
    extra = 1


class ProgrammeSectionInline(admin.TabularInline):
    model = ProgrammeSection
    extra = 1


# ==================================================
# ADMIN MODELS
# ==================================================

@admin.register(Cycle)
class CycleAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'min_duration_years', 'max_duration_years', 'theme', 'is_active']
    list_filter = ['is_active', 'theme']
    search_fields = ['name']
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Diploma)
class DiplomaAdmin(admin.ModelAdmin):
    list_display = ['name', 'level']
    list_filter = ['level']
    search_fields = ['name']


@admin.register(Filiere)
class FiliereAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_active']
    list_filter = ['is_active']
    search_fields = ['name']


@admin.register(Programme)
class ProgrammeAdmin(admin.ModelAdmin):
    list_display = [
        'title',
        'display_school',  # NOUVEAU
        'filiere',
        'cycle',
        'duration_years',
        'is_active',
        'is_featured'
    ]

    list_filter = [
        'school',  # NOUVEAU - Filtre par école
        'cycle',
        'filiere',
        'is_active',
        'is_featured'
    ]

    search_fields = ['title', 'short_description', 'school__short_name']

    list_editable = ['is_active', 'is_featured']

    prepopulated_fields = {'slug': ('title',)}

    autocomplete_fields = ['school', 'filiere', 'cycle', 'diploma_awarded']

    readonly_fields = ['created_at', 'updated_at']

    inlines = [
        ProgrammeYearInline,
        ProgrammeQuickFactInline,
        ProgrammeRequiredDocumentInline,
    ]

    fieldsets = (
        ('Informations principales', {
            'fields': ('title', 'slug', 'school', 'filiere', 'cycle', 'diploma_awarded', 'duration_years')
        }),
        ('Description', {
            'fields': ('short_description', 'description', 'illustration')
        }),
        ('Contenu détaillé', {
            'fields': ('learning_outcomes', 'career_opportunities', 'program_structure'),
            'classes': ('collapse',)
        }),
        ('Paramètres', {
            'fields': ('is_active', 'is_featured')
        }),
        ('Métadonnées', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def display_school(self, obj):
        if obj.school:
            return format_html(
                '<span style="background-color: {}; color: white; '
                'padding: 3px 8px; border-radius: 4px; font-size: 11px;">{}</span>',
                obj.school.primary_color,
                obj.school.short_name
            )
        return "-"

    display_school.short_description = "École"
    display_school.admin_order_field = "school"


@admin.register(ProgrammeYear)
class ProgrammeYearAdmin(admin.ModelAdmin):
    list_display = ['programme', 'year_number']
    list_filter = ['programme__school', 'year_number']  # NOUVEAU - Filtre par école
    search_fields = ['programme__title']
    inlines = [FeeInline]


@admin.register(Fee)
class FeeAdmin(admin.ModelAdmin):
    list_display = ['programme_year', 'label', 'amount', 'due_month']
    list_filter = ['programme_year__programme__school']  # NOUVEAU - Filtre par école
    search_fields = ['label', 'programme_year__programme__title']


@admin.register(ProgrammeTab)
class ProgrammeTabAdmin(admin.ModelAdmin):
    list_display = ['programme', 'title', 'tab_type', 'order', 'is_active']
    list_filter = ['programme__school', 'tab_type', 'is_active']  # NOUVEAU
    search_fields = ['title', 'programme__title']
    inlines = [ProgrammeSectionInline]


@admin.register(CompetenceBlock)
class CompetenceBlockAdmin(admin.ModelAdmin):
    list_display = ['programme', 'title', 'order']
    list_filter = ['programme__school']  # NOUVEAU
    search_fields = ['title', 'programme__title']
    inlines = [CompetenceItemInline]


@admin.register(RequiredDocument)
class RequiredDocumentAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_mandatory']
    list_filter = ['is_mandatory']
    search_fields = ['name']