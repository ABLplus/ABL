from django.contrib import admin
from .models import Question

@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ('subject_name', 'year', 'topic', 'subtopic')
    search_fields = ('subject_name', 'topic', 'subtopic')
