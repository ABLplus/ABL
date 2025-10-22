from django.db import models
from ckeditor.fields import RichTextField
from django.utils import timezone



class Exam(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.name
    


class Subject(models.Model):
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='subjects')
    name = models.CharField(max_length=100)
    
    class Meta:
        unique_together = ('exam', 'name')

    def __str__(self):
        return f"{self.name} ({self.exam.name})"
    

class Section(models.Model):
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='sections',default=1)
    name = models.CharField(max_length=100)
    class Meta:
        unique_together = ('subject', 'name')
        ordering = ['id']  

    def __str__(self):
        return f"{self.name} ({self.subject.name})"  
    

class TopicTier(models.TextChoices):
    MOST = "most", "Most Asked"
    GENERAL = "general", "Generally Asked"
    RARE = "rare", "Rarely Asked"
    NEVER = "never", "Never Asked"

class Topic(models.Model):
    section   = models.ForeignKey("syllabus.Section", on_delete=models.CASCADE, related_name="topics")
    name      = models.CharField(max_length=100)
    weightage = models.FloatField(default=0)  # weightage %
    tier      = models.CharField(             # <-- renamed from asked_band
        max_length=10,
        choices=TopicTier.choices,
        default=TopicTier.NEVER,
        db_index=True
    )

    class Meta:
        unique_together = ("section", "name")
        ordering = ["id"]

    def __str__(self):
        return f"{self.name} ({self.section.name})"


class SubTopic(models.Model):
    topic = models.ForeignKey(Topic, on_delete=models.CASCADE, related_name='subtopics')
    name = models.CharField(max_length=100)

    class Meta:
        unique_together = ('topic', 'name')
        ordering = ['id']

    def __str__(self):
        return f"{self.name} ({self.topic.name})"


class MicroTopic(models.Model):
    subtopic = models.ForeignKey(SubTopic, on_delete=models.CASCADE, related_name='microtopics')
    name = models.CharField(max_length=150)

    class Meta:
        unique_together = ('subtopic', 'name')
        ordering = ['id']

    def __str__(self):
        return f"{self.name} ({self.subtopic.name})"

class Ques(models.Model):
    q_no = models.CharField(max_length=10)
    q_statement = RichTextField()
    q_markdown = RichTextField(blank=True, null=True)
    a = models.TextField()
    b = models.TextField()
    c = models.TextField()
    d = models.TextField()
    correct_option = models.CharField(max_length=1)
    explanation = RichTextField(blank=True, null=True)
    exp_generated= RichTextField(blank=True, null=True)
   
    exam = models.CharField(max_length=100)
    year = models.IntegerField(blank=True, null=True)    
    
    # ForeignKey relationships to syllabus models
    
    subject = models.ForeignKey(Subject, on_delete=models.SET_NULL, null=True, blank=True)
    section= models.ForeignKey(Section, on_delete=models.SET_NULL, null=True, blank=True)
    topic = models.ForeignKey(Topic, on_delete=models.SET_NULL, null=True, blank=True)
    subtopic = models.ForeignKey(SubTopic, on_delete=models.SET_NULL, null=True, blank=True)
    microtopic = models.ForeignKey(MicroTopic, on_delete=models.SET_NULL, null=True, blank=True)
    
    # Additional fields for better context  
    unit=models.PositiveSmallIntegerField(null=True, blank=True)
    subject_name = models.CharField(max_length=100, blank=True, null=True)
    section_name = models.CharField(max_length=100, blank=True, null=True)
    topic_name = models.CharField(max_length=100, blank=True, null=True)
    subtopic_name = models.CharField(max_length=150, blank=True, null=True)
    microtopic_name = models.CharField(max_length=150, blank=True, null=True)

    olt_type=models.CharField(max_length=100, blank=True, null=True)
   
    olt = models.ForeignKey(
            'question.OLT',
            on_delete=models.SET_NULL,
            related_name='ques_set',       #  <-- another unique name
            null=True,
            blank=True,
        )


    is_check = models.BooleanField(default=False)
    for_review = models.BooleanField(default=False)


    
    added_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(  auto_now=True)

    def __str__(self):
        return f"Q{self.q_no} ({self.year} - {self.exam})"
