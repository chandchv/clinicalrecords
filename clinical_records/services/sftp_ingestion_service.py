"""
SFTP Ingestion Service for Clinical Records

This service handles monitoring SFTP directories for clinical document uploads,
including file naming convention parsing, patient matching, and batch processing.
"""
import logging
import os
import re
import time
import threading
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from pathlib import Path
import tempfile
import shutil

from django.conf import settings
from django.core.files.base import ContentFile
from django.utils import timezone
from django.db import transaction

try:
    import paramiko
    PARAMIKO_AVAILABLE = True
except ImportError:
    PARAMIKO_AVAILABLE = False
    logging.warning("paramiko not available - SFTP functionality will be limited")

from users.models import Patient, Clinic, AuditLog
from ..models import ClinicalRecord, ClinicalDocument
from ..utils.file_utils import FileValidator, FileTypeDetector
from .ocr_processor import ClinicalOCRProcessor

logger = logging.getLogger(__name__)


class SFTPIngestionError(Exception):
    """Custom exception for SFTP ingestion errors"""
    pass


class FileNamingConventionParser:
    """Service for parsing file naming conventions to extract metadata"""
    
    def __init__(self):
        # Define common naming convention patterns
        self.naming_patterns = {
            # Pattern: clinic_patient_type_date.ext
            'standard': r'^(?P<clinic_code>[A-Za-z0-9]+)_(?P<patient_id>[A-Za-z0-9]+)_(?P<record_type>[A-Za-z_]+)_(?P<date>\d{8})\.(?P<extension>[A-Za-z0-9]+)$',
            
            # Pattern: CLINIC-PATIENT-TYPE-YYYYMMDD.ext
            'dash_separated': r'^(?P<clinic_code>[A-Za-z0-9]+)-(?P<patient_id>[A-Za-z0-9]+)-(?P<record_type>[A-Za-z_]+)-(?P<date>\d{8})\.(?P<extension>[A-Za-z0-9]+)$',
            
            # Pattern: PatientID_RecordType_YYYYMMDD_HHMMSS.ext
            'detailed': r'^(?P<patient_id>[A-Za-z0-9]+)_(?P<record_type>[A-Za-z_]+)_(?P<date>\d{8})_(?P<time>\d{6})\.(?P<extension>[A-Za-z0-9]+)$',
            
            # Pattern: YYYYMMDD_PatientID_Type.ext
            'date_first': r'^(?P<date>\d{8})_(?P<patient_id>[A-Za-z0-9]+)_(?P<record_type>[A-Za-z_]+)\.(?P<extension>[A-Za-z0-9]+)$',
            
            # Pattern: Type_PatientID_YYYYMMDD.ext
            'type_first': r'^(?P<record_type>[A-Za-z_]+)_(?P<patient_id>[A-Za-z0-9]+)_(?P<date>\d{8})\.(?P<extension>[A-Za-z0-9]+)$',
            
            # Pattern: PatientLastName_FirstName_DOB_Type.ext
            'name_based': r'^(?P<last_name>[A-Za-z]+)_(?P<first_name>[A-Za-z]+)_(?P<dob>\d{8})_(?P<record_type>[A-Za-z_]+)\.(?P<extension>[A-Za-z0-9]+)$',
            
            # Pattern: MRN12345_LabReport_20240101.pdf
            'mrn_based': r'^MRN(?P<patient_id>[0-9]+)_(?P<record_type>[A-Za-z_]+)_(?P<date>\d{8})\.(?P<extension>[A-Za-z0-9]+)$',
        }
        
        # Record type mappings
        self.record_type_mappings = {
            'lab': 'lab_report',
            'labs': 'lab_report',
            'laboratory': 'lab_report',
            'blood': 'lab_report',
            'urine': 'lab_report',
            'pathology': 'lab_report',
            
            'rx': 'prescription',
            'prescription': 'prescription',
            'medication': 'prescription',
            'meds': 'prescription',
            
            'xray': 'imaging',
            'ct': 'imaging',
            'mri': 'imaging',
            'ultrasound': 'imaging',
            'imaging': 'imaging',
            'radiology': 'imaging',
            
            'discharge': 'discharge_summary',
            'summary': 'discharge_summary',
            
            'consult': 'consultation',
            'consultation': 'consultation',
            'visit': 'consultation',
            'note': 'consultation',
            
            'vaccine': 'vaccination',
            'vaccination': 'vaccination',
            'immunization': 'vaccination',
        }
    
    def parse_filename(self, filename: str) -> Dict:
        """
        Parse filename to extract metadata
        
        Args:
            filename: Name of the file to parse
            
        Returns:
            Dictionary with extracted metadata
        """
        result = {
            'parsed': False,
            'pattern_used': None,
            'clinic_code': None,
            'patient_id': None,
            'record_type': None,
            'date': None,
            'time': None,
            'extension': None,
            'first_name': None,
            'last_name': None,
            'dob': None,
            'original_filename': filename
        }
        
        # Try each pattern
        for pattern_name, pattern in self.naming_patterns.items():
            match = re.match(pattern, filename, re.IGNORECASE)
            if match:
                result['parsed'] = True
                result['pattern_used'] = pattern_name
                
                # Extract matched groups
                groups = match.groupdict()
                for key, value in groups.items():
                    if value:
                        result[key] = value
                
                # Normalize record type
                if result.get('record_type'):
                    normalized_type = self._normalize_record_type(result['record_type'])
                    result['record_type'] = normalized_type
                
                # Parse date if present
                if result.get('date'):
                    try:
                        date_obj = datetime.strptime(result['date'], '%Y%m%d')
                        result['parsed_date'] = date_obj
                    except ValueError:
                        logger.warning(f"Could not parse date {result['date']} in filename {filename}")
                
                # Parse DOB if present
                if result.get('dob'):
                    try:
                        dob_obj = datetime.strptime(result['dob'], '%Y%m%d').date()
                        result['parsed_dob'] = dob_obj
                    except ValueError:
                        logger.warning(f"Could not parse DOB {result['dob']} in filename {filename}")
                
                break
        
        return result
    
    def _normalize_record_type(self, record_type: str) -> str:
        """Normalize record type to standard values"""
        record_type_lower = record_type.lower().replace('-', '_')
        return self.record_type_mappings.get(record_type_lower, 'other')
    
    def generate_filename(self, patient_id: str, record_type: str, 
                         clinic_code: str = None, date: datetime = None) -> str:
        """
        Generate filename following standard naming convention
        
        Args:
            patient_id: Patient identifier
            record_type: Type of clinical record
            clinic_code: Clinic code (optional)
            date: Date for the record (defaults to today)
            
        Returns:
            Generated filename
        """
        if not date:
            date = datetime.now()
        
        date_str = date.strftime('%Y%m%d')
        
        if clinic_code:
            return f"{clinic_code}_{patient_id}_{record_type}_{date_str}.pdf"
        else:
            return f"{patient_id}_{record_type}_{date_str}.pdf"


