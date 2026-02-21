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
    
    topicstatus_method = models.CharField(
    max_length=3,
    choices=[
        ("MAS", "Mastery indices"),
        ("PCT", "Percentage wrong"),
    ],
    default="PCT",
    db_index=True, )


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

    days_since_joined = models.PositiveIntegerField(default=0)
    days_since_active = models.PositiveIntegerField(default=0)

    total_practice_attempts = models.PositiveIntegerField(default=0)
    total_test_attempts     = models.PositiveIntegerField(default=0)

    # Internal dates / counters (all local-date based)
    last_seen_on          = models.DateField(auto_now_add=True)
    last_attempt_day      = models.DateField(null=True, blank=True)
    last_attempt_count    = models.PositiveIntegerField(default=0)
    last_streak_credit_on = models.DateField(null=True, blank=True)

    # ── 5. Flags ──────────────────────────────────────────────────────
    is_onboarded = models.BooleanField(default=False)  
    is_verified = models.BooleanField(default=False)  # New field for verification status
    is_paid_user = models.BooleanField(default=False)  # New field for paid user status
    subscription=models.ForeignKey('Subscription', on_delete=models.SET_NULL, null=True, blank=True)

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


class Subscription(models.Model):
    """
    Subscription + attempt limits for ABL+.

    Rules:
    - BASIC: 700 total attempts, no expiry, no daily cap.
    - BONUS: 1000 total attempts (700 + 300), no expiry, no daily cap.
    - PRO:   Unlimited total attempts, daily cap = 1200, has expiry date.
             Expiry date is inclusive (allowed ON expiry date, blocked AFTER).
    """

    # ─────────────────────────────
    # PLAN TYPES
    # ─────────────────────────────
    PLAN_BASIC = "basic"
    PLAN_BONUS = "bonus"
    PLAN_PRO   = "pro"

    PLAN_CHOICES = [
        (PLAN_BASIC, "Basic"),
        (PLAN_BONUS, "Bonus"),
        (PLAN_PRO,   "Pro"),
    ]

    STATUS_ACTIVE   = "active"
    STATUS_EXPIRED  = "expired"
    STATUS_CANCELLED= "cancelled"

    # ─────────────────────────────
    # CORE FIELDS
    # ─────────────────────────────
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="subscription",
        db_index=True,
    )
    

    plan = models.CharField(max_length=20, choices=PLAN_CHOICES)

    # Limits (configured from plan)
    total_attempts_limit = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="None = unlimited total attempts.",
    )
    daily_attempts_limit = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="None = no daily cap.",
    )

    # Usage counters
    total_attempts_booked = models.PositiveIntegerField(default=0)
    daily_attempts_booked = models.PositiveIntegerField(default=0)
    last_attempt_day    = models.DateField(null=True, blank=True)

    #  when Pro subscription was started / expires
    
    start_datetime  = models.DateTimeField(auto_now_add=True)
    expiry_datetime = models.DateTimeField(
        null=True, blank=True,
        help_text="Only relevant for PRO; Basic/Bonus usually keep this null.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-start_datetime"]
        indexes = [
            models.Index(fields=["user", "plan"]),
            models.Index(fields=["user", "start_datetime"]),
            models.Index(fields=["user", "expiry_datetime"]),
        ]

    def __str__(self):
        return f"{self.user.username} – {self.plan}"

    # ─────────────────────────────
    # PLAN → LIMITS MAPPING
    # ─────────────────────────────
    def apply_plan_limits(
        self,
        *,
        basic_limit: int = 700,
        bonus_limit: int = 1000,
        pro_daily_limit: int = 1000,
    ):
        """
        Set attempt limits based on current plan.

        Call this:
        - right after creating a subscription, or
        - when upgrading plan (Basic → Bonus → Pro).
        """
        if self.plan == self.PLAN_BASIC:
            self.total_attempts_limit = basic_limit
            self.daily_attempts_limit = None          # no daily cap
            self.expiry_datetime = None               # no expiry

        elif self.plan == self.PLAN_BONUS:
            self.total_attempts_limit = bonus_limit   # 700 + 300
            self.daily_attempts_limit = None          # no daily cap
            self.expiry_datetime = None               # no expiry

        elif self.plan == self.PLAN_PRO:
            self.total_attempts_limit = None          # unlimited total
            self.daily_attempts_limit = pro_daily_limit
            # expiry_datetime will be set by caller (e.g., now + 90 days)

        else:
            # Fallback: no limits, no expiry
            self.total_attempts_limit = None
            self.daily_attempts_limit = None

    # ─────────────────────────────
    # EXPIRY CHECK (Pro only)
    # ─────────────────────────────
    def is_within_expiry(self) -> bool:
        """
        For PRO plan:
            True if today <= expiry_date (inclusive).
        For BASIC/BONUS or no expiry:
            Always True.
        """
        # Basic / Bonus: ignore expiry
        if self.plan in [self.PLAN_BASIC, self.PLAN_BONUS]:
            return True

        # No expiry set: treat as unlimited
        if not self.expiry_datetime:
            return True

        today = timezone.localdate()
        expiry_date = self.expiry_datetime.date()

        # Inclusive expiry: allowed on the expiry date
        return today <= expiry_date

    # ─────────────────────────────
    # DAILY RESET
    # ─────────────────────────────
    def ensure_day(self):
        """
        Reset daily_attempts_booked when a new calendar day starts
        (based on local date).
        """
        today = timezone.localdate()
        if self.last_attempt_day != today:
            self.daily_attempts_booked = 0
            self.last_attempt_day = today

    # ─────────────────────────────
    # LIMIT CHECK (READ-ONLY)
    # ─────────────────────────────
    def can_attempt(self, increment: int = 1) -> bool:
        """
        Check if the user *can* attempt `increment` more questions,
        based on:
        - plan limits (total & daily)
        - expiry rules (for PRO)
        Does NOT write anything to the DB.
        """
        if not self.is_within_expiry():
            return False

        # Use in-memory counters; caller may or may not have persisted them
        self.ensure_day()

        # total limit check (if any)
        if self.total_attempts_limit is not None:
            if self.total_attempts_booked + increment > self.total_attempts_limit:
                return False

        # daily limit check (if any)
        if self.daily_attempts_limit is not None:
            if self.daily_attempts_booked + increment > self.daily_attempts_limit:
                return False

        return True

    # ─────────────────────────────
    # COUNT ATTEMPTS (WRITES)
    # ─────────────────────────────
    def count_attempts(self, increment: int = 1, *, strict: bool = True):
        """
        Count `increment` attempts toward this subscription.

        - Enforces:
            • expiry for PRO (inclusive expiry date)
            • total limit (Basic/Bonus)
            • daily cap (Pro)
        - Uses row-level locking to be safe under concurrency.
        - If strict=True and limits exceeded or expired:
            raises ValueError.
        - If strict=False:
            returns False when attempts are not allowed.
        """
        with transaction.atomic():
            sub = type(self).objects.select_for_update().get(pk=self.pk)

            # 1) Expiry / plan validity
            if not sub.is_within_expiry():
                if strict:
                    raise ValueError("Subscription expired for this plan.")
                return False

            # 2) Make sure daily counter is for today
            sub.ensure_day()

            # 3) Check limits on the locked row
            #    (re-implementing can_attempt inline to avoid double ensure_day)
            # total limit
            if sub.total_attempts_limit is not None:
                if sub.total_attempts_booked + increment > sub.total_attempts_limit:
                    if strict:
                        raise ValueError("Total attempt limit exceeded.")
                    return False

            # daily limit
            if sub.daily_attempts_limit is not None:
                if sub.daily_attempts_booked + increment > sub.daily_attempts_limit:
                    if strict:
                        raise ValueError("Daily attempt limit exceeded.")
                    return False

            # 4) All good → increment usage
            sub.total_attempts_booked += increment
            sub.daily_attempts_booked += increment

            sub.save(update_fields=[
                "total_attempts_booked",
                "daily_attempts_booked",
                "last_attempt_day",
                "updated_at",
            ])

        return True

