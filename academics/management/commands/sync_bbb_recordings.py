"""Discover processed BBB recordings for completed online sessions."""

from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.core.exceptions import ValidationError
from django.utils import timezone

from academics.models import AcademicScheduleEvent
from academics.services.recording_service import sync_bbb_recordings


class Command(BaseCommand):
    help = "Détecte les enregistrements BBB traités d'une séance en ligne terminée."

    def add_arguments(self, parser):
        parser.add_argument("--event-id", type=int)
        parser.add_argument(
            "--lookback-hours",
            type=int,
            default=168,
            help="Fenêtre des séances terminées à examiner en mode global (défaut : 168).",
        )

    def handle(self, *args, **options):
        event_id = options.get("event_id")
        base_queryset = AcademicScheduleEvent.objects.filter(
            is_online=True,
            is_active=True,
            external_meeting_id__gt="",
            online_provider="bigbluebutton",
        )
        if event_id:
            events = list(base_queryset.filter(pk=event_id))
            if not events:
                raise CommandError("Séance BBB en ligne introuvable ou sans meeting ID.")
        else:
            lookback_hours = max(1, options["lookback_hours"])
            events = list(base_queryset.filter(
                end_datetime__lt=timezone.now(),
                end_datetime__gte=timezone.now() - timedelta(hours=lookback_hours),
            ).order_by("end_datetime", "id"))

        found = 0
        failures = 0
        for event in events:
            try:
                found += len(sync_bbb_recordings(event=event))
            except ValidationError:
                failures += 1
                # A provider still processing one recording must not prevent
                # other ended meetings from being reconciled on this run.
                self.stderr.write(f"Séance {event.pk} : synchronisation BBB indisponible.")
        self.stdout.write(self.style.SUCCESS(
            f"Détection BBB terminée : {len(events)} séance(s), "
            f"{found} enregistrement(s), {failures} échec(s) temporaire(s)."
        ))
