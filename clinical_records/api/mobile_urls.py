"""
Mobile API URLs for Clinical Records

URL patterns for mobile-optimized clinical records API endpoints.
"""
from django.urls import path, include
from . import mobile_views

app_name = 'clinical_records_mobile_api'

urlpatterns = [
    # Clinical Records Mobile API
    path('clinical-records/', mobile_views.mobile_clinical_records_list, name='clinical-records-list'),
    path('clinical-records/<uuid:record_id>/', mobile_views.mobile_clinical_record_detail, name='clinical-record-detail'),
    path('clinical-records/search/', mobile_views.mobile_clinical_records_search, name='clinical-records-search'),
    path('clinical-records/upload/', mobile_views.mobile_document_upload, name='document-upload'),
    
    # Document Processing Status
    path('documents/<uuid:document_id>/status/', mobile_views.mobile_document_processing_status, name='document-processing-status'),
    
    # Search functionality
    path('search/suggestions/', mobile_views.mobile_search_suggestions, name='search-suggestions'),
]