from django.contrib import admin
from .models import Test, QuestionLog, QuestionAttemptSummary

@admin.register(Test)
class TestAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'name', 'year', 'status', 'start_time', 'end_time', 'total_questions', 'correct_answers')
    list_filter = ('status', 'year', 'test_type')
    search_fields = ('user__username', 'name', 'subject', 'topic', 'exam')
    ordering = ('-start_time',)
    readonly_fields = ('start_time', 'end_time')

@admin.register(QuestionLog)
class QuestionLogAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'question', 'test', 'serial', 'user_answered', 'attempt_result', 'attempt_type','timestamp')
    list_filter = ('attempt_result', 'attempt_type')
    search_fields = ('user__username', 'question__id')
    ordering = ('-timestamp',)
    readonly_fields = ('timestamp',)

@admin.register(QuestionAttemptSummary)
class QuestionAttemptSummaryAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'question', 'total_attempts', 'correct_attempts', 'wrong_attempts', 'net_marks')
    search_fields = ('user__username', 'question__id')
    ordering = ('user', 'question')
