from django.db import models
from ckeditor.fields import RichTextField
from syllabus.models import Subject, Section, Topic, SubTopic
from django.core.exceptions import ValidationError


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
        ('pending', 'Pending'),
        ('review', 'Under Review'),
        ('checked', 'Checked'),
    ]
    CATEGORY_CHOICES = [
        ('Core', 'Core'),
        ('Derivative', 'Derivative'),
        ('Peripheral', 'Peripheral'),
    ]

    category= models.CharField(
        max_length=20, 
        choices=CATEGORY_CHOICES,
        blank=True,
        null=True,
        db_index=True
    )

    # ... your existing fields ...
    check_status = models.CharField(
        max_length=10,
        choices=CHECK_STATUS_CHOICES,
        default='pending',
        db_index=True
    )
    source_type = models.CharField(max_length=20, choices=[('PYQ', 'PYQ'), ('AI', 'AI')], default='PYQ')
    year = models.IntegerField(blank=True, null=True)
    exam_name = models.CharField(max_length=100, blank=True, null=True, default='CSE Prelims')    
        
    question_html = RichTextField()
    q_markdown = models.TextField(blank=True, null=True)
    option_a = models.TextField()
    option_b = models.TextField()
    option_c = models.TextField()
    option_d = models.TextField()
    correct_option = models.CharField(max_length=1)

    explanation_html = RichTextField(blank=True, null=True)
    explanation_generated = RichTextField(blank=True, null=True)

    difficulty_level = models.CharField(max_length=50, blank=True, null=True)
    nature = models.CharField(max_length=50, blank=True, null=True)
    

    # Additional fields for better context  
    unit=models.PositiveSmallIntegerField(null=True, blank=True)
    q_no= models.CharField(max_length=10, blank=True, null=True)
    
    subject_name = models.CharField(max_length=100, blank=True, null=True)
    section_name = models.CharField(max_length=100, blank=True, null=True)
    topic_name = models.CharField(max_length=100, blank=True, null=True)
    subtopic_name = models.CharField(max_length=150, blank=True, null=True)
    microtopic_name = models.CharField(max_length=150, blank=True, null=True)
    
    # ForeignKey relationships to syllabus models
    subject = models.ForeignKey(
    Subject,
    on_delete=models.SET_NULL,  # 👉 sets subject = NULL if related subject is deleted
    related_name='questions',
    null=True,                  # 👉 allow NULL in database
    blank=True                  # 👉 allow blank in forms/admin
) 
    section = models.ForeignKey(
    Section,
    on_delete=models.SET_NULL,  # 👉 sets subject = NULL if related subject is deleted
    related_name='questions',
    null=True,                  # 👉 allow NULL in database
    blank=True                  # 👉 allow blank in forms/admin
)
    topic = models.ForeignKey(
    Topic,
    on_delete=models.SET_NULL,  # 👉 sets subject = NULL if related subject is deleted
    related_name='questions',
    null=True,                  # 👉 allow NULL in database
    blank=True                  # 👉 allow blank in forms/admin
)
    subtopic = models.ForeignKey(
    SubTopic,
    on_delete=models.SET_NULL,  # 👉 sets subject = NULL if related subject is deleted
    related_name='questions',
    null=True,                  # 👉 allow NULL in database
    blank=True                  # 👉 allow blank in forms/admin
)
    olt_type = models.CharField(max_length=100, blank=True, null=True)
    olt= models.ForeignKey(
        OLT,
        on_delete=models.SET_NULL,
        related_name='questions',
        null=True,
        blank=True
    )
           

    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if self.check_status == 'checked':
            missing_fields = []
            if self.subject is None:
                missing_fields.append('subject')
            if self.section is None:
                missing_fields.append('section')
            if self.topic is None:
                missing_fields.append('topic')
            if self.olt is None:
                missing_fields.append('olt')

            if missing_fields:
                raise ValidationError(
                    f"Cannot mark as 'checked' unless these fields are filled: {', '.join(missing_fields)}"
                )

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.subject} - {self.question_html[:30]}..."


