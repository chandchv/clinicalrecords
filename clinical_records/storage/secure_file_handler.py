"""
Secure file handling for production clinical records storage.
Handles file serving with authentication, logging, and security checks.
"""

import os
import mimetypes
import logging
from pathlib import Path
from django.conf import settings
from django.http import HttpResponse, Http404, HttpResponseForbidden
from django.core.exceptions import PermissionDenied
from django.utils.http import http_date
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views import View
from users.models import AuditLog
import hashlib
import time

logger = logging.getLogger(__name__)

class SecureFileHandler:
    """
    Handles secure file serving with authentication and audit logging.
    """
    
    def __init__(self):
        self.media_root = Path(settings.MEDIA_ROOT)
        self.use_nginx_x_accel = getattr(settings, 'USE_NGINX_X_ACCEL', False)
        self.use_apache_x_sendfile = getattr(settings, 'USE_APACHE_X_SENDFILE', False)
        self.internal_url_prefix = getattr(settings, 'INTERNAL_URL_PREFIX', '/internal/media/')
        
    def serve_file(self, request, file_path, content_type=None, filename=None):
        """
        Serve file securely with proper authentication and logging.
        """
        try:
            # Validate file path
            full_path = self.media_root / file_path
            if not self._is_safe_path(full_path):
                logger.warning(f"Unsafe file path access attempt: {file_path} by user {request.user}")
                raise PermissionDenied("Invalid file path")
            
            # Check if file exists
            if not full_path.exists() or not full_path.is_file():
                logger.warning(f"File not found: {file_path} requested by user {request.user}")
                raise Http404("File not found")
            
            # Log file access
            self._log_file_access(request, file_path, 'ACCESS')
            
            # Determine content type
            if not content_type:
                content_type, _ = mimetypes.guess_type(str(full_path))
                if not content_type:
                    content_type = 'application/octet-stream'
            
            # Use web server acceleration if available
            if self.use_nginx_x_accel:
                return self._serve_with_nginx_x_accel(file_path, content_type, filename)
            elif self.use_apache_x_sendfile:
                return self._serve_with_apache_x_sendfile(full_path, content_type, filename)
            else:
                return self._serve_with_django(full_path, content_type, filename)
                
        except Exception as e:
            logger.error(f"Error serving file {file_path}: {str(e)}")
            self._log_file_access(request, file_path, 'ERROR', str(e))
            raise
    
    def _serve_with_nginx_x_accel(self, file_path, content_type, filename):
        """
        Serve file using nginx X-Accel-Redirect for better performance.
        """
        response = HttpResponse()
        response['Content-Type'] = content_type
        response['X-Accel-Redirect'] = f"{self.internal_url_prefix}{file_path}"
        
        if filename:
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        # Security headers
        response['X-Content-Type-Options'] = 'nosniff'
        response['X-Frame-Options'] = 'DENY'
        response['Cache-Control'] = 'private, no-cache, no-store, must-revalidate'
        response['Pragma'] = 'no-cache'
        response['Expires'] = '0'
        
        return response
    
    def _serve_with_apache_x_sendfile(self, full_path, content_type, filename):
        """
        Serve file using Apache X-Sendfile for better performance.
        """
        response = HttpResponse()
        response['Content-Type'] = content_type
        response['X-Sendfile'] = str(full_path)
        
        if filename:
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        # Security headers
        response['X-Content-Type-Options'] = 'nosniff'
        response['X-Frame-Options'] = 'DENY'
        response['Cache-Control'] = 'private, no-cache, no-store, must-revalidate'
        response['Pragma'] = 'no-cache'
        response['Expires'] = '0'
        
        return response
    
    def _serve_with_django(self, full_path, content_type, filename):
        """
        Serve file directly through Django (fallback method).
        """
        try:
            with open(full_path, 'rb') as f:
                response = HttpResponse(f.read(), content_type=content_type)
            
            if filename:
                response['Content-Disposition'] = f'attachment; filename="{filename}"'
            
            # Security headers
            response['X-Content-Type-Options'] = 'nosniff'
            response['X-Frame-Options'] = 'DENY'
            response['Cache-Control'] = 'private, no-cache, no-store, must-revalidate'
            response['Pragma'] = 'no-cache'
            response['Expires'] = '0'
            
            # Set file size
            response['Content-Length'] = full_path.stat().st_size
            
            return response
            
        except IOError as e:
            logger.error(f"Error reading file {full_path}: {str(e)}")
            raise Http404("File could not be read")
    
    def _is_safe_path(self, path):
        """
        Check if the file path is safe (no directory traversal).
        """
        try:
            # Resolve the path and check if it's within media root
            resolved_path = path.resolve()
            media_root_resolved = self.media_root.resolve()
            
            # Check if the resolved path is within the media root
            return str(resolved_path).startswith(str(media_root_resolved))
        except (OSError, ValueError):
            return False
    
    def _log_file_access(self, request, file_path, action, details=None):
        """
        Log file access for audit purposes.
        """
        try:
            # Get client IP
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            if x_forwarded_for:
                ip_address = x_forwarded_for.split(',')[0].strip()
            else:
                ip_address = request.META.get('REMOTE_ADDR', 'unknown')
            
            # Create audit log entry
            AuditLog.log_action(
                user=request.user if request.user.is_authenticated else None,
                action=f'FILE_{action}',
                resource_type='CLINICAL_DOCUMENT',
                resource_id=file_path,
                details=details or f"File {action.lower()}: {file_path}",
                ip_address=ip_address,
                tenant=getattr(request.user, 'current_tenant', None) if request.user.is_authenticated else None
            )
            
            # Also log to file access log if configured
            if hasattr(settings, 'FILE_ACCESS_LOGGING'):
                self._log_to_file_access_log(request, file_path, action, ip_address)
                
        except Exception as e:
            logger.error(f"Error logging file access: {str(e)}")
    
    def _log_to_file_access_log(self, request, file_path, action, ip_address):
        """
        Log to dedicated file access log.
        """
        try:
            log_config = settings.FILE_ACCESS_LOGGING
            log_file = log_config.get('LOG_FILE', '/var/log/rxdoctor/file_access.log')
            
            # Ensure log directory exists
            os.makedirs(os.path.dirname(log_file), exist_ok=True)
            
            # Format log entry
            timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
            user = request.user.username if request.user.is_authenticated else 'anonymous'
            log_entry = f"{timestamp} - {user} - {action} - {file_path} - {ip_address}\n"
            
            # Write to log file
            with open(log_file, 'a') as f:
                f.write(log_entry)
                
        except Exception as e:
            logger.error(f"Error writing to file access log: {str(e)}")


