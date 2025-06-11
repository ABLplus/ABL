from django.db import models
from ckeditor.fields import RichTextField


class Subject(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name

class Question(models.Model):
    source_type = models.CharField(max_length=20, choices=[('PYQ', 'PYQ'), ('AI', 'AI')], default='PYQ')
    year = models.IntegerField(blank=True, null=True)
    subject_name = models.CharField(max_length=100)

    subject=models.ForeignKey('Subject', on_delete=models.CASCADE, related_name='questions',
    null=True, blank=True)

    topic = models.CharField(max_length=100, blank=True, null=True)
    subtopic = models.CharField(max_length=100, blank=True, null=True)
    question_html = RichTextField()
    option_a = models.TextField()
    option_b = models.TextField()
    option_c = models.TextField()
    option_d = models.TextField()
    correct_option = models.CharField(max_length=1)
    difficulty_level = models.CharField(max_length=50, blank=True, null=True)
    nature = models.CharField(max_length=50, blank=True, null=True)
    explanation_html = RichTextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.id }-{self.subject} - {self.question_html[:30]}..."


