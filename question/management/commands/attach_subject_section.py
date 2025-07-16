from django.core.management.base import BaseCommand
from syllabus.models import Ques, Subject, Section

class Command(BaseCommand):
    help = "Attach Subject and Section foreign keys to Ques based on subject_name and section_name"

    def handle(self, *args, **kwargs):
        updated = 0
        skipped = 0

        for q in Ques.objects.all():
            changed = False

            # Match subject
            if not q.subject and q.subject_name:
                q.subject = Subject.objects.filter(name=q.subject_name.strip()).first()
                if q.subject:
                    changed = True
                else:
                    skipped += 1
                    continue  # Can't attach section without subject

            # Match section only if subject is set
            if not q.section and q.section_name and q.subject:
                q.section = Section.objects.filter(
                    subject=q.subject,
                    name=q.section_name.strip()
                ).first()
                if q.section:
                    changed = True
                else:
                    skipped += 1
                    continue

            if changed:
                q.save()
                updated += 1

        self.stdout.write(self.style.SUCCESS(
            f"✅ Subject and Section linking complete.\nUpdated: {updated}\nSkipped (no match): {skipped}"
        ))
