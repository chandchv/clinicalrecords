"""
Widget views for clinical records dashboard widgets.
"""
from django.http import JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator


@method_decorator(csrf_exempt, name='dispatch')
class ClinicalRecordsWidgetView(View):
    """
    Widget view for clinical records dashboard.
    """
    
    def get(self, request, *args, **kwargs):
        """
        Handle GET requests for the clinical records widget.
        """
        # Get query parameters to determine widget type
        patient_view = request.GET.get('patient_view', 'false').lower() == 'true'
        staff_view = request.GET.get('staff_view', 'false').lower() == 'true'
        admin_view = request.GET.get('admin_view', 'false').lower() == 'true'
        refresh = request.GET.get('refresh', 'false').lower() == 'true'
        
        # Mock data for the widget
        data = {
            'clinical_data': {
                'summary': {
                    'total_records': 0,
                    'recent_records': 0,
                    'total_documents': 0,
                    'today_records': 0,
                    'pending_reviews': 0,
                    'failed_processing': 0,
                },
                'recent_activity': [],
                'records_by_type': [],
                'processing_status': [],
            },
            'processing_data': {
                'failed': 0,
                'pending': 0,
                'processing': 0,
                'completed_today': 0,
                'total': 0,
            },
            'daily_tasks': [],
            'recent_activity': [],
            'widget_type': 'summary',
        }
        
        # Adjust data based on view type
        if patient_view:
            data['widget_type'] = 'patient'
            data['clinical_data']['summary']['total_records'] = 5
            data['clinical_data']['summary']['recent_records'] = 2
        elif staff_view:
            data['widget_type'] = 'staff'
            data['processing_data']['pending'] = 3
            data['processing_data']['processing'] = 1
        elif admin_view:
            data['widget_type'] = 'admin'
            data['clinical_data']['summary']['total_records'] = 25
            data['clinical_data']['summary']['pending_reviews'] = 5
        
        return JsonResponse(data)


@csrf_exempt
def clinical_records_widget(request):
    """
    Function-based view for clinical records widget.
    """
    view = ClinicalRecordsWidgetView()
    return view.get(request)
