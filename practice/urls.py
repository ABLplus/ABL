# practice/urls.py

from django.urls import path
from . import views

app_name = 'practice'

urlpatterns = [
    # Practice Home (list pending, form, history)
    path('practice/', views.practice_home, name='practice_home'),
    path("history-page/", views.history_page, name="history_page"),

    path('create_capsule/', views.create_capsule, name='create_capsule'),

    # HTMX endpoints for chained dropdowns
    path('ajax/sections/',   views.ajax_load_sections,   name='ajax_load_sections'),
    path('ajax/topics/',     views.ajax_load_topics,     name='ajax_load_topics'),
    path('ajax/subtopics/',  views.ajax_load_subtopics,  name='ajax_load_subtopics'),

    # HTMX endpoint for subject-wise syllabus tree
    path('ajax/subject_tree/<int:subject_id>/', views.ajax_subject_tree, name='ajax_subject_tree'),

    path("topics/<int:topic_id>/modal/", views.topic_modal, name="topic_modal"),
    
    path("subject-modal/<int:subject_id>/", views.subject_modal, name="subject_modal"),
    path("section-modal/<int:section_id>/", views.section_modal, name="section_modal"),
    
    path("modal/empty/", views.modal_empty, name="modal_empty"),

    path("subject/<int:subject_id>/sections/", views.ajax_subject_sections,
         name="ajax_subject_sections"),

    # Create a new PracticeSession
    path('create/', views.create_practice, name='create_practice'),

    # Take a PracticeSession (question-by-question interface)
    path("take/<int:session_id>/", views.take_practice, name="take_practice"),
    # HTMX endpoints
    path(
    "take/<int:session_id>/q/<int:serial>/",
    views.practice_question_htmx,
    name="practice_question_htmx",
),
    path(
        "summary/<int:session_id>/",
        views.practice_summary,
        name="practice_summary",
    ),

    path("topic-summary/", views.topic_summary, name="topic_summary"),

    
]
