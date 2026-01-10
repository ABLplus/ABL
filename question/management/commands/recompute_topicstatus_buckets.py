# question/management/commands/recompute_topicstatus_buckets.py

from django.core.management.base import BaseCommand
from django.db import transaction

from analysis.models import TopicStatus


class Command(BaseCommand):
    help = "Recompute TopicStatus.bucket_by_mastery from pmi and bucket_by_pct from pctwrong_practice for all rows."

    def handle(self, *args, **options):
        STRONG = TopicStatus.BUCKET_STRONG
        TRANSITION = TopicStatus.BUCKET_TRANSITION
        WEAK = TopicStatus.BUCKET_WEAK

        # Thresholds (same as your dashboard logic)
        PMI_STRONG = 70.0
        PMI_WEAK = 40.0
        PCT_STRONG = 30.0
        PCT_WEAK = 70.0

        qs = TopicStatus.objects.all()

        updated = []
        mastery_changes = 0
        pct_changes = 0

        self.stdout.write(f"Scanning {qs.count()} TopicStatus rows...")

        for ts in qs.iterator(chunk_size=2000):
            changed = False

            # --- bucket_by_mastery from pmi ---
            if ts.pmi is not None:
                if ts.pmi >= PMI_STRONG:
                    new_mastery = STRONG
                elif ts.pmi <= PMI_WEAK:
                    new_mastery = WEAK
                else:
                    new_mastery = TRANSITION

                if ts.bucket_by_mastery != new_mastery:
                    ts.bucket_by_mastery = new_mastery
                    mastery_changes += 1
                    changed = True

            # --- bucket_by_pct from pctwrong_practice ---
            if ts.pctwrong_practice is not None:
                pct = float(ts.pctwrong_practice)
                if pct <= PCT_STRONG:
                    new_pct = STRONG
                elif pct >= PCT_WEAK:
                    new_pct = WEAK
                else:
                    new_pct = TRANSITION

                if ts.bucket_by_pct != new_pct:
                    ts.bucket_by_pct = new_pct
                    pct_changes += 1
                    changed = True

            if changed:
                updated.append(ts)

        if not updated:
            self.stdout.write(self.style.SUCCESS("✅ Nothing to update."))
            return

        with transaction.atomic():
            TopicStatus.objects.bulk_update(
                updated,
                fields=["bucket_by_mastery", "bucket_by_pct"],
                batch_size=2000,
            )

        self.stdout.write(self.style.SUCCESS("✅ Buckets recomputed and saved."))
        self.stdout.write(f"Updated rows: {len(updated)}")
        self.stdout.write(f"bucket_by_mastery changes: {mastery_changes}")
        self.stdout.write(f"bucket_by_pct changes: {pct_changes}")
