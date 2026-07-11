"""
File Utilities for Clinical Records

This module provides utilities for file handling, type detection, and validation
for clinical documents.
"""
import os
import hashlib
try:
    import magic
    MAGIC_AVAILABLE = True
except ImportError:
    MAGIC_AVAILABLE = False
    magic = None
import mimetypes
from typing import Dict, Any, Optional, Tuple
from PIL import Image
import logging

logger = logging.getLogger(__name__)


class FileTypeDetector:
    """
    Utility class for detecting file types and validating clinical documents.
    """
    
    # Supported file types for clinical documents
    SUPPORTED_TYPES = {
        'application/pdf': 'pdf',
        'image/jpeg': 'image',
        'image/jpg': 'image',
        'image/png': 'image',
        'image/tiff': 'image',
        'image/bmp': 'image',
        'application/dicom': 'dicom',
        'text/plain': 'text',
        'text/csv': 'text',
        'application/msword': 'office',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'office',
        'application/vnd.ms-excel': 'office',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'office'
    }
    
    def __init__(self):
        self.magic_mime = None
        if MAGIC_AVAILABLE:
            try:
                # Try to initialize python-magic for better file type detection
                self.magic_mime = magic.Magic(mime=True)
            except Exception as e:
                logger.warning(f"Could not initialize python-magic: {e}")
                self.magic_mime = None
        else:
            logger.info("python-magic not available, using fallback file type detection")
    
    def detect_file_type(self, file_path: str) -> Dict[str, Any]:
        """
        Detect the file type and return detailed information.
        
        Args:
            file_path: Path to the file to analyze
            
        Returns:
            Dictionary containing file type information
        """
        try:
            file_info = {
                'file_path': file_path,
                'file_size': os.path.getsize(file_path),
                'mime_type': None,
                'document_type': 'other',
                'is_supported': False,
                'validation_errors': []
            }
            
            # Detect MIME type
            if self.magic_mime:
                try:
                    file_info['mime_type'] = self.magic_mime.from_file(file_path)
                except Exception as e:
                    logger.warning(f"Magic MIME detection failed: {e}")
                    file_info['mime_type'] = mimetypes.guess_type(file_path)[0]
            else:
                file_info['mime_type'] = mimetypes.guess_type(file_path)[0]
            
            # Fallback if MIME type is None
            if not file_info['mime_type']:
                file_info['mime_type'] = 'application/octet-stream'
            
            # Map to document type
            file_info['document_type'] = self.SUPPORTED_TYPES.get(
                file_info['mime_type'], 'other'
            )
            file_info['is_supported'] = file_info['mime_type'] in self.SUPPORTED_TYPES
            
            # Additional validation based on file type
            if file_info['document_type'] == 'image':
                file_info.update(self._validate_image_file(file_path))
            elif file_info['document_type'] == 'pdf':
                file_info.update(self._validate_pdf_file(file_path))
            elif file_info['document_type'] == 'dicom':
                file_info.update(self._validate_dicom_file(file_path))
            
            return file_info
            
        except Exception as e:
            logger.error(f"File type detection failed for {file_path}: {e}")
            return {
                'file_path': file_path,
                'file_size': 0,
                'mime_type': 'application/octet-stream',
                'document_type': 'other',
                'is_supported': False,
                'validation_errors': [f"Detection failed: {str(e)}"]
            }
    
    def _validate_image_file(self, file_path: str) -> Dict[str, Any]:
        """Validate image files and extract metadata."""
        validation_info = {
            'image_width': None,
            'image_height': None,
            'image_format': None,
            'image_mode': None
        }
        
        try:
            with Image.open(file_path) as img:
                validation_info.update({
                    'image_width': img.width,
                    'image_height': img.height,
                    'image_format': img.format,
                    'image_mode': img.mode
                })
                
                # Validate image dimensions
                if img.width < 100 or img.height < 100:
                    validation_info.setdefault('validation_errors', []).append(
                        "Image dimensions too small for reliable OCR"
                    )
                
                # Check if image is too large
                if img.width > 5000 or img.height > 5000:
                    validation_info.setdefault('validation_errors', []).append(
                        "Image dimensions very large, may affect processing performance"
                    )
                
        except Exception as e:
            validation_info.setdefault('validation_errors', []).append(
                f"Image validation failed: {str(e)}"
            )
        
        return validation_info
    
    def _validate_pdf_file(self, file_path: str) -> Dict[str, Any]:
        """Validate PDF files."""
        validation_info = {
            'pdf_pages': None,
            'pdf_encrypted': False
        }
        
        try:
            # TODO: Implement PDF validation using PyPDF2 or similar
            # For now, just check if file can be opened
            with open(file_path, 'rb') as f:
                header = f.read(8)
                if not header.startswith(b'%PDF-'):
                    validation_info.setdefault('validation_errors', []).append(
                        "File does not appear to be a valid PDF"
                    )
                    
        except Exception as e:
            validation_info.setdefault('validation_errors', []).append(
                f"PDF validation failed: {str(e)}"
            )
        
        return validation_info
    
    def _validate_dicom_file(self, file_path: str) -> Dict[str, Any]:
        """Validate DICOM files."""
        validation_info = {
            'dicom_valid': False,
            'dicom_modality': None
        }
        
        try:
            # TODO: Implement DICOM validation using pydicom
            # For now, just check file header
            with open(file_path, 'rb') as f:
                f.seek(128)  # DICOM preamble is 128 bytes
                dicom_prefix = f.read(4)
                if dicom_prefix == b'DICM':
                    validation_info['dicom_valid'] = True
                else:
                    validation_info.setdefault('validation_errors', []).append(
                        "File does not appear to be a valid DICOM file"
                    )
                    
        except Exception as e:
            validation_info.setdefault('validation_errors', []).append(
                f"DICOM validation failed: {str(e)}"
            )
        
        return validation_info


