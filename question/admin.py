from django.contrib import admin
from .models import *


@admin.register(OLT)
class OLTAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'description', 'rules', 'created_at')
    search_fields = ('code', 'name')

@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ('subject_name', 'subject', 'section', 'topic','subtopic' , 'year', 'topic_name', 'subtopic_name')
    search_fields = ('subject_name', 'topic_name', 'subtopic_name')


