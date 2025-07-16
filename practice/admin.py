from django.contrib import admin
from .models import PracticeSession

@admin.register(PracticeSession)
class PracticeSessionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "subject",
        "section",
        "topic",
        "subtopic",
        "total_questions",
        "status",
        "start_time",
        "end_time",
    )
    list_filter   = ("status", "subject", "section", "topic")
    search_fields = (
        "user__username",
        "subject__name",
        "section__name",
        "topic__name",
        "subtopic__name",
    )
    date_hierarchy = "start_time"
    ordering       = ("-start_time",)