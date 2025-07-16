from django.contrib import admin
from syllabus.models import *



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