class SFTPPatientMatcher:
    """Service for matching patients from SFTP file metadata"""
    
    def __init__(self, clinic: Clinic):
        self.clinic = clinic
    
    def match_patient_from_metadata(self, metadata: Dict) -> Optional[Patient]:
        """
        Match patient from parsed file metadata
        
        Args:
            metadata: Parsed metadata from filename
            
        Returns:
            Patient object if match found, None otherwise
        """
        # Strategy 1: Match by patient ID
        if metadata.get('patient_id'):
            patient = self._match_by_patient_id(metadata['patient_id'])
            if patient:
                return patient
        
        # Strategy 2: Match by name and DOB
        if metadata.get('first_name') and metadata.get('last_name') and metadata.get('parsed_dob'):
            patient = self._match_by_name_and_dob(
                metadata['first_name'], 
                metadata['last_name'], 
                metadata['parsed_dob']
            )
            if patient:
                return patient
        
        # Strategy 3: Match by name only (less reliable)
        if metadata.get('first_name') and metadata.get('last_name'):
            patient = self._match_by_name_only(
                metadata['first_name'], 
                metadata['last_name']
            )
            if patient:
                return patient
        
        return None
    
    def _match_by_patient_id(self, patient_id: str) -> Optional[Patient]:
        """Match patient by ID"""
        try:
            # Try exact ID match
            patient = Patient.objects.filter(
                clinic=self.clinic,
                id=patient_id
            ).first()
            if patient:
                return patient
            
            # Try phone number match if ID looks like a phone number
            if patient_id.isdigit() and len(patient_id) >= 10:
                patient = Patient.objects.filter(
                    clinic=self.clinic,
                    phone__icontains=patient_id[-10:]
                ).first()
                if patient:
                    return patient
            
        except Exception as e:
            logger.debug(f"Error matching patient by ID {patient_id}: {e}")
        
        return None
    
    def _match_by_name_and_dob(self, first_name: str, last_name: str, dob) -> Optional[Patient]:
        """Match patient by name and date of birth"""
        try:
            patient = Patient.objects.filter(
                clinic=self.clinic,
                first_name__iexact=first_name,
                last_name__iexact=last_name,
                date_of_birth=dob
            ).first()
            return patient
        except Exception as e:
            logger.debug(f"Error matching patient by name and DOB: {e}")
            return None
    
    def _match_by_name_only(self, first_name: str, last_name: str) -> Optional[Patient]:
        """Match patient by name only (less reliable)"""
        try:
            # Try exact match first
            patient = Patient.objects.filter(
                clinic=self.clinic,
                first_name__iexact=first_name,
                last_name__iexact=last_name
            ).first()
            if patient:
                return patient
            
            # Try partial match
            patient = Patient.objects.filter(
                clinic=self.clinic,
                first_name__icontains=first_name,
                last_name__icontains=last_name
            ).first()
            return patient
            
        except Exception as e:
            logger.debug(f"Error matching patient by name: {e}")
            return None


