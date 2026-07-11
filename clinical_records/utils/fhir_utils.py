"""
FHIR Export Utilities

This module provides comprehensive FHIR R4 export functionality for clinical records.
It supports exporting patient data, clinical records, and documents in FHIR format
for interoperability with other healthcare systems.
"""
import logging
import uuid
from datetime import datetime, date
from typing import Dict, List, Any, Optional, Union
from decimal import Decimal

try:
    from fhir.resources.patient import Patient as FHIRPatient
    from fhir.resources.bundle import Bundle, BundleEntry
    from fhir.resources.documentreference import DocumentReference, DocumentReferenceContent
    from fhir.resources.observation import Observation, ObservationComponent
    from fhir.resources.diagnosticreport import DiagnosticReport
    from fhir.resources.medicationrequest import MedicationRequest
    from fhir.resources.condition import Condition
    from fhir.resources.practitioner import Practitioner
    from fhir.resources.organization import Organization
    from fhir.resources.attachment import Attachment
    from fhir.resources.codeableconcept import CodeableConcept
    from fhir.resources.coding import Coding
    from fhir.resources.identifier import Identifier
    from fhir.resources.humanname import HumanName
    from fhir.resources.contactpoint import ContactPoint
    from fhir.resources.address import Address
    from fhir.resources.reference import Reference
    from fhir.resources.quantity import Quantity
    from fhir.resources.period import Period
    from fhir.resources.dosage import Dosage
    FHIR_AVAILABLE = True
    BundleType = Bundle
    BundleEntryType = BundleEntry
    DocumentReferenceType = DocumentReference
    ObservationType = Observation
    DiagnosticReportType = DiagnosticReport
    MedicationRequestType = MedicationRequest
    ConditionType = Condition
    PractitionerType = Practitioner
    OrganizationType = Organization
    PatientType = FHIRPatient
except ImportError:
    FHIR_AVAILABLE = False
    BundleType = Any
    BundleEntryType = Any
    DocumentReferenceType = Any
    ObservationType = Any
    DiagnosticReportType = Any
    MedicationRequestType = Any
    ConditionType = Any
    PractitionerType = Any
    OrganizationType = Any
    PatientType = Any

logger = logging.getLogger(__name__)


