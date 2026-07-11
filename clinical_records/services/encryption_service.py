"""
Encryption service for clinical records file storage.

This service provides file-level encryption for sensitive clinical documents
using the cryptography library with AES-256-GCM encryption.
"""

import os
import base64
import hashlib
import logging
from typing import Optional, Tuple, Dict, Any
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)


class EncryptionService:
    """Service for encrypting and decrypting clinical document files."""
    
    # Encryption constants
    KEY_SIZE = 32  # 256 bits for AES-256
    NONCE_SIZE = 12  # 96 bits for GCM
    SALT_SIZE = 16  # 128 bits for key derivation
    TAG_SIZE = 16  # 128 bits for authentication tag
    
    def __init__(self):
        self.master_key = self._get_master_key()
        
    def _get_master_key(self) -> bytes:
        """Get or generate the master encryption key."""
        master_key_env = getattr(settings, 'CLINICAL_RECORDS_MASTER_KEY', None)
        
        if master_key_env:
            try:
                return base64.b64decode(master_key_env)
            except Exception as e:
                logger.error(f"Invalid master key format: {e}")
                raise ValueError("Invalid master key format in settings")
        
        # For development, generate a key (NOT for production)
        if settings.DEBUG:
            logger.warning("Using development master key - NOT for production!")
            return b'development_key_not_for_production_use_32_bytes'
        
        raise ValueError("CLINICAL_RECORDS_MASTER_KEY must be set in production")
    
    def derive_tenant_key(self, tenant_id: int, salt: bytes = None) -> Tuple[bytes, bytes]:
        """
        Derive a tenant-specific encryption key from the master key.
        
        Args:
            tenant_id: Clinic/tenant ID
            salt: Optional salt for key derivation (generated if not provided)
            
        Returns:
            Tuple of (derived_key, salt)
        """
        if salt is None:
            salt = os.urandom(self.SALT_SIZE)
        
        # Create tenant-specific info for key derivation
        tenant_info = f"clinical_records_tenant_{tenant_id}".encode('utf-8')
        
        # Use PBKDF2 for key derivation
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=self.KEY_SIZE,
            salt=salt + tenant_info,  # Combine salt with tenant info
            iterations=100000,  # OWASP recommended minimum
        )
        
        derived_key = kdf.derive(self.master_key)
        return derived_key, salt
    
    def encrypt_file(self, file_path: str, tenant_id: int) -> Dict[str, Any]:
        """
        Encrypt a file and return encryption metadata.
        
        Args:
            file_path: Path to the file to encrypt
            tenant_id: Clinic/tenant ID for key derivation
            
        Returns:
            Dictionary containing encryption metadata
        """
        try:
            # Read the original file
            with open(file_path, 'rb') as f:
                plaintext = f.read()
            
            # Derive tenant-specific key
            key, salt = self.derive_tenant_key(tenant_id)
            
            # Generate nonce for this encryption
            nonce = os.urandom(self.NONCE_SIZE)
            
            # Encrypt the data
            aesgcm = AESGCM(key)
            ciphertext = aesgcm.encrypt(nonce, plaintext, None)
            
            # Create encrypted file path
            encrypted_path = f"{file_path}.encrypted"
            
            # Write encrypted data to file
            with open(encrypted_path, 'wb') as f:
                f.write(salt + nonce + ciphertext)
            
            # Calculate file hash for integrity
            file_hash = hashlib.sha256(plaintext).hexdigest()
            
            # Remove original file
            os.remove(file_path)
            
            # Rename encrypted file to original name
            os.rename(encrypted_path, file_path)
            
            return {
                'encrypted': True,
                'encryption_algorithm': 'AES-256-GCM',
                'key_derivation': 'PBKDF2-SHA256',
                'file_hash': file_hash,
                'encrypted_at': timezone.now().isoformat(),
                'tenant_id': tenant_id
            }
            
        except Exception as e:
            logger.error(f"Error encrypting file {file_path}: {str(e)}")
            raise
    
    def decrypt_file(self, file_path: str, tenant_id: int) -> bytes:
        """
        Decrypt a file and return the plaintext data.
        
        Args:
            file_path: Path to the encrypted file
            tenant_id: Clinic/tenant ID for key derivation
            
        Returns:
            Decrypted file data as bytes
        """
        try:
            # Read the encrypted file
            with open(file_path, 'rb') as f:
                encrypted_data = f.read()
            
            # Extract components
            salt = encrypted_data[:self.SALT_SIZE]
            nonce = encrypted_data[self.SALT_SIZE:self.SALT_SIZE + self.NONCE_SIZE]
            ciphertext = encrypted_data[self.SALT_SIZE + self.NONCE_SIZE:]
            
            # Derive the same key used for encryption
            key, _ = self.derive_tenant_key(tenant_id, salt)
            
            # Decrypt the data
            aesgcm = AESGCM(key)
            plaintext = aesgcm.decrypt(nonce, ciphertext, None)
            
            return plaintext
            
        except Exception as e:
            logger.error(f"Error decrypting file {file_path}: {str(e)}")
            raise
    
    def decrypt_file_to_temp(self, file_path: str, tenant_id: int) -> str:
        """
        Decrypt a file to a temporary location for serving.
        
        Args:
            file_path: Path to the encrypted file
            tenant_id: Clinic/tenant ID for key derivation
            
        Returns:
            Path to the temporary decrypted file
        """
        import tempfile
        
        # Decrypt the file data
        plaintext = self.decrypt_file(file_path, tenant_id)
        
        # Create temporary file
        temp_fd, temp_path = tempfile.mkstemp()
        
        try:
            with os.fdopen(temp_fd, 'wb') as temp_file:
                temp_file.write(plaintext)
            
            return temp_path
            
        except Exception as e:
            # Clean up on error
            try:
                os.close(temp_fd)
                os.unlink(temp_path)
            except:
                pass
            raise e
    
    def verify_file_integrity(self, file_path: str, tenant_id: int, 
                            expected_hash: str) -> bool:
        """
        Verify the integrity of an encrypted file.
        
        Args:
            file_path: Path to the encrypted file
            tenant_id: Clinic/tenant ID for key derivation
            expected_hash: Expected SHA-256 hash of the original file
            
        Returns:
            True if file integrity is verified
        """
        try:
            # Decrypt and hash the file
            plaintext = self.decrypt_file(file_path, tenant_id)
            actual_hash = hashlib.sha256(plaintext).hexdigest()
            
            return actual_hash == expected_hash
            
        except Exception as e:
            logger.error(f"Error verifying file integrity {file_path}: {str(e)}")
            return False
    
    def is_file_encrypted(self, file_path: str) -> bool:
        """
        Check if a file is encrypted by examining its structure.
        
        Args:
            file_path: Path to the file to check
            
        Returns:
            True if file appears to be encrypted
        """
        try:
            if not os.path.exists(file_path):
                return False
            
            # Check file size (must be at least salt + nonce + tag size)
            min_size = self.SALT_SIZE + self.NONCE_SIZE + self.TAG_SIZE
            if os.path.getsize(file_path) < min_size:
                return False
            
            # Read the beginning of the file
            with open(file_path, 'rb') as f:
                header = f.read(self.SALT_SIZE + self.NONCE_SIZE)
            
            # Encrypted files should have random-looking headers
            # This is a heuristic check - not foolproof
            return len(header) == (self.SALT_SIZE + self.NONCE_SIZE)
            
        except Exception:
            return False
    
    def get_encryption_stats(self, tenant_id: int) -> Dict[str, Any]:
        """
        Get encryption statistics for a tenant.
        
        Args:
            tenant_id: Clinic/tenant ID
            
        Returns:
            Dictionary with encryption statistics
        """
        from ..models import ClinicalDocument
        
        try:
            # Get document counts
            total_docs = ClinicalDocument.objects.filter(
                clinical_record__clinic_id=tenant_id
            ).count()
            
            encrypted_docs = ClinicalDocument.objects.filter(
                clinical_record__clinic_id=tenant_id,
                is_encrypted=True
            ).count()
            
            return {
                'tenant_id': tenant_id,
                'total_documents': total_docs,
                'encrypted_documents': encrypted_docs,
                'unencrypted_documents': total_docs - encrypted_docs,
                'encryption_percentage': round((encrypted_docs / total_docs) * 100, 2) if total_docs > 0 else 0,
                'encryption_algorithm': 'AES-256-GCM',
                'key_derivation': 'PBKDF2-SHA256'
            }
            
        except Exception as e:
            logger.error(f"Error getting encryption stats for tenant {tenant_id}: {str(e)}")
            return {
                'tenant_id': tenant_id,
                'error': str(e)
            }