@method_decorator([login_required, never_cache], name='dispatch')
class SecureFileView(View):
    """
    View for serving clinical record files securely.
    """
    
    def __init__(self):
        super().__init__()
        self.file_handler = SecureFileHandler()
    
    def get(self, request, file_path):
        """
        Serve file with authentication and permission checks.
        """
        try:
            # Import here to avoid circular imports
            from clinical_records.models import ClinicalDocument
            
            # Find the document record
            try:
                document = ClinicalDocument.objects.get(
                    file_path=file_path,
                    clinical_record__clinic=request.user.current_tenant
                )
            except ClinicalDocument.DoesNotExist:
                logger.warning(f"Document not found or access denied: {file_path} for user {request.user}")
                raise Http404("Document not found")
            
            # Check permissions
            if not self._has_permission(request.user, document):
                logger.warning(f"Permission denied for document {file_path} by user {request.user}")
                raise PermissionDenied("You don't have permission to access this document")
            
            # Serve the file
            return self.file_handler.serve_file(
                request,
                file_path,
                content_type=document.content_type,
                filename=document.file_name
            )
            
        except (Http404, PermissionDenied):
            raise
        except Exception as e:
            logger.error(f"Error in SecureFileView: {str(e)}")
            return HttpResponseForbidden("Access denied")
    
    def _has_permission(self, user, document):
        """
        Check if user has permission to access the document.
        """
        # Check tenant isolation
        if document.clinical_record.clinic != user.current_tenant:
            return False
        
        # Check role-based permissions
        if user.role == 'doctor':
            # Doctors can access documents for their patients
            return document.clinical_record.patient in user.patients.all()
        elif user.role == 'clinic_admin':
            # Clinic admins can access all documents in their clinic
            return True
        elif user.role == 'patient':
            # Patients can only access their own documents
            return document.clinical_record.patient.user == user
        
        return False