class FileHasher:
    """
    Utility class for calculating file hashes for integrity checking and deduplication.
    """
    
    @staticmethod
    def calculate_file_hash(file_path: str, algorithm: str = 'sha256') -> str:
        """
        Calculate hash of a file.
        
        Args:
            file_path: Path to the file
            algorithm: Hash algorithm to use ('md5', 'sha1', 'sha256')
            
        Returns:
            Hexadecimal hash string
        """
        try:
            hash_obj = hashlib.new(algorithm)
            
            with open(file_path, 'rb') as f:
                # Read file in chunks to handle large files
                for chunk in iter(lambda: f.read(8192), b''):
                    hash_obj.update(chunk)
            
            return hash_obj.hexdigest()
            
        except Exception as e:
            logger.error(f"Hash calculation failed for {file_path}: {e}")
            raise
    
    @staticmethod
    def verify_file_integrity(file_path: str, expected_hash: str, algorithm: str = 'sha256') -> bool:
        """
        Verify file integrity by comparing hash.
        
        Args:
            file_path: Path to the file
            expected_hash: Expected hash value
            algorithm: Hash algorithm used
            
        Returns:
            True if file integrity is verified, False otherwise
        """
        try:
            actual_hash = FileHasher.calculate_file_hash(file_path, algorithm)
            return actual_hash.lower() == expected_hash.lower()
        except Exception as e:
            logger.error(f"File integrity verification failed: {e}")
            return False


