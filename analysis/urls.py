
from django.urls import path
from . import views

urlpatterns = [
    # Review / list view with filters


    path('dashboard/', views.dashboard, name='dashboard'),    
    path("dashboard/toggle-mode/", views.toggle_mode, name="dashboard_toggle_mode"),
    path("tests/filter-form/",views.test_filter_form,name="test_filter_form",),
    path("tests/history-page/", views.test_history_page, name="test_history_page"),
    path("tests/<int:test_id>/delete/", views.delete_test, name="delete_test"),
    path("user-pmi-recalc/", views.user_pmi_recalc, name="user_pmi_recalc"),
]
   
