from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db import transaction

from user.models import Subscription


class Command(BaseCommand):
    help = (
        "Populate a Basic subscription for every existing user who does not "
        "already have any subscription."
    )

    def handle(self, *args, **options):
        User = get_user_model()

        # Only users with NO subscriptions at all
        users_without_sub = (
            User.objects
            .filter(subscriptions__isnull=True)
            .distinct()
        )

        total_users = users_without_sub.count()
        created = 0

        if total_users == 0:
            self.stdout.write(self.style.WARNING(
                "No users without subscriptions found. Nothing to do."
            ))
            return

        self.stdout.write(f"Found {total_users} users without subscriptions.")
        self.stdout.write("Creating Basic subscriptions...")

        for user in users_without_sub.iterator():
            with transaction.atomic():
                # Double-check inside the transaction, in case something was
                # created between the initial query and now.
                if Subscription.objects.filter(user=user).exists():
                    continue

                sub = Subscription(
                    user=user,
                    plan=Subscription.PLAN_BASIC,
                )
                # Set limits according to Basic plan (700 total, no expiry)
                sub.apply_plan_limits()
                sub.save()
                created += 1

        self.stdout.write(self.style.SUCCESS(
            f"Created Basic subscriptions for {created} user(s)."
        ))
