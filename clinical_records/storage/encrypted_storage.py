"""
Encrypted file storage backend for Django.

This module provides a custom Django storage backend that automatically
encrypts files when they are saved and decrypts them when accessed.
"""

import os
import tempfile
import logging
from typing import Optional, IO, Any
from urllib.parse import urljoin

from django.core.files.storage import FileSystemStorage
from django.core.files.base import ContentFile
from django.conf import settings
from django.utils.deconstruct import deconstructible
from django.http import HttpResponse, FileResponse

from ..services.encryption_service import EncryptionService, EncryptedFileStorage

logger = logging.getLogger(__name__)


@deconstructible
class EncryptedFileSystemStorage(FileSystemStorage):
    """
    Django storage backend that provides transparent file encryption.
    
    Files are encrypted when saved and decrypted when accessed.
    The encryption is transparent to the application layer.
    """
    
    def __init__(self, location=None, base_url=None, file_permissions_mode=None,
                 directory_permissions_mode=None):
        super().__init__(location, base_url, file_permissions_mode, directory_permissions_mode)
        self.encryption_service = EncryptionService()
        self.encrypted_storage = EncryptedFileStorage()
    
    def _save(self, name: str, content: ContentFile) -> str:
        """
        Save a file with encryption.
        
        Args:
            name: File name
            content: File content
            
        Returns:
            The saved file name
        """
        # Get tenant ID from the file path or current context
        tenant_id = self._extract_tenant_id(name)
        
        if tenant_id is None:
            # Fall back to regular storage if no tenant context
            logger.warning(f"No tenant context for file {name}, saving without encryption")
            return super()._save(name, content)
        
        try:
            # Get the full file path
            full_path = self.path(name)
            
            # Ensure directory exists
            directory = os.path.dirname(full_path)
            if not os.path.exists(directory):
                os.makedirs(directory, mode=self.directory_permissions_mode)
            
            # Read content
            content.seek(0)
            file_content = content.read()
            
            # Save with encryption
            metadata = self.encrypted_storage.save_encrypted(
                full_path, 
                file_content, 
                tenant_id
            )
            
            # Set file permissions
            if self.file_permissions_mode is not None:
                os.chmod(full_path, self.file_permissions_mode)
            
            logger.info(f"Encrypted file saved: {name} for tenant {tenant_id}")
            return name
            
        except Exception as e:
            logger.error(f"Error saving encrypted file {name}: {str(e)}")
            # Fall back to regular storage on encryption error
            return super()._save(name, content)
    
    def _open(self, name: str, mode: str = 'rb') -> ContentFile:
        """
        Open and decrypt a file.
        
        Args:
            name: File name
            mode: File open mode
            
        Returns:
            ContentFile with decrypted content
        """
        tenant_id = self._extract_tenant_id(name)
        full_path = self.path(name)
        
        # Check if file is encrypted
        if tenant_id and self.encryption_service.is_file_encrypted(full_path):
            try:
                # Decrypt the file content
                decrypted_content = self.encrypted_storage.read_encrypted(
                    full_path, 
                    tenant_id
                )
                
                return ContentFile(decrypted_content, name=name)
                
            except Exception as e:
                logger.error(f"Error decrypting file {name}: {str(e)}")
                # Fall back to regular file access
                pass
        
        # Regular file access for non-encrypted files
        return super()._open(name, mode)
    
    def exists(self, name: str) -> bool:
        """Check if a file exists."""
        return os.path.exists(self.path(name))
    
    def size(self, name: str) -> int:
        """
        Get the size of a file.
        
        For encrypted files, this returns the size of the encrypted file,
        not the original file size.
        """
        return os.path.getsize(self.path(name))
    
    def url(self, name: str) -> str:
        """
        Get the URL for a file.
        
        For encrypted files, this should go through a decryption view.
        """
        if self.base_url is None:
            raise ValueError("This file is not accessible via a URL.")
        
        # Check if file is encrypted
        tenant_id = self._extract_tenant_id(name)
        if tenant_id and self.encryption_service.is_file_encrypted(self.path(name)):
            # Return URL that goes through decryption view
            from django.urls import reverse
            try:
                return reverse('clinical_records:encrypted_file_serve', kwargs={
                    'file_path': name,
                    'tenant_id': tenant_id
                })
            except:
                # Fall back to regular URL if reverse fails
                pass
        
        return urljoin(self.base_url, name)
    
    def delete(self, name: str) -> None:
        """Delete a file."""
        try:
            os.remove(self.path(name))
        except FileNotFoundError:
            pass
    
    def get_temp_decrypted_path(self, name: str) -> Optional[str]:
        """
        Get a temporary path to the decrypted file for serving.
        
        Args:
            name: File name
            
        Returns:
            Path to temporary decrypted file, or None if not encrypted
        """
        tenant_id = self._extract_tenant_id(name)
        full_path = self.path(name)
        
        if tenant_id and self.encryption_service.is_file_encrypted(full_path):
            try:
                return self.encrypted_storage.get_temp_decrypted_path(
                    full_path, 
                    tenant_id
                )
            except Exception as e:
                logger.error(f"Error creating temp decrypted file for {name}: {str(e)}")
                return None
        
        return None
    
    def _extract_tenant_id(self, file_path: str) -> Optional[int]:
        """
        Extract tenant ID from file path.
        
        Expected path format: clinical_records/clinic_<id>/...
        
        Args:
            file_path: File path
            
        Returns:
            Tenant ID or None if not found
        """
        try:
            path_parts = file_path.split('/')
            for part in path_parts:
                if part.startswith('clinic_'):
                    return int(part.split('_')[1])
            return None
        except (ValueError, IndexError):
            return None
    
    def is_encrypted(self, name: str) -> bool:
        """
        Check if a file is encrypted.
        
        Args:
            name: File name
            
        Returns:
            True if file is encrypted
        """
        return self.encryption_service.is_file_encrypted(self.path(name))
    
    def get_encryption_metadata(self, name: str) -> Optional[dict]:
        """
        Get encryption metadata for a file.
        
        Args:
            name: File name
            
        Returns:
            Encryption metadata or None if not encrypted
        """
        if self.is_encrypted(name):
            tenant_id = self._extract_tenant_id(name)
            if tenant_id:
                return {
                    'encrypted': True,
                    'tenant_id': tenant_id,
                    'algorithm': 'AES-256-GCM',
                    'key_derivation': 'PBKDF2-SHA256'
                }
        return None


