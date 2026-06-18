from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),

    path('api/risk-ranking/', views.risk_ranking_chart, name='api_risk_ranking'),
    path('api/risk-trend/', views.risk_trend_data, name='api_risk_trend'),
    path('api/temp-humidity/', views.temp_humidity_trend, name='api_temp_humidity'),
    path('api/warning-trend/', views.warning_trend_api, name='api_warning_trend'),
    path('api/warning-by-granary/', views.warning_by_granary_api, name='api_warning_by_granary'),

    path('grain-types/', views.GrainTypeListView.as_view(), name='grain_type_list'),
    path('grain-types/create/', views.GrainTypeCreateView.as_view(), name='grain_type_create'),
    path('grain-types/<int:pk>/update/', views.GrainTypeUpdateView.as_view(), name='grain_type_update'),
    path('grain-types/<int:pk>/delete/', views.GrainTypeDeleteView.as_view(), name='grain_type_delete'),

    path('granaries/', views.GranaryListView.as_view(), name='granary_list'),
    path('granaries/create/', views.GranaryCreateView.as_view(), name='granary_create'),
    path('granaries/<int:pk>/', views.GranaryDetailView.as_view(), name='granary_detail'),
    path('granaries/<int:pk>/update/', views.GranaryUpdateView.as_view(), name='granary_update'),
    path('granaries/<int:pk>/delete/', views.GranaryDeleteView.as_view(), name='granary_delete'),

    path('th-logs/', views.THLogListView.as_view(), name='th_log_list'),
    path('th-logs/create/', views.THLogCreateView.as_view(), name='th_log_create'),
    path('th-logs/<int:pk>/update/', views.THLogUpdateView.as_view(), name='th_log_update'),
    path('th-logs/<int:pk>/delete/', views.THLogDeleteView.as_view(), name='th_log_delete'),

    path('ventilations/', views.VentilationLogListView.as_view(), name='ventilation_list'),
    path('ventilations/create/', views.VentilationLogCreateView.as_view(), name='ventilation_create'),
    path('ventilations/<int:pk>/update/', views.VentilationLogUpdateView.as_view(), name='ventilation_update'),
    path('ventilations/<int:pk>/delete/', views.VentilationLogDeleteView.as_view(), name='ventilation_delete'),

    path('pests/', views.PestInspectionListView.as_view(), name='pest_list'),
    path('pests/create/', views.PestInspectionCreateView.as_view(), name='pest_create'),
    path('pests/<int:pk>/update/', views.PestInspectionUpdateView.as_view(), name='pest_update'),
    path('pests/<int:pk>/delete/', views.PestInspectionDeleteView.as_view(), name='pest_delete'),

    path('risks/', views.RiskAssessmentListView.as_view(), name='risk_list'),
    path('risks/<int:pk>/', views.RiskAssessmentDetailView.as_view(), name='risk_detail'),
    path('risks/generate/', views.generate_risk_assessments, name='risk_generate'),
    path('risks/<int:pk>/process/', views.process_risk, name='risk_process'),

    path('warnings/', views.WarningListView.as_view(), name='warning_list'),
    path('warnings/dashboard/', views.warning_dashboard, name='warning_dashboard'),
    path('warnings/create/', views.warning_create, name='warning_create'),
    path('warnings/<int:pk>/', views.WarningDetailView.as_view(), name='warning_detail'),
    path('warnings/generate/', views.generate_warnings, name='warning_generate'),
    path('warnings/check-overdue/', views.check_overdue_warnings, name='warning_check_overdue'),
    path('warnings/<int:warning_pk>/assign-task/', views.task_assign, name='warning_assign_task'),

    path('tasks/', views.TaskListView.as_view(), name='task_list'),
    path('tasks/<int:pk>/', views.TaskDetailView.as_view(), name='task_detail'),
    path('tasks/<int:pk>/update-progress/', views.task_update_progress, name='task_update_progress'),
    path('tasks/<int:pk>/submit-review/', views.task_submit_review, name='task_submit_review'),
    path('tasks/<int:pk>/review/', views.task_review, name='task_review'),
    path('tasks/<int:pk>/redo/', views.task_redo, name='task_redo'),
    path('tasks/<int:pk>/archive/', views.task_archive, name='task_archive'),
]
