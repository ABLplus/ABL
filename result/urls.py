from django.urls import path
from . import views

urlpatterns = [
    path('result/<int:test_id>/', views.test_result, name='test_result'),
    path('<int:test_id>/<str:attempt_type>/', views.attempt_type_detail, name='attempt_type_detail'),
    path("topic-summary/", views.topic_summary, name="topic_summary"),
    path('daily-engagement/', views.daily_engagement_report, name='daily_engagement'),


    path("question-log-history/", views.question_log_history_view, name="question_log_history_view"),
]

    # path('result/<int:test_id>/<str:attempt_type>/', views.attempt_type_detail, name='attempt_type_detail'),  # for future