class EncryptedFileStorage:
    """
    File storage backend that provides transparent encryption/decryption.
    """
    
    def __init__(self):
        self.encryption_service = EncryptionService()
    
    def save_encrypted(self, file_path: str, content: bytes, tenant_id: int) -> Dict[str, Any]:
        """
        Save file content with encryption.
        
        Args:
            file_path: Path where to save the file
            content: File content as bytes
            tenant_id: Clinic/tenant ID
            
        Returns:
            Encryption metadata
        """
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            # Write content to temporary file
            temp_path = f"{file_path}.tmp"
            with open(temp_path, 'wb') as f:
                f.write(content)
            
            # Encrypt the file
            metadata = self.encryption_service.encrypt_file(temp_path, tenant_id)
            
            # Move to final location
            os.rename(temp_path, file_path)
            
            return metadata
            
        except Exception as e:
            # Clean up on error
            for path in [temp_path, file_path]:
                try:
                    if os.path.exists(path):
                        os.remove(path)
                except:
                    pass
            raise e
    
    def read_encrypted(self, file_path: str, tenant_id: int) -> bytes:
        """
        Read and decrypt file content.
        
        Args:
            file_path: Path to the encrypted file
            tenant_id: Clinic/tenant ID
            
        Returns:
            Decrypted file content as bytes
        """
        return self.encryption_service.decrypt_file(file_path, tenant_id)
    
    def get_temp_decrypted_path(self, file_path: str, tenant_id: int) -> str:
        """
        Get a temporary path to the decrypted file for serving.
        
        Args:
            file_path: Path to the encrypted file
            tenant_id: Clinic/tenant ID
            
        Returns:
            Path to temporary decrypted file
        """
        return self.encryption_service.decrypt_file_to_temp(file_path, tenant_id)