class SFTPMonitor:
    """SFTP directory monitoring service"""
    
    def __init__(self, config: Dict):
        self.config = config
        self.is_running = False
        self.monitor_thread = None
        self.last_check = None
        
        # Validate configuration
        self._validate_config()
        
        # Initialize SFTP client if using remote SFTP
        self.sftp_client = None
        if config.get('connection_type') == 'remote':
            if not PARAMIKO_AVAILABLE:
                raise SFTPIngestionError("paramiko is required for remote SFTP connections")
            self._init_sftp_client()
    
    def _validate_config(self):
        """Validate SFTP configuration"""
        required_fields = ['clinic_id', 'monitor_directory', 'connection_type']
        for field in required_fields:
            if field not in self.config:
                raise SFTPIngestionError(f"Missing required config field: {field}")
        
        if self.config['connection_type'] == 'remote':
            remote_required = ['host', 'username']
            for field in remote_required:
                if field not in self.config:
                    raise SFTPIngestionError(f"Missing required remote config field: {field}")
    
    def _init_sftp_client(self):
        """Initialize SFTP client for remote connections"""
        try:
            # Create SSH client
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            # Connect
            connect_kwargs = {
                'hostname': self.config['host'],
                'username': self.config['username'],
                'port': self.config.get('port', 22),
                'timeout': self.config.get('timeout', 30)
            }
            
            # Add authentication
            if self.config.get('password'):
                connect_kwargs['password'] = self.config['password']
            elif self.config.get('key_file'):
                connect_kwargs['key_filename'] = self.config['key_file']
            
            ssh.connect(**connect_kwargs)
            
            # Create SFTP client
            self.sftp_client = ssh.open_sftp()
            
            logger.info(f"Connected to SFTP server {self.config['host']}")
            
        except Exception as e:
            logger.error(f"Failed to connect to SFTP server: {e}")
            raise SFTPIngestionError(f"SFTP connection failed: {e}")
    
    def start_monitoring(self):
        """Start monitoring SFTP directory"""
        if self.is_running:
            logger.warning("SFTP monitor is already running")
            return
        
        self.is_running = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        
        logger.info(f"Started SFTP monitoring for directory: {self.config['monitor_directory']}")
    
    def stop_monitoring(self):
        """Stop monitoring SFTP directory"""
        self.is_running = False
        
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=10)
        
        if self.sftp_client:
            try:
                self.sftp_client.close()
            except Exception:
                pass
        
        logger.info("Stopped SFTP monitoring")
    
    def _monitor_loop(self):
        """Main monitoring loop"""
        check_interval = self.config.get('check_interval', 60)  # seconds
        
        while self.is_running:
            try:
                self._check_for_new_files()
                self.last_check = timezone.now()
            except Exception as e:
                logger.error(f"Error during SFTP monitoring: {e}")
                
                # Log monitoring failure
                self._log_monitoring_failure(str(e))
                
                # Wait before retrying
                time.sleep(min(check_interval * 2, 300))  # Max 5 minutes
            
            # Wait for next check
            time.sleep(check_interval)
    
    def _check_for_new_files(self):
        """Check for new files in monitored directory"""
        if self.config['connection_type'] == 'local':
            files = self._list_local_files()
        else:
            files = self._list_remote_files()
        
        # Filter for new files
        new_files = self._filter_new_files(files)
        
        if new_files:
            logger.info(f"Found {len(new_files)} new files to process")
            
            # Process files
            for file_info in new_files:
                try:
                    self._process_file(file_info)
                except Exception as e:
                    logger.error(f"Error processing file {file_info['name']}: {e}")
    
    def _list_local_files(self) -> List[Dict]:
        """List files in local directory"""
        files = []
        directory = Path(self.config['monitor_directory'])
        
        if not directory.exists():
            logger.warning(f"Monitor directory does not exist: {directory}")
            return files
        
        for file_path in directory.iterdir():
            if file_path.is_file():
                stat = file_path.stat()
                files.append({
                    'name': file_path.name,
                    'path': str(file_path),
                    'size': stat.st_size,
                    'modified_time': datetime.fromtimestamp(stat.st_mtime),
                    'is_local': True
                })
        
        return files
    
    def _list_remote_files(self) -> List[Dict]:
        """List files in remote SFTP directory"""
        files = []
        
        if not self.sftp_client:
            raise SFTPIngestionError("SFTP client not initialized")
        
        try:
            file_attrs = self.sftp_client.listdir_attr(self.config['monitor_directory'])
            
            for attr in file_attrs:
                if not attr.filename.startswith('.'):  # Skip hidden files
                    files.append({
                        'name': attr.filename,
                        'path': f"{self.config['monitor_directory']}/{attr.filename}",
                        'size': attr.st_size,
                        'modified_time': datetime.fromtimestamp(attr.st_mtime),
                        'is_local': False
                    })
        
        except Exception as e:
            logger.error(f"Error listing remote files: {e}")
            raise
        
        return files
    
    def _filter_new_files(self, files: List[Dict]) -> List[Dict]:
        """Filter for files that haven't been processed"""
        # Simple implementation - could be enhanced with database tracking
        new_files = []
        
        # Filter by file age (only process files older than 30 seconds to avoid partial uploads)
        min_age = timedelta(seconds=30)
        cutoff_time = timezone.now() - min_age
        
        for file_info in files:
            # Convert to timezone-aware datetime
            modified_time = timezone.make_aware(file_info['modified_time'])
            
            if modified_time < cutoff_time:
                # Check if file has supported extension
                if self._is_supported_file(file_info['name']):
                    new_files.append(file_info)
        
        return new_files
    
    def _is_supported_file(self, filename: str) -> bool:
        """Check if file type is supported"""
        supported_extensions = ['.pdf', '.jpg', '.jpeg', '.png', '.tiff', '.dcm', '.csv', '.txt']
        return any(filename.lower().endswith(ext) for ext in supported_extensions)
    
    def _process_file(self, file_info: Dict):
        """Process a single file"""
        logger.info(f"Processing file: {file_info['name']}")
        
        # Download file if remote
        if file_info['is_local']:
            local_path = file_info['path']
            cleanup_file = False
        else:
            local_path = self._download_remote_file(file_info)
            cleanup_file = True
        
        try:
            # Get clinic
            clinic = Clinic.objects.get(id=self.config['clinic_id'])
            
            # Process the file
            processor = SFTPFileProcessor(clinic)
            result = processor.process_file(
                file_path=local_path,
                original_filename=file_info['name'],
                file_size=file_info['size'],
                processing_user=None  # System processing
            )
            
            if result['success']:
                logger.info(f"Successfully processed {file_info['name']}")
                
                # Move processed file if configured
                if self.config.get('move_processed_files'):
                    self._move_processed_file(file_info)
            else:
                logger.error(f"Failed to process {file_info['name']}: {result.get('errors', [])}")
                
                # Move failed file if configured
                if self.config.get('move_failed_files'):
                    self._move_failed_file(file_info)
        
        finally:
            # Clean up downloaded file
            if cleanup_file and os.path.exists(local_path):
                try:
                    os.unlink(local_path)
                except Exception:
                    pass
    
    def _download_remote_file(self, file_info: Dict) -> str:
        """Download remote file to temporary location"""
        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(file_info['name']).suffix) as temp_file:
            self.sftp_client.get(file_info['path'], temp_file.name)
            return temp_file.name
    
    def _move_processed_file(self, file_info: Dict):
        """Move processed file to processed directory"""
        try:
            processed_dir = self.config.get('processed_directory', 'processed')
            self._move_file(file_info, processed_dir)
        except Exception as e:
            logger.error(f"Error moving processed file: {e}")
    
    def _move_failed_file(self, file_info: Dict):
        """Move failed file to failed directory"""
        try:
            failed_dir = self.config.get('failed_directory', 'failed')
            self._move_file(file_info, failed_dir)
        except Exception as e:
            logger.error(f"Error moving failed file: {e}")
    
    def _move_file(self, file_info: Dict, target_directory: str):
        """Move file to target directory"""
        if file_info['is_local']:
            # Local file move
            source_path = Path(file_info['path'])
            target_dir = source_path.parent / target_directory
            target_dir.mkdir(exist_ok=True)
            target_path = target_dir / source_path.name
            shutil.move(str(source_path), str(target_path))
        else:
            # Remote file move
            source_path = file_info['path']
            target_path = f"{self.config['monitor_directory']}/{target_directory}/{file_info['name']}"
            
            # Create target directory if it doesn't exist
            target_dir = f"{self.config['monitor_directory']}/{target_directory}"
            try:
                self.sftp_client.mkdir(target_dir)
            except Exception:
                pass  # Directory might already exist
            
            # Move file
            self.sftp_client.rename(source_path, target_path)
    
    def _log_monitoring_failure(self, error_message: str):
        """Log monitoring failure for alerting"""
        try:
            clinic = Clinic.objects.get(id=self.config['clinic_id'])
            
            AuditLog.log_action(
                user=None,
                action='SFTP_MONITORING_FAILURE',
                resource_type='SFTP_INGESTION',
                resource_id=self.config.get('monitor_id', 'unknown'),
                details={
                    'monitor_directory': self.config['monitor_directory'],
                    'connection_type': self.config['connection_type'],
                    'error_message': error_message,
                    'last_successful_check': self.last_check.isoformat() if self.last_check else None
                },
                tenant=clinic
            )
        except Exception as e:
            logger.error(f"Failed to log monitoring failure: {e}")


