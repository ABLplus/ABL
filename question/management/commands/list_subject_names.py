from django.core.management.base import BaseCommand
from question.models import Question, Subject  # Adjust app name if needed

class Command(BaseCommand):
    help = "List unique subject_name values from Questions (2000–2012) with counts, and existing Subjects"

    def handle(self, *args, **kwargs):
        # 1. Get questions between 2000 and 2012
        qs = Question.objects.filter(year__gte=2000, year__lte=2012)

        # 2. Count questions for each unique subject_name
        subject_name_counts = {}
        for q in qs:
            if q.subject_name:
                subject_name_counts[q.subject_name] = subject_name_counts.get(q.subject_name, 0) + 1

        self.stdout.write("\n📚 Unique `subject_name` values in Questions (2000–2012) with question count:")
        for name in sorted(subject_name_counts):
            self.stdout.write(f"- {name}: {subject_name_counts[name]} question(s)")

        # 3. Print all Subject model entries
        subjects = Subject.objects.all().values_list('name', flat=True)
        self.stdout.write("\n✅ Existing Subjects in `Subject` model:")
        for s in sorted(subjects):
            self.stdout.write(f"- {s}")
