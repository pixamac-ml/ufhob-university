# schools/models.py

from django.db import models
from django.contrib.auth import get_user_model
from django.utils.text import slugify

User = get_user_model()


class School(models.Model):
    """
    Représente une école de l'université UFHOB.
    Exemples : EsMed, ESGA, FATEC
    """

    # ==================================================
    # IDENTITÉ
    # ==================================================

    name = models.CharField(
        max_length=200,
        unique=True,
        verbose_name="Nom de l'école",
        help_text="Ex: École des Sciences Médicales Félix Houphouët-Boigny"
    )

    short_name = models.CharField(
        max_length=20,
        unique=True,
        verbose_name="Nom court",
        help_text="Ex: EsMed, ESGA, FATEC"
    )

    code = models.CharField(
        max_length=10,
        unique=True,
        help_text="Code unique (ex: ESMED, ESGA, FATEC)"
    )

    slug = models.SlugField(
        unique=True,
        blank=True
    )

    # ==================================================
    # DESCRIPTION
    # ==================================================

    description = models.TextField(
        blank=True,
        verbose_name="Description",
        help_text="Présentation de l'école"
    )

    mission = models.TextField(
        blank=True,
        verbose_name="Mission",
        help_text="Mission et objectifs de l'école"
    )

    # ==================================================
    # IDENTITÉ VISUELLE
    # ==================================================

    logo = models.ImageField(
        upload_to="schools/logos/",
        blank=True,
        null=True,
        verbose_name="Logo de l'école"
    )

    cover_image = models.ImageField(
        upload_to="schools/covers/",
        blank=True,
        null=True,
        verbose_name="Image de couverture"
    )

    primary_color = models.CharField(
        max_length=7,
        default="#1E3A8A",
        help_text="Couleur principale HEX (ex: #1E3A8A)"
    )

    secondary_color = models.CharField(
        max_length=7,
        default="#F97316",
        help_text="Couleur secondaire HEX (ex: #F97316)"
    )

    # ==================================================
    # CONTACT
    # ==================================================

    email = models.EmailField(
        blank=True,
        verbose_name="Email de l'école"
    )

    phone = models.CharField(
        max_length=30,
        blank=True,
        verbose_name="Téléphone"
    )

    address = models.TextField(
        blank=True,
        verbose_name="Adresse"
    )

    # ==================================================
    # DIRECTION
    # ==================================================

    director = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="directed_schools",
        verbose_name="Directeur"
    )

    # ==================================================
    # PARAMÈTRES
    # ==================================================

    is_active = models.BooleanField(
        default=True,
        verbose_name="Active"
    )

    accepts_online_applications = models.BooleanField(
        default=True,
        verbose_name="Accepte les candidatures en ligne"
    )

    order = models.PositiveIntegerField(
        default=0,
        verbose_name="Ordre d'affichage"
    )

    # ==================================================
    # MÉTADONNÉES
    # ==================================================

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "École"
        verbose_name_plural = "Écoles"
        ordering = ["order", "name"]

    def __str__(self):
        return f"{self.short_name} - {self.name}"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.short_name)
        super().save(*args, **kwargs)

    # ==================================================
    # PROPRIÉTÉS
    # ==================================================

    @property
    def programmes_count(self):
        """Nombre de programmes actifs dans cette école."""
        return self.programmes.filter(is_active=True).count()