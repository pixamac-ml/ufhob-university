# formations/models.py

from django.db import models
from django.urls import reverse
from django.utils.text import slugify
from unidecode import unidecode


# ==================================================
# CYCLE (Licence / Master / Doctorat)
# ==================================================
class Cycle(models.Model):
    THEME_CHOICES = [
        ("accent", "Bleu institutionnel"),
        ("secondary", "Orange premium"),
        ("dark", "Sombre (Doctorat)"),
    ]

    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(unique=True, blank=True)
    description = models.TextField(blank=True)

    theme = models.CharField(
        max_length=20,
        choices=THEME_CHOICES,
        default="accent",
    )

    min_duration_years = models.PositiveSmallIntegerField()
    max_duration_years = models.PositiveSmallIntegerField()

    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Cycle"
        verbose_name_plural = "Cycles"
        ordering = ["min_duration_years"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base = unidecode(self.name).lower()
            base = base.replace("'", "").replace("'", "")
            self.slug = slugify(base)
        super().save(*args, **kwargs)


# ==================================================
# DIPLÔME
# ==================================================
class Diploma(models.Model):
    name = models.CharField(max_length=150, unique=True)
    level = models.CharField(
        max_length=50,
        choices=[
            ("secondaire", "Secondaire"),
            ("superieur", "Supérieur"),
        ]
    )

    class Meta:
        verbose_name = "Diplôme"
        verbose_name_plural = "Diplômes"

    def __str__(self):
        return self.name


# ==================================================
# FILIÈRE
# ==================================================
class Filiere(models.Model):
    name = models.CharField(max_length=200, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Filière"
        verbose_name_plural = "Filières"
        ordering = ["name"]

    def __str__(self):
        return self.name


# ==================================================
# PROGRAMME
# ==================================================
class Programme(models.Model):
    title = models.CharField(max_length=255)
    slug = models.SlugField(unique=True, blank=True)

    # ==================================================
    # LIEN VERS L'ÉCOLE (NOUVEAU - UFHOB)
    # ==================================================
    school = models.ForeignKey(
        'schools.School',
        on_delete=models.PROTECT,
        related_name="programmes",
        verbose_name="École",
        help_text="École à laquelle appartient ce programme (EsMed, ESGA, FATEC)",
        null=True,
        blank=True
    )
    # ==================================================

    filiere = models.ForeignKey(
        Filiere,
        on_delete=models.PROTECT,
        related_name="programmes"
    )
    cycle = models.ForeignKey(
        Cycle,
        on_delete=models.PROTECT,
        related_name="programmes"
    )
    diploma_awarded = models.ForeignKey(
        Diploma,
        on_delete=models.PROTECT,
        related_name="programmes"
    )

    duration_years = models.PositiveSmallIntegerField()

    short_description = models.CharField(max_length=300)
    description = models.TextField()

    # ==================================================
    # CONTENU LANDING PAGE
    # ==================================================

    learning_outcomes = models.TextField(
        blank=True,
        help_text="Compétences et savoir-faire développés durant la formation"
    )

    career_opportunities = models.TextField(
        blank=True,
        help_text="Métiers et secteurs accessibles après la formation"
    )

    program_structure = models.TextField(
        blank=True,
        help_text="Organisation pédagogique : cours, stages, travaux pratiques, etc."
    )

    illustration = models.ImageField(
        upload_to="programmes/illustrations/",
        blank=True,
        null=True
    )

    # ==================================================

    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Programme"
        verbose_name_plural = "Programmes"
        ordering = ["title"]
        indexes = [
            models.Index(fields=["is_active"]),
            models.Index(fields=["is_featured"]),
            models.Index(fields=["school"]),  # Index pour filtrage par école
        ]

    def __str__(self):
        if self.school:
            return f"{self.title} ({self.school.short_name})"
        return self.title

    def get_absolute_url(self):
        return reverse("formations:detail", args=[self.slug])

    def save(self, *args, **kwargs):
        if not self.slug:
            base = unidecode(self.title).lower()
            base = base.replace("'", "").replace("'", "")
            slug = slugify(base)

            counter = 1
            original_slug = slug
            while Programme.objects.filter(slug=slug).exists():
                slug = f"{original_slug}-{counter}"
                counter += 1

            self.slug = slug

        super().save(*args, **kwargs)

    # ==================================================
    # LOGIQUE FINANCIÈRE
    # ==================================================
    def get_inscription_amount_for_year(self, year_number):
        programme_year = self.years.filter(
            year_number=year_number
        ).first()

        if not programme_year:
            return 0

        return sum(
            fee.amount for fee in programme_year.fees.all()
        )


# ==================================================
# ANNÉES DU PROGRAMME
# ==================================================
class ProgrammeYear(models.Model):
    programme = models.ForeignKey(
        Programme,
        related_name="years",
        on_delete=models.CASCADE
    )
    year_number = models.PositiveSmallIntegerField()

    class Meta:
        verbose_name = "Année de programme"
        verbose_name_plural = "Années de programme"
        unique_together = ("programme", "year_number")
        ordering = ["year_number"]

    def __str__(self):
        return f"{self.programme.title} – Année {self.year_number}"


# ==================================================
# FRAIS PAR ANNÉE (TRANCHES)
# ==================================================
class Fee(models.Model):
    programme_year = models.ForeignKey(
        ProgrammeYear,
        related_name="fees",
        on_delete=models.CASCADE
    )
    label = models.CharField(max_length=100)
    amount = models.PositiveIntegerField()
    due_month = models.CharField(max_length=50)

    class Meta:
        verbose_name = "Frais"
        verbose_name_plural = "Frais"
        ordering = ["amount"]
        unique_together = ("programme_year", "label")

    def __str__(self):
        return f"{self.label} – {self.amount} FCFA"


# ==================================================
# FAITS RAPIDES (QUICK FACTS)
# ==================================================
class ProgrammeQuickFact(models.Model):
    ICON_CHOICES = [
        ("academic_cap", "Capacité académique"),
        ("calendar", "Calendrier"),
        ("clock", "Horloge/Durée"),
        ("location", "Localisation"),
        ("certificate", "Certification"),
        ("user", "Profil étudiant"),
        ("briefcase", "Valise/Métier"),
    ]

    programme = models.ForeignKey(
        Programme,
        related_name="quick_facts",
        on_delete=models.CASCADE
    )
    icon = models.CharField(max_length=30, choices=ICON_CHOICES, default="academic_cap")
    label = models.CharField(max_length=100, help_text="Ex: Niveau, Durée, Rentrée")
    value = models.CharField(max_length=200, help_text="Ex: Bac+5, 2 ans, Septembre 2026")
    order = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Fait rapide"
        verbose_name_plural = "Faits rapides"
        ordering = ["order", "id"]
        unique_together = ("programme", "icon", "label")

    def __str__(self):
        return f"{self.programme.title} - {self.label}: {self.value}"


# ==================================================
# ONGLETS DE LA PAGE DÉTAIL
# ==================================================
class ProgrammeTab(models.Model):
    TAB_TYPE_CHOICES = [
        ("key_info", "Infos clés"),
        ("program", "Programme"),
        ("careers", "Débouchés"),
        ("admission", "Admission"),
        ("custom", "Personnalisé"),
    ]

    programme = models.ForeignKey(
        Programme,
        related_name="tabs",
        on_delete=models.CASCADE
    )
    tab_type = models.CharField(max_length=20, choices=TAB_TYPE_CHOICES, default="custom")
    title = models.CharField(max_length=100)
    slug = models.SlugField(max_length=50)
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Onglet"
        verbose_name_plural = "Onglets"
        ordering = ["order", "id"]
        unique_together = ("programme", "slug")

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        super().save(*args, **kwargs)


# ==================================================
# SECTIONS DE CONTENU
# ==================================================
class ProgrammeSection(models.Model):
    SECTION_TYPE_CHOICES = [
        ("text", "Texte simple"),
        ("heading", "Titre + Description"),
        ("list", "Liste à puces"),
        ("cards", "Cartes/Blocs"),
        ("cta", "Appel à l'action"),
    ]

    tab = models.ForeignKey(
        ProgrammeTab,
        related_name="sections",
        on_delete=models.CASCADE
    )
    section_type = models.CharField(max_length=20, choices=SECTION_TYPE_CHOICES, default="text")
    title = models.CharField(max_length=200, blank=True)
    content = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Section"
        verbose_name_plural = "Sections"
        ordering = ["order", "id"]


# ==================================================
# BLOCS DE COMPÉTENCES
# ==================================================
class CompetenceBlock(models.Model):
    programme = models.ForeignKey(
        Programme,
        related_name="competence_blocks",
        on_delete=models.CASCADE
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Bloc de compétences"
        verbose_name_plural = "Blocs de compétences"
        ordering = ["order", "id"]


# ==================================================
# ITEMS DE COMPÉTENCES
# ==================================================
class CompetenceItem(models.Model):
    block = models.ForeignKey(
        CompetenceBlock,
        related_name="items",
        on_delete=models.CASCADE
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Item de compétence"
        verbose_name_plural = "Items de compétences"
        ordering = ["order", "id"]


# ==================================================
# DOCUMENTS REQUIS
# ==================================================
class RequiredDocument(models.Model):
    name = models.CharField(max_length=200, unique=True)
    description = models.TextField(blank=True)
    is_mandatory = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Document requis"
        verbose_name_plural = "Documents requis"

    def __str__(self):
        return self.name


class ProgrammeRequiredDocument(models.Model):
    programme = models.ForeignKey(
        Programme,
        related_name="required_documents",
        on_delete=models.CASCADE
    )
    document = models.ForeignKey(
        RequiredDocument,
        on_delete=models.PROTECT
    )

    class Meta:
        verbose_name = "Document requis pour programme"
        verbose_name_plural = "Documents requis pour programmes"
        unique_together = ("programme", "document")