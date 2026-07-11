"""
Clinical Records API URLs
"""
from django.urls import path, include
from . import views
from .views import patient_record_views, patient_upload_views, jwt_upload_views, dashboard_views, record_action_views

urlpatterns = [
    # Health check and authentication test endpoints
    path('health/', views.health_check, name='health_check'),
    path('user/profile/', views.user_profile, name='user_profile'),
    
    # General records endpoints
    path('records/', views.clinical_records_list, name='clinical_records_list'),
    
    # Patient-scoped endpoints
    path('patients/<int:patient_id>/records/', patient_record_views.patient_records_list, name='patient_records_list'),
    path('patients/<int:patient_id>/records/<uuid:record_id>/', patient_record_views.patient_record_detail, name='patient_record_detail'),
    path('patients/<int:patient_id>/records/create/', patient_record_views.patient_record_create, name='patient_record_create'),
    path('patients/<int:patient_id>/documents/upload/', patient_record_views.patient_document_upload, name='patient_document_upload'),
    path('patients/<int:patient_id>/records/search/', patient_record_views.patient_search_records, name='patient_search_records'),
    
    # Patient upload page and endpoints for external records
    path('patients/<int:patient_id>/upload/', patient_upload_views.patient_upload_page, name='patient_upload_page'),
    path('patients/<int:patient_id>/upload/prescription/', patient_upload_views.patient_upload_external_prescription, name='patient_upload_prescription'),
    path('patients/<int:patient_id>/upload/lab-report/', patient_upload_views.patient_upload_external_lab_report, name='patient_upload_lab_report'),
    path('patients/<int:patient_id>/upload/record/', patient_upload_views.patient_upload_external_record, name='patient_upload_record'),
    path('patients/<int:patient_id>/external-records/', patient_upload_views.patient_external_records_list, name='patient_external_records'),
    path('patients/<int:patient_id>/upload-history/', patient_upload_views.patient_upload_history, name='patient_upload_history'),
    
    # Current patient endpoints (for logged-in patients)
    path('patient/records/', patient_record_views.current_patient_records, name='current_patient_records'),
    
    # JWT-based patient upload endpoints (no patient_id in URL)
    path('patient/upload/', jwt_upload_views.jwt_patient_upload_page, name='jwt_patient_upload_page'),
    path('patient/upload/prescription/', jwt_upload_views.jwt_patient_upload_prescription, name='jwt_patient_upload_prescription'),
    path('patient/upload/lab-report/', jwt_upload_views.jwt_patient_upload_lab_report, name='jwt_patient_upload_lab_report'),
    path('patient/upload/record/', jwt_upload_views.jwt_patient_upload_record, name='jwt_patient_upload_record'),
    path('patient/external-records/', jwt_upload_views.jwt_patient_external_records, name='jwt_patient_external_records'),
    path('patient/upload-history/', jwt_upload_views.jwt_patient_upload_history, name='jwt_patient_upload_history'),
    
    # Record Actions (Sync, Seal, Share)
    path('records/sync/', record_action_views.sync_records, name='sync_records'),
    path('records/<uuid:record_id>/seal/', record_action_views.toggle_seal_record, name='record_toggle_seal'),
    path('records/<uuid:record_id>/share/', record_action_views.share_record, name='record_share'),
    
    # Dashboard and UI endpoints
    path('', dashboard_views.landing_page, name='landing_page'),
    path('dashboard/', dashboard_views.dashboard_home, name='dashboard_home'),
    path('records/', dashboard_views.records_list_page, name='records_list_page'),
    path('dashboard/stats/', dashboard_views.dashboard_stats, name='dashboard_stats'),
    
    # Include other view modules
    # path('', include('clinical_records.views.api_views')),  # Commented out - no urlpatterns
]