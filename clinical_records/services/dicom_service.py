"""
DICOM Processing Service for ImagingStudy integration
"""
import logging
from typing import Optional, Dict, Any

from ..models import ImagingStudy, ClinicalDocument
from ..utils import DICOMProcessor

logger = logging.getLogger(__name__)


class DICOMStudyService:
    """
    Service for processing DICOM files and creating ImagingStudy records
    """
    
    def __init__(self):
        self.dicom_processor = DICOMProcessor()
    
    def process_dicom_document(self, clinical_document: ClinicalDocument) -> Optional[ImagingStudy]:
        """
        Process a DICOM document and create/update associated ImagingStudy
        """
        if clinical_document.document_type != 'dicom':
            logger.warning(f"Document {clinical_document.id} is not a DICOM file")
            return None
        
        try:
            # Read DICOM file
            dataset = self.dicom_processor.read_dicom_file(clinical_document.file.path)
            if not dataset:
                logger.error(f"Failed to read DICOM file: {clinical_document.file.path}")
                return None
            
            # Extract metadata
            metadata = self.dicom_processor.extract_metadata(dataset)
            
            # Update document with DICOM metadata
            clinical_document.dicom_metadata = metadata
            clinical_document.save(update_fields=['dicom_metadata'])
            
            # Create or get ImagingStudy
            study = self._create_or_update_imaging_study(
                clinical_document.clinical_record,
                metadata
            )
            
            # Update study statistics
            if study:
                study.update_statistics()
            
            return study
            
        except Exception as e:
            logger.error(f"Error processing DICOM document {clinical_document.id}: {e}")
            return None
    
    def _create_or_update_imaging_study(self, clinical_record, metadata: Dict[str, Any]) -> Optional[ImagingStudy]:
        """
        Create or update ImagingStudy based on DICOM metadata
        """
        study_uid = metadata.get('study_instance_uid')
        if not study_uid:
            logger.error("DICOM metadata missing study_instance_uid")
            return None
        
        try:
            # Try to get existing study
            study = ImagingStudy.objects.filter(study_instance_uid=study_uid).first()
            
            if study:
                # Update existing study with new metadata
                self._update_study_metadata(study, metadata)
                return study
            else:
                # Create new study
                return ImagingStudy.create_from_dicom_metadata(clinical_record, metadata)
                
        except Exception as e:
            logger.error(f"Error creating/updating ImagingStudy: {e}")
            return None
    
    def _update_study_metadata(self, study: ImagingStudy, metadata: Dict[str, Any]):
        """
        Update existing ImagingStudy with new metadata
        """
        try:
            # Update fields that might have changed
            if metadata.get('study_description') and not study.study_description:
                study.study_description = metadata['study_description']
            
            if metadata.get('referring_physician_name') and not study.referring_physician_name:
                study.referring_physician_name = metadata['referring_physician_name']
            
            # Merge DICOM metadata
            study.dicom_metadata.update(metadata)
            
            study.save(update_fields=['study_description', 'referring_physician_name', 'dicom_metadata'])
            
        except Exception as e:
            logger.error(f"Error updating study metadata: {e}")
    
    def generate_study_thumbnail(self, study: ImagingStudy) -> Optional[str]:
        """
        Generate a thumbnail for the imaging study
        """
        try:
            # Get the first DICOM document for this study
            dicom_doc = study.dicom_documents.first()
            if not dicom_doc:
                return None
            
            # Read DICOM file
            dataset = self.dicom_processor.read_dicom_file(dicom_doc.file.path)
            if not dataset:
                return None
            
            # Generate thumbnail
            thumbnail = self.dicom_processor.generate_thumbnail(dataset)
            if thumbnail is not None:
                # TODO: Save thumbnail to file system or return as base64
                # For now, just return success indicator
                return "thumbnail_generated"
            
            return None
            
        except Exception as e:
            logger.error(f"Error generating thumbnail for study {study.id}: {e}")
            return None
    
    def anonymize_study(self, study: ImagingStudy) -> bool:
        """
        Anonymize all DICOM files in a study
        """
        try:
            # Anonymize the study record
            study.anonymize()
            
            # Anonymize all associated DICOM documents
            for doc in study.dicom_documents:
                self._anonymize_dicom_document(doc)
            
            return True
            
        except Exception as e:
            logger.error(f"Error anonymizing study {study.id}: {e}")
            return False
    
    def _anonymize_dicom_document(self, document: ClinicalDocument):
        """
        Anonymize a single DICOM document
        """
        try:
            # Read DICOM file
            dataset = self.dicom_processor.read_dicom_file(document.file.path)
            if not dataset:
                return
            
            # Anonymize dataset
            anonymized_dataset = self.dicom_processor.anonymize_dicom(dataset)
            
            # Save anonymized file back
            anonymized_dataset.save_as(document.file.path)
            
            # Update document metadata to reflect anonymization
            document.metadata['anonymized'] = True
            document.save(update_fields=['metadata'])
            
        except Exception as e:
            logger.error(f"Error anonymizing DICOM document {document.id}: {e}")
    
    def validate_dicom_study(self, study: ImagingStudy) -> Dict[str, Any]:
        """
        Validate the completeness and integrity of a DICOM study
        """
        validation_result = {
            'is_valid': True,
            'errors': [],
            'warnings': [],
            'statistics': {}
        }
        
        try:
            # Check if study has any documents
            dicom_docs = study.dicom_documents
            if not dicom_docs.exists():
                validation_result['errors'].append("Study has no DICOM documents")
                validation_result['is_valid'] = False
                return validation_result
            
            # Validate each document
            series_count = set()
            instance_count = 0
            
            for doc in dicom_docs:
                # Check if document is processed
                if doc.processing_status != 'completed':
                    validation_result['warnings'].append(
                        f"Document {doc.original_filename} is not fully processed"
                    )
                
                # Check DICOM metadata
                if not doc.dicom_metadata:
                    validation_result['errors'].append(
                        f"Document {doc.original_filename} missing DICOM metadata"
                    )
                    validation_result['is_valid'] = False
                    continue
                
                # Count series and instances
                series_uid = doc.dicom_metadata.get('series_instance_uid')
                if series_uid:
                    series_count.add(series_uid)
                instance_count += 1
            
            # Update statistics
            validation_result['statistics'] = {
                'total_documents': dicom_docs.count(),
                'unique_series': len(series_count),
                'total_instances': instance_count
            }
            
            # Check if statistics match study record
            if study.number_of_series != len(series_count):
                validation_result['warnings'].append(
                    f"Study series count mismatch: recorded={study.number_of_series}, actual={len(series_count)}"
                )
            
            if study.number_of_instances != instance_count:
                validation_result['warnings'].append(
                    f"Study instance count mismatch: recorded={study.number_of_instances}, actual={instance_count}"
                )
            
        except Exception as e:
            validation_result['errors'].append(f"Validation error: {str(e)}")
            validation_result['is_valid'] = False
        
        return validation_result