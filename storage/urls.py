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

    # Prediction API endpoints
    path('api/prediction-trend/', views.api_prediction_trend, name='api_prediction_trend'),
    path('api/risk-distribution/', views.api_risk_distribution, name='api_risk_distribution'),
    path('api/inventory-distribution/', views.api_inventory_distribution, name='api_inventory_distribution'),
    path('api/allocation-efficiency/', views.api_allocation_efficiency, name='api_allocation_efficiency'),
    path('api/allocation-by-granary/', views.api_allocation_by_granary, name='api_allocation_by_granary'),
    path('api/inventory-turnover/', views.api_inventory_turnover, name='api_inventory_turnover'),
    path('api/allocation-trend/', views.api_allocation_trend, name='api_allocation_trend'),
    path('api/allocation-status/', views.api_allocation_status, name='api_allocation_status'),
    path('api/turnover-trend/', views.api_turnover_trend, name='api_turnover_trend'),
    path('api/granary-turnover/', views.api_granary_turnover, name='api_granary_turnover'),
    path('api/risk-reduction/', views.api_risk_reduction, name='api_risk_reduction'),
    path('api/allocation-cost/', views.api_allocation_cost, name='api_allocation_cost'),

    # Prediction views
    path('prediction/', views.prediction_dashboard, name='prediction_dashboard'),
    path('prediction/generate/', views.generate_predictions, name='prediction_generate'),
    path('prediction/list/', views.prediction_list, name='prediction_list'),
    path('prediction/<int:pk>/', views.prediction_detail, name='prediction_detail'),

    # Inventory change views
    path('inventory/', views.InventoryChangeLogListView.as_view(), name='inventory_list'),
    path('inventory/create/', views.InventoryChangeLogCreateView.as_view(), name='inventory_create'),

    # Allocation config views
    path('allocation/configs/', views.AllocationConfigListView.as_view(), name='allocation_config_list'),
    path('allocation/configs/create/', views.AllocationConfigCreateView.as_view(), name='allocation_config_create'),
    path('allocation/configs/<int:pk>/update/', views.AllocationConfigUpdateView.as_view(), name='allocation_config_update'),
    path('allocation/configs/<int:pk>/delete/', views.AllocationConfigDeleteView.as_view(), name='allocation_config_delete'),

    # Allocation suggestion views
    path('allocation/suggestions/', views.AllocationSuggestionListView.as_view(), name='allocation_suggestion_list'),
    path('allocation/suggestions/generate/', views.generate_allocation_suggestions, name='allocation_suggestion_generate'),
    path('allocation/suggestions/<int:pk>/', views.allocation_suggestion_detail, name='allocation_suggestion_detail'),
    path('allocation/suggestions/<int:pk>/approve/', views.approve_allocation_suggestion, name='allocation_suggestion_approve'),
    path('allocation/suggestions/<int:pk>/reject/', views.reject_allocation_suggestion, name='allocation_suggestion_reject'),

    # Allocation execution views
    path('allocation/executions/', views.AllocationExecutionListView.as_view(), name='allocation_execution_list'),
    path('allocation/executions/<int:pk>/', views.allocation_execution_detail, name='allocation_execution_detail'),
    path('allocation/executions/<int:pk>/update/', views.update_allocation_execution, name='allocation_execution_update'),
    path('allocation/executions/<int:pk>/status/', views.update_execution_status, name='allocation_execution_status'),

    # Analysis views
    path('allocation/analysis/', views.allocation_analysis, name='allocation_analysis'),

    # Region views
    path('regions/', views.RegionListView.as_view(), name='region_list'),
    path('regions/create/', views.RegionCreateView.as_view(), name='region_create'),
    path('regions/<int:pk>/update/', views.RegionUpdateView.as_view(), name='region_update'),
    path('regions/<int:pk>/delete/', views.RegionDeleteView.as_view(), name='region_delete'),

    # Transport route views
    path('transport-routes/', views.TransportRouteListView.as_view(), name='transport_route_list'),
    path('transport-routes/create/', views.TransportRouteCreateView.as_view(), name='transport_route_create'),
    path('transport-routes/<int:pk>/update/', views.TransportRouteUpdateView.as_view(), name='transport_route_update'),
    path('transport-routes/<int:pk>/delete/', views.TransportRouteDeleteView.as_view(), name='transport_route_delete'),

    # Batch views
    path('batches/', views.batch_list, name='batch_list'),
    path('batches/<int:pk>/', views.batch_detail, name='batch_detail'),
    path('batches/<int:pk>/update/', views.batch_update, name='batch_update'),
    path('batches/<int:pk>/status/', views.batch_update_status, name='batch_status'),
    path('batches/<int:pk>/split/', views.batch_split, name='batch_split'),
    path('executions/<int:execution_pk>/batches/create/', views.batch_create, name='batch_create'),
    path('executions/<int:execution_pk>/batches/merge/', views.batch_merge, name='batch_merge'),

    # Execution node views
    path('batches/<int:batch_pk>/nodes/create/', views.node_create, name='node_create'),
    path('nodes/<int:pk>/complete/', views.node_complete, name='node_complete'),
    path('nodes/<int:pk>/depart/', views.node_depart, name='node_depart'),
    path('nodes/<int:pk>/delete/', views.node_delete, name='node_delete'),

    # Abnormal loss views
    path('losses/', views.loss_list, name='loss_list'),
    path('batches/<int:batch_pk>/losses/create/', views.loss_create, name='loss_create'),
    path('losses/<int:pk>/handle/', views.loss_handle, name='loss_handle'),

    # Arrival verification views
    path('verifications/', views.verification_list, name='verification_list'),
    path('verifications/<int:pk>/', views.verification_detail, name='verification_detail'),
    path('verifications/<int:pk>/submit/', views.verification_submit, name='verification_submit'),
    path('verifications/<int:pk>/confirm/', views.verification_confirm, name='verification_confirm'),
    path('batches/<int:batch_pk>/verifications/create/', views.verification_create, name='verification_create'),

    # Collaborative analytics views
    path('allocation/collaborative/', views.collaborative_dashboard, name='collaborative_dashboard'),
    path('api/timeliness-stats/', views.api_timeliness_stats, name='api_timeliness_stats'),
    path('api/loss-rate-stats/', views.api_loss_rate_stats, name='api_loss_rate_stats'),
    path('api/execution-rate-stats/', views.api_execution_rate_stats, name='api_execution_rate_stats'),
    path('api/collaboration-efficiency/', views.api_collaboration_efficiency, name='api_collaboration_efficiency'),
    path('api/region-collaboration/', views.api_region_collaboration, name='api_region_collaboration'),
    path('api/route-efficiency/', views.api_route_efficiency, name='api_route_efficiency'),
    path('api/loss-by-type/', views.api_loss_by_type, name='api_loss_by_type'),
]
