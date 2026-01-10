# analysis/models.py
from django.db import models
from django.conf import settings

# Create your models here.
class Errortype(models.Model):
    name = models.CharField(max_length=100, unique=True)
    category = models.CharField(max_length=100, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    user = models.ForeignKey(
        'auth.User', on_delete=models.CASCADE, related_name='errortypes'
    )
    is_predefined = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class TopicStatus(models.Model):
    user    = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="topic_statuses")
    exam    = models.ForeignKey("syllabus.Exam",    on_delete=models.CASCADE, related_name="topic_statuses")
    subject = models.ForeignKey("syllabus.Subject", on_delete=models.CASCADE, related_name="topic_statuses")
    section = models.ForeignKey("syllabus.Section", on_delete=models.CASCADE,
                                related_name="topic_statuses", null=True, blank=True)
    topic   = models.ForeignKey("syllabus.Topic",   on_delete=models.CASCADE, related_name="topic_statuses")

    practice_rounds          = models.PositiveIntegerField(default=0)
    test_questions_attempted = models.PositiveIntegerField(default=0)
    test_questions_seen     = models.PositiveIntegerField(default=0)


    pmi = models.FloatField(null=True, blank=True, db_index=True)
    tmi = models.FloatField(null=True, blank=True, db_index=True)
    cmi = models.FloatField(null=True, blank=True, db_index=True)

    tci = models.FloatField(null=True, blank=True, db_index=True) # test coverage index attempted/seen

    pctwrong_practice = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    pctwrong_test     = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)

    # --- bucket (coarse) ---
    BUCKET_WEAK       = "weak"
    BUCKET_TRANSITION = "transition"
    BUCKET_STRONG     = "strong"

    BUCKET_CHOICES = [
        (BUCKET_WEAK, "Weak"),
        (BUCKET_TRANSITION, "Transition"),
        (BUCKET_STRONG, "Strong"),
    ]

    bucket_by_mastery = models.CharField(
        max_length=20,
        choices=BUCKET_CHOICES,
        blank=True,
        null=True,
        db_index=True,
    )
    bucket_by_pct = models.CharField(
        max_length=20,
        choices=BUCKET_CHOICES,
        blank=True,
        null=True,
        db_index=True,
    )
    # --- band (fine) ---
    BAND_HIGH   = "high"
    BAND_MEDIUM = "medium"
    BAND_LOW    = "low"

    BAND_CHOICES = [
        (BAND_HIGH,   "High"),
        (BAND_MEDIUM, "Medium"),
        (BAND_LOW,    "Low"),
    ]

    band = models.CharField(
        max_length=10,
        choices=BAND_CHOICES,
        blank=True,
        null=True,
        db_index=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("user", "topic")]
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["user", "subject"]),
            models.Index(fields=["user", "bucket_by_mastery"]),
            models.Index(fields=["user", "bucket_by_pct"]),
            models.Index(fields=["user", "band"]),
        ]

    def __str__(self):
        return f"TopicStatus(u={self.user_id}, t={self.topic_id}, bucket={self.bucket_by_mastery/self.bucket_by_pct}, band={self.band})"