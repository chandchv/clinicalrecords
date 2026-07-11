"""
Views for handling encrypted file operations.

This module provides views for serving encrypted files, managing encryption
settings, and monitoring encryption status.
"""

import logging
from typing import Dict, Any

from django.http import HttpResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.utils.decorators import method_decorator
from django.views import View
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from ..models import ClinicalDocument
from ..storage.encrypted_storage import EncryptedFileResponse, get_encrypted_storage
from ..services.encryption_service import EncryptionService, rotate_tenant_keys
from ..permissions import ClinicalRecordsPermission

logger = logging.getLogger(__name__)


@method_decorator(login_required, name='dispatch')
class EncryptedFileServeView(View):
    """
    View for serving encrypted files with proper access control.
    """
    
    def get(self, request, file_path: str, tenant_id: int):
        """
        Serve an encrypted file after access control checks.
        
        Args:
            request: HTTP request
            file_path: Path to the encrypted file
            tenant_id: Tenant ID for decryption
            
        Returns:
            HTTP response with decrypted file content
        """
        try:
            # Check if user has access to this tenant
            if not hasattr(request.user, 'clinic') or request.user.clinic.id != tenant_id:
                return HttpResponse("Access denied", status=403)
            
            # Get storage and file response handler
            storage = get_encrypted_storage()
            file_response = EncryptedFileResponse(storage)
            
            # Determine if file should be served as attachment
            as_attachment = request.GET.get('download', '').lower() == 'true'
            
            # Serve the encrypted file
            return file_response.serve_encrypted_file(
                file_path, 
                tenant_id, 
                as_attachment=as_attachment
            )
            
        except Exception as e:
            logger.error(f"Error serving encrypted file {file_path}: {str(e)}")
            return HttpResponse("Error serving file", status=500)


