from decimal import Decimal, ROUND_HALF_UP

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Sum

from analysis.models import TopicStatus
from tests.models import TopicAttemptSummary


PRACTICE_MODE = "practice"
TEST_MODE = "test"


def pct_wrong(wrong: int, total: int):
    """
    Return wrong percentage as Decimal(0.01) rounded to 2 dp, or None if total == 0.
    """
    if not total:
        return None
    val = (Decimal(wrong) * Decimal("100")) / Decimal(total)
    return val.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class Command(BaseCommand):
    help = (
        "Populate TopicStatus.pctwrong_practice, pctwrong_test and "
        "test_questions_attempted from TopicAttemptSummary."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--practice-mode",
            default=PRACTICE_MODE,
            help='Mode value in TopicAttemptSummary for practice (default: "practice")',
        )
        parser.add_argument(
            "--test-mode",
            default=TEST_MODE,
            help='Mode value in TopicAttemptSummary for test (default: "test")',
        )

    def handle(self, *args, **options):
        practice_mode = options["practice_mode"]
        test_mode = options["test_mode"]

        self.stdout.write("Aggregating TopicAttemptSummary...")

        summaries = (
            TopicAttemptSummary.objects
            .values("user_id", "topic_id", "mode")
            .annotate(
                total_attempts_sum=Sum("total_attempts"),
                wrong_attempts_sum=Sum("wrong_attempts"),
            )
        )

        # lookup structure:
        # {(user_id, topic_id): {"pct": {mode: pct}, "total": {mode: total}}}
        lookup = {}
        for row in summaries:
            total = int(row["total_attempts_sum"] or 0)
            wrong = int(row["wrong_attempts_sum"] or 0)
            pct = pct_wrong(wrong, total)

            key = (row["user_id"], row["topic_id"])
            bucket = lookup.setdefault(key, {"pct": {}, "total": {}})
            bucket["pct"][row["mode"]] = pct
            bucket["total"][row["mode"]] = total

        self.stdout.write(
            f"Found {len(summaries)} user-topic-mode rows. Updating TopicStatus..."
        )

        to_update = []
        qs = TopicStatus.objects.all().only(
            "id",
            "user_id",
            "topic_id",
            "pctwrong_practice",
            "pctwrong_test",
            "test_questions_attempted",
        )

        for ts in qs:
            data = lookup.get((ts.user_id, ts.topic_id), {"pct": {}, "total": {}})

            ts.pctwrong_practice = data["pct"].get(practice_mode)
            ts.pctwrong_test = data["pct"].get(test_mode)

            # Update attempted questions count from TEST mode total attempts
            ts.test_questions_attempted = data["total"].get(test_mode, 0)

            to_update.append(ts)

        with transaction.atomic():
            TopicStatus.objects.bulk_update(
                to_update,
                ["pctwrong_practice", "pctwrong_test", "test_questions_attempted"],
            )

        self.stdout.write(self.style.SUCCESS(f"Updated {len(to_update)} TopicStatus rows."))
