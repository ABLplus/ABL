from django.urls import path
from . import views

urlpatterns = [

    path('ques/', views.ques_list, name='ques_list'),
    path('ques/<int:pk>/edit/', views.edit_ques, name='edit_ques'),
    path('exams/', views.exams_view, name='exams_view'),
    path('exam/<int:exam_id>/', views.exam_detail_view, name='exam_detail'),
    path('subject/<int:subject_id>/', views.subject_detail_view, name='subject_detail'),
    

    # full page with filters
    path("edit/", views.ques_edit_view, name="ques_edit"),
    
    path('ques_summary/', views.ques_summary_view, name='ques_summary'),




    path('htmx/section-dropdown/', views.get_section_dropdown, name='get_section_dropdown'),
    path('htmx/topic-dropdown/', views.get_topic_dropdown, name='get_topic_dropdown'),
    path('htmx/subtopic-dropdown/', views.get_subtopic_dropdown, name='get_subtopic_dropdown'),

    path('ques/<int:pk>/generate_explanation/', views.generate_explanation, name='generate_explanation'),

    path('section-tree/', views.section_topic_subtopic_view, name='section_tree'),

   
]
