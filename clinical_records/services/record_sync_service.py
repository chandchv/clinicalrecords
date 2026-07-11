"""
Record Sync Service for Clinical Records Service

This service handles synchronization of medical records (prescriptions, labs) from RxBackend.
"""

import requests
import logging
from typing import Dict, Optional, List
from django.conf import settings
from django.utils import timezone
import datetime
from ..models import Patient, ClinicalRecord
from ..serializers import ClinicalRecordSerializer

logger = logging.getLogger(__name__)


class RecordSyncService:
    """
    Service to synchronize medical records from RxBackend
    """
    
    def __init__(self):
        self.rxbackend_url = getattr(settings, 'RXBACKEND_SERVICE_URL', 'http://127.0.0.1:8000') # specific fallback
        self.timeout = getattr(settings, 'RXBACKEND_API_TIMEOUT', 10)
        self.session = requests.Session()
        
        # Set default headers
        self.session.headers.update({
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        })
    
    def sync_prescriptions(self, patient: Patient, token: str, user=None) -> int:
        """
        Sync prescriptions for a patient
        
        Args:
            patient: Local Patient instance
            token: JWT token for authentication with RxBackend
            user: User instance initiating the sync
            
        Returns:
            Number of new records synced
        """
        try:
            if not token:
                logger.warning("No token provided for prescription sync")
                return 0

            headers = {'Authorization': f'Bearer {token}'}
            
            response = self.session.get(
                f"{self.rxbackend_url}/api/api/patient/sync/prescriptions/",
                headers=headers,
                timeout=self.timeout
            )
            
            if response.status_code != 200:
                logger.warning(f"Failed to fetch prescriptions from RxBackend: {response.status_code}")
                return 0
                
            prescriptions = response.json()
            synced_count = 0
            
            for pres in prescriptions:
                # Check for duplicate
                external_id = str(pres.get('id'))
                if ClinicalRecord.objects.filter(external_id=external_id, record_type='prescription').exists():
                    continue
                
                # Create record
                # pres keys depend on RxBackend serializer. 
                # Assuming: id, doctor_name, date, diagnosis...
                
                # Parse date
                record_date = timezone.now().date()
                if pres.get('created_at'):
                    try:
                        record_date = datetime.datetime.fromisoformat(pres.get('created_at').replace('Z', '+00:00')).date()
                    except:
                        pass
                
                doctor_name = "Unknown Doctor"
                if pres.get('doctor'):
                    if isinstance(pres['doctor'], dict):
                        doctor_name = pres['doctor'].get('name', doctor_name)
                    else:
                        doctor_name = str(pres['doctor'])
                        
                title = f"Prescription by {doctor_name}"
                description = f"Synced from RxBackend. Diagnosis: {pres.get('diagnosis', 'N/A')}"
                
                # Handle created_by
                if not user:
                     # Fallback to ID 1 if no user provided, or fetch a system user
                     created_by_id = 1
                     created_by = None
                else: 
                     created_by_id = None
                     created_by = user

                # Using created_by_id if created_by is None, assuming ID 1 exists
                record_kwargs = {
                    'patient': patient,
                    'title': title,
                    'description': description,
                    'record_type': 'prescription',
                    'status': 'active',
                    'record_date': record_date,
                    'external_id': external_id,
                    'tenant_id': patient.tenant_id if hasattr(patient, 'tenant_id') else 1,
                }
                
                if created_by:
                    record_kwargs['created_by'] = created_by
                else:
                    record_kwargs['created_by_id'] = 1

                ClinicalRecord.objects.create(**record_kwargs)
                synced_count += 1
            
            return synced_count

        except Exception as e:
            logger.error(f"Error syncing prescriptions: {e}")
            return 0



    def sync_labs(self, patient: Patient, token: str, user=None) -> int:
        """
        Sync lab records for a patient
        """
        try:
            if not token:
                return 0

            headers = {'Authorization': f'Bearer {token}'}
            
            response = self.session.get(
                f"{self.rxbackend_url}/api/api/patient/sync/labs/",
                headers=headers,
                timeout=self.timeout
            )
            
            if response.status_code != 200:
                logger.warning(f"Failed to fetch labs from RxBackend: {response.status_code}")
                return 0
                
            labs = response.json()
            synced_count = 0
            
            for lab in labs:
                external_id = str(lab.get('id'))
                if ClinicalRecord.objects.filter(external_id=external_id, record_type='lab_report').exists():
                    continue
                
                # Parse date
                record_date = timezone.now().date()
                if lab.get('test_date'):
                     try:
                        record_date = datetime.datetime.strptime(lab.get('test_date'), '%Y-%m-%d').date()
                     except:
                        pass
                
                test_name = lab.get('test_name', 'Lab Test')
                lab_name = lab.get('lab_name', 'Unknown Lab')
                
                title = f"{test_name} - {lab_name}"
                description = f"Synced from RxBackend.\nResult: {lab.get('result_value', 'N/A')}\nReference: {lab.get('reference_range', 'N/A')}"
                
                # Handle created_by
                created_by = None
                if user:
                    created_by = user
                
                record_kwargs = {
                    'patient': patient,
                    'title': title,
                    'description': description,
                    'record_type': 'lab_report',
                    'status': 'completed',
                    'record_date': record_date,
                    'external_id': external_id,
                    'tenant_id': patient.tenant_id if hasattr(patient, 'tenant_id') else 1,
                }
                
                if created_by:
                    record_kwargs['created_by'] = created_by
                else:
                    record_kwargs['created_by_id'] = 1

                ClinicalRecord.objects.create(**record_kwargs)
                synced_count += 1
                
            return synced_count
            
        except Exception as e:
            logger.error(f"Error syncing labs: {e}")
            return 0


# Singleton
record_sync_service = RecordSyncService()

def get_record_sync_service():
    return record_sync_service
