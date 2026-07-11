from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.core.paginator import Paginator
from django.db.models import Q, Count
from clinical_records.models import ClinicalRecord, ClinicalDocument
from clinical_records.forms import ClinicalRecordForm, ClinicalDocumentForm

@login_required
def record_list(request):
    """List all clinical records with search and filtering"""
    records = ClinicalRecord.objects.all().order_by('-created_at')
    
    # Search functionality
    search_query = request.GET.get('search', '')
    if search_query:
        records = records.filter(
            Q(title__icontains=search_query) |
            Q(record_type__icontains=search_query) |
            Q(description__icontains=search_query)
        )
    
    # Filter by record type
    record_type = request.GET.get('record_type', '')
    if record_type:
        records = records.filter(record_type=record_type)
    
    # Filter by status
    status = request.GET.get('status', '')
    if status:
        records = records.filter(status=status)
    
    # Pagination
    paginator = Paginator(records, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'search_query': search_query,
        'record_type': record_type,
        'status': status,
        'record_types': [('lab_report', 'Lab Report'), ('prescription', 'Prescription'), ('imaging', 'Imaging'), ('other', 'Other')],
        'status_choices': [('active', 'Active'), ('inactive', 'Inactive'), ('archived', 'Archived')],
    }
    return render(request, 'clinical_records/record_list.html', context)

@login_required
def record_detail(request, record_id):
    """View detailed information about a clinical record"""
    record = get_object_or_404(ClinicalRecord, id=record_id)
    documents = ClinicalDocument.objects.filter(clinical_record=record)
    
    context = {
        'record': record,
        'documents': documents,
    }
    return render(request, 'clinical_records/record_detail.html', context)

@login_required
def record_create(request):
    """Create a new clinical record"""
    if request.method == 'POST':
        form = ClinicalRecordForm(request.POST)
        if form.is_valid():
            record = form.save(commit=False)
            record.created_by = request.user
            record.save()
            messages.success(request, 'Clinical record created successfully.')
            return redirect('record_detail', record_id=record.id)
    else:
        form = ClinicalRecordForm()
    
    context = {
        'form': form,
        'action': 'Create',
    }
    return render(request, 'clinical_records/record_form.html', context)

@login_required
def record_update(request, record_id):
    """Update an existing clinical record"""
    record = get_object_or_404(ClinicalRecord, id=record_id)
    
    if request.method == 'POST':
        form = ClinicalRecordForm(request.POST, instance=record)
        if form.is_valid():
            form.save()
            messages.success(request, 'Clinical record updated successfully.')
            return redirect('record_detail', record_id=record.id)
    else:
        form = ClinicalRecordForm(instance=record)
    
    context = {
        'form': form,
        'record': record,
        'action': 'Update',
    }
    return render(request, 'clinical_records/record_form.html', context)

@login_required
def record_delete(request, record_id):
    """Delete a clinical record"""
    record = get_object_or_404(ClinicalRecord, id=record_id)
    
    if request.method == 'POST':
        record.delete()
        messages.success(request, 'Clinical record deleted successfully.')
        return redirect('record_list')
    
    context = {
        'record': record,
    }
    return render(request, 'clinical_records/record_confirm_delete.html', context)

@login_required
def document_upload(request, record_id=None):
    """Upload documents for clinical records"""
    if request.method == 'POST':
        form = ClinicalDocumentForm(request.POST, request.FILES)
        if form.is_valid():
            document = form.save(commit=False)
            document.uploaded_by = request.user
            document.save()
            messages.success(request, 'Document uploaded successfully.')
            if record_id:
                return redirect('record_detail', record_id=record_id)
            else:
                return redirect('record_list')
    else:
        form = ClinicalDocumentForm()
        if record_id:
            record = get_object_or_404(ClinicalRecord, id=record_id)
            form.fields['clinical_record'].initial = record
    
    context = {
        'form': form,
        'record_id': record_id,
    }
    return render(request, 'clinical_records/document_upload.html', context)

@login_required
def document_delete(request, document_id):
    """Delete a document"""
    document = get_object_or_404(ClinicalDocument, id=document_id)
    record_id = document.clinical_record.id
    
    if request.method == 'POST':
        document.delete()
        messages.success(request, 'Document deleted successfully.')
        return redirect('record_detail', record_id=record_id)
    
    context = {
        'document': document,
    }
    return render(request, 'clinical_records/document_confirm_delete.html', context)

@login_required
def analytics_dashboard(request):
    """Analytics dashboard with charts and statistics"""
    total_records = ClinicalRecord.objects.count()
    records_by_type = ClinicalRecord.objects.values('record_type').annotate(
        count=Count('id')
    )
    records_by_status = ClinicalRecord.objects.values('status').annotate(
        count=Count('id')
    )
    
    # Recent activity
    recent_records = ClinicalRecord.objects.all().order_by('-created_at')[:10]
    
    context = {
        'total_records': total_records,
        'records_by_type': records_by_type,
        'records_by_status': records_by_status,
        'recent_records': recent_records,
    }
    return render(request, 'clinical_records/analytics_dashboard.html', context)

@csrf_exempt
def api_records(request):
    """API endpoint for records"""
    if request.method == 'GET':
        records = ClinicalRecord.objects.all().order_by('-created_at')
        data = []
        for record in records:
            data.append({
                'id': record.id,
                'title': record.title,
                'record_type': record.record_type,
                'status': record.status,
                'created_at': record.created_at.isoformat(),
            })
        return JsonResponse({'records': data})
    return JsonResponse({'error': 'Method not allowed'}, status=405)