class EncryptionManagementViewSet(viewsets.ViewSet):
    """
    ViewSet for managing encryption settings and operations.
    """
    
    permission_classes = [IsAuthenticated, ClinicalRecordsPermission]
    
    @action(detail=False, methods=['get'])
    def status(self, request):
        """
        Get encryption status for the current clinic.
        """
        try:
            if not hasattr(request.user, 'clinic'):
                return Response({
                    'error': 'No clinic context'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            tenant_id = request.user.clinic.id
            encryption_service = EncryptionService()
            
            # Get encryption statistics
            stats = encryption_service.get_encryption_stats(tenant_id)
            
            # Add configuration information
            config = {
                'encryption_enabled': True,
                'algorithm': 'AES-256-GCM',
                'key_derivation': 'PBKDF2-SHA256',
                'master_key_configured': bool(encryption_service.master_key),
                'tenant_id': tenant_id
            }
            
            return Response({
                'config': config,
                'statistics': stats
            })
            
        except Exception as e:
            logger.error(f"Error getting encryption status: {str(e)}")
            return Response({
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['post'])
    def encrypt_existing_files(self, request):
        """
        Encrypt existing unencrypted files for the current clinic.
        """
        try:
            if not hasattr(request.user, 'clinic'):
                return Response({
                    'error': 'No clinic context'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            tenant_id = request.user.clinic.id
            encryption_service = EncryptionService()
            
            # Get unencrypted documents
            unencrypted_docs = ClinicalDocument.objects.filter(
                clinical_record__clinic_id=tenant_id,
                is_encrypted=False
            )
            
            results = {
                'tenant_id': tenant_id,
                'total_files': unencrypted_docs.count(),
                'processed': 0,
                'errors': 0,
                'error_details': []
            }
            
            for document in unencrypted_docs:
                try:
                    if document.file and document.file.path:
                        # Encrypt the file
                        metadata = encryption_service.encrypt_file(
                            document.file.path, 
                            tenant_id
                        )
                        
                        # Update document record
                        document.is_encrypted = True
                        document.metadata.update({
                            'encryption': metadata
                        })
                        document.save(update_fields=['is_encrypted', 'metadata'])
                        
                        results['processed'] += 1
                        
                except Exception as e:
                    results['errors'] += 1
                    results['error_details'].append({
                        'document_id': str(document.id),
                        'filename': document.original_filename,
                        'error': str(e)
                    })
                    logger.error(f"Error encrypting document {document.id}: {str(e)}")
            
            return Response(results)
            
        except Exception as e:
            logger.error(f"Error encrypting existing files: {str(e)}")
            return Response({
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['post'])
    def rotate_keys(self, request):
        """
        Rotate encryption keys for the current clinic.
        """
        try:
            if not hasattr(request.user, 'clinic'):
                return Response({
                    'error': 'No clinic context'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            tenant_id = request.user.clinic.id
            
            # Perform key rotation
            results = rotate_tenant_keys(tenant_id)
            
            return Response(results)
            
        except Exception as e:
            logger.error(f"Error rotating keys: {str(e)}")
            return Response({
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['post'])
    def verify_integrity(self, request):
        """
        Verify the integrity of encrypted files for the current clinic.
        """
        try:
            if not hasattr(request.user, 'clinic'):
                return Response({
                    'error': 'No clinic context'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            tenant_id = request.user.clinic.id
            encryption_service = EncryptionService()
            
            # Get encrypted documents with file hashes
            encrypted_docs = ClinicalDocument.objects.filter(
                clinical_record__clinic_id=tenant_id,
                is_encrypted=True
            ).exclude(file_hash='')
            
            results = {
                'tenant_id': tenant_id,
                'total_files': encrypted_docs.count(),
                'verified': 0,
                'failed': 0,
                'error_details': []
            }
            
            for document in encrypted_docs:
                try:
                    if document.file and document.file.path and document.file_hash:
                        # Verify file integrity
                        is_valid = encryption_service.verify_file_integrity(
                            document.file.path,
                            tenant_id,
                            document.file_hash
                        )
                        
                        if is_valid:
                            results['verified'] += 1
                        else:
                            results['failed'] += 1
                            results['error_details'].append({
                                'document_id': str(document.id),
                                'filename': document.original_filename,
                                'error': 'File integrity check failed'
                            })
                            
                except Exception as e:
                    results['failed'] += 1
                    results['error_details'].append({
                        'document_id': str(document.id),
                        'filename': document.original_filename,
                        'error': str(e)
                    })
                    logger.error(f"Error verifying document {document.id}: {str(e)}")
            
            return Response(results)
            
        except Exception as e:
            logger.error(f"Error verifying file integrity: {str(e)}")
            return Response({
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@require_http_methods(["GET"])
@login_required
def encryption_health_check(request):
    """
    Health check endpoint for encryption system.
    
    Returns:
        JSON response with encryption system health status
    """
    try:
        encryption_service = EncryptionService()
        
        # Basic health checks
        health_status = {
            'encryption_service': 'healthy',
            'master_key_configured': bool(encryption_service.master_key),
            'timestamp': timezone.now().isoformat()
        }
        
        # Test key derivation
        try:
            test_key, test_salt = encryption_service.derive_tenant_key(1)
            health_status['key_derivation'] = 'healthy'
        except Exception as e:
            health_status['key_derivation'] = f'error: {str(e)}'
            health_status['encryption_service'] = 'degraded'
        
        # Test encryption/decryption
        try:
            import tempfile
            test_data = b'test encryption data'
            
            with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                temp_file.write(test_data)
                temp_path = temp_file.name
            
            try:
                # Test encryption
                metadata = encryption_service.encrypt_file(temp_path, 1)
                
                # Test decryption
                decrypted_data = encryption_service.decrypt_file(temp_path, 1)
                
                if decrypted_data == test_data:
                    health_status['encryption_test'] = 'healthy'
                else:
                    health_status['encryption_test'] = 'error: data mismatch'
                    health_status['encryption_service'] = 'degraded'
                    
            finally:
                # Clean up
                try:
                    os.unlink(temp_path)
                except:
                    pass
                    
        except Exception as e:
            health_status['encryption_test'] = f'error: {str(e)}'
            health_status['encryption_service'] = 'unhealthy'
        
        # Determine overall status
        if health_status['encryption_service'] == 'healthy':
            status_code = 200
        elif health_status['encryption_service'] == 'degraded':
            status_code = 200  # Still functional but with issues
        else:
            status_code = 503  # Service unavailable
        
        return JsonResponse(health_status, status=status_code)
        
    except Exception as e:
        logger.error(f"Error in encryption health check: {str(e)}")
        return JsonResponse({
            'encryption_service': 'unhealthy',
            'error': str(e),
            'timestamp': timezone.now().isoformat()
        }, status=503)