class EncryptedFileResponse:
    """
    Helper class for serving encrypted files through HTTP responses.
    """
    
    def __init__(self, storage: EncryptedFileSystemStorage):
        self.storage = storage
    
    def serve_encrypted_file(self, file_path: str, tenant_id: int, 
                           as_attachment: bool = False) -> HttpResponse:
        """
        Serve an encrypted file as HTTP response.
        
        Args:
            file_path: Path to the encrypted file
            tenant_id: Tenant ID for decryption
            as_attachment: Whether to serve as download attachment
            
        Returns:
            HTTP response with decrypted file content
        """
        try:
            full_path = self.storage.path(file_path)
            
            if not self.storage.exists(file_path):
                from django.http import Http404
                raise Http404("File not found")
            
            # Get temporary decrypted file
            temp_path = self.storage.get_temp_decrypted_path(file_path)
            
            if temp_path:
                # Serve decrypted file
                response = FileResponse(
                    open(temp_path, 'rb'),
                    as_attachment=as_attachment,
                    filename=os.path.basename(file_path)
                )
                
                # Clean up temp file after response
                def cleanup_temp_file():
                    try:
                        os.unlink(temp_path)
                    except:
                        pass
                
                # Schedule cleanup (this is a simple approach)
                # In production, you might want a more robust cleanup mechanism
                import atexit
                atexit.register(cleanup_temp_file)
                
                return response
            else:
                # File is not encrypted, serve normally
                return FileResponse(
                    open(full_path, 'rb'),
                    as_attachment=as_attachment,
                    filename=os.path.basename(file_path)
                )
                
        except Exception as e:
            logger.error(f"Error serving encrypted file {file_path}: {str(e)}")
            from django.http import HttpResponseServerError
            return HttpResponseServerError("Error serving file")


# Configuration helper
def get_encrypted_storage():
    """
    Get configured encrypted storage instance.
    
    Returns:
        EncryptedFileSystemStorage instance
    """
    media_root = getattr(settings, 'MEDIA_ROOT', None)
    media_url = getattr(settings, 'MEDIA_URL', None)
    
    if not media_root:
        raise ValueError("MEDIA_ROOT must be configured for encrypted storage")
    
    return EncryptedFileSystemStorage(
        location=media_root,
        base_url=media_url
    )


# Storage instance for use in models
encrypted_storage = get_encrypted_storage()