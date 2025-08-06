from django.core.management.base import BaseCommand
from question.models import Question
from syllabus.models import Subject

class Command(BaseCommand):
    help = "Assigns Subject FK to Question based on subject_name"

    def handle(self, *args, **options):
        # Mapping from Question.subject_name to Subject.name
        subject_mapping = {
            "Polity and Governance": "Polity and Governance",
            "Geography": "Geography",
            "Art and Culture": "Art and Culture",
            "Science and Technology": "Science and Technology",
            "Ancient and Medieval History": "Ancient-Medieval History",
            "Environment": "Environment",
            "History of Modern India": "Modern Indian History",
            "Economics": "Indian Economy",
            "Current Affairs": "Current Affairs",
            "Indian Art and Culture": "Art and Culture",
            "Basic Sciences": "Science and Technology",
            "Ecology and Environment": "Environment",
            "International Affairs and Institutions": "Current Affairs",
            "Basic Science (Biology)": "Science and Technology",
            "India and World": "Current Affairs",
            "World History": "Modern Indian History",
            "Social issues": "Polity and Governance",
            "Economy: External Sector": "Indian Economy",
            "Basic Science": "Science and Technology",
            "gs_unclassified": "Current Affairs",
            "Polity": "Polity and Governance",
        }

        updated_count = 0
        not_found_subjects = set()

        for q in Question.objects.all():
            subject_name = q.subject_name.strip()
            target_subject_name = subject_mapping.get(subject_name)

            if not target_subject_name:
                not_found_subjects.add(subject_name)
                continue

            try:
                subject = Subject.objects.get(name=target_subject_name)
                if q.subject != subject:
                    q.subject = subject
                    q.save()
                    updated_count += 1
            except Subject.DoesNotExist:
                self.stdout.write(self.style.WARNING(f"Subject not found: {target_subject_name}"))

        self.stdout.write(self.style.SUCCESS(f"Updated {updated_count} question(s)."))

        if not_found_subjects:
            self.stdout.write(self.style.WARNING("Unmapped subject names in questions:"))
            for s in sorted(not_found_subjects):
                self.stdout.write(f"  - {s}")
