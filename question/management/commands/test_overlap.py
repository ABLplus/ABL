
from django.core.management.base import BaseCommand, CommandError
from tests.models import QuestionLog, Test


class Command(BaseCommand):
    help = "Print overlapping Question IDs between two Test IDs"

    def add_arguments(self, parser):
        parser.add_argument("test_id_1", type=int, help="First Test ID")
        parser.add_argument("test_id_2", type=int, help="Second Test ID")

    def handle(self, *args, **options):
        t1_id = options["test_id_1"]
        t2_id = options["test_id_2"]

        # validate tests exist
        if not Test.objects.filter(id=t1_id).exists():
            raise CommandError(f"Test {t1_id} does not exist")

        if not Test.objects.filter(id=t2_id).exists():
            raise CommandError(f"Test {t2_id} does not exist")

        t1_qs = QuestionLog.objects.filter(test_id=t1_id)
        t2_qs = QuestionLog.objects.filter(test_id=t2_id)

        t1_count = t1_qs.count()
        t2_count = t2_qs.count()

        if t1_count == 0 or t2_count == 0:
            self.stdout.write(self.style.WARNING("One of the tests has no questions"))
            return

        # subquery for intersection
        t2_question_ids = t2_qs.values("question_id")

        overlap_qs = (
            t1_qs
            .filter(question_id__in=t2_question_ids)
            .values_list("question_id", flat=True)
            .distinct()
            .order_by("question_id")
        )

        overlap_ids = list(overlap_qs)
        overlap_count = len(overlap_ids)

        # output summary
        self.stdout.write(self.style.SUCCESS("=== TEST OVERLAP REPORT ==="))
        self.stdout.write(f"Test A ID        : {t1_id}")
        self.stdout.write(f"Test B ID        : {t2_id}")
        self.stdout.write(f"Questions in A   : {t1_count}")
        self.stdout.write(f"Questions in B   : {t2_count}")
        self.stdout.write(f"Overlaps         : {overlap_count}")
        self.stdout.write(
            f"Overlap % (A)    : {overlap_count / t1_count * 100:.2f}%"
        )
        self.stdout.write(
            f"Overlap % (B)    : {overlap_count / t2_count * 100:.2f}%"
        )

        # print question ids
        self.stdout.write("\nOverlapping Question IDs:")
        for qid in overlap_ids:
            self.stdout.write(f"  - {qid}")

        if overlap_count == 0:
            self.stdout.write(self.style.SUCCESS("\nNo overlap detected 🎉"))