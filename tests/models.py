from django.db import models
from question.models import *
from django.contrib.auth.models import User
from practice.models import PracticeSession
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils import timezone



class TestTemplate(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, db_index=True)

    exam = models.ForeignKey('syllabus.Exam', on_delete=models.CASCADE, null=True, blank=True, db_index=True)
    year = models.IntegerField(null=True, blank=True, db_index=True)

    subject = models.ForeignKey('syllabus.Subject', on_delete=models.CASCADE, null=True, blank=True, db_index=True)
    section = models.ForeignKey('syllabus.Section', on_delete=models.CASCADE, null=True, blank=True, db_index=True)

    is_olt_filters = models.BooleanField(default=False)   # keep if you'll use it; otherwise remove
    no_of_attempts = models.PositiveIntegerField(default=0)
    last_attempted = models.DateTimeField(auto_now=True)

    class Meta:
        # One template per (user, exam, year) *only when* subject & section are NULL (exam–year mode)
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'exam', 'year'],
                condition=Q(subject__isnull=True, section__isnull=True),
                name='uniq_exam_year_template_per_user',
            ),
        ]

    def __str__(self):
        return f"Tmpl[{self.pk}] u={self.user} exam={self.exam} year={self.year} subj={self.subject} sec={self.section} attempts={self.no_of_attempts}"

class Test(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, db_index=True)
    attempt_serial=models.PositiveSmallIntegerField(default=1)
    name = models.CharField(max_length=255, blank=True, null=True)
    template = models.ForeignKey(TestTemplate, on_delete=models.SET_NULL, null=True, blank=True, db_index=True)
    test_type = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        choices=[
            ('full_length', 'Full-Length Test'),
            ('sectional', 'Sectional Test'),
            ('micro', 'Micro Test')
        ]
    )
    exam = models.CharField(max_length=255, blank=True, null=True)

    year = models.IntegerField(db_index=True, blank=True, null=True)

    total_questions = models.PositiveIntegerField(default=0)
    correct_answers = models.PositiveIntegerField(default=0)
    unattempted = models.PositiveIntegerField(default=0)
    total_score = models.DecimalField(max_digits=6, decimal_places=2, default=0.0)

    sureshot_attempts = models.PositiveIntegerField(default=0)
    applied_attempts = models.PositiveIntegerField(default=0)
    guesswork_attempts = models.PositiveIntegerField(default=0)
    blind_attempts = models.PositiveIntegerField(default=0)

    sureshot_wrong = models.PositiveIntegerField(default=0)
    applied_wrong = models.PositiveIntegerField(default=0)
    guesswork_wrong = models.PositiveIntegerField(default=0)
    blind_wrong = models.PositiveIntegerField(default=0)

    start_time = models.DateTimeField(auto_now_add=True)
    end_time = models.DateTimeField(blank=True, null=True)

    total_marks = models.DecimalField(max_digits=6, decimal_places=2, default=0.0)
    score= models.DecimalField(max_digits=6, decimal_places=2, default=0.0)

    

    status = models.CharField(
        max_length=20,
        choices=[('pending', 'Pending'), ('completed', 'Completed')],
        default='pending',
        db_index=True
    )

    def wrong_answers(self):
        return self.total_questions - self.correct_answers - self.unattempted

    def __str__(self):
        return f"Test {self.id} - {self.user.username} - {self.name or 'Unnamed'}"

