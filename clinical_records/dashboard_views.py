"""
Dashboard views for Clinical Records Service
"""
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from .models import ClinicalRecord, ClinicalDocument


@login_required
def dashboard(request):
    """
    Main dashboard view
    """
    # Get basic statistics
    total_records = ClinicalRecord.objects.count()
    total_documents = ClinicalDocument.objects.count()
    
    # Get recent records
    recent_records = ClinicalRecord.objects.order_by('-created_at')[:5]
    
    context = {
        'total_records': total_records,
        'total_documents': total_documents,
        'recent_records': recent_records,
        'user': request.user,
    }
    
    return render(request, 'clinical_records/dashboard.html', context)