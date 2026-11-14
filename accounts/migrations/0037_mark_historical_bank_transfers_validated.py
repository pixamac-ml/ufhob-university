from django.db import migrations
from django.db.models import F


def mark_historical_transfers_validated(apps, schema_editor):
    """Existing rows were created by the former one-shot closure workflow.

    They already represent completed bank deposits, so keep them visible to
    the ledger reconciliation and reports after the explicit status field was
    introduced.  Their before/after snapshots cannot be reconstructed safely
    from a mutable historical ledger and intentionally remain at the additive
    migration default.
    """
    BranchBankTransfer = apps.get_model("accounts", "BranchBankTransfer")
    BranchBankTransfer.objects.filter(status="draft").update(
        status="validated",
        validated_at=F("created_at"),
    )


class Migration(migrations.Migration):
    dependencies = [("accounts", "0036_manager_cash_v1")]

    operations = [
        migrations.RunPython(mark_historical_transfers_validated, migrations.RunPython.noop),
    ]
