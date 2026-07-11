from django import forms
from .models import Patient, ClinicalRecord, ClinicalDocument

class ClinicalRecordForm(forms.ModelForm):
    patient_id = forms.IntegerField(required=False, help_text="Patient ID from RxBackend")
    
    class Meta:
        model = ClinicalRecord
        fields = ['patient_id', 'title', 'record_type', 'description', 'status', 'priority', 'record_date', 'is_confidential']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-input rounded-md border-gray-300 w-full'}),
            'record_type': forms.Select(attrs={'class': 'form-select rounded-md border-gray-300 w-full'}, choices=[
                ('lab_report', 'Lab Report'),
                ('prescription', 'Prescription'),
                ('imaging', 'Imaging Study'),
                ('consultation', 'Consultation'),
                ('discharge_summary', 'Discharge Summary'),
                ('other', 'Other'),
            ]),
            'description': forms.Textarea(attrs={'class': 'form-textarea rounded-md border-gray-300 w-full', 'rows': 4}),
            'status': forms.Select(attrs={'class': 'form-select rounded-md border-gray-300 w-full'}, choices=[
                ('active', 'Active'),
                ('inactive', 'Inactive'),
                ('archived', 'Archived'),
            ]),
            'priority': forms.Select(attrs={'class': 'form-select rounded-md border-gray-300 w-full'}, choices=[
                ('low', 'Low'),
                ('normal', 'Normal'),
                ('high', 'High'),
                ('urgent', 'Urgent'),
            ]),
            'record_date': forms.DateInput(attrs={'class': 'form-input rounded-md border-gray-300 w-full', 'type': 'date'}),
            'is_confidential': forms.CheckboxInput(attrs={'class': 'form-checkbox rounded border-gray-300'}),
        }

class ClinicalDocumentForm(forms.ModelForm):
    class Meta:
        model = ClinicalDocument
        fields = ['clinical_record', 'title', 'file', 'is_encrypted']
        widgets = {
            'clinical_record': forms.Select(attrs={'class': 'form-select rounded-md border-gray-300 w-full'}),
            'title': forms.TextInput(attrs={'class': 'form-input rounded-md border-gray-300 w-full'}),
            'file': forms.FileInput(attrs={'class': 'form-input rounded-md border-gray-300 w-full', 'accept': '.pdf,.doc,.docx,.jpg,.jpeg,.png,.tiff,.dcm'}),
            'is_encrypted': forms.CheckboxInput(attrs={'class': 'form-checkbox rounded border-gray-300'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make file field required for new documents
        if not self.instance.pk:
            self.fields['file'].required = True

class PatientSearchForm(forms.Form):
    """Form for searching patients"""
    search_query = forms.CharField(
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-input rounded-md border-gray-300 w-full',
            'placeholder': 'Search by name, patient ID, or phone number'
        })
    )
    clinic_id = forms.IntegerField(
        required=False,
        widget=forms.NumberInput(attrs={
            'class': 'form-input rounded-md border-gray-300 w-full',
            'placeholder': 'Clinic ID'
        })
    )


class PatientUploadPrescriptionForm(forms.Form):
    """Form for patient prescription uploads"""
    file = forms.FileField(
        required=True,
        widget=forms.FileInput(attrs={
            'class': 'form-input rounded-md border-gray-300 w-full',
            'accept': '.pdf,.jpg,.jpeg,.png,.tiff,.dcm',
            'id': 'prescription-file'
        }),
        help_text="Upload prescription image or PDF (PDF, JPG, PNG, TIFF, DICOM supported)"
    )
    title = forms.CharField(
        max_length=255,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-input rounded-md border-gray-300 w-full',
            'placeholder': 'e.g., Prescription for Diabetes Medication'
        })
    )
    description = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-textarea rounded-md border-gray-300 w-full',
            'rows': 3,
            'placeholder': 'Additional notes about the prescription...'
        })
    )
    prescription_date = forms.DateField(
        required=True,
        widget=forms.DateInput(attrs={
            'class': 'form-input rounded-md border-gray-300 w-full',
            'type': 'date'
        })
    )
    doctor_name = forms.CharField(
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-input rounded-md border-gray-300 w-full',
            'placeholder': 'Dr. John Smith'
        })
    )
    pharmacy_name = forms.CharField(
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-input rounded-md border-gray-300 w-full',
            'placeholder': 'ABC Pharmacy'
        })
    )


class PatientUploadLabReportForm(forms.Form):
    """Form for patient lab report uploads"""
    file = forms.FileField(
        required=True,
        widget=forms.FileInput(attrs={
            'class': 'form-input rounded-md border-gray-300 w-full',
            'accept': '.pdf,.jpg,.jpeg,.png,.tiff,.dcm',
            'id': 'lab-report-file'
        }),
        help_text="Upload lab report image or PDF (PDF, JPG, PNG, TIFF, DICOM supported)"
    )
    title = forms.CharField(
        max_length=255,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-input rounded-md border-gray-300 w-full',
            'placeholder': 'e.g., Blood Test Results - CBC'
        })
    )
    description = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-textarea rounded-md border-gray-300 w-full',
            'rows': 3,
            'placeholder': 'Additional notes about the lab report...'
        })
    )
    test_date = forms.DateField(
        required=True,
        widget=forms.DateInput(attrs={
            'class': 'form-input rounded-md border-gray-300 w-full',
            'type': 'date'
        })
    )
    lab_name = forms.CharField(
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-input rounded-md border-gray-300 w-full',
            'placeholder': 'ABC Diagnostic Lab'
        })
    )
    test_type = forms.CharField(
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-input rounded-md border-gray-300 w-full',
            'placeholder': 'Complete Blood Count, Lipid Profile, etc.'
        })
    )


class PatientUploadRecordForm(forms.Form):
    """Form for patient general medical record uploads"""
    file = forms.FileField(
        required=True,
        widget=forms.FileInput(attrs={
            'class': 'form-input rounded-md border-gray-300 w-full',
            'accept': '.pdf,.jpg,.jpeg,.png,.tiff,.dcm,.doc,.docx',
            'id': 'medical-record-file'
        }),
        help_text="Upload medical record (PDF, JPG, PNG, TIFF, DICOM, DOC, DOCX supported)"
    )
    title = forms.CharField(
        max_length=255,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-input rounded-md border-gray-300 w-full',
            'placeholder': 'e.g., Discharge Summary, Consultation Report'
        })
    )
    description = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-textarea rounded-md border-gray-300 w-full',
            'rows': 3,
            'placeholder': 'Additional notes about the medical record...'
        })
    )
    record_date = forms.DateField(
        required=True,
        widget=forms.DateInput(attrs={
            'class': 'form-input rounded-md border-gray-300 w-full',
            'type': 'date'
        })
    )
    record_type = forms.ChoiceField(
        choices=[
            ('external_record', 'General Medical Record'),
            ('discharge_summary', 'Discharge Summary'),
            ('consultation_report', 'Consultation Report'),
            ('imaging_report', 'Imaging Report'),
            ('pathology_report', 'Pathology Report'),
            ('other', 'Other Medical Record'),
        ],
        widget=forms.Select(attrs={
            'class': 'form-select rounded-md border-gray-300 w-full'
        })
    )
    source_name = forms.CharField(
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-input rounded-md border-gray-300 w-full',
            'placeholder': 'Hospital/Clinic name where record was created'
        })
    )
