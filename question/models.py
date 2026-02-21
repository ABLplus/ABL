from django.db import models
from ckeditor.fields import RichTextField
from syllabus.models import Subject, Section, Topic, SubTopic
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from django.utils.html import strip_tags


class OLT(models.Model):
    code = models.CharField(max_length=100, unique=True)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    rules = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self):
        return f"{self.code}-{self.name}"


class Question(models.Model):

    CHECK_STATUS_CHOICES = [
        ("pending", "Pending"),
        ("review", "Under Review"),
        ("checked", "Checked"),
    ]

    CATEGORY_CHOICES = [
        ("Core", "Core"),
        ("Derivative", "Derivative"),
        ("Peripheral", "Peripheral"),
    ]

    QUESTION_CLASS_CHOICES = [
        ("PYQ", "PYQ"),
        ("A", "Class A"),
        ("B", "Class B"),
        ("C", "Class C"),
        ("D", "Class D"),
        ("E", "Class E"),
    ]

    # -------------------------
    # Control / workflow
    # -------------------------
    category = models.CharField(
        max_length=20,
        choices=CATEGORY_CHOICES,
        blank=True,
        null=True,
        db_index=True,
    )

    check_status = models.CharField(
        max_length=10,
        choices=CHECK_STATUS_CHOICES,
        default="pending",
        db_index=True,
    )

    is_active = models.BooleanField(default=True, db_index=True)

    # -------------------------
    # Origin / classification
    # -------------------------
    source_type = models.CharField(
        max_length=20,
        choices=[("PYQ", "PYQ"), ("AI", "AI")],
        default="PYQ",
        db_index=True,
    )

    q_class = models.CharField(
        max_length=3,
        choices=QUESTION_CLASS_CHOICES,
        default="PYQ",
        db_index=True,
    )

    base_question = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="variants",
        db_index=True,
    )

    # -------------------------
    # Exam context
    # -------------------------
    year = models.IntegerField(blank=True, null=True, db_index=True)  # PYQ year / exam year
    exam_name = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        default="CSE Prelims",
        db_index=True,
    )

    # -------------------------
    # Question content
    # -------------------------
    question_html = RichTextField()
    q_markdown = models.TextField(blank=True, null=True)

    image = models.CharField(max_length=200, blank=True, null=True)

    option_a = models.TextField()
    option_b = models.TextField()
    option_c = models.TextField()
    option_d = models.TextField()
    correct_option = models.CharField(max_length=1)

    explanation_html = RichTextField(blank=True, null=True)
    explanation_generated = RichTextField(blank=True, null=True)

    difficulty_level = models.CharField(max_length=50, blank=True, null=True)
    nature = models.CharField(max_length=50, blank=True, null=True)

    # -------------------------
    # Additional fields
    # -------------------------
    unit = models.PositiveSmallIntegerField(null=True, blank=True)
    q_no = models.CharField(max_length=10, blank=True, null=True, db_index=True)

    # Snapshot strings (optional convenience; keep if used in templates/exports)
    subject_name = models.CharField(max_length=100, blank=True, null=True)
    section_name = models.CharField(max_length=100, blank=True, null=True)
    topic_name = models.CharField(max_length=100, blank=True, null=True)
    subtopic_name = models.CharField(max_length=150, blank=True, null=True)
    microtopic_name = models.CharField(max_length=150, blank=True, null=True)

    # -------------------------
    # Syllabus Foreign Keys
    # -------------------------
    subject = models.ForeignKey(
        Subject,
        on_delete=models.SET_NULL,
        related_name="questions",
        null=True,
        blank=True,
        db_index=True,
    )

    section = models.ForeignKey(
        Section,
        on_delete=models.SET_NULL,
        related_name="questions",
        null=True,
        blank=True,
        db_index=True,
    )

    topic = models.ForeignKey(
        Topic,
        on_delete=models.SET_NULL,
        related_name="questions",
        null=True,
        blank=True,
        db_index=True,
    )

    subtopic = models.ForeignKey(
        SubTopic,
        on_delete=models.SET_NULL,
        related_name="questions",
        null=True,
        blank=True,
        db_index=True,
    )

    olt_type = models.CharField(max_length=100, blank=True, null=True)

    olt = models.ForeignKey(
        OLT,
        on_delete=models.SET_NULL,
        related_name="questions",
        null=True,
        blank=True,
        db_index=True,
    )

    # -------------------------
    # Current Affairs tagging
    # - Daily news: set current_date (year/month auto-filled)
    # - Monthly CA: set current_year + current_month
    # -------------------------
    is_current_related = models.BooleanField(default=False, db_index=True)

    current_year = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        db_index=True,
        validators=[MinValueValidator(2000), MaxValueValidator(2030)],
    )

    current_month = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        db_index=True,
        validators=[MinValueValidator(1), MaxValueValidator(12)],
    )

    current_date = models.DateField(null=True, blank=True, db_index=True)

    current_source = models.CharField(max_length=200, blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["exam_name", "subject", "is_active"]),
            models.Index(fields=["q_class", "is_active"]),
            models.Index(fields=["current_year", "current_month"]),
        ]

    # -------------------------
    # Convenience
    # -------------------------
    @property
    def is_current(self) -> bool:
        """
        Current if:
        - current_date is set (daily news), OR
        - current_year is set (monthly CA tagging).
        """
        return bool(self.current_date or self.current_year)

    # -------------------------
    # Validation
    # -------------------------
    def clean(self):
        super().clean()
        today = timezone.localdate()

        # If current_date is provided, derive year/month automatically
        if self.current_date:
            self.current_year = self.current_date.year
            self.current_month = self.current_date.month

        # Rule 1: current_date cannot be in the future
        if self.current_date and self.current_date > today:
            raise ValidationError({"current_date": "Current date cannot be in the future."})

        # Rule 2: current_year cannot be in the future
        if self.current_year and self.current_year > today.year:
            raise ValidationError({"current_year": "Current year cannot be in the future."})

        # Rule 3: (current_year, current_month) cannot be a future month
        if self.current_year and self.current_month:
            if (self.current_year > today.year) or (
                self.current_year == today.year and self.current_month > today.month
            ):
                raise ValidationError({"current_month": "Current year/month cannot be in the future."})

        # Rule 4: if current_year is set, current_month must be set (monthly CA)
        if self.current_year and not self.current_month:
            raise ValidationError({"current_month": "Current month is required when current_year is set."})

        # Rule 5 (optional strictness): month without year is invalid
        if self.current_month and not self.current_year:
            raise ValidationError({"current_year": "Current year is required when current_month is set."})

        # Rule 6: Variant integrity (ABL+)
        if self.q_class != "PYQ" and self.base_question is None:
            raise ValidationError({"base_question": "Non-PYQ question_class (A–E) must have base_question set."})

        if self.q_class == "PYQ" and self.base_question is not None:
            raise ValidationError({"base_question": "PYQ question_class must not have base_question set."})

        # Rule 7: Checked questions must have anchors
        if self.check_status == "checked":
            missing = []
            if self.subject is None:
                missing.append("subject")
            if self.section is None:
                missing.append("section")
            if self.topic is None:
                missing.append("topic")
            if self.olt is None:
                missing.append("olt")

            if missing:
                raise ValidationError(
                    {"check_status": f"Cannot mark as 'checked' unless filled: {', '.join(missing)}"}
                )

    def save(self, *args, **kwargs):
        # Ensures validators + clean() run always (admin/shell/scripts)
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        subj = self.subject.name if self.subject else (self.subject_name or "Unknown Subject")
        preview = strip_tags(self.question_html)[:30] if self.question_html else ""
        return f"{subj} - {preview}..."


