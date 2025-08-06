from django.db import models, transaction
from django.utils import timezone
from datetime import timedelta
from django.contrib.auth.models import User 
from django.db.models.signals import post_save
from django.dispatch import receiver
from syllabus.models import Exam


    
class Profile(models.Model):
    """
    Extended user profile for the ABL+ platform.
    Keeps all engagement counters in one row for fast dashboard reads.
    """

    # ── 1. Core link ──────────────────────────────────────────────────
    user = models.OneToOneField(User, on_delete=models.CASCADE)

    # ── 2. Contact & exam meta (captured at onboarding) ───────────────
    mobile_number = models.CharField(max_length=15, blank=True, null=True)

    exam= models.ForeignKey(Exam, on_delete=models.SET_NULL, null=True, blank=True)


    exam_date = models.DateField(null=True, blank=True)
    
    exam_year = models.PositiveSmallIntegerField(null=True, blank=True)

    mode= models.CharField(max_length=10, choices=[('practice', 'Practice'), ('test', 'Test')], default='practice')
    

    # ── 3. Onboarding reflection fields ───────────────────────────────
    pledge   = models.TextField(
        blank=True,
        help_text="User-written pledge captured during onboarding."
    )
    why_exam = models.TextField(
        blank=True,
        verbose_name="Why are you preparing?",
        help_text="Personal reason or motivation statement."
    )

    # ── 4. Engagement counters & streak bookkeeping ───────────────────
    date_joined   = models.DateField(auto_now_add=True)

    days_active   = models.PositiveIntegerField(default=0)   # Day 1 = signup
    streak_questions_target = models.PositiveIntegerField(default=100)
    streak_days   = models.PositiveIntegerField(default=0)

    # Internal dates / counters (all local-date based)
    last_seen_on          = models.DateField(auto_now_add=True)
    last_attempt_day      = models.DateField(null=True, blank=True)
    last_attempt_count    = models.PositiveIntegerField(default=0)
    last_streak_credit_on = models.DateField(null=True, blank=True)

    # ── 5. Flags ──────────────────────────────────────────────────────
    is_onboarded = models.BooleanField(default=False)  
    is_verified = models.BooleanField(default=False)  # New field for verification status

    # ── 6. Helpers ────────────────────────────────────────────────────
    def __str__(self):
        return self.user.username

    # Called once per question attempt ────────────────────────────────
    def register_attempt(self, increment: int):
        """
        Bump engagement counters.
        • `increment` defaults to 1 but can be >1 if you batch-log attempts.
        """
        today     = timezone.localdate()
        yesterday = today - timedelta(days=1)

        with transaction.atomic():
            p = type(self).objects.select_for_update().get(pk=self.pk)

            # 1️⃣ active-day
            if p.last_attempt_day != today:
                p.days_active       += 1
                p.last_attempt_day   = today
                p.last_attempt_count = 0

            # 2️⃣ daily question tally
            p.last_attempt_count += increment

            # 3️⃣ streak credit (once per day)
            if (
                p.last_attempt_count >= p.streak_questions_target and
                p.last_streak_credit_on != today
            ):
                p.streak_days = (
                    p.streak_days + 1
                    if p.last_streak_credit_on == yesterday
                    else 1
                )
                p.last_streak_credit_on = today

            p.save(update_fields=[
                "days_active",
                "last_attempt_day",
                "last_attempt_count",
                "streak_days",
                "last_streak_credit_on",
            ])

    # Called from middleware on first request of each day ─────────────
    def reset_if_new_day(self):
        today = timezone.localdate()
        if self.last_seen_on == today:          # already processed today
            return

        yesterday = today - timedelta(days=1)
        if self.last_streak_credit_on != yesterday:
            self.streak_days = 0                # streak broken

        self.last_attempt_count = 0             # fresh daily tally
        self.last_seen_on       = today
        self.save(update_fields=[
            "streak_days", "last_attempt_count", "last_seen_on"
        ])



# Signal to create or update Profile when User is created or updated
@receiver(post_save, sender=User)
def create_or_update_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)
    instance.profile.save()