class SFTPFileProcessor:
    """Processes individual files from SFTP"""
    
    def __init__(self, clinic: Clinic):
        self.clinic = clinic
        self.parser = FileNamingConventionParser()
        self.patient_matcher = SFTPPatientMatcher(clinic)
        self.file_validator = FileValidator()
        self.ocr_processor = ClinicalOCRProcessor()
    
    def process_file(self, file_path: str, original_filename: str, 
                    file_size: int, processing_user=None) -> Dict:
        """
        Process a single file from SFTP
        
        Args:
            file_path: Path to the file to process
            original_filename: Original filename
            file_size: Size of the file
            processing_user: User processing the file (optional)
            
        Returns:
            Processing result dictionary
        """
        result = {
            'success': False,
            'filename': original_filename,
            'parsed_metadata': {},
            'patient_match': None,
            'document_created': None,
            'errors': []
        }
        
        try:
            with transaction.atomic():
                return self._process_file_internal(
                    file_path, original_filename, file_size, processing_user, result
                )
        except Exception as e:
            result['errors'].append(f"Processing failed: {e}")
            logger.error(f"File processing failed for {original_filename}: {e}")
            return result
    
    def _process_file_internal(self, file_path: str, original_filename: str, 
                              file_size: int, processing_user, result: Dict) -> Dict:
        """Internal file processing logic"""
        
        # Parse filename
        metadata = self.parser.parse_filename(original_filename)
        result['parsed_metadata'] = metadata
        
        if not metadata['parsed']:
            result['errors'].append("Could not parse filename - no matching naming convention")
            self._log_unparseable_file(original_filename, processing_user)
            return result
        
        # Match patient
        patient = self.patient_matcher.match_patient_from_metadata(metadata)
        
        if not patient:
            result['errors'].append("Could not match patient from filename metadata")
            self._log_unmatched_file(original_filename, metadata, processing_user)
            return result
        
        result['patient_match'] = {
            'id': str(patient.id),
            'name': patient.get_full_name(),
            'phone': patient.phone
        }
        
        # Validate file
        validation_result = self.file_validator.validate_file_path(file_path)
        if not validation_result['is_valid']:
            result['errors'].append(f"File validation failed: {validation_result['errors']}")
            return result
        
        # Detect file type
        detector = FileTypeDetector()
        file_info = detector.detect_file_type(file_path)
        
        # Create clinical record
        record_type = metadata.get('record_type', 'other')
        record_date = metadata.get('parsed_date', timezone.now())
        
        clinical_record = ClinicalRecord.objects.create(
            patient=patient,
            clinic=self.clinic,
            record_type=record_type,
            title=f"SFTP: {original_filename}",
            description=f"Document received via SFTP from {original_filename}",
            record_date=record_date,
            created_by=processing_user,
            metadata={
                'source': 'sftp',
                'original_filename': original_filename,
                'parsed_metadata': metadata,
                'naming_pattern': metadata.get('pattern_used')
            }
        )
        
        # Create document
        with open(file_path, 'rb') as f:
            file_content = ContentFile(f.read(), name=original_filename)
        
        clinical_document = ClinicalDocument.objects.create(
            clinical_record=clinical_record,
            uploaded_by=processing_user,
            file=file_content,
            original_filename=original_filename,
            file_size=file_size,
            content_type=file_info.get('mime_type', 'application/octet-stream'),
            document_type=file_info.get('document_type', 'other'),
            processing_status='pending',
            metadata={
                'source': 'sftp_upload',
                'parsed_metadata': metadata
            }
        )
        
        # Queue for background processing
        try:
            clinical_document.queue_for_processing(priority='normal')
        except Exception as e:
            logger.warning(f"Failed to queue document for processing: {e}")
        
        result['success'] = True
        result['document_created'] = {
            'clinical_record_id': str(clinical_record.id),
            'document_id': str(clinical_document.id),
            'record_type': record_type
        }
        
        # Log successful processing
        AuditLog.log_action(
            user=processing_user,
            action='SFTP_FILE_PROCESSED',
            resource_type='SFTP_INGESTION',
            resource_id=str(clinical_document.id),
            details={
                'filename': original_filename,
                'patient_id': str(patient.id),
                'record_type': record_type,
                'parsed_metadata': metadata
            },
            tenant=self.clinic
        )
        
        return result
    
    def _log_unparseable_file(self, filename: str, processing_user):
        """Log files that couldn't be parsed"""
        AuditLog.log_action(
            user=processing_user,
            action='SFTP_FILE_UNPARSEABLE',
            resource_type='SFTP_INGESTION',
            resource_id=filename,
            details={
                'filename': filename,
                'reason': 'No matching naming convention pattern'
            },
            tenant=self.clinic
        )
    
    def _log_unmatched_file(self, filename: str, metadata: Dict, processing_user):
        """Log files that couldn't be matched to patients"""
        AuditLog.log_action(
            user=processing_user,
            action='SFTP_FILE_UNMATCHED',
            resource_type='SFTP_INGESTION',
            resource_id=filename,
            details={
                'filename': filename,
                'parsed_metadata': metadata,
                'reason': 'Could not match patient from metadata'
            },
            tenant=self.clinic
        )