class FHIRExportService:
    """
    Comprehensive service for exporting clinical records in FHIR R4 format.
    
    This service provides methods to export patient data, clinical records,
    and documents in FHIR-compliant format for interoperability with other
    healthcare systems.
    """
    
    def __init__(self):
        if not FHIR_AVAILABLE:
            raise ImportError("fhir.resources is required for FHIR export")
    
    def create_patient_bundle(self, patient, clinical_records=None, 
                            include_documents=True, date_range=None,
                            record_types=None) -> Optional[BundleType]:
        """
        Create a comprehensive FHIR Bundle for a patient with their clinical records.
        
        Args:
            patient: Patient model instance
            clinical_records: List of ClinicalRecord instances (optional)
            include_documents: Whether to include DocumentReference resources
            date_range: Tuple of (start_date, end_date) to filter records
            record_types: List of record types to include
            
        Returns:
            FHIR Bundle or None if error
        """
        try:
            bundle_id = f"patient-bundle-{patient.id}"
            
            # Create Bundle
            bundle = Bundle(
                id=bundle_id,
                type="collection",
                timestamp=datetime.utcnow().isoformat() + "Z",
                entry=[]
            )
            
            # Add Patient resource
            fhir_patient = self._create_patient_resource(patient)
            patient_entry = BundleEntry(
                resource=fhir_patient,
                fullUrl=f"Patient/{patient.id}"
            )
            bundle.entry.append(patient_entry)
            
            # Add Organization (Clinic) resource
            if patient.clinic:
                fhir_org = self._create_organization_resource(patient.clinic)
                org_entry = BundleEntry(
                    resource=fhir_org,
                    fullUrl=f"Organization/{patient.clinic.id}"
                )
                bundle.entry.append(org_entry)
            
            # Process clinical records
            if clinical_records:
                for record in clinical_records:
                    # Apply filters
                    if date_range:
                        start_date, end_date = date_range
                        if record.record_date < start_date or record.record_date > end_date:
                            continue
                    
                    if record_types and record.record_type not in record_types:
                        continue
                    
                    # Create appropriate FHIR resources based on record type
                    resources = self._create_resources_for_record(record, str(patient.id))
                    
                    for resource in resources:
                        entry = BundleEntry(
                            resource=resource,
                            fullUrl=f"{resource.resource_type}/{resource.id}"
                        )
                        bundle.entry.append(entry)
                    
                    # Add DocumentReference resources if requested
                    if include_documents:
                        for document in record.documents.all():
                            doc_ref = self._create_document_reference(document, str(patient.id))
                            if doc_ref:
                                doc_entry = BundleEntry(
                                    resource=doc_ref,
                                    fullUrl=f"DocumentReference/{document.id}"
                                )
                                bundle.entry.append(doc_entry)
            
            return bundle
            
        except Exception as e:
            logger.error(f"Error creating FHIR patient bundle: {e}")
            return None
    
    def create_individual_resource(self, clinical_record, resource_type=None):
        """
        Create individual FHIR resources for a clinical record.
        
        Args:
            clinical_record: ClinicalRecord instance
            resource_type: Specific FHIR resource type to create
            
        Returns:
            List of FHIR resources
        """
        try:
            patient_id = str(clinical_record.patient.id)
            return self._create_resources_for_record(clinical_record, patient_id, resource_type)
        except Exception as e:
            logger.error(f"Error creating individual FHIR resource: {e}")
            return []
    
    def _create_resources_for_record(self, clinical_record, patient_id, resource_type=None):
        """
        Create appropriate FHIR resources based on clinical record type.
        
        Args:
            clinical_record: ClinicalRecord instance
            patient_id: Patient ID string
            resource_type: Specific resource type to create (optional)
            
        Returns:
            List of FHIR resources
        """
        resources = []
        record_type = clinical_record.record_type
        
        try:
            if record_type == 'lab_report' and (not resource_type or resource_type == 'Observation'):
                observations = self._create_observation_resources(clinical_record, patient_id)
                resources.extend(observations)
                
                # Also create DiagnosticReport for lab reports
                if not resource_type or resource_type == 'DiagnosticReport':
                    diagnostic_report = self._create_diagnostic_report_resource(clinical_record, patient_id)
                    if diagnostic_report:
                        resources.append(diagnostic_report)
            
            elif record_type == 'prescription' and (not resource_type or resource_type == 'MedicationRequest'):
                medication_requests = self._create_medication_request_resources(clinical_record, patient_id)
                resources.extend(medication_requests)
            
            elif record_type in ['imaging', 'pathology'] and (not resource_type or resource_type == 'DiagnosticReport'):
                diagnostic_report = self._create_diagnostic_report_resource(clinical_record, patient_id)
                if diagnostic_report:
                    resources.append(diagnostic_report)
            
            elif record_type in ['allergy'] and (not resource_type or resource_type == 'Condition'):
                condition = self._create_condition_resource(clinical_record, patient_id)
                if condition:
                    resources.append(condition)
            
            # For other record types, create a generic DocumentReference
            # This is handled separately in the bundle creation
            
        except Exception as e:
            logger.error(f"Error creating resources for record {clinical_record.id}: {e}")
        
        return resources
    
    def _create_patient_resource(self, patient) -> PatientType:
        """
        Create a FHIR Patient resource from Patient model instance.
        
        Args:
            patient: Patient model instance
            
        Returns:
            FHIR Patient resource
        """
        try:
            # Build identifiers
            identifiers = []
            if hasattr(patient, 'global_identifier') and patient.global_identifier:
                identifiers.append(Identifier(
                    system="http://hospital.local/patient-id",
                    value=patient.global_identifier
                ))
            
            # Add internal ID
            identifiers.append(Identifier(
                system="http://hospital.local/internal-id",
                value=str(patient.id)
            ))
            
            # Build name
            names = []
            if patient.first_name or patient.last_name:
                name = HumanName(
                    family=patient.last_name or "",
                    given=[patient.first_name] if patient.first_name else []
                )
                names.append(name)
            
            # Build telecom
            telecom = []
            if hasattr(patient, 'contact_phone') and patient.contact_phone:
                telecom.append(ContactPoint(
                    system="phone",
                    value=patient.contact_phone
                ))
            if hasattr(patient, 'email') and patient.email:
                telecom.append(ContactPoint(
                    system="email",
                    value=patient.email
                ))
            
            # Build address
            addresses = []
            if hasattr(patient, 'address') and patient.address:
                addresses.append(Address(
                    text=patient.address
                ))
            
            # Create Patient resource
            fhir_patient = FHIRPatient(
                id=str(patient.id),
                identifier=identifiers,
                name=names,
                gender=self._map_gender(getattr(patient, 'gender', '')),
                birthDate=patient.date_of_birth.isoformat() if patient.date_of_birth else None,
                telecom=telecom if telecom else None,
                address=addresses if addresses else None
            )
            
            return fhir_patient
            
        except Exception as e:
            logger.error(f"Error creating FHIR Patient resource: {e}")
            raise
    
    def _create_organization_resource(self, clinic) -> OrganizationType:
        """
        Create a FHIR Organization resource from Clinic model instance.
        
        Args:
            clinic: Clinic model instance
            
        Returns:
            FHIR Organization resource
        """
        try:
            # Build telecom
            telecom = []
            if hasattr(clinic, 'phone') and clinic.phone:
                telecom.append(ContactPoint(
                    system="phone",
                    value=clinic.phone
                ))
            if hasattr(clinic, 'email') and clinic.email:
                telecom.append(ContactPoint(
                    system="email",
                    value=clinic.email
                ))
            
            # Build address
            addresses = []
            if hasattr(clinic, 'address') and clinic.address:
                addresses.append(Address(
                    text=clinic.address
                ))
            
            organization = Organization(
                id=str(clinic.id),
                name=clinic.name,
                telecom=telecom if telecom else None,
                address=addresses if addresses else None,
                active=True
            )
            
            return organization
            
        except Exception as e:
            logger.error(f"Error creating FHIR Organization resource: {e}")
            raise
    
    def _create_observation_resources(self, clinical_record, patient_id):
        """
        Create FHIR Observation resources from lab report data.
        
        Args:
            clinical_record: ClinicalRecord instance
            patient_id: Patient ID string
            
        Returns:
            List of FHIR Observation resources
        """
        observations = []
        
        try:
            # Extract structured data from documents
            for document in clinical_record.documents.all():
                if document.structured_data and 'tests' in document.structured_data:
                    for test in document.structured_data['tests']:
                        observation = self._create_single_observation(
                            test, clinical_record, patient_id, document
                        )
                        if observation:
                            observations.append(observation)
            
            # If no structured data, create a generic observation
            if not observations:
                generic_obs = self._create_generic_observation(clinical_record, patient_id)
                if generic_obs:
                    observations.append(generic_obs)
                    
        except Exception as e:
            logger.error(f"Error creating Observation resources: {e}")
        
        return observations
    
    def _create_single_observation(self, test_data, clinical_record, patient_id, document):
        """Create a single FHIR Observation from test data."""
        try:
            observation_id = f"{clinical_record.id}-{uuid.uuid4()}"
            
            # Build value quantity
            value_quantity = None
            if 'value' in test_data and 'unit' in test_data:
                value_quantity = Quantity(
                    value=float(test_data['value']),
                    unit=test_data['unit'],
                    system="http://unitsofmeasure.org"
                )
            
            # Build reference range
            reference_range = None
            if 'reference_range' in test_data:
                # Parse reference range like "10-20"
                range_parts = test_data['reference_range'].split('-')
                if len(range_parts) == 2:
                    try:
                        low = float(range_parts[0].strip())
                        high = float(range_parts[1].strip())
                        reference_range = [{
                            "low": {"value": low, "unit": test_data.get('unit', '')},
                            "high": {"value": high, "unit": test_data.get('unit', '')}
                        }]
                    except ValueError:
                        pass
            
            observation = Observation(
                id=observation_id,
                status="final",
                category=[{
                    "coding": [{
                        "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                        "code": "laboratory",
                        "display": "Laboratory"
                    }]
                }],
                code={
                    "text": test_data.get('name', 'Unknown Test')
                },
                subject=Reference(reference=f"Patient/{patient_id}"),
                effectiveDateTime=clinical_record.record_date.isoformat(),
                valueQuantity=value_quantity,
                referenceRange=reference_range,
                interpretation=[{
                    "coding": [{
                        "system": "http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation",
                        "code": "A" if test_data.get('is_abnormal') else "N",
                        "display": "Abnormal" if test_data.get('is_abnormal') else "Normal"
                    }]
                }] if 'is_abnormal' in test_data else None
            )
            
            return observation
            
        except Exception as e:
            logger.error(f"Error creating single observation: {e}")
            return None
    
    def _create_generic_observation(self, clinical_record, patient_id):
        """Create a generic observation when no structured data is available."""
        try:
            observation = Observation(
                id=str(clinical_record.id),
                status="final",
                category=[{
                    "coding": [{
                        "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                        "code": "survey",
                        "display": "Survey"
                    }]
                }],
                code={
                    "text": clinical_record.title
                },
                subject=Reference(reference=f"Patient/{patient_id}"),
                effectiveDateTime=clinical_record.record_date.isoformat(),
                valueString=clinical_record.description or clinical_record.title
            )
            
            return observation
            
        except Exception as e:
            logger.error(f"Error creating generic observation: {e}")
            return None
    
    def _create_diagnostic_report_resource(self, clinical_record, patient_id):
        """
        Create a FHIR DiagnosticReport resource.
        
        Args:
            clinical_record: ClinicalRecord instance
            patient_id: Patient ID string
            
        Returns:
            FHIR DiagnosticReport resource or None
        """
        try:
            # Build result references (observations)
            result_references = []
            for document in clinical_record.documents.all():
                if document.structured_data and 'tests' in document.structured_data:
                    for i, test in enumerate(document.structured_data['tests']):
                        obs_id = f"{clinical_record.id}-{uuid.uuid4()}"
                        result_references.append(Reference(
                            reference=f"Observation/{obs_id}"
                        ))
            
            diagnostic_report = DiagnosticReport(
                id=str(clinical_record.id),
                status="final",
                category=[{
                    "coding": [{
                        "system": "http://terminology.hl7.org/CodeSystem/v2-0074",
                        "code": self._get_diagnostic_category_code(clinical_record.record_type),
                        "display": clinical_record.get_record_type_display()
                    }]
                }],
                code={
                    "text": clinical_record.title
                },
                subject=Reference(reference=f"Patient/{patient_id}"),
                effectiveDateTime=clinical_record.record_date.isoformat(),
                issued=clinical_record.created_at.isoformat(),
                result=result_references if result_references else None,
                conclusion=clinical_record.description
            )
            
            return diagnostic_report
            
        except Exception as e:
            logger.error(f"Error creating DiagnosticReport resource: {e}")
            return None
    
    def _create_medication_request_resources(self, clinical_record, patient_id):
        """
        Create FHIR MedicationRequest resources from prescription data.
        
        Args:
            clinical_record: ClinicalRecord instance
            patient_id: Patient ID string
            
        Returns:
            List of FHIR MedicationRequest resources
        """
        medication_requests = []
        
        try:
            # Extract medication data from documents
            for document in clinical_record.documents.all():
                if document.structured_data and 'medications' in document.structured_data:
                    for med in document.structured_data['medications']:
                        med_request = self._create_single_medication_request(
                            med, clinical_record, patient_id
                        )
                        if med_request:
                            medication_requests.append(med_request)
            
            # If no structured data, create a generic medication request
            if not medication_requests:
                generic_med = self._create_generic_medication_request(clinical_record, patient_id)
                if generic_med:
                    medication_requests.append(generic_med)
                    
        except Exception as e:
            logger.error(f"Error creating MedicationRequest resources: {e}")
        
        return medication_requests
    
    def _create_single_medication_request(self, med_data, clinical_record, patient_id):
        """Create a single FHIR MedicationRequest from medication data."""
        try:
            med_request_id = f"{clinical_record.id}-{uuid.uuid4()}"
            
            # Build dosage instruction
            dosage_instruction = []
            if 'instructions' in med_data:
                dosage_instruction.append(Dosage(
                    text=med_data['instructions']
                ))
            
            medication_request = MedicationRequest(
                id=med_request_id,
                status="active",
                intent="order",
                medicationCodeableConcept={
                    "text": f"{med_data.get('name', 'Unknown Medication')} {med_data.get('strength', '')}"
                },
                subject=Reference(reference=f"Patient/{patient_id}"),
                authoredOn=clinical_record.record_date.isoformat(),
                dosageInstruction=dosage_instruction if dosage_instruction else None
            )
            
            return medication_request
            
        except Exception as e:
            logger.error(f"Error creating single medication request: {e}")
            return None
    
    def _create_generic_medication_request(self, clinical_record, patient_id):
        """Create a generic medication request when no structured data is available."""
        try:
            medication_request = MedicationRequest(
                id=str(clinical_record.id),
                status="active",
                intent="order",
                medicationCodeableConcept={
                    "text": clinical_record.title
                },
                subject=Reference(reference=f"Patient/{patient_id}"),
                authoredOn=clinical_record.record_date.isoformat(),
                note=[{
                    "text": clinical_record.description or clinical_record.title
                }] if clinical_record.description else None
            )
            
            return medication_request
            
        except Exception as e:
            logger.error(f"Error creating generic medication request: {e}")
            return None
    
    def _create_condition_resource(self, clinical_record, patient_id):
        """
        Create a FHIR Condition resource for allergy or condition records.
        
        Args:
            clinical_record: ClinicalRecord instance
            patient_id: Patient ID string
            
        Returns:
            FHIR Condition resource or None
        """
        try:
            condition = Condition(
                id=str(clinical_record.id),
                clinicalStatus={
                    "coding": [{
                        "system": "http://terminology.hl7.org/CodeSystem/condition-clinical",
                        "code": "active",
                        "display": "Active"
                    }]
                },
                category=[{
                    "coding": [{
                        "system": "http://terminology.hl7.org/CodeSystem/condition-category",
                        "code": "problem-list-item",
                        "display": "Problem List Item"
                    }]
                }],
                code={
                    "text": clinical_record.title
                },
                subject=Reference(reference=f"Patient/{patient_id}"),
                recordedDate=clinical_record.record_date.isoformat(),
                note=[{
                    "text": clinical_record.description
                }] if clinical_record.description else None
            )
            
            return condition
            
        except Exception as e:
            logger.error(f"Error creating Condition resource: {e}")
            return None
    
    def _create_document_reference(self, clinical_document, patient_id):
        """
        Create a FHIR DocumentReference from ClinicalDocument instance.
        
        Args:
            clinical_document: ClinicalDocument instance
            patient_id: Patient ID string
            
        Returns:
            FHIR DocumentReference resource or None
        """
        try:
            # Build content attachment
            attachment = Attachment(
                contentType=clinical_document.content_type,
                size=clinical_document.file_size,
                title=clinical_document.original_filename,
                creation=clinical_document.created_at.isoformat()
            )
            
            # Add URL if file is accessible
            if clinical_document.file:
                # This would be replaced with secure URL generation in production
                attachment.url = f"/api/documents/{clinical_document.id}/download/"
            
            content = DocumentReferenceContent(
                attachment=attachment
            )
            
            doc_ref = DocumentReference(
                id=str(clinical_document.id),
                status="current",
                type={
                    "coding": [{
                        "system": "http://loinc.org",
                        "code": self._get_loinc_code(clinical_document.clinical_record.record_type),
                        "display": clinical_document.clinical_record.get_record_type_display()
                    }]
                },
                subject=Reference(reference=f"Patient/{patient_id}"),
                date=clinical_document.created_at.isoformat(),
                author=[Reference(
                    reference=f"Practitioner/{clinical_document.uploaded_by.id}"
                )] if clinical_document.uploaded_by else [],
                description=clinical_document.clinical_record.title,
                content=[content]
            )
            
            return doc_ref
            
        except Exception as e:
            logger.error(f"Error creating FHIR DocumentReference: {e}")
            return None
    
    def _map_gender(self, gender: str) -> str:
        """
        Map internal gender values to FHIR gender codes.
        
        Args:
            gender: Internal gender value
            
        Returns:
            FHIR-compliant gender code
        """
        gender_map = {
            'M': 'male',
            'F': 'female',
            'male': 'male',
            'female': 'female',
            'other': 'other',
            'undisclosed': 'unknown',
            'unknown': 'unknown'
        }
        return gender_map.get(str(gender).lower(), 'unknown')
    
    def _get_loinc_code(self, record_type: str) -> str:
        """
        Map record types to LOINC codes for better interoperability.
        
        Args:
            record_type: Internal record type
            
        Returns:
            LOINC code string
        """
        loinc_map = {
            'lab_report': '11502-2',      # Laboratory report
            'prescription': '57833-6',     # Prescription for medication
            'discharge_summary': '18842-5', # Discharge summary
            'progress_note': '11506-3',    # Progress note
            'consultation': '11488-4',     # Consultation note
            'imaging': '18748-4',          # Diagnostic imaging study
            'pathology': '11529-5',        # Surgical pathology study
            'vaccination': '87273-9',      # Immunization record
            'allergy': '48765-2',          # Allergies and adverse reactions
            'surgery': '11504-8',          # Surgical operation note
        }
        return loinc_map.get(record_type, '34133-9')  # Default: Summary of episode note
    
    def _get_diagnostic_category_code(self, record_type: str) -> str:
        """
        Map record types to diagnostic category codes.
        
        Args:
            record_type: Internal record type
            
        Returns:
            Diagnostic category code
        """
        category_map = {
            'lab_report': 'LAB',
            'imaging': 'RAD',
            'pathology': 'PAT',
            'prescription': 'PH',
        }
        return category_map.get(record_type, 'OTH')
    
    def export_to_json(self, bundle: BundleType) -> str:
        """
        Export FHIR Bundle to JSON string with proper formatting.
        
        Args:
            bundle: FHIR Bundle resource
            
        Returns:
            JSON string representation
        """
        try:
            return bundle.json(indent=2)
        except Exception as e:
            logger.error(f"Error exporting FHIR bundle to JSON: {e}")
            return "{}"
    
    def export_to_dict(self, bundle: BundleType) -> Dict[str, Any]:
        """
        Export FHIR Bundle to Python dictionary.
        
        Args:
            bundle: FHIR Bundle resource
            
        Returns:
            Dictionary representation
        """
        try:
            return bundle.dict()
        except Exception as e:
            logger.error(f"Error exporting FHIR bundle to dict: {e}")
            return {}
    
    def validate_bundle(self, bundle: BundleType) -> Dict[str, Any]:
        """
        Comprehensive validation of FHIR Bundle structure.
        
        Args:
            bundle: FHIR Bundle resource
            
        Returns:
            Dictionary with validation results
        """
        validation_result = {
            'is_valid': True,
            'errors': [],
            'warnings': [],
            'resource_count': 0,
            'resource_types': {}
        }
        
        try:
            # Check bundle structure
            if not bundle.type:
                validation_result['errors'].append("Bundle type is required")
                validation_result['is_valid'] = False
            
            if not bundle.entry:
                validation_result['warnings'].append("Bundle has no entries")
            else:
                validation_result['resource_count'] = len(bundle.entry)
                
                # Validate each entry
                for i, entry in enumerate(bundle.entry):
                    if not entry.resource:
                        validation_result['errors'].append(f"Entry {i} has no resource")
                        validation_result['is_valid'] = False
                        continue
                    
                    resource_type = entry.resource.resource_type
                    validation_result['resource_types'][resource_type] = \
                        validation_result['resource_types'].get(resource_type, 0) + 1
                    
                    # Validate resource-specific requirements
                    if resource_type == 'Patient':
                        if not entry.resource.id:
                            validation_result['errors'].append(f"Patient resource missing ID")
                            validation_result['is_valid'] = False
                    
                    elif resource_type == 'Observation':
                        if not entry.resource.status:
                            validation_result['errors'].append(f"Observation {i} missing status")
                            validation_result['is_valid'] = False
                        if not entry.resource.code:
                            validation_result['errors'].append(f"Observation {i} missing code")
                            validation_result['is_valid'] = False
            
            # Check for required Patient resource
            if 'Patient' not in validation_result['resource_types']:
                validation_result['warnings'].append("Bundle should contain a Patient resource")
            
        except Exception as e:
            logger.error(f"Error validating FHIR bundle: {e}")
            validation_result['is_valid'] = False
            validation_result['errors'].append(f"Validation error: {str(e)}")
        
        return validation_result
    
    def get_supported_resource_types(self) -> List[str]:
        """
        Get list of FHIR resource types supported by this service.
        
        Returns:
            List of supported resource type names
        """
        return [
            'Patient',
            'Organization',
            'Observation',
            'DiagnosticReport',
            'MedicationRequest',
            'Condition',
            'DocumentReference'
        ]
    
    def get_supported_record_types(self) -> List[str]:
        """
        Get list of clinical record types that can be exported to FHIR.
        
        Returns:
            List of supported record type names
        """
        return [
            'lab_report',
            'prescription',
            'discharge_summary',
            'progress_note',
            'consultation',
            'imaging',
            'pathology',
            'vaccination',
            'allergy',
            'surgery'
        ]
    
    def get_diagnostic_category_code(self, record_type: str) -> str:
        """
        Get FHIR diagnostic category code for internal record type.
        
        Args:
            record_type: Internal record type
            
        Returns:
            Diagnostic category code
        """
        category_map = {
            'lab_report': 'LAB',
            'imaging': 'RAD',
            'pathology': 'PAT',
            'cardiology': 'CG',
            'microbiology': 'MB',
            'chemistry': 'CH',
            'hematology': 'HM',
            'immunology': 'IMM',
            'toxicology': 'TOX',
            'cytology': 'CYT',
            'genetics': 'GE'
        }
        return category_map.get(record_type, 'OTH')  # Default: Other
    
    def validate_fhir_resource(self, resource) -> Dict[str, Any]:
        """
        Validate a FHIR resource for R4 compliance.
        
        Args:
            resource: FHIR resource instance
            
        Returns:
            Dictionary with validation results
        """
        validation_result = {
            'is_valid': True,
            'errors': [],
            'warnings': []
        }
        
        try:
            # Basic validation - check required fields
            if not hasattr(resource, 'resource_type'):
                validation_result['is_valid'] = False
                validation_result['errors'].append("Missing resource_type")
            
            if not hasattr(resource, 'id') or not resource.id:
                validation_result['warnings'].append("Missing resource ID")
            
            # Resource-specific validation
            if hasattr(resource, 'resource_type'):
                if resource.resource_type == 'Patient':
                    self._validate_patient_resource(resource, validation_result)
                elif resource.resource_type == 'Observation':
                    self._validate_observation_resource(resource, validation_result)
                elif resource.resource_type == 'DiagnosticReport':
                    self._validate_diagnostic_report_resource(resource, validation_result)
                elif resource.resource_type == 'MedicationRequest':
                    self._validate_medication_request_resource(resource, validation_result)
                elif resource.resource_type == 'Bundle':
                    self._validate_bundle_resource(resource, validation_result)
            
            # Try to serialize to catch any structural issues
            try:
                resource.json()
            except Exception as e:
                validation_result['is_valid'] = False
                validation_result['errors'].append(f"Serialization error: {str(e)}")
                
        except Exception as e:
            validation_result['is_valid'] = False
            validation_result['errors'].append(f"Validation error: {str(e)}")
        
        return validation_result
    
    def _validate_patient_resource(self, patient, validation_result):
        """Validate Patient resource specific requirements."""
        if not hasattr(patient, 'identifier') or not patient.identifier:
            validation_result['warnings'].append("Patient missing identifier")
        
        if not hasattr(patient, 'name') or not patient.name:
            validation_result['warnings'].append("Patient missing name")
    
    def _validate_observation_resource(self, observation, validation_result):
        """Validate Observation resource specific requirements."""
        required_fields = ['status', 'code', 'subject']
        for field in required_fields:
            if not hasattr(observation, field) or not getattr(observation, field):
                validation_result['is_valid'] = False
                validation_result['errors'].append(f"Observation missing required field: {field}")
        
        # Check status is valid
        if hasattr(observation, 'status'):
            valid_statuses = ['registered', 'preliminary', 'final', 'amended', 'corrected', 'cancelled', 'entered-in-error', 'unknown']
            if observation.status not in valid_statuses:
                validation_result['is_valid'] = False
                validation_result['errors'].append(f"Invalid observation status: {observation.status}")
    
    def _validate_diagnostic_report_resource(self, report, validation_result):
        """Validate DiagnosticReport resource specific requirements."""
        required_fields = ['status', 'code', 'subject']
        for field in required_fields:
            if not hasattr(report, field) or not getattr(report, field):
                validation_result['is_valid'] = False
                validation_result['errors'].append(f"DiagnosticReport missing required field: {field}")
        
        # Check status is valid
        if hasattr(report, 'status'):
            valid_statuses = ['registered', 'partial', 'preliminary', 'final', 'amended', 'corrected', 'appended', 'cancelled', 'entered-in-error', 'unknown']
            if report.status not in valid_statuses:
                validation_result['is_valid'] = False
                validation_result['errors'].append(f"Invalid diagnostic report status: {report.status}")
    
    def _validate_medication_request_resource(self, med_request, validation_result):
        """Validate MedicationRequest resource specific requirements."""
        required_fields = ['status', 'intent', 'subject']
        for field in required_fields:
            if not hasattr(med_request, field) or not getattr(med_request, field):
                validation_result['is_valid'] = False
                validation_result['errors'].append(f"MedicationRequest missing required field: {field}")
        
        # Check medication is specified
        if not (hasattr(med_request, 'medicationCodeableConcept') or hasattr(med_request, 'medicationReference')):
            validation_result['is_valid'] = False
            validation_result['errors'].append("MedicationRequest missing medication specification")
    
    def _validate_bundle_resource(self, bundle, validation_result):
        """Validate Bundle resource specific requirements."""
        required_fields = ['type']
        for field in required_fields:
            if not hasattr(bundle, field) or not getattr(bundle, field):
                validation_result['is_valid'] = False
                validation_result['errors'].append(f"Bundle missing required field: {field}")
        
        # Validate bundle type
        if hasattr(bundle, 'type'):
            valid_types = ['document', 'message', 'transaction', 'transaction-response', 'batch', 'batch-response', 'history', 'searchset', 'collection']
            if bundle.type not in valid_types:
                validation_result['is_valid'] = False
                validation_result['errors'].append(f"Invalid bundle type: {bundle.type}")
        
        # Check entries
        if hasattr(bundle, 'entry') and bundle.entry:
            for i, entry in enumerate(bundle.entry):
                if not hasattr(entry, 'resource') or not entry.resource:
                    validation_result['warnings'].append(f"Bundle entry {i} missing resource")
    
    def export_to_json(self, resource) -> str:
        """
        Export FHIR resource to JSON string.
        
        Args:
            resource: FHIR resource instance
            
        Returns:
            JSON string representation
        """
        try:
            return resource.json(indent=2)
        except Exception as e:
            logger.error(f"Error exporting FHIR resource to JSON: {e}")
            return "{}"
    
    def export_to_xml(self, resource) -> str:
        """
        Export FHIR resource to XML string.
        
        Args:
            resource: FHIR resource instance
            
        Returns:
            XML string representation
        """
        try:
            # Note: This would require additional XML serialization
            # For now, return JSON wrapped in XML structure
            json_data = resource.json()
            return f"<fhir>{json_data}</fhir>"
        except Exception as e:
            logger.error(f"Error exporting FHIR resource to XML: {e}")
            return "<fhir></fhir>"
    
    def get_supported_resource_types(self) -> List[str]:
        """
        Get list of supported FHIR resource types.
        
        Returns:
            List of supported resource type names
        """
        return [
            'Patient',
            'Organization', 
            'Practitioner',
            'Observation',
            'DiagnosticReport',
            'MedicationRequest',
            'Condition',
            'DocumentReference',
            'Bundle'
        ]
    
    def create_operation_outcome(self, severity: str, code: str, details: str) -> Dict[str, Any]:
        """
        Create a FHIR OperationOutcome for error reporting.
        
        Args:
            severity: Severity level (fatal, error, warning, information)
            code: Error code
            details: Error details
            
        Returns:
            OperationOutcome as dictionary
        """
        return {
            "resourceType": "OperationOutcome",
            "id": str(uuid.uuid4()),
            "issue": [{
                "severity": severity,
                "code": code,
                "details": {
                    "text": details
                }
            }]
        }