class FileValidator:
    """
    Utility class for validating clinical document files.
    """
    
    # Maximum file sizes (in bytes)
    MAX_FILE_SIZES = {
        'image': 50 * 1024 * 1024,  # 50MB for images
        'pdf': 100 * 1024 * 1024,   # 100MB for PDFs
        'dicom': 500 * 1024 * 1024, # 500MB for DICOM files
        'text': 10 * 1024 * 1024,   # 10MB for text files
        'office': 50 * 1024 * 1024, # 50MB for office documents
        'other': 25 * 1024 * 1024   # 25MB for other types
    }
    
    def __init__(self):
        self.file_detector = FileTypeDetector()
    
    def validate_clinical_document(self, file_path: str, max_size_override: Optional[int] = None) -> Dict[str, Any]:
        """
        Comprehensive validation of a clinical document file.
        
        Args:
            file_path: Path to the file to validate
            max_size_override: Override default maximum file size
            
        Returns:
            Dictionary containing validation results
        """
        validation_result = {
            'is_valid': True,
            'errors': [],
            'warnings': [],
            'file_info': {}
        }
        
        try:
            # Check if file exists
            if not os.path.exists(file_path):
                validation_result['is_valid'] = False
                validation_result['errors'].append("File does not exist")
                return validation_result
            
            # Get file type information
            file_info = self.file_detector.detect_file_type(file_path)
            validation_result['file_info'] = file_info
            
            # Check if file type is supported
            if not file_info['is_supported']:
                validation_result['is_valid'] = False
                validation_result['errors'].append(
                    f"Unsupported file type: {file_info['mime_type']}"
                )
            
            # Check file size
            max_size = max_size_override or self.MAX_FILE_SIZES.get(
                file_info['document_type'], 
                self.MAX_FILE_SIZES['other']
            )
            
            if file_info['file_size'] > max_size:
                validation_result['is_valid'] = False
                validation_result['errors'].append(
                    f"File size ({file_info['file_size']} bytes) exceeds maximum allowed size ({max_size} bytes)"
                )
            
            # Check for empty files
            if file_info['file_size'] == 0:
                validation_result['is_valid'] = False
                validation_result['errors'].append("File is empty")
            
            # Add any validation errors from file type detection
            if 'validation_errors' in file_info:
                validation_result['errors'].extend(file_info['validation_errors'])
                if file_info['validation_errors']:
                    validation_result['is_valid'] = False
            
            # Add warnings for potential issues
            if file_info['file_size'] > max_size * 0.8:  # 80% of max size
                validation_result['warnings'].append(
                    "File size is large and may take longer to process"
                )
            
            return validation_result
            
        except Exception as e:
            logger.error(f"File validation failed for {file_path}: {e}")
            validation_result['is_valid'] = False
            validation_result['errors'].append(f"Validation failed: {str(e)}")
            return validation_result
    
    def get_supported_file_types(self) -> Dict[str, str]:
        """
        Get list of supported file types.
        
        Returns:
            Dictionary mapping MIME types to document types
        """
        return self.file_detector.SUPPORTED_TYPES.copy()
    
    def is_file_type_supported(self, mime_type: str) -> bool:
        """
        Check if a MIME type is supported.
        
        Args:
            mime_type: MIME type to check
            
        Returns:
            True if supported, False otherwise
        """
        return mime_type in self.file_detector.SUPPORTED_TYPES
    
    def validate_uploaded_file(self, uploaded_file) -> Dict[str, Any]:
        """
        Validate a Django UploadedFile object.
        
        Args:
            uploaded_file: Django UploadedFile instance
            
        Returns:
            Dictionary containing validation results
        """
        validation_result = {
            'is_valid': True,
            'errors': [],
            'warnings': [],
            'content_type': None,
            'document_type': 'other',
            'file_hash': None
        }
        
        try:
            # Check file size
            if uploaded_file.size == 0:
                validation_result['is_valid'] = False
                validation_result['errors'].append("File is empty")
                return validation_result
            
            # Detect content type
            content_type = uploaded_file.content_type
            if not content_type:
                # Try to guess from filename
                content_type = mimetypes.guess_type(uploaded_file.name)[0]
                if not content_type:
                    content_type = 'application/octet-stream'
            
            validation_result['content_type'] = content_type
            
            # Map to document type
            document_type = self.file_detector.SUPPORTED_TYPES.get(content_type, 'other')
            validation_result['document_type'] = document_type
            
            # Check if file type is supported
            if not self.is_file_type_supported(content_type):
                validation_result['is_valid'] = False
                validation_result['errors'].append(
                    f"Unsupported file type: {content_type}"
                )
                return validation_result
            
            # Check file size limits
            max_size = self.MAX_FILE_SIZES.get(document_type, self.MAX_FILE_SIZES['other'])
            if uploaded_file.size > max_size:
                validation_result['is_valid'] = False
                validation_result['errors'].append(
                    f"File size ({uploaded_file.size} bytes) exceeds maximum allowed size ({max_size} bytes)"
                )
            
            # Calculate file hash
            try:
                hash_obj = hashlib.sha256()
                for chunk in uploaded_file.chunks():
                    hash_obj.update(chunk)
                validation_result['file_hash'] = hash_obj.hexdigest()
                
                # Reset file pointer
                uploaded_file.seek(0)
            except Exception as e:
                logger.warning(f"Failed to calculate file hash: {e}")
                validation_result['file_hash'] = None
            
            # Add warnings for large files
            if uploaded_file.size > max_size * 0.8:  # 80% of max size
                validation_result['warnings'].append(
                    "File size is large and may take longer to process"
                )
            
            # Validate filename
            if not uploaded_file.name or len(uploaded_file.name.strip()) == 0:
                validation_result['warnings'].append("File has no name")
            elif len(uploaded_file.name) > 255:
                validation_result['warnings'].append("Filename is very long")
            
            # Check for potentially dangerous file extensions
            dangerous_extensions = ['.exe', '.bat', '.cmd', '.scr', '.pif', '.com']
            if any(uploaded_file.name.lower().endswith(ext) for ext in dangerous_extensions):
                validation_result['is_valid'] = False
                validation_result['errors'].append("File type not allowed for security reasons")
            
            return validation_result
            
        except Exception as e:
            logger.error(f"Uploaded file validation failed: {e}")
            validation_result['is_valid'] = False
            validation_result['errors'].append(f"Validation failed: {str(e)}")
            return validation_result