# Utility functions for key management
def generate_master_key() -> str:
    """
    Generate a new master key for encryption.
    
    Returns:
        Base64-encoded master key
    """
    key = os.urandom(32)  # 256 bits
    return base64.b64encode(key).decode('utf-8')


def rotate_tenant_keys(tenant_id: int) -> Dict[str, Any]:
    """
    Rotate encryption keys for a tenant (re-encrypt all files).
    
    Args:
        tenant_id: Clinic/tenant ID
        
    Returns:
        Dictionary with rotation results
    """
    from ..models import ClinicalDocument
    
    encryption_service = EncryptionService()
    results = {
        'tenant_id': tenant_id,
        'processed': 0,
        'errors': 0,
        'error_details': []
    }
    
    try:
        # Get all encrypted documents for the tenant
        documents = ClinicalDocument.objects.filter(
            clinical_record__clinic_id=tenant_id,
            is_encrypted=True
        )
        
        for document in documents:
            try:
                if document.file and os.path.exists(document.file.path):
                    # Decrypt with old key
                    plaintext = encryption_service.decrypt_file(
                        document.file.path, 
                        tenant_id
                    )
                    
                    # Re-encrypt with new key (new salt will be generated)
                    temp_path = f"{document.file.path}.reencrypt"
                    with open(temp_path, 'wb') as f:
                        f.write(plaintext)
                    
                    metadata = encryption_service.encrypt_file(temp_path, tenant_id)
                    
                    # Update document metadata
                    document.metadata.update({
                        'encryption': metadata,
                        'key_rotated_at': timezone.now().isoformat()
                    })
                    document.save(update_fields=['metadata'])
                    
                    results['processed'] += 1
                    
            except Exception as e:
                results['errors'] += 1
                results['error_details'].append({
                    'document_id': str(document.id),
                    'error': str(e)
                })
                logger.error(f"Error rotating key for document {document.id}: {str(e)}")
        
        return results
        
    except Exception as e:
        logger.error(f"Error rotating keys for tenant {tenant_id}: {str(e)}")
        results['error_details'].append({
            'general_error': str(e)
        })
        return results