class QuestionLog(models.Model):
    user = models.ForeignKey('auth.User', on_delete=models.CASCADE, db_index=True)
    question = models.ForeignKey('question.Question', on_delete=models.CASCADE, db_index=True)

    # Exactly one of these must be set (enforced below)
    test = models.ForeignKey('Test', on_delete=models.CASCADE, blank=True, null=True, db_index=True)
    practiceSession = models.ForeignKey('practice.PracticeSession', on_delete=models.CASCADE, blank=True, null=True, db_index=True)

    # Display/ordering position inside the test/practice session
    serial = models.PositiveIntegerField(blank=True, null=True)

    # Snapshot to avoid joins for summaries
    topic = models.ForeignKey('syllabus.Topic', on_delete=models.SET_NULL, blank=True, null=True, db_index=True)

    user_answered = models.CharField(
        max_length=1,
        blank=True,
        null=True,
        choices=[('a', 'a'), ('b', 'b'), ('c', 'c'), ('d', 'd')]
    )

    attempt_type = models.CharField(
        max_length=11,
        blank=True,
        default='unattempted',
        choices=[
            ('sureshot', 'Sureshot'),
            ('applied', 'Applied'),
            ('guesswork', 'Guesswork'),
            ('blind', 'Blind Attempt'),
            ('unattempted', 'Unattempted'),
        ]
    )

    attempt_result = models.CharField(
        max_length=5,
        blank=True,
        null=True,
        choices=[('right', 'Right'), ('wrong', 'Wrong')]
    )

    timestamp = models.DateTimeField(auto_now_add=True, blank=True, null=True)
    time_taken_seconds = models.PositiveIntegerField(blank=True, null=True)

    

    class Meta:
        ordering = ["serial", "timestamp"]

        indexes = [
            models.Index(fields=["user", "question"], name="ql_user_question_idx"),
            models.Index(fields=["user", "topic"], name="ql_user_topic_idx"),
            # add others later only if a real query pattern needs them
        ]

        constraints = [
            models.CheckConstraint(
            condition=(
                models.Q(test__isnull=False, practiceSession__isnull=True) |
                models.Q(test__isnull=True, practiceSession__isnull=False)
            ),
            name='only_one_mode_active',
        ),
            models.UniqueConstraint(fields=["test", "question"], name="unique_question_per_test"),
            models.UniqueConstraint(fields=["test", "serial"], name="unique_serial_per_test"),
            models.UniqueConstraint(fields=["practiceSession", "question"], name="unique_question_per_practice"),
            models.UniqueConstraint(fields=["practiceSession", "serial"], name="unique_serial_per_practice"),
        ]

    # ── Validation & helpers ──
    def clean(self):
        # Exactly one of test/practiceSession must be set
        if bool(self.test) == bool(self.practiceSession):
            raise ValidationError("QuestionLog must be linked to either a Test or a PracticeSession, not both or neither.")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        mode = 'Test' if self.test_id else 'Practice'
        return f"{getattr(self.user, 'username', self.user_id)} - Q{self.question_id} ({mode})"

    def is_test_attempt(self):
        return self.test_id is not None

    def is_practice_attempt(self):
        return self.practiceSession_id is not None

class TopicAttemptSummary(models.Model):
    """Aggregated attempt stats for a (user, topic, mode) tuple."""

    MODE_CHOICES = [
        ('practice', 'Practice'),
        ('test',     'Test'),
    ]

    # Identifiers
    user  = models.ForeignKey(User, on_delete=models.CASCADE, db_index=True)
    topic = models.ForeignKey('syllabus.Topic', on_delete=models.CASCADE, db_index=True)
    mode  = models.CharField(max_length=8, choices=MODE_CHOICES)

    total_test_questions     = models.PositiveIntegerField(default=0)

    # Attempt outcomes
    
    total_attempts   = models.PositiveIntegerField(default=0)
    correct_attempts = models.PositiveIntegerField(default=0)
    wrong_attempts   = models.PositiveIntegerField(default=0)

    # Attempt-type breakdowns
    sureshot_attempts  = models.PositiveIntegerField(default=0)
    applied_attempts   = models.PositiveIntegerField(default=0)
    guesswork_attempts = models.PositiveIntegerField(default=0)
    blind_attempts     = models.PositiveIntegerField(default=0)

    # Wrong counts per attempt-type
    sureshot_wrong  = models.PositiveIntegerField(default=0)
    applied_wrong   = models.PositiveIntegerField(default=0)
    guesswork_wrong = models.PositiveIntegerField(default=0)
    blind_wrong     = models.PositiveIntegerField(default=0)

    last_n_questions_test =models.JSONField(default=list)  # store last N question IDs attempted in this topic-mode

    # Scoring (keep same formula you use elsewhere)
    net_marks = models.DecimalField(max_digits=6, decimal_places=2, default=0.0)
    

    last_updated = models.DateTimeField(auto_now=True, blank=True, null=True)

    # ──────────────────────────────────────────────────────────
    # Meta & helpers
    # ──────────────────────────────────────────────────────────
    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'topic', 'mode'],
                name='unique_user_topic_mode_summary'
            ),
        ]
        indexes = [
            models.Index(fields=['user', 'topic', 'mode']),
        ]
        ordering = ['user', 'topic', 'mode']

    def __str__(self):
        return f"{self.user.username} · {self.topic.name} · {self.mode}"

    # Quick stats
    @property
    def accuracy(self):
        return 0 if self.total_attempts == 0 else (self.correct_attempts / self.total_attempts) * 100

    @property
    def wrong_rate(self):
        return 0 if self.total_attempts == 0 else (self.wrong_attempts / self.total_attempts) * 100