class FileStorageMonitor:
    """
    Monitor file storage usage and send alerts.
    """
    
    def __init__(self):
        self.media_root = Path(settings.MEDIA_ROOT)
        self.warning_threshold = getattr(settings, 'DISK_SPACE_WARNING_THRESHOLD', 80)
        self.critical_threshold = getattr(settings, 'DISK_SPACE_CRITICAL_THRESHOLD', 90)
    
    def check_disk_space(self):
        """
        Check disk space usage and send alerts if necessary.
        """
        try:
            # Get disk usage statistics
            statvfs = os.statvfs(self.media_root)
            
            # Calculate usage percentage
            total_space = statvfs.f_frsize * statvfs.f_blocks
            free_space = statvfs.f_frsize * statvfs.f_available
            used_space = total_space - free_space
            usage_percent = (used_space / total_space) * 100
            
            logger.info(f"Disk usage: {usage_percent:.1f}% ({used_space / (1024**3):.1f}GB / {total_space / (1024**3):.1f}GB)")
            
            # Check thresholds and send alerts
            if usage_percent >= self.critical_threshold:
                self._send_disk_space_alert('CRITICAL', usage_percent, used_space, total_space)
            elif usage_percent >= self.warning_threshold:
                self._send_disk_space_alert('WARNING', usage_percent, used_space, total_space)
            
            return {
                'usage_percent': usage_percent,
                'used_space_gb': used_space / (1024**3),
                'total_space_gb': total_space / (1024**3),
                'free_space_gb': free_space / (1024**3)
            }
            
        except Exception as e:
            logger.error(f"Error checking disk space: {str(e)}")
            return None
    
    def _send_disk_space_alert(self, level, usage_percent, used_space, total_space):
        """
        Send disk space alert email.
        """
        try:
            from django.core.mail import send_mail
            
            subject = f"RxDoctor Disk Space {level} Alert"
            message = f"""
Disk space usage has reached {level.lower()} threshold.

Current usage: {usage_percent:.1f}%
Used space: {used_space / (1024**3):.1f} GB
Total space: {total_space / (1024**3):.1f} GB

Please take action to free up disk space.

Server: {os.uname().nodename}
Path: {self.media_root}
Time: {time.strftime('%Y-%m-%d %H:%M:%S')}
            """
            
            admin_email = getattr(settings, 'ADMIN_EMAIL', 'admin@rxdoctor.com')
            
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                [admin_email],
                fail_silently=False
            )
            
            logger.warning(f"Disk space {level} alert sent: {usage_percent:.1f}% usage")
            
        except Exception as e:
            logger.error(f"Error sending disk space alert: {str(e)}")
    
    def cleanup_temp_files(self, days_old=7):
        """
        Clean up temporary files older than specified days.
        """
        try:
            temp_dir = self.media_root / 'clinical_records' / 'temp'
            if not temp_dir.exists():
                return 0
            
            cutoff_time = time.time() - (days_old * 24 * 60 * 60)
            cleaned_count = 0
            
            for file_path in temp_dir.rglob('*'):
                if file_path.is_file() and file_path.stat().st_mtime < cutoff_time:
                    try:
                        file_path.unlink()
                        cleaned_count += 1
                        logger.info(f"Cleaned up temp file: {file_path}")
                    except Exception as e:
                        logger.error(f"Error deleting temp file {file_path}: {str(e)}")
            
            logger.info(f"Cleaned up {cleaned_count} temporary files older than {days_old} days")
            return cleaned_count
            
        except Exception as e:
            logger.error(f"Error cleaning up temp files: {str(e)}")
            return 0