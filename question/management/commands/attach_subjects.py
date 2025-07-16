from django.core.management.base import BaseCommand
from question.models import Question, Subject
from django.db import transaction

class Command(BaseCommand):
    help = "Attach existing Subject to Question.subject based on subject_name for years 2000–2012"

    # Manual mapping from Question.subject_name → Subject.name
    SUBJECT_MAPPING = {
        'Ancient and Medieval History': 'Ancient and Medieval History',
        'Indian Art and Culture': 'Art and Culture',
        'Current Affairs': 'Current Affairs',
        'Economics': 'Economics',
        'Economy: External Sector': 'Economics',
        'Ecology and Environment': 'Environment',
        'Environment': 'Environment',
        'Geography': 'Geography',
        'History of Modern India': 'History of Modern India',
        'India and World': 'History of Modern India',
        'World History': 'History of Modern India',
        'Polity and Governance': 'Polity and Governance',
        'International Affairs and Institutions': 'Polity and Governance',
        'Social issues': 'Polity and Governance',
        'Science and Technology': 'Science and Technology',
        'Basic Science': 'Science and Technology',
        'Basic Science (Biology)': 'Science and Technology',
        'Basic Sciences': 'Science and Technology',
    }

    EXCLUDED = {'CSAT', 'gs_unclassified'}

    def handle(self, *args, **kwargs):
        updated_count = 0
        unmatched = set()

        with transaction.atomic():
            questions = Question.objects.filter(year__gte=2000, year__lte=2012)
            for q in questions:
                if q.subject is not None or not q.subject_name:
                    continue
                if q.subject_name in self.EXCLUDED:
                    continue

                mapped_subject = self.SUBJECT_MAPPING.get(q.subject_name)
                if mapped_subject:
                    try:
                        subject = Subject.objects.get(name=mapped_subject)
                        q.subject = subject
                        q.save(update_fields=['subject'])
                        updated_count += 1
                    except Subject.DoesNotExist:
                        unmatched.add(q.subject_name)
                else:
                    unmatched.add(q.subject_name)

        self.stdout.write(f"\n✅ Attached Subjects to {updated_count} questions.")
        if unmatched:
            self.stdout.write("\n⚠️ Unmatched subject_name values:")
            for name in sorted(unmatched):
                self.stdout.write(f"- {name}")