class UserDailyStats(models.Model):
    """
    Minimal per-user, per-day statistics.
    Updated ONCE per session finalisation using aggregated QuestionLogs.
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE, db_index=True)
    date = models.DateField(db_index=True)

    #session
    practice_sessions = models.PositiveIntegerField(default=0)
    test_sessions     = models.PositiveIntegerField(default=0)

    total_attempts = models.PositiveIntegerField(default=0)
    total_correct  = models.PositiveIntegerField(default=0)     
    total_wrong    = models.PositiveIntegerField(default=0)

    # Attempts by type
    sureshot_attempts = models.PositiveIntegerField(default=0)
    applied_attempts  = models.PositiveIntegerField(default=0)
    guesswork_attempts    = models.PositiveIntegerField(default=0)

    # Wrong counts by type
    sureshot_wrong = models.PositiveIntegerField(default=0)
    applied_wrong  = models.PositiveIntegerField(default=0)
    guesswork_wrong    = models.PositiveIntegerField(default=0)

    # Time spent (in hours, decimal)
    practice_time = models.FloatField(default=0.0)   # e.g., 1.75 hours = 1h 45m
    test_time     = models.FloatField(default=0.0)

    #Daily coverage & mastery%
    coverage_pct = models.FloatField(default=0.0)  # % of syllabus topics attempted
    mastery_pct  = models.FloatField(default=0.0)  # % of attempted topics mastered (if using mastery system)
    

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("user", "date")
        indexes = [
            models.Index(fields=["user", "date"]),
        ]

    def __str__(self):
        return f"{self.user.username} – {self.date}"


class Payment(models.Model):
    """
    Immutable record of subscription-related payments.
    Use this to derive history (what user paid, when, for which plan).
    """

    # ---- Status choices -------------------------------------------------
    STATUS_INITIATED = "initiated"   # order created, payment not confirmed
    STATUS_SUCCESS   = "success"     # payment captured / verified
    STATUS_FAILED    = "failed"      # payment failed
    STATUS_REFUNDED  = "refunded"    # refunded fully or partially

    STATUS_CHOICES = [
        (STATUS_INITIATED, "Initiated"),
        (STATUS_SUCCESS,   "Success"),
        (STATUS_FAILED,    "Failed"),
        (STATUS_REFUNDED,  "Refunded"),
    ]

    # ---- Payment provider (optional but useful) ------------------------
    PROVIDER_RAZORPAY = "razorpay"
    PROVIDER_STRIPE   = "stripe"
    PROVIDER_OTHER    = "other"

    PROVIDER_CHOICES = [
        (PROVIDER_RAZORPAY, "Razorpay"),
        (PROVIDER_STRIPE,   "Stripe"),
        (PROVIDER_OTHER,    "Other / Manual"),
    ]

    # ---- Core relations -----------------------------------------------
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="payments",
        db_index=True,
    )

    # Snapshot of what plan this payment is for
    plan = models.CharField(
        max_length=20,
        choices=Subscription.PLAN_CHOICES,
        help_text="Plan that this payment is intended to activate or extend.",
    )

    # Optional: how long this purchase is for (mainly Pro)
    duration_days = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Number of days of PRO access this payment corresponds to (if applicable).",
    )

    # ---- Money fields ---------------------------------------------------
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(
        max_length=10,
        default="INR",
        help_text="ISO currency code, e.g., INR, USD."
    )

    # ---- Gateway / provider info ---------------------------------------
    provider = models.CharField(
        max_length=20,
        choices=PROVIDER_CHOICES,
        default=PROVIDER_RAZORPAY,
    )

    # IDs from gateway (Razorpay/Stripe/etc.)
    provider_order_id   = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Order ID from the payment gateway."
    )
    provider_payment_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Payment ID from the payment gateway."
    )
    provider_signature  = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Signature / HMAC sent by payment gateway for verification.",
    )

    # ---- Status & timestamps -------------------------------------------
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_INITIATED,
        db_index=True,
    )

    requested_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(
        null=True, blank=True,
        help_text="Set when payment moves to SUCCESS / FAILED / REFUNDED."
    )

    # Optional free-form metadata (for debugging / extra info)
    meta = models.JSONField(
        blank=True, null=True,
        help_text="Optional extra data from gateway or internal notes.",
    )

    class Meta:
        ordering = ["-requested_at"]
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["provider", "provider_order_id"]),
            models.Index(fields=["provider", "provider_payment_id"]),
        ]
        constraints = [
            # no strict uniqueness (because some providers reuse order IDs),
            # but you can uncomment if your gateway guarantees uniqueness:
            # models.UniqueConstraint(
            #     fields=["provider", "provider_payment_id"],
            #     name="uniq_provider_payment"
            # )
        ]

    def __str__(self):
        return f"{self.user} – {self.plan} – {self.amount} {self.currency} [{self.status}]"

    # Convenience helper
    def mark_success(self):
        self.status = self.STATUS_SUCCESS
        self.completed_at = timezone.now()
        self.save(update_fields=["status", "completed_at"])

    def mark_failed(self):
        self.status = self.STATUS_FAILED
        self.completed_at = timezone.now()
        self.save(update_fields=["status", "completed_at"])

    def mark_refunded(self):
        self.status = self.STATUS_REFUNDED
        self.completed_at = timezone.now()
        self.save(update_fields=["status", "completed_at"])

    
class UserOverallStats(models.Model):
    """
    Aggregate overall statistics per user.
    Updated ONCE per session finalisation using aggregated QuestionLogs.
    """

    user = models.OneToOneField(User, on_delete=models.CASCADE, db_index=True)

    # Overall counts 
    overall_attempts = models.PositiveIntegerField(default=0)
    
    #Test counts
    number_of_tests  = models.PositiveIntegerField(default=0)

    test_attempts    = models.PositiveIntegerField(default=0)
    test_correct     = models.PositiveIntegerField(default=0)
    test_wrong       = models.PositiveIntegerField(default=0)
    
    test_sureshot_attempts = models.PositiveIntegerField(default=0)
    test_applied_attempts  = models.PositiveIntegerField(default=0) 
    test_guesswork_attempts    = models.PositiveIntegerField(default=0)

    test_sureshot_wrong = models.PositiveIntegerField(default=0)
    test_applied_wrong  = models.PositiveIntegerField(default=0)    
    test_guesswork_wrong    = models.PositiveIntegerField(default=0)

    # Practice counts

    number_of_practice_sessions = models.PositiveIntegerField(default=0)

    practice_attempts= models.PositiveIntegerField(default=0)
    practice_correct = models.PositiveIntegerField(default=0)
    practice_wrong   = models.PositiveIntegerField(default=0)

    practice_sureshot_attempts = models.PositiveIntegerField(default=0)
    practice_applied_attempts  = models.PositiveIntegerField(default=0)
    practice_guesswork_attempts    = models.PositiveIntegerField(default=0)

    practice_sureshot_wrong = models.PositiveIntegerField(default=0)
    practice_applied_wrong  = models.PositiveIntegerField(default=0)
    practice_guesswork_wrong = models.PositiveIntegerField(default=0)


    # Time spent (in hours, decimal)
    practice_time = models.FloatField(default=0.0)   # e.g., 1.75 hours = 1h 45m
    test_time     = models.FloatField(default=0.0)

    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} – Overall Stats"