class QuestionAttemptSummary(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, db_index=True)
    question = models.ForeignKey('question.Question', on_delete=models.CASCADE, db_index=True)
    topic= models.ForeignKey('syllabus.Topic', on_delete=models.SET_NULL, blank=True, null=True, db_index=True)

    # Attempt Outcomes
    total_attempts = models.PositiveIntegerField(default=0)
    correct_attempts = models.PositiveIntegerField(default=0)
    wrong_attempts = models.PositiveIntegerField(default=0)

    # Attempt Types
    sureshot_attempts = models.PositiveIntegerField(default=0)
    applied_attempts = models.PositiveIntegerField(default=0)
    guesswork_attempts = models.PositiveIntegerField(default=0)
   

    # Wrong Attempts per Attempt Type
    sureshot_wrong = models.PositiveIntegerField(default=0)
    applied_wrong = models.PositiveIntegerField(default=0)
    guesswork_wrong = models.PositiveIntegerField(default=0)
    

    # Scoring
    net_marks = models.DecimalField(max_digits=6, decimal_places=2, default=0.0)
    last_attempted = models.DateTimeField(auto_now=True, blank=True, null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'question'], name='unique_user_question_summary')
        ]
        indexes = [
            models.Index(fields=['user', 'question']),  # (redundant if UniqueConstraint also automatically indexes, but still safe to specify)
        ]
        ordering = ['user', 'question']

    def __str__(self):
        return f"{self.user.username} - Question {self.question.id} Summary"

    @property
    def accuracy(self):
        """Return accuracy % for this question."""
        if self.total_attempts == 0:
            return 0
        return (self.correct_attempts / self.total_attempts) * 100

    @property
    def wrong_rate(self):
        """Return wrong % for this question."""
        if self.total_attempts == 0:
            return 0
        return (self.wrong_attempts / self.total_attempts) * 100

class TopicOLTSummary(models.Model):
    MODE_CHOICES = [
        ("practice", "Practice"),
        ("test", "Test"),
    ]

    user  = models.ForeignKey(User, on_delete=models.CASCADE)
    subject= models.ForeignKey("syllabus.Subject", on_delete=models.CASCADE)
    section = models.ForeignKey("syllabus.Section", on_delete=models.CASCADE, null=True, blank=True)
    topic = models.ForeignKey("syllabus.Topic", on_delete=models.CASCADE)
    olt   = models.ForeignKey("question.OLT", on_delete=models.CASCADE)
    mode  = models.CharField(max_length=10, choices=MODE_CHOICES)

    # Attempts
    total_attempts   = models.PositiveIntegerField(default=0)
    correct_attempts = models.PositiveIntegerField(default=0)
    wrong_attempts   = models.PositiveIntegerField(default=0)

    # Attempt types
    sureshot_attempts  = models.PositiveIntegerField(default=0)
    applied_attempts   = models.PositiveIntegerField(default=0)
    guesswork_attempts = models.PositiveIntegerField(default=0)

    sureshot_wrong  = models.PositiveIntegerField(default=0)
    applied_wrong   = models.PositiveIntegerField(default=0)
    guesswork_wrong = models.PositiveIntegerField(default=0)

    # Optional score / mastery
    net_marks      = models.FloatField(default=0.0)
    

    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("user", "topic", "olt", "mode")]
        indexes = [
            models.Index(fields=["user", "topic", "mode"]),
            models.Index(fields=["user", "olt", "mode"]),
        ]

    def __str__(self):
        return f"{self.user} · {self.topic} · {self.olt} · {self.mode}"