class FHIRBundleBuilder:
    """
    Helper class for building complex FHIR bundles with multiple resources.
    """
    
    def __init__(self, bundle_type: str = "collection"):
        self.bundle_type = bundle_type
        self.entries = []
        self.bundle_id = str(uuid.uuid4())
    
    def add_resource(self, resource, full_url: str = None):
        """
        Add a resource to the bundle.
        
        Args:
            resource: FHIR resource instance
            full_url: Full URL for the resource (optional)
        """
        if not full_url and hasattr(resource, 'resource_type') and hasattr(resource, 'id'):
            full_url = f"{resource.resource_type}/{resource.id}"
        
        entry = BundleEntry(
            resource=resource,
            fullUrl=full_url
        )
        self.entries.append(entry)
    
    def build(self) -> BundleType:
        """
        Build and return the FHIR Bundle.
        
        Returns:
            FHIR Bundle resource
        """
        bundle = Bundle(
            id=self.bundle_id,
            type=self.bundle_type,
            timestamp=datetime.utcnow().isoformat() + "Z",
            entry=self.entries
        )
        return bundle
    
    def get_entry_count(self) -> int:
        """Get the number of entries in the bundle."""
        return len(self.entries)
    
    def clear(self):
        """Clear all entries from the bundle."""
        self.entries = []
        self.bundle_id = str(uuid.uuid4())


