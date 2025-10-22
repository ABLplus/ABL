from django.urls import path

from django.urls import path
from . import views
app_name = "question"
urlpatterns = [
    # Review / list view with filters
    path('questions/', views.question_list, name='question_list'),
     path("question_summary/", views.question_summary, name="question_summary"),

    path("questions-status/", views.questions_check_status_tree, name="questions_check_status_tree"),


    # HTMX endpoints for chained Subject → Section → Topic → Subtopic
    path('questions/sections/',  views.ajax_sections,   name='ajax_sections'),
    path('questions/topics/',    views.ajax_topics,     name='ajax_topics'),
    path('questions/subtopics/', views.ajax_subtopics,  name='ajax_subtopics'),

    # Standard CRUD & attempt routes
    path('questions/add/',       views.add_question,    name='add_question'),
    path('questions/edit/<int:pk>/',   views.edit_question,   name='edit_question'),
    path('questions/delete/<int:pk>/', views.delete_question, name='delete_question'),
    path('attempt/',             views.attempt_question, name='attempt_question'),

    # AJAX endpoint for question search
    path('ajax/question/<int:pk>/sections/',  views.ajax_question_sections,  name='ajax_question_sections'),
    path('ajax/question/<int:pk>/topics/',    views.ajax_question_topics,    name='ajax_question_topics'),
    path('ajax/question/<int:pk>/subtopics/', views.ajax_question_subtopics, name='ajax_question_subtopics'),

    #Actuion Button routes for question status updates
    path("<int:pk>/check-save/", views.check_save, name="check_save"),
    path("<int:pk>/mark-review/", views.mark_review, name="mark_review"),
    path("<int:pk>/reset/", views.reset_status, name="reset_status"),


    path('subjects/', views.subject_summary, name='subject_summary'),
]