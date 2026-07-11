"""
Patient Sync Service for Clinical Records Service

This service handles synchronization of patient data from RxBackend to ClinicalRecordsService.
It ensures patient data is up-to-date and creates patient records when needed.
"""

import requests
import logging
from typing import Dict, Optional, List
from django.conf import settings
from django.utils import timezone
from ..models import Patient
from .exceptions import PatientSyncError

logger = logging.getLogger(__name__)


class PatientSyncService:
    """
    Service to synchronize patient data from RxBackend
    """
    
    def __init__(self):
        self.rxbackend_url = settings.RXBACKEND_SERVICE_URL
        self.timeout = settings.RXBACKEND_API_TIMEOUT
        self.session = requests.Session()
        
        # Set default headers
        self.session.headers.update({
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        })
    
    def sync_patient_from_rxbackend(self, patient_id: int, token: str = None) -> Optional[Patient]:
        """
        Sync a specific patient from RxBackend
        
        Args:
            patient_id: Patient ID from RxBackend
            token: JWT token for authentication
            
        Returns:
            Patient instance if successful, None otherwise
        """
        try:
            headers = {}
            if token:
                headers['Authorization'] = f'Bearer {token}'
            
            # Fetch patient data from RxBackend
            response = self.session.get(
                f"{self.rxbackend_url}/api/api/patients/{patient_id}/sync/",
                headers=headers,
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                patient_data = response.json()
                return self._create_or_update_patient(patient_data)
            else:
                logger.warning(f"Failed to fetch patient {patient_id} from RxBackend: {response.status_code}")
                return None
                
        except requests.RequestException as e:
            logger.error(f"Error syncing patient {patient_id} from RxBackend: {e}")
            return None
    
    def _create_or_update_patient(self, patient_data: Dict) -> Patient:
        """
        Create or update patient based on RxBackend data
        
        Args:
            patient_data: Patient data from RxBackend
            
        Returns:
            Patient instance
        """
        try:
            rxbackend_patient_id = patient_data.get('id')
            if not rxbackend_patient_id:
                raise PatientSyncError("Patient ID is required")
            
            # Get or create patient
            patient, created = Patient.objects.get_or_create(
                rxbackend_patient_id=rxbackend_patient_id,
                defaults={
                    'patient_id': patient_data.get('patient_id') or f"P{rxbackend_patient_id}",
                    'first_name': patient_data.get('first_name') or '',
                    'last_name': patient_data.get('last_name') or '',
                    'date_of_birth': patient_data.get('date_of_birth'),
                    'phone_number': patient_data.get('phone_number') or '',
                    'email': patient_data.get('email'),
                    'clinic_id': patient_data.get('clinic_id') or 1,
                    'clinic_name': patient_data.get('clinic_name') or '',
                    'address': patient_data.get('address') or '',
                    'gender': patient_data.get('gender') or '',
                    'blood_group': patient_data.get('blood_group') or '',
                    'is_active': patient_data.get('is_active') if patient_data.get('is_active') is not None else True,
                }
            )
            
            if not created:
                # Update existing patient
                patient.patient_id = patient_data.get('patient_id') or patient.patient_id
                patient.first_name = patient_data.get('first_name') or patient.first_name
                patient.last_name = patient_data.get('last_name') or patient.last_name
                if 'date_of_birth' in patient_data:
                    patient.date_of_birth = patient_data.get('date_of_birth')
                if 'phone_number' in patient_data:
                    patient.phone_number = patient_data.get('phone_number') or ''
                if 'email' in patient_data:
                    patient.email = patient_data.get('email')
                patient.clinic_id = patient_data.get('clinic_id') or patient.clinic_id
                patient.clinic_name = patient_data.get('clinic_name') or patient.clinic_name
                patient.address = patient_data.get('address') or patient.address
                patient.gender = patient_data.get('gender') or patient.gender
                patient.blood_group = patient_data.get('blood_group') or patient.blood_group
                if 'is_active' in patient_data:
                    patient.is_active = patient_data.get('is_active') if patient_data.get('is_active') is not None else patient.is_active
                patient.last_synced = timezone.now()
                patient.save()
            
            action = "Created" if created else "Updated"
            logger.info(f"{action} patient: {patient.get_full_name()} (ID: {patient.rxbackend_patient_id})")
            
            return patient
            
        except Exception as e:
            logger.error(f"Error creating/updating patient: {e}")
            raise PatientSyncError(f"Failed to sync patient: {e}")
    
    def bulk_sync_patients(self, token: str = None, limit: int = 100) -> int:
        """
        Bulk synchronize patients from RxBackend
        
        Args:
            token: JWT token for authentication
            limit: Maximum number of patients to sync
            
        Returns:
            Number of patients synced
        """
        try:
            headers = {}
            if token:
                headers['Authorization'] = f'Bearer {token}'
            
            response = self.session.get(
                f"{self.rxbackend_url}/api/api/patients/sync/",
                headers=headers,
                timeout=self.timeout,
                params={'limit': limit}
            )
            
            if response.status_code == 200:
                data = response.json()
                patients = data.get('results', [])
                
                synced_count = 0
                for patient_data in patients:
                    try:
                        if self._create_or_update_patient(patient_data):
                            synced_count += 1
                    except PatientSyncError as e:
                        logger.error(f"Failed to sync patient {patient_data.get('id')}: {e}")
                        continue
                
                logger.info(f"Bulk synced {synced_count} patients from RxBackend")
                return synced_count
            else:
                logger.warning(f"Failed to bulk sync patients from RxBackend: {response.status_code}")
                return 0
                
        except requests.RequestException as e:
            logger.error(f"Error bulk syncing patients from RxBackend: {e}")
            return 0
    
    def get_patient_by_rxbackend_id(self, rxbackend_patient_id: int) -> Optional[Patient]:
        """
        Get patient by RxBackend patient ID
        
        Args:
            rxbackend_patient_id: Patient ID from RxBackend
            
        Returns:
            Patient instance if found, None otherwise
        """
        try:
            return Patient.objects.get(rxbackend_patient_id=rxbackend_patient_id)
        except Patient.DoesNotExist:
            return None
    
    def ensure_patient_exists(self, rxbackend_patient_id: int, token: str = None) -> Optional[Patient]:
        """
        Ensure patient exists in ClinicalRecordsService, sync if needed
        
        Args:
            rxbackend_patient_id: Patient ID from RxBackend
            token: JWT token for authentication
            
        Returns:
            Patient instance if successful, None otherwise
        """
        # First try to get existing patient
        patient = self.get_patient_by_rxbackend_id(rxbackend_patient_id)
        if patient:
            return patient
        
        # If not found, sync from RxBackend
        logger.info(f"Patient {rxbackend_patient_id} not found, syncing from RxBackend")
        return self.sync_patient_from_rxbackend(rxbackend_patient_id, token)
    
    def get_patients_by_clinic(self, clinic_id: int) -> List[Patient]:
        """
        Get all patients for a specific clinic
        
        Args:
            clinic_id: Clinic ID from RxBackend
            
        Returns:
            List of Patient instances
        """
        return Patient.objects.filter(clinic_id=clinic_id, is_active=True).order_by('first_name', 'last_name')
    
    def deactivate_patient(self, rxbackend_patient_id: int) -> bool:
        """
        Deactivate a patient (mark as inactive)
        
        Args:
            rxbackend_patient_id: Patient ID from RxBackend
            
        Returns:
            True if successful, False otherwise
        """
        try:
            patient = Patient.objects.get(rxbackend_patient_id=rxbackend_patient_id)
            patient.is_active = False
            patient.save()
            logger.info(f"Deactivated patient: {patient.get_full_name()}")
            return True
        except Patient.DoesNotExist:
            logger.warning(f"Patient {rxbackend_patient_id} not found for deactivation")
            return False
        except Exception as e:
            logger.error(f"Error deactivating patient {rxbackend_patient_id}: {e}")
            return False


# Create singleton instance
patient_sync_service = PatientSyncService()


def get_patient_sync_service() -> PatientSyncService:
    """
    Factory function to get PatientSyncService instance
    
    Returns:
        PatientSyncService: Service instance
    """
    return patient_sync_service
