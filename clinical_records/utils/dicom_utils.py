"""
Enhanced DICOM Processing Utilities with pydicom integration
"""
import os
import io
import base64
import logging
from typing import Dict, Any, Optional, Tuple, Union
from PIL import Image
from django.conf import settings
from django.core.files.base import ContentFile

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False
    np = None

try:
    import pydicom
    from pydicom.dataset import Dataset
    from pydicom.pixel_data_handlers.util import apply_voi_lut
    DICOM_AVAILABLE = True
    DatasetType = Dataset
except ImportError:
    DICOM_AVAILABLE = False
    DatasetType = Any

logger = logging.getLogger(__name__)


class DICOMProcessor:
    """
    Utility class for processing DICOM files
    """
    
    def __init__(self):
        if not DICOM_AVAILABLE:
            raise ImportError("pydicom is required for DICOM processing")
    
    def read_dicom_file(self, file_path: str) -> Optional[DatasetType]:
        """
        Read a DICOM file and return the dataset
        """
        try:
            dataset = pydicom.dcmread(file_path)
            return dataset
        except Exception as e:
            logger.error(f"Error reading DICOM file {file_path}: {e}")
            return None
    
    def extract_metadata(self, dataset: DatasetType) -> Dict[str, Any]:
        """
        Extract comprehensive metadata from DICOM dataset
        """
        metadata = {}
        
        try:
            # Basic patient information
            metadata['patient_name'] = str(getattr(dataset, 'PatientName', ''))
            metadata['patient_id'] = str(getattr(dataset, 'PatientID', ''))
            metadata['patient_birth_date'] = str(getattr(dataset, 'PatientBirthDate', ''))
            metadata['patient_sex'] = str(getattr(dataset, 'PatientSex', ''))
            metadata['patient_age'] = str(getattr(dataset, 'PatientAge', ''))
            metadata['patient_weight'] = str(getattr(dataset, 'PatientWeight', ''))
            
            # Study information
            metadata['study_instance_uid'] = str(getattr(dataset, 'StudyInstanceUID', ''))
            metadata['study_date'] = str(getattr(dataset, 'StudyDate', ''))
            metadata['study_time'] = str(getattr(dataset, 'StudyTime', ''))
            metadata['study_description'] = str(getattr(dataset, 'StudyDescription', ''))
            metadata['study_id'] = str(getattr(dataset, 'StudyID', ''))
            metadata['accession_number'] = str(getattr(dataset, 'AccessionNumber', ''))
            
            # Series information
            metadata['series_instance_uid'] = str(getattr(dataset, 'SeriesInstanceUID', ''))
            metadata['series_number'] = str(getattr(dataset, 'SeriesNumber', ''))
            metadata['series_description'] = str(getattr(dataset, 'SeriesDescription', ''))
            metadata['modality'] = str(getattr(dataset, 'Modality', ''))
            metadata['body_part_examined'] = str(getattr(dataset, 'BodyPartExamined', ''))
            
            # Image information
            metadata['sop_instance_uid'] = str(getattr(dataset, 'SOPInstanceUID', ''))
            metadata['sop_class_uid'] = str(getattr(dataset, 'SOPClassUID', ''))
            metadata['instance_number'] = str(getattr(dataset, 'InstanceNumber', ''))
            
            # Equipment information
            metadata['manufacturer'] = str(getattr(dataset, 'Manufacturer', ''))
            metadata['manufacturer_model_name'] = str(getattr(dataset, 'ManufacturerModelName', ''))
            metadata['device_serial_number'] = str(getattr(dataset, 'DeviceSerialNumber', ''))
            metadata['software_versions'] = str(getattr(dataset, 'SoftwareVersions', ''))
            
            # Institution information
            metadata['institution_name'] = str(getattr(dataset, 'InstitutionName', ''))
            metadata['institution_address'] = str(getattr(dataset, 'InstitutionAddress', ''))
            
            # Physician information
            metadata['referring_physician_name'] = str(getattr(dataset, 'ReferringPhysicianName', ''))
            metadata['performing_physician_name'] = str(getattr(dataset, 'PerformingPhysicianName', ''))
            
            # Technical parameters
            if hasattr(dataset, 'pixel_array'):
                pixel_array = dataset.pixel_array
                metadata['image_shape'] = list(pixel_array.shape)
                metadata['image_dtype'] = str(pixel_array.dtype)
                metadata['pixel_min'] = int(pixel_array.min())
                metadata['pixel_max'] = int(pixel_array.max())
                metadata['pixel_mean'] = float(pixel_array.mean())
                metadata['pixel_std'] = float(pixel_array.std())
            
            # Image acquisition parameters
            metadata['rows'] = int(getattr(dataset, 'Rows', 0))
            metadata['columns'] = int(getattr(dataset, 'Columns', 0))
            metadata['pixel_spacing'] = str(getattr(dataset, 'PixelSpacing', ''))
            metadata['slice_thickness'] = str(getattr(dataset, 'SliceThickness', ''))
            metadata['slice_location'] = str(getattr(dataset, 'SliceLocation', ''))
            
            # Window/Level information for display
            metadata['window_center'] = str(getattr(dataset, 'WindowCenter', ''))
            metadata['window_width'] = str(getattr(dataset, 'WindowWidth', ''))
            
            # Modality-specific parameters
            if metadata['modality'] == 'CT':
                metadata['kvp'] = str(getattr(dataset, 'KVP', ''))
                metadata['exposure_time'] = str(getattr(dataset, 'ExposureTime', ''))
                metadata['x_ray_tube_current'] = str(getattr(dataset, 'XRayTubeCurrent', ''))
                metadata['reconstruction_diameter'] = str(getattr(dataset, 'ReconstructionDiameter', ''))
            elif metadata['modality'] == 'MR':
                metadata['magnetic_field_strength'] = str(getattr(dataset, 'MagneticFieldStrength', ''))
                metadata['repetition_time'] = str(getattr(dataset, 'RepetitionTime', ''))
                metadata['echo_time'] = str(getattr(dataset, 'EchoTime', ''))
                metadata['flip_angle'] = str(getattr(dataset, 'FlipAngle', ''))
            elif metadata['modality'] == 'US':
                metadata['transducer_frequency'] = str(getattr(dataset, 'TransducerFrequency', ''))
                metadata['mechanical_index'] = str(getattr(dataset, 'MechanicalIndex', ''))
            
            # File information
            metadata['file_meta_information_version'] = str(getattr(dataset.file_meta, 'FileMetaInformationVersion', ''))
            metadata['transfer_syntax_uid'] = str(getattr(dataset.file_meta, 'TransferSyntaxUID', ''))
            
        except Exception as e:
            logger.error(f"Error extracting DICOM metadata: {e}")
        
        return metadata
    
    def generate_thumbnail(self, dataset: DatasetType, size: Tuple[int, int] = (256, 256)) -> Optional[bytes]:
        """
        Generate a thumbnail image from DICOM dataset and return as JPEG bytes
        """
        try:
            if not hasattr(dataset, 'pixel_array'):
                logger.warning("DICOM dataset has no pixel data")
                return None
            
            # Get pixel array
            pixel_array = dataset.pixel_array
            
            # Apply VOI LUT (Value of Interest Look-Up Table) if available
            try:
                pixel_array = apply_voi_lut(pixel_array, dataset)
            except Exception as e:
                logger.debug(f"Could not apply VOI LUT: {e}")
            
            # Handle different pixel array shapes
            if len(pixel_array.shape) == 3:
                # Multi-frame or RGB image - take the first frame/channel
                if pixel_array.shape[0] < pixel_array.shape[2]:
                    # Likely RGB (height, width, channels)
                    pixel_array = pixel_array
                else:
                    # Likely multi-frame (frames, height, width)
                    pixel_array = pixel_array[0]
            
            # Normalize pixel values to 0-255 range
            if pixel_array.dtype != np.uint8:
                pixel_array = pixel_array.astype(np.float64)
                # Handle different bit depths and signed/unsigned data
                if pixel_array.min() < 0:
                    # Signed data - shift to positive range
                    pixel_array = pixel_array - pixel_array.min()
                
                # Normalize to 0-255
                if pixel_array.max() > 0:
                    pixel_array = (pixel_array / pixel_array.max() * 255).astype(np.uint8)
                else:
                    pixel_array = np.zeros_like(pixel_array, dtype=np.uint8)
            
            # Convert to PIL Image
            if len(pixel_array.shape) == 2:
                # Grayscale image
                image = Image.fromarray(pixel_array, mode='L')
            elif len(pixel_array.shape) == 3 and pixel_array.shape[2] == 3:
                # RGB image
                image = Image.fromarray(pixel_array, mode='RGB')
            else:
                logger.warning(f"Unsupported pixel array shape: {pixel_array.shape}")
                return None
            
            # Resize to thumbnail size
            image.thumbnail(size, Image.Resampling.LANCZOS)
            
            # Convert to JPEG bytes
            img_buffer = io.BytesIO()
            image.save(img_buffer, format='JPEG', quality=85, optimize=True)
            img_buffer.seek(0)
            
            return img_buffer.getvalue()
            
        except Exception as e:
            logger.error(f"Error generating DICOM thumbnail: {e}")
            return None
    
    def generate_preview_image(self, dataset: DatasetType, size: Tuple[int, int] = (1024, 1024)) -> Optional[bytes]:
        """
        Generate a preview image from DICOM dataset and return as JPEG bytes
        """
        try:
            if not hasattr(dataset, 'pixel_array'):
                logger.warning("DICOM dataset has no pixel data")
                return None
            
            # Get pixel array
            pixel_array = dataset.pixel_array
            
            # Apply VOI LUT (Value of Interest Look-Up Table) if available
            try:
                pixel_array = apply_voi_lut(pixel_array, dataset)
            except Exception as e:
                logger.debug(f"Could not apply VOI LUT: {e}")
            
            # Handle different pixel array shapes
            if len(pixel_array.shape) == 3:
                # Multi-frame or RGB image - take the first frame/channel
                if pixel_array.shape[0] < pixel_array.shape[2]:
                    # Likely RGB (height, width, channels)
                    pixel_array = pixel_array
                else:
                    # Likely multi-frame (frames, height, width)
                    pixel_array = pixel_array[0]
            
            # Normalize pixel values to 0-255 range
            if pixel_array.dtype != np.uint8:
                pixel_array = pixel_array.astype(np.float64)
                # Handle different bit depths and signed/unsigned data
                if pixel_array.min() < 0:
                    # Signed data - shift to positive range
                    pixel_array = pixel_array - pixel_array.min()
                
                # Normalize to 0-255
                if pixel_array.max() > 0:
                    pixel_array = (pixel_array / pixel_array.max() * 255).astype(np.uint8)
                else:
                    pixel_array = np.zeros_like(pixel_array, dtype=np.uint8)
            
            # Convert to PIL Image
            if len(pixel_array.shape) == 2:
                # Grayscale image
                image = Image.fromarray(pixel_array, mode='L')
            elif len(pixel_array.shape) == 3 and pixel_array.shape[2] == 3:
                # RGB image
                image = Image.fromarray(pixel_array, mode='RGB')
            else:
                logger.warning(f"Unsupported pixel array shape: {pixel_array.shape}")
                return None
            
            # Resize to preview size while maintaining aspect ratio
            image.thumbnail(size, Image.Resampling.LANCZOS)
            
            # Convert to JPEG bytes
            img_buffer = io.BytesIO()
            image.save(img_buffer, format='JPEG', quality=90, optimize=True)
            img_buffer.seek(0)
            
            return img_buffer.getvalue()
            
        except Exception as e:
            logger.error(f"Error generating DICOM preview image: {e}")
            return None
    
    def get_image_as_base64(self, dataset: DatasetType, size: Tuple[int, int] = (512, 512)) -> Optional[str]:
        """
        Generate a base64-encoded image from DICOM dataset for web display
        """
        try:
            image_bytes = self.generate_preview_image(dataset, size)
            if image_bytes:
                return base64.b64encode(image_bytes).decode('utf-8')
            return None
        except Exception as e:
            logger.error(f"Error generating base64 image: {e}")
            return None
    
    def anonymize_dicom(self, dataset: DatasetType, anonymization_level: str = 'standard') -> DatasetType:
        """
        Remove or replace sensitive information from DICOM dataset
        
        Args:
            dataset: DICOM dataset to anonymize
            anonymization_level: 'basic', 'standard', or 'strict'
        """
        try:
            # Basic anonymization - patient identifiers
            if hasattr(dataset, 'PatientName'):
                dataset.PatientName = 'ANONYMOUS'
            if hasattr(dataset, 'PatientID'):
                dataset.PatientID = 'ANON_ID'
            if hasattr(dataset, 'PatientBirthDate'):
                dataset.PatientBirthDate = ''
            if hasattr(dataset, 'PatientSex'):
                if anonymization_level == 'strict':
                    dataset.PatientSex = ''
            if hasattr(dataset, 'PatientAge'):
                if anonymization_level == 'strict':
                    dataset.PatientAge = ''
            
            if anonymization_level in ['standard', 'strict']:
                # Standard anonymization - remove institution and physician info
                standard_tags_to_remove = [
                    'InstitutionName',
                    'InstitutionAddress',
                    'InstitutionalDepartmentName',
                    'ReferringPhysicianName',
                    'ReferringPhysicianAddress',
                    'ReferringPhysicianTelephoneNumbers',
                    'PerformingPhysicianName',
                    'PerformingPhysicianIdentificationSequence',
                    'OperatorsName',
                    'PatientAddress',
                    'PatientTelephoneNumbers',
                    'PatientMotherBirthName',
                    'CountryOfResidence',
                    'RegionOfResidence',
                    'PatientComments',
                    'StudyComments',
                    'SeriesComments',
                    'ImageComments',
                ]
                
                for tag in standard_tags_to_remove:
                    if hasattr(dataset, tag):
                        delattr(dataset, tag)
            
            if anonymization_level == 'strict':
                # Strict anonymization - remove dates and additional identifiers
                strict_tags_to_remove = [
                    'StudyDate',
                    'SeriesDate',
                    'AcquisitionDate',
                    'ContentDate',
                    'StudyTime',
                    'SeriesTime',
                    'AcquisitionTime',
                    'ContentTime',
                    'AccessionNumber',
                    'StudyID',
                    'DeviceSerialNumber',
                    'SoftwareVersions',
                    'ProtocolName',
                    'StationName',
                    'ManufacturerModelName',
                ]
                
                for tag in strict_tags_to_remove:
                    if hasattr(dataset, tag):
                        delattr(dataset, tag)
                
                # Replace dates with generic values if needed for processing
                if hasattr(dataset, 'StudyDate'):
                    dataset.StudyDate = '19000101'
                if hasattr(dataset, 'StudyTime'):
                    dataset.StudyTime = '000000'
            
            # Generate new UIDs to prevent tracking
            if anonymization_level in ['standard', 'strict']:
                dataset.StudyInstanceUID = pydicom.uid.generate_uid()
                dataset.SeriesInstanceUID = pydicom.uid.generate_uid()
                dataset.SOPInstanceUID = pydicom.uid.generate_uid()
            
            return dataset
            
        except Exception as e:
            logger.error(f"Error anonymizing DICOM: {e}")
            return dataset
    
    def validate_dicom_file(self, file_path: str) -> Dict[str, Any]:
        """
        Validate a DICOM file and return validation results
        """
        validation_result = {
            'is_valid': False,
            'is_dicom': False,
            'has_pixel_data': False,
            'modality': None,
            'errors': [],
            'warnings': [],
            'file_size': 0,
            'metadata_summary': {}
        }
        
        try:
            # Check if file exists and get size
            if not os.path.exists(file_path):
                validation_result['errors'].append("File does not exist")
                return validation_result
            
            validation_result['file_size'] = os.path.getsize(file_path)
            
            # Try to read as DICOM
            dataset = pydicom.dcmread(file_path, force=True)
            validation_result['is_dicom'] = True
            
            # Check for required DICOM elements
            required_elements = ['SOPInstanceUID', 'StudyInstanceUID', 'SeriesInstanceUID']
            for element in required_elements:
                if not hasattr(dataset, element):
                    validation_result['errors'].append(f"Missing required element: {element}")
            
            # Check for pixel data
            if hasattr(dataset, 'pixel_array'):
                validation_result['has_pixel_data'] = True
                try:
                    pixel_array = dataset.pixel_array
                    validation_result['metadata_summary']['image_shape'] = list(pixel_array.shape)
                    validation_result['metadata_summary']['pixel_dtype'] = str(pixel_array.dtype)
                except Exception as e:
                    validation_result['warnings'].append(f"Could not access pixel data: {e}")
                    validation_result['has_pixel_data'] = False
            
            # Get modality
            if hasattr(dataset, 'Modality'):
                validation_result['modality'] = str(dataset.Modality)
                validation_result['metadata_summary']['modality'] = validation_result['modality']
            
            # Get basic metadata
            if hasattr(dataset, 'StudyDescription'):
                validation_result['metadata_summary']['study_description'] = str(dataset.StudyDescription)
            if hasattr(dataset, 'SeriesDescription'):
                validation_result['metadata_summary']['series_description'] = str(dataset.SeriesDescription)
            if hasattr(dataset, 'Rows') and hasattr(dataset, 'Columns'):
                validation_result['metadata_summary']['image_size'] = f"{dataset.Rows}x{dataset.Columns}"
            
            # Check for common issues
            if hasattr(dataset, 'BitsAllocated') and hasattr(dataset, 'BitsStored'):
                if dataset.BitsAllocated < dataset.BitsStored:
                    validation_result['warnings'].append("BitsAllocated < BitsStored")
            
            # Validation passed if no errors
            validation_result['is_valid'] = len(validation_result['errors']) == 0
            
        except Exception as e:
            validation_result['errors'].append(f"DICOM validation error: {str(e)}")
        
        return validation_result
    
    def extract_text_from_dicom(self, dataset: DatasetType) -> Dict[str, Any]:
        """
        Extract any text content from DICOM dataset for OCR-like functionality
        """
        text_data = {
            'extracted_text': '',
            'text_sources': [],
            'confidence': 0.9  # High confidence since this is structured data
        }
        
        try:
            text_elements = []
            
            # Extract text from various DICOM fields
            text_fields = [
                ('StudyDescription', 'Study Description'),
                ('SeriesDescription', 'Series Description'),
                ('ProtocolName', 'Protocol Name'),
                ('ImageComments', 'Image Comments'),
                ('StudyComments', 'Study Comments'),
                ('SeriesComments', 'Series Comments'),
                ('PatientComments', 'Patient Comments'),
                ('RequestedProcedureDescription', 'Requested Procedure'),
                ('PerformedProcedureStepDescription', 'Performed Procedure'),
                ('AdditionalPatientHistory', 'Additional History'),
                ('ClinicalTrialSubjectID', 'Clinical Trial Subject'),
                ('ClinicalTrialProtocolID', 'Clinical Trial Protocol'),
            ]
            
            for field_name, display_name in text_fields:
                if hasattr(dataset, field_name):
                    value = str(getattr(dataset, field_name, '')).strip()
                    if value:
                        text_elements.append(f"{display_name}: {value}")
                        text_data['text_sources'].append(display_name)
            
            # Look for text in overlay data (if present)
            if hasattr(dataset, 'OverlayData'):
                text_data['text_sources'].append('Overlay Data')
                # Note: Actual overlay text extraction would require more complex processing
            
            # Look for burned-in annotations (would require image processing)
            if hasattr(dataset, 'pixel_array') and hasattr(dataset, 'BurnedInAnnotation'):
                if str(getattr(dataset, 'BurnedInAnnotation', '')).upper() == 'YES':
                    text_data['text_sources'].append('Burned-in Annotations')
                    # Note: Actual burned-in text extraction would require OCR on the image
            
            text_data['extracted_text'] = '\n'.join(text_elements)
            
        except Exception as e:
            logger.error(f"Error extracting text from DICOM: {e}")
            text_data['confidence'] = 0.0
        
        return text_data
    
    def get_dicom_summary(self, dataset: DatasetType) -> Dict[str, Any]:
        """
        Get a comprehensive summary of DICOM dataset for display purposes
        """
        summary = {
            'patient_info': {},
            'study_info': {},
            'series_info': {},
            'image_info': {},
            'technical_info': {},
            'processing_info': {}
        }
        
        try:
            # Patient information
            summary['patient_info'] = {
                'name': str(getattr(dataset, 'PatientName', 'Unknown')),
                'id': str(getattr(dataset, 'PatientID', 'Unknown')),
                'birth_date': str(getattr(dataset, 'PatientBirthDate', 'Unknown')),
                'sex': str(getattr(dataset, 'PatientSex', 'Unknown')),
                'age': str(getattr(dataset, 'PatientAge', 'Unknown'))
            }
            
            # Study information
            summary['study_info'] = {
                'description': str(getattr(dataset, 'StudyDescription', 'Unknown')),
                'date': str(getattr(dataset, 'StudyDate', 'Unknown')),
                'time': str(getattr(dataset, 'StudyTime', 'Unknown')),
                'id': str(getattr(dataset, 'StudyID', 'Unknown')),
                'accession_number': str(getattr(dataset, 'AccessionNumber', 'Unknown'))
            }
            
            # Series information
            summary['series_info'] = {
                'description': str(getattr(dataset, 'SeriesDescription', 'Unknown')),
                'number': str(getattr(dataset, 'SeriesNumber', 'Unknown')),
                'modality': str(getattr(dataset, 'Modality', 'Unknown')),
                'body_part': str(getattr(dataset, 'BodyPartExamined', 'Unknown'))
            }
            
            # Image information
            if hasattr(dataset, 'pixel_array'):
                pixel_array = dataset.pixel_array
                summary['image_info'] = {
                    'dimensions': f"{pixel_array.shape}",
                    'data_type': str(pixel_array.dtype),
                    'size_mb': round(pixel_array.nbytes / (1024 * 1024), 2),
                    'pixel_range': f"{pixel_array.min()} - {pixel_array.max()}"
                }
            else:
                summary['image_info'] = {
                    'dimensions': f"{getattr(dataset, 'Rows', 0)}x{getattr(dataset, 'Columns', 0)}",
                    'has_pixel_data': False
                }
            
            # Technical information
            summary['technical_info'] = {
                'manufacturer': str(getattr(dataset, 'Manufacturer', 'Unknown')),
                'model': str(getattr(dataset, 'ManufacturerModelName', 'Unknown')),
                'software_version': str(getattr(dataset, 'SoftwareVersions', 'Unknown')),
                'institution': str(getattr(dataset, 'InstitutionName', 'Unknown'))
            }
            
            # Processing information
            summary['processing_info'] = {
                'can_generate_preview': hasattr(dataset, 'pixel_array'),
                'can_generate_thumbnail': hasattr(dataset, 'pixel_array'),
                'anonymization_possible': True,
                'text_extraction_possible': True
            }
            
        except Exception as e:
            logger.error(f"Error generating DICOM summary: {e}")
            summary['error'] = str(e)
        
        return summary