class SFTPIngestionService:
    """Main service for SFTP ingestion functionality"""
    
    def __init__(self):
        self.monitors = {}  # Active monitors by clinic
    
    def start_monitoring(self, clinic: Clinic, config: Dict) -> str:
        """
        Start SFTP monitoring for a clinic
        
        Args:
            clinic: Clinic to monitor for
            config: SFTP configuration
            
        Returns:
            Monitor ID
        """
        monitor_id = f"{clinic.id}_{config.get('monitor_directory', 'default')}"
        
        if monitor_id in self.monitors:
            raise SFTPIngestionError(f"Monitor already running for {monitor_id}")
        
        # Add clinic ID to config
        config['clinic_id'] = str(clinic.id)
        config['monitor_id'] = monitor_id
        
        # Create and start monitor
        monitor = SFTPMonitor(config)
        monitor.start_monitoring()
        
        self.monitors[monitor_id] = monitor
        
        logger.info(f"Started SFTP monitoring for clinic {clinic.name} (ID: {monitor_id})")
        
        return monitor_id
    
    def stop_monitoring(self, monitor_id: str):
        """Stop SFTP monitoring"""
        if monitor_id not in self.monitors:
            raise SFTPIngestionError(f"No monitor found with ID: {monitor_id}")
        
        monitor = self.monitors[monitor_id]
        monitor.stop_monitoring()
        
        del self.monitors[monitor_id]
        
        logger.info(f"Stopped SFTP monitoring for {monitor_id}")
    
    def get_monitor_status(self, monitor_id: str) -> Dict:
        """Get status of SFTP monitor"""
        if monitor_id not in self.monitors:
            return {'status': 'not_found'}
        
        monitor = self.monitors[monitor_id]
        
        return {
            'status': 'running' if monitor.is_running else 'stopped',
            'last_check': monitor.last_check.isoformat() if monitor.last_check else None,
            'config': {
                'monitor_directory': monitor.config['monitor_directory'],
                'connection_type': monitor.config['connection_type'],
                'check_interval': monitor.config.get('check_interval', 60)
            }
        }
    
    def list_active_monitors(self) -> List[Dict]:
        """List all active monitors"""
        monitors = []
        
        for monitor_id, monitor in self.monitors.items():
            monitors.append({
                'monitor_id': monitor_id,
                'clinic_id': monitor.config['clinic_id'],
                'status': 'running' if monitor.is_running else 'stopped',
                'last_check': monitor.last_check.isoformat() if monitor.last_check else None,
                'monitor_directory': monitor.config['monitor_directory'],
                'connection_type': monitor.config['connection_type']
            })
        
        return monitors
    
    def process_single_file(self, file_path: str, clinic: Clinic, 
                           processing_user=None) -> Dict:
        """
        Process a single file manually
        
        Args:
            file_path: Path to file to process
            clinic: Clinic to process for
            processing_user: User processing the file
            
        Returns:
            Processing result
        """
        if not os.path.exists(file_path):
            raise SFTPIngestionError(f"File not found: {file_path}")
        
        processor = SFTPFileProcessor(clinic)
        
        file_stat = os.stat(file_path)
        filename = os.path.basename(file_path)
        
        return processor.process_file(
            file_path=file_path,
            original_filename=filename,
            file_size=file_stat.st_size,
            processing_user=processing_user
        )
    
    def get_processing_statistics(self, clinic: Clinic, days: int = 30) -> Dict:
        """
        Get SFTP processing statistics for a clinic
        
        Args:
            clinic: Clinic to get statistics for
            days: Number of days to look back
            
        Returns:
            Statistics dictionary
        """
        from django.db.models import Count
        from datetime import timedelta
        
        since_date = timezone.now() - timedelta(days=days)
        
        # Get audit logs for SFTP processing
        sftp_logs = AuditLog.objects.filter(
            tenant=clinic,
            action__in=['SFTP_FILE_PROCESSED', 'SFTP_FILE_UNMATCHED', 'SFTP_FILE_UNPARSEABLE'],
            created_at__gte=since_date
        )
        
        processed_count = sftp_logs.filter(action='SFTP_FILE_PROCESSED').count()
        unmatched_count = sftp_logs.filter(action='SFTP_FILE_UNMATCHED').count()
        unparseable_count = sftp_logs.filter(action='SFTP_FILE_UNPARSEABLE').count()
        
        # Get documents created from SFTP
        sftp_documents = ClinicalDocument.objects.filter(
            clinical_record__clinic=clinic,
            metadata__source='sftp_upload',
            created_at__gte=since_date
        )
        
        total_files = processed_count + unmatched_count + unparseable_count
        
        return {
            'period_days': days,
            'files_processed': processed_count,
            'files_unmatched': unmatched_count,
            'files_unparseable': unparseable_count,
            'total_files': total_files,
            'success_rate': (processed_count / total_files * 100) if total_files > 0 else 0,
            'documents_created': sftp_documents.count(),
            'document_types': dict(
                sftp_documents.values_list('document_type').annotate(
                    count=Count('document_type')
                )
            )
        }


# Singleton instance
sftp_ingestion_service = SFTPIngestionService()