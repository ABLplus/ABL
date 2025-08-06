from django.core.management.base import BaseCommand
from django.db import transaction

from question.models import Question

class Command(BaseCommand):
    help = "Assign section FK on Questions that have a topic but no section"

    def handle(self, *args, **options):
        qs = Question.objects.filter(topic__isnull=False, section__isnull=True)
        total = qs.count()
        if not total:
            self.stdout.write(self.style.SUCCESS("Nothing to do."))
            return

        self.stdout.write(f"Found {total} questions without section. Updating…")
        with transaction.atomic():
            for q in qs.select_related('topic__section'):
                q.section = q.topic.section
                q.save(update_fields=['section'])
        self.stdout.write(self.style.SUCCESS(f"Updated {total} questions."))