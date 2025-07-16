from django.core.management.base import BaseCommand
from syllabus.models import Ques

class Command(BaseCommand):
    help = "Standardize topic_name values in 'Systems' section, ignoring case and whitespace"

    def handle(self, *args, **kwargs):
        # Normalized mapping (all lower and stripped)
        normalized_mapping = {
            'the supreme court': 'Supreme Court',
            'supreme court': 'Supreme Court',
            'the union executive': 'Union Executive',
            'union executive': 'Union Executive',
            'governor: appointment, powers, removal': 'State Executive',
            'state executive': 'State Executive',
        }

        total_updated = 0

        # Get all Ques entries in Systems with no FK topic
        qs = Ques.objects.filter(section_name='Systems', topic__isnull=True)

        for q in qs:
            normalized_name = q.topic_name.strip().lower() if q.topic_name else ''

            if normalized_name in normalized_mapping:
                corrected_name = normalized_mapping[normalized_name]
                if q.topic_name != corrected_name:
                    q.topic_name = corrected_name
                    q.save()
                    total_updated += 1
                    self.stdout.write(f"✅ Updated Q{q.q_no}: → '{corrected_name}'")

        self.stdout.write(self.style.SUCCESS(f"\n✅ Total corrected: {total_updated}"))