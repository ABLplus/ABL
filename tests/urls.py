from django.urls import path
from . import views

urlpatterns = [
    path('dashboard/', views.dashboard, name='dashboard'),
    path('start_test/', views.start_test, name='start_test'),
    path('<int:test_id>/question/<int:serial>/', views.take_test, name='take_test'),
    path('test/<int:test_id>/proceed-to-submit/', views.proceed_to_submit, name='proceed_to_submit'),
    path('test/<int:test_id>/blind-attempt/', views.blind_attempt, name='blind_attempt'),
    path('test/<int:test_id>/submit/', views.submit_test, name='submit_test'),
    path('<int:test_id>/question/<int:serial>/reset/', views.reset_question, name='reset_question'),

]
    # path('<int:test_id>/complete/', views.complete_test, name='complete_test'),
    # path('<int:test_id>/summary/', views.test_summary, name='test_summary'),
