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

    tci = models.FloatField(null=True, blank=True, db_index=True) # test coverage index attempted/seen

    

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("user", "topic")]
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["user", "subject"]),
           
        ]

    def __str__(self):
        return f"TopicStatus(u={self.user_id}, t={self.topic_id}"