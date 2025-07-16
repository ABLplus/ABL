from django.core.management.base import BaseCommand
from django.db import transaction
from syllabus.models import Ques

REPLACEMENT_LIST = {
    None :                         "Not Defined",

   
    
}
class Command(BaseCommand):
    help = "Normalize the `exam` field on Ques using the REPLACEMENT_LIST mapping"

    def handle(self, *args, **options):
        total_changed = 0
        with transaction.atomic():
            for old, new in REPLACEMENT_LIST.items():
                qs = Ques.objects.filter(exam=old)
                count = qs.count()
                if count == 0:
                    continue

                if new is None:
                    # If you want to clear or skip NULL variants
                    qs.update(exam="")
                else:
                    qs.update(exam=new)

                total_changed += count
                self.stdout.write(
                    f"→ {count:4d} rows: '{old}' → '{new or ''}'"
                )

        self.stdout.write(self.style.SUCCESS(
            f"✅ Normalization complete: {total_changed} rows updated."
        ))