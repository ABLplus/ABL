from django.contrib import admin
from syllabus.models import *


from .models import TopicDemand


@admin.register(TopicDemand)
class TopicDemandAdmin(admin.ModelAdmin):
    list_display = (
        "exam_name",
        "get_subject",
        "get_section",
        "topic",
        "pyq_count",
        "created_at",
        "updated_at",
    )

    list_filter = (
        "exam_name",
        "topic__section__subject",
        "topic__section",
        "created_at",
    )

    search_fields = (
        "exam_name",
        "topic__name",
        "topic__section__name",
        "topic__section__subject__name",
        "demand_insights",
    )

    readonly_fields = ("created_at", "updated_at")

    ordering = ("-created_at",)

    def get_subject(self, obj):
        return obj.topic.section.subject.name
    get_subject.short_description = "Subject"

    def get_section(self, obj):
        return obj.topic.section.name
    get_section.short_description = "Section"



class SubTopicInline(admin.TabularInline):
    model = SubTopic
    extra = 1

class TopicInline(admin.TabularInline):
    model = Topic
    extra = 1

class SectionInline(admin.TabularInline):
    model = Section
    extra = 1

class TopicAdmin(admin.ModelAdmin):
    inlines = [SubTopicInline]

class SectionAdmin(admin.ModelAdmin):
    inlines = [TopicInline]

class SubjectAdmin(admin.ModelAdmin):
    inlines = [SectionInline]

admin.site.register(Exam)
admin.site.register(Subject, SubjectAdmin)
admin.site.register(Section, SectionAdmin)
admin.site.register(Topic, TopicAdmin)
admin.site.register(SubTopic)


@admin.register(Ques)
class QuesAdmin(admin.ModelAdmin):
    list_display = ('q_no', 'q_statement', 'is_check', 'for_review')

