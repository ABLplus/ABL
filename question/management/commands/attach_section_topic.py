from django.core.management.base import BaseCommand
from syllabus.models import Ques, Section, Topic
import re


name_of_section="Systems"
def normalize(text):
    if not text:
        return ""
    return re.sub(r'\s+', ' ', text.strip().lower().replace('–', '-').replace('—', '-'))

class Command(BaseCommand):
    help = "Attach Topic ForeignKey to Ques objects for section 'Bodies' based on topic_name (normalized match)"

    
    def handle(self, *args, **kwargs):
        try:
            section = Section.objects.get(name=name_of_section, subject__name='Polity')
        except Section.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"❌ Section {name_of_section} under subject 'Polity' not found."))
            return

        topics = Topic.objects.filter(section=section)
        topic_map = {normalize(t.name): t for t in topics}

        updated = 0
        unmatched = 0

        ques_queryset = Ques.objects.filter(section_name=name_of_section)

        for q in ques_queryset:
            norm_name = normalize(q.topic_name)

            if norm_name in topic_map:
                q.topic = topic_map[norm_name]
                q.save()
                updated += 1
            else:
                unmatched += 1
                self.stdout.write(self.style.WARNING(f"⚠ No match for Q{q.q_no}: '{q.topic_name}'"))

        self.stdout.write(self.style.SUCCESS(f"\n✅ Done. {updated} Ques updated. {unmatched} unmatched."))
