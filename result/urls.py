from django.urls import path
from . import views

urlpatterns = [
    path('result/<int:test_id>/', views.test_result, name='test_result'),
    path('<int:test_id>/<str:attempt_type>/', views.attempt_type_detail, name='attempt_type_detail'),

    # path('result/<int:test_id>/<str:attempt_type>/', views.attempt_type_detail, name='attempt_type_detail'),  # for future
]