# Convenience functions for easy import
def create_patient_bundle(patient, clinical_records=None, **kwargs):
    """
    Convenience function to create a patient bundle.
    
    Args:
        patient: Patient model instance
        clinical_records: List of ClinicalRecord instances
        **kwargs: Additional arguments for bundle creation
        
    Returns:
        FHIR Bundle or None
    """
    if not FHIR_AVAILABLE:
        logger.error("FHIR resources not available")
        return None
    
    service = FHIRExportService()
    return service.create_patient_bundle(patient, clinical_records, **kwargs)


def create_individual_resource(clinical_record, resource_type=None):
    """
    Convenience function to create individual FHIR resources.
    
    Args:
        clinical_record: ClinicalRecord instance
        resource_type: Specific FHIR resource type
        
    Returns:
        List of FHIR resources
    """
    if not FHIR_AVAILABLE:
        logger.error("FHIR resources not available")
        return []
    
    service = FHIRExportService()
    return service.create_individual_resource(clinical_record, resource_type)


def validate_fhir_resource(resource):
    """
    Convenience function to validate FHIR resources.
    
    Args:
        resource: FHIR resource instance
        
    Returns:
        Validation result dictionary
    """
    if not FHIR_AVAILABLE:
        return {
            'is_valid': False,
            'errors': ['FHIR resources not available'],
            'warnings': []
        }
    
    service = FHIRExportService()
    return service.validate_fhir_resource(resource)