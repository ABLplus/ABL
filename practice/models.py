from django.db import models
from syllabus.models import Subject, Section, Topic, SubTopic


class PracticeSession(models.Model):
    user = models.ForeignKey('auth.User', on_delete=models.CASCADE, db_index=True)

    name = models.CharField(max_length=255, blank=True, null=True)

    # Syllabus hierarchy
    subject = models.ForeignKey(Subject, on_delete=models.SET_NULL, null=True, blank=True, related_name='practice_sessions')
    section = models.ForeignKey(Section, on_delete=models.SET_NULL, null=True, blank=True, related_name='practice_sessions')
    topic = models.ForeignKey(Topic, on_delete=models.SET_NULL, null=True, blank=True, related_name='practice_sessions')
    subtopic = models.ForeignKey(SubTopic, on_delete=models.SET_NULL, null=True, blank=True, related_name='practice_sessions')

    # Session Stats
    total_questions = models.PositiveIntegerField(default=0)
    correct_answers = models.PositiveIntegerField(default=0)
    unattempted = models.PositiveIntegerField(default=0)
    total_score = models.DecimalField(max_digits=6, decimal_places=2, default=0.0)

    # Attempt Type Tracking
    sureshot_attempts = models.PositiveIntegerField(default=0)
    applied_attempts = models.PositiveIntegerField(default=0)
    guesswork_attempts = models.PositiveIntegerField(default=0)
    blind_attempts = models.PositiveIntegerField(default=0)

    sureshot_wrong = models.PositiveIntegerField(default=0)
    applied_wrong = models.PositiveIntegerField(default=0)
    guesswork_wrong = models.PositiveIntegerField(default=0)
    blind_wrong = models.PositiveIntegerField(default=0)

    # Timestamps
    start_time = models.DateTimeField(auto_now_add=True)
    end_time = models.DateTimeField(blank=True, null=True)

    # Status
    status = models.CharField(
        max_length=20,
        choices=[('pending', 'Pending'), ('completed', 'Completed')],
        default='pending',
        db_index=True
    )

    def wrong_answers(self):
        return self.total_questions - self.correct_answers - self.unattempted

    def __str__(self):
        return f"PracticeSession {self.id} - {self.user.username} - {self.name or 'Unnamed'}"

    def save(self, *args, **kwargs):
        if not self.name:
            parts = []
            if self.subject:
                parts.append(self.subject.name)
            if self.section:
                parts.append(self.section.name)
            if self.topic:
                parts.append(self.topic.name)
            if self.subtopic:
                parts.append(self.subtopic.name)
            self.name = " | ".join(parts) or f"Practice Session {self.pk or ''}"
        super().save(*args, **kwargs)