class S3StorageService:
    """
    Service class for handling S3 storage operations for clinical documents.
    This is a placeholder implementation that can be extended with actual S3 functionality.
    """
    
    def __init__(self, bucket_name: str = None, region: str = None):
        self.bucket_name = bucket_name or 'clinical-documents'
        self.region = region or 'us-east-1'
        self.logger = logging.getLogger(__name__)
    
    def upload_file(self, file_path: str, s3_key: str) -> Dict[str, Any]:
        """
        Upload a file to S3.
        
        Args:
            file_path: Local path to the file
            s3_key: S3 key (path) for the file
            
        Returns:
            Dictionary with upload result information
        """
        try:
            # Placeholder implementation
            self.logger.info(f"Would upload {file_path} to s3://{self.bucket_name}/{s3_key}")
            return {
                'success': True,
                's3_key': s3_key,
                'bucket': self.bucket_name,
                'url': f"s3://{self.bucket_name}/{s3_key}"
            }
        except Exception as e:
            self.logger.error(f"Failed to upload file to S3: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def download_file(self, s3_key: str, local_path: str) -> Dict[str, Any]:
        """
        Download a file from S3.
        
        Args:
            s3_key: S3 key (path) of the file
            local_path: Local path to save the file
            
        Returns:
            Dictionary with download result information
        """
        try:
            # Placeholder implementation
            self.logger.info(f"Would download s3://{self.bucket_name}/{s3_key} to {local_path}")
            return {
                'success': True,
                'local_path': local_path,
                's3_key': s3_key
            }
        except Exception as e:
            self.logger.error(f"Failed to download file from S3: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def delete_file(self, s3_key: str) -> Dict[str, Any]:
        """
        Delete a file from S3.
        
        Args:
            s3_key: S3 key (path) of the file to delete
            
        Returns:
            Dictionary with delete result information
        """
        try:
            # Placeholder implementation
            self.logger.info(f"Would delete s3://{self.bucket_name}/{s3_key}")
            return {
                'success': True,
                's3_key': s3_key
            }
        except Exception as e:
            self.logger.error(f"Failed to delete file from S3: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_file_url(self, s3_key: str, expires_in: int = 3600) -> str:
        """
        Get a presigned URL for a file in S3.
        
        Args:
            s3_key: S3 key (path) of the file
            expires_in: URL expiration time in seconds
            
        Returns:
            Presigned URL string
        """
        # Placeholder implementation
        return f"https://{self.bucket_name}.s3.{self.region}.amazonaws.com/{s3_key}"


# Convenience functions for easy import
def detect_file_type(file_path: str) -> Dict[str, Any]:
    """
    Convenience function to detect file type.
    
    Args:
        file_path: Path to the file to analyze
        
    Returns:
        Dictionary containing file type information
    """
    detector = FileTypeDetector()
    return detector.detect_file_type(file_path)


def validate_clinical_document_file(file_path: str) -> Dict[str, Any]:
    """
    Convenience function to validate a clinical document file.
    
    Args:
        file_path: Path to the file to validate
        
    Returns:
        Dictionary containing validation results
    """
    validator = FileValidator()
    return validator.validate_clinical_document(file_path)


def calculate_file_hash(file_path: str) -> str:
    """
    Convenience function to calculate SHA-256 hash of a file.
    
    Args:
        file_path: Path to the file
        
    Returns:
        SHA-256 hash string
    """
    return FileHasher.calculate_file_hash(file_path, 'sha256')