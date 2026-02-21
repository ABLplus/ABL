
from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.contrib.auth import get_user_model

from tests.models import TopicAttemptSummary
from user.models import UserOverallStats

User = get_user_model()
MODES = ("practice", "test")


def empty_mode_dict():
    return {m: 0 for m in MODES}


class Command(BaseCommand):
    help = "Rebuild UserOverallStats from TopicAttemptSummary (practice + test)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--user",
            type=int,
            help="Optional user_id to rebuild stats for a single user",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        user_id = options.get("user")

        qs = TopicAttemptSummary.objects.all()
        if user_id:
            qs = qs.filter(user_id=user_id)

        rows = (
            qs.values("user_id", "mode")
              .annotate(
                  total_attempts=Coalesce(Sum("total_attempts"), 0),
                  total_correct=Coalesce(Sum("correct_attempts"), 0),
                  total_wrong=Coalesce(Sum("wrong_attempts"), 0),

                  sureshot_attempts=Coalesce(Sum("sureshot_attempts"), 0),
                  applied_attempts=Coalesce(Sum("applied_attempts"), 0),
                  guesswork_attempts=Coalesce(Sum("guesswork_attempts"), 0),

                  sureshot_wrong=Coalesce(Sum("sureshot_wrong"), 0),
                  applied_wrong=Coalesce(Sum("applied_wrong"), 0),
                  guesswork_wrong=Coalesce(Sum("guesswork_wrong"), 0),
              )
        )

        per_user = defaultdict(lambda: {
            "total_attempts": empty_mode_dict(),
            "total_correct": empty_mode_dict(),
            "total_wrong": empty_mode_dict(),
            "sureshot_attempts": empty_mode_dict(),
            "applied_attempts": empty_mode_dict(),
            "guesswork_attempts": empty_mode_dict(),
            "sureshot_wrong": empty_mode_dict(),
            "applied_wrong": empty_mode_dict(),
            "guesswork_wrong": empty_mode_dict(),
        })

        for r in rows:
            uid = r["user_id"]
            mode = r["mode"]

            if mode not in MODES:
                continue

            per_user[uid]["total_attempts"][mode] = r["total_attempts"]
            per_user[uid]["total_correct"][mode] = r["total_correct"]
            per_user[uid]["total_wrong"][mode] = r["total_wrong"]

            per_user[uid]["sureshot_attempts"][mode] = r["sureshot_attempts"]
            per_user[uid]["applied_attempts"][mode] = r["applied_attempts"]
            per_user[uid]["guesswork_attempts"][mode] = r["guesswork_attempts"]

            per_user[uid]["sureshot_wrong"][mode] = r["sureshot_wrong"]
            per_user[uid]["applied_wrong"][mode] = r["applied_wrong"]
            per_user[uid]["guesswork_wrong"][mode] = r["guesswork_wrong"]

        created, updated = 0, 0

        # Ensure single-user rebuild works even if TAS empty
        if user_id and user_id not in per_user:
            per_user[user_id]

        for uid, data in per_user.items():
            obj, is_created = UserOverallStats.objects.get_or_create(user_id=uid)

            obj.total_attempts = data["total_attempts"]
            obj.total_correct = data["total_correct"]
            obj.total_wrong = data["total_wrong"]

            obj.sureshot_attempts = data["sureshot_attempts"]
            obj.applied_attempts = data["applied_attempts"]
            obj.guesswork_attempts = data["guesswork_attempts"]

            obj.sureshot_wrong = data["sureshot_wrong"]
            obj.applied_wrong = data["applied_wrong"]
            obj.guesswork_wrong = data["guesswork_wrong"]

            obj.save()

            created += int(is_created)
            updated += int(not is_created)

        self.stdout.write(
            self.style.SUCCESS(
                f"Done | users={len(per_user)} created={created} updated={updated}"
            )
        )