from django.db import models
from question.models import *
from django.contrib.auth.models import User


class Test(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, db_index=True)
    attempt_serial=models.PositiveSmallIntegerField(default=1)

    name = models.CharField(max_length=255, blank=True, null=True)
    subject = models.CharField(max_length=255, blank=True, null=True)
    topic = models.CharField(max_length=255, blank=True, null=True)
    sub_topic = models.CharField(max_length=255, blank=True, null=True)
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

    year = models.IntegerField(db_index=True)

    total_questions = models.PositiveIntegerField(default=0)
    correct_answers = models.PositiveIntegerField(default=0)
    unattempted = models.PositiveIntegerField(default=0)
    total_score = models.DecimalField(max_digits=6, decimal_places=2, default=0.0)

    sureshot_attempts = models.PositiveIntegerField(default=0)
    applied_attempts = models.PositiveIntegerField(default=0)
    guesswork_attempts = models.PositiveIntegerField(default=0)

    sureshot_wrong = models.PositiveIntegerField(default=0)
    applied_wrong = models.PositiveIntegerField(default=0)
    guesswork_wrong = models.PositiveIntegerField(default=0)
    blind_wrong = models.PositiveIntegerField(default=0)

    start_time = models.DateTimeField(auto_now_add=True)
    end_time = models.DateTimeField(blank=True, null=True)

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
    user = models.ForeignKey(User, on_delete=models.CASCADE, db_index=True)
    question = models.ForeignKey('question.Question', on_delete=models.CASCADE, db_index=True)
    test = models.ForeignKey('Test', on_delete=models.CASCADE, blank=True, null=True, db_index=True)

    serial = models.PositiveIntegerField(blank=True, null=True)  # Only meaningful if part of a Test

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

    timestamp = models.DateTimeField(auto_now_add=True)
    time_taken_seconds = models.PositiveIntegerField(blank=True, null=True)

    class Meta:
        ordering = ['timestamp']
        indexes = [
            models.Index(fields=['user', 'question']),
            models.Index(fields=['test', 'serial']),
        ]

    def __str__(self):
        mode = 'Test' if self.test else 'Practice'
        return f"{self.user.username} - Q{self.question.id} ({mode})"

    def is_test_attempt(self):
        return self.test is not None

    def is_practice_attempt(self):
        return self.test is None


class QuestionAttemptSummary(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, db_index=True)
    question = models.ForeignKey('question.Question', on_delete=models.CASCADE, db_index=True)

    # Attempt Outcomes
    total_attempts = models.PositiveIntegerField(default=0)
    correct_attempts = models.PositiveIntegerField(default=0)
    wrong_attempts = models.PositiveIntegerField(default=0)

    # Attempt Types
    sureshot_attempts = models.PositiveIntegerField(default=0)
    applied_attempts = models.PositiveIntegerField(default=0)
    guesswork_attempts = models.PositiveIntegerField(default=0)
    blind_attempts = models.PositiveIntegerField(default=0)

    # Wrong Attempts per Attempt Type
    sureshot_wrong = models.PositiveIntegerField(default=0)
    applied_wrong = models.PositiveIntegerField(default=0)
    guesswork_wrong = models.PositiveIntegerField(default=0)
    blind_wrong = models.PositiveIntegerField(default=0)

    # Scoring
    net_marks = models.DecimalField(max_digits=6, decimal_places=2, default=0.0)

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
