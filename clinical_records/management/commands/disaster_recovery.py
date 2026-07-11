#!/usr/bin/env python3
"""
Disaster recovery management command for clinical records system.
Handles emergency recovery procedures, system health checks, and automated failover.
"""

import os
import sys
import subprocess
import datetime
import json
import time
import logging
import psutil
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.db import connection, connections
from django.core.management import call_command
from django.core.cache import cache
from clinical_records.models import ClinicalRecord, ClinicalDocument
from users.models import Clinic, CustomUser

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Disaster recovery operations for clinical records system'

    def add_arguments(self, parser):
        parser.add_argument(
            'operation',
            type=str,
            choices=[
                'health-check',
                'emergency-backup',
                'emergency-restore',
                'system-recovery',
                'failover-test',
                'recovery-plan'
            ],
            help='Disaster recovery operation to perform'
        )
        parser.add_argument(
            '--backup-source',
            type=str,
            help='Source backup for emergency restore'
        )
        parser.add_argument(
            '--target-clinic',
            type=str,
            help='Target clinic for recovery operations'
        )
        parser.add_argument(
            '--emergency-mode',
            action='store_true',
            help='Enable emergency mode (bypass some safety checks)'
        )
        parser.add_argument(
            '--notification-email',
            type=str,
            help='Email address for disaster recovery notifications'
        )

    def handle(self, *args, **options):
        """Main disaster recovery execution"""
        try:
            self.operation = options['operation']
            self.backup_source = options.get('backup_source')
            self.target_clinic = options.get('target_clinic')
            self.emergency_mode = options['emergency_mode']
            self.notification_email = options.get('notification_email')
            
            self.stdout.write(f"Starting disaster recovery operation: {self.operation}")
            
            # Initialize recovery metadata
            self.recovery_metadata = {
                'operation': self.operation,
                'start_time': datetime.datetime.now().isoformat(),
                'emergency_mode': self.emergency_mode,
                'target_clinic': self.target_clinic,
                'status': 'in_progress',
                'checks_performed': [],
                'actions_taken': []
            }
            
            # Execute operation
            if self.operation == 'health-check':
                self.perform_health_check()
            elif self.operation == 'emergency-backup':
                self.perform_emergency_backup()
            elif self.operation == 'emergency-restore':
                self.perform_emergency_restore()
            elif self.operation == 'system-recovery':
                self.perform_system_recovery()
            elif self.operation == 'failover-test':
                self.perform_failover_test()
            elif self.operation == 'recovery-plan':
                self.generate_recovery_plan()
            
            # Finalize recovery
            self.finalize_recovery()
            
            self.stdout.write(
                self.style.SUCCESS(f'Disaster recovery operation completed: {self.operation}')
            )
            
        except Exception as e:
            logger.error(f"Disaster recovery failed: {e}")
            self.recovery_metadata['status'] = 'failed'
            self.recovery_metadata['error'] = str(e)
            self.save_recovery_metadata()
            
            # Send emergency notification
            if self.notification_email:
                self.send_emergency_notification(str(e))
            
            raise CommandError(f'Disaster recovery failed: {e}')

    def perform_health_check(self):
        """Comprehensive system health check"""
        self.stdout.write("Performing comprehensive health check...")
        
        health_status = {
            'database': self.check_database_health(),
            'file_storage': self.check_file_storage_health(),
            'cache': self.check_cache_health(),
            'background_jobs': self.check_background_jobs_health(),
            'system_resources': self.check_system_resources(),
            'data_integrity': self.check_data_integrity(),
            'backup_status': self.check_backup_status()
        }
        
        # Evaluate overall health
        critical_issues = []
        warnings = []
        
        for component, status in health_status.items():
            if status['status'] == 'critical':
                critical_issues.append(f"{component}: {status['message']}")
            elif status['status'] == 'warning':
                warnings.append(f"{component}: {status['message']}")
        
        # Report results
        if critical_issues:
            self.stdout.write(self.style.ERROR("CRITICAL ISSUES DETECTED:"))
            for issue in critical_issues:
                self.stdout.write(self.style.ERROR(f"  ❌ {issue}"))
        
        if warnings:
            self.stdout.write(self.style.WARNING("WARNINGS:"))
            for warning in warnings:
                self.stdout.write(self.style.WARNING(f"  ⚠️  {warning}"))
        
        if not critical_issues and not warnings:
            self.stdout.write(self.style.SUCCESS("✅ All systems healthy"))
        
        self.recovery_metadata['health_check'] = health_status
        self.recovery_metadata['critical_issues'] = critical_issues
        self.recovery_metadata['warnings'] = warnings

    def check_database_health(self):
        """Check database connectivity and performance"""
        try:
            # Test database connection
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                result = cursor.fetchone()
            
            # Check database size and performance
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT 
                        pg_size_pretty(pg_database_size(current_database())) as db_size,
                        (SELECT count(*) FROM clinical_records_clinicalrecord) as record_count,
                        (SELECT count(*) FROM clinical_records_clinicaldocument) as document_count
                """)
                db_stats = cursor.fetchone()
            
            # Check for long-running queries
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT count(*) FROM pg_stat_activity 
                    WHERE state = 'active' AND query_start < now() - interval '5 minutes'
                """)
                long_queries = cursor.fetchone()[0]
            
            status = 'healthy'
            message = f"Database operational. Size: {db_stats[0]}, Records: {db_stats[1]}, Documents: {db_stats[2]}"
            
            if long_queries > 0:
                status = 'warning'
                message += f". {long_queries} long-running queries detected"
            
            return {'status': status, 'message': message, 'stats': db_stats}
            
        except Exception as e:
            return {'status': 'critical', 'message': f"Database connection failed: {e}"}

    def check_file_storage_health(self):
        """Check file storage availability and space"""
        try:
            media_root = Path(settings.MEDIA_ROOT)
            
            if not media_root.exists():
                return {'status': 'critical', 'message': 'Media root directory does not exist'}
            
            # Check disk space
            disk_usage = psutil.disk_usage(str(media_root))
            free_space_gb = disk_usage.free / (1024**3)
            total_space_gb = disk_usage.total / (1024**3)
            usage_percent = (disk_usage.used / disk_usage.total) * 100
            
            # Check file accessibility
            test_file = media_root / "health_check_test.txt"
            try:
                test_file.write_text("health check")
                test_file.unlink()
                file_access = True
            except Exception:
                file_access = False
            
            status = 'healthy'
            message = f"Storage: {free_space_gb:.1f}GB free of {total_space_gb:.1f}GB ({usage_percent:.1f}% used)"
            
            if usage_percent > 90:
                status = 'critical'
                message += " - CRITICAL: Low disk space"
            elif usage_percent > 80:
                status = 'warning'
                message += " - WARNING: Disk space running low"
            
            if not file_access:
                status = 'critical'
                message += " - CRITICAL: Cannot write to storage"
            
            return {
                'status': status,
                'message': message,
                'free_space_gb': free_space_gb,
                'usage_percent': usage_percent,
                'file_access': file_access
            }
            
        except Exception as e:
            return {'status': 'critical', 'message': f"File storage check failed: {e}"}

    def check_cache_health(self):
        """Check cache system health"""
        try:
            # Test cache connectivity
            cache.set('health_check', 'test', 30)
            result = cache.get('health_check')
            cache.delete('health_check')
            
            if result == 'test':
                return {'status': 'healthy', 'message': 'Cache system operational'}
            else:
                return {'status': 'warning', 'message': 'Cache not responding correctly'}
                
        except Exception as e:
            return {'status': 'warning', 'message': f"Cache check failed: {e}"}

    def check_background_jobs_health(self):
        """Check background job processing health"""
        try:
            # Check Django-Q cluster status (if available)
            from django_q.models import Task
            
            # Check recent task failures
            recent_failures = Task.objects.filter(
                started__gte=datetime.datetime.now() - datetime.timedelta(hours=1),
                success=False
            ).count()
            
            # Check pending tasks
            pending_tasks = Task.objects.filter(started__isnull=True).count()
            
            status = 'healthy'
            message = f"Background jobs: {recent_failures} recent failures, {pending_tasks} pending"
            
            if recent_failures > 10:
                status = 'warning'
                message += " - High failure rate"
            
            if pending_tasks > 100:
                status = 'warning'
                message += " - High pending queue"
            
            return {'status': status, 'message': message}
            
        except ImportError:
            return {'status': 'warning', 'message': 'Django-Q not available for monitoring'}
        except Exception as e:
            return {'status': 'warning', 'message': f"Background job check failed: {e}"}

    def check_system_resources(self):
        """Check system resource utilization"""
        try:
            # CPU usage
            cpu_percent = psutil.cpu_percent(interval=1)
            
            # Memory usage
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            
            # Load average (Unix systems)
            try:
                load_avg = os.getloadavg()[0] if hasattr(os, 'getloadavg') else 0
            except:
                load_avg = 0
            
            status = 'healthy'
            message = f"CPU: {cpu_percent:.1f}%, Memory: {memory_percent:.1f}%"
            
            if cpu_percent > 90 or memory_percent > 90:
                status = 'critical'
                message += " - CRITICAL: High resource usage"
            elif cpu_percent > 80 or memory_percent > 80:
                status = 'warning'
                message += " - WARNING: High resource usage"
            
            return {
                'status': status,
                'message': message,
                'cpu_percent': cpu_percent,
                'memory_percent': memory_percent,
                'load_avg': load_avg
            }
            
        except Exception as e:
            return {'status': 'warning', 'message': f"System resource check failed: {e}"}

    def check_data_integrity(self):
        """Check data integrity and consistency"""
        try:
            # Check for orphaned documents
            orphaned_docs = ClinicalDocument.objects.filter(
                clinical_record__isnull=True
            ).count()
            
            # Check for missing files
            missing_files = 0
            sample_docs = ClinicalDocument.objects.all()[:100]
            for doc in sample_docs:
                if hasattr(doc, 'file') and doc.file:
                    if not Path(doc.file.path).exists():
                        missing_files += 1
            
            # Check for duplicate records
            duplicate_records = ClinicalRecord.objects.values(
                'patient', 'record_type', 'title'
            ).annotate(
                count=models.Count('id')
            ).filter(count__gt=1).count()
            
            issues = []
            if orphaned_docs > 0:
                issues.append(f"{orphaned_docs} orphaned documents")
            if missing_files > 0:
                issues.append(f"{missing_files} missing files (sample)")
            if duplicate_records > 0:
                issues.append(f"{duplicate_records} potential duplicate records")
            
            if issues:
                status = 'warning'
                message = f"Data integrity issues: {', '.join(issues)}"
            else:
                status = 'healthy'
                message = "Data integrity checks passed"
            
            return {
                'status': status,
                'message': message,
                'orphaned_docs': orphaned_docs,
                'missing_files': missing_files,
                'duplicate_records': duplicate_records
            }
            
        except Exception as e:
            return {'status': 'warning', 'message': f"Data integrity check failed: {e}"}

    def check_backup_status(self):
        """Check backup system status"""
        try:
            backup_dir = Path("clinical_backups")
            
            if not backup_dir.exists():
                return {'status': 'warning', 'message': 'No backup directory found'}
            
            # Find most recent backup
            backup_files = list(backup_dir.glob("clinical_backup_*"))
            if not backup_files:
                return {'status': 'warning', 'message': 'No backups found'}
            
            # Get most recent backup
            latest_backup = max(backup_files, key=lambda x: x.stat().st_mtime)
            backup_age = datetime.datetime.now() - datetime.datetime.fromtimestamp(
                latest_backup.stat().st_mtime
            )
            
            status = 'healthy'
            message = f"Latest backup: {backup_age.days} days ago"
            
            if backup_age.days > 7:
                status = 'warning'
                message += " - WARNING: Backup is old"
            elif backup_age.days > 1:
                status = 'warning'
                message += " - Backup should be more recent"
            
            return {
                'status': status,
                'message': message,
                'latest_backup': str(latest_backup),
                'backup_age_days': backup_age.days
            }
            
        except Exception as e:
            return {'status': 'warning', 'message': f"Backup status check failed: {e}"}

    def perform_emergency_backup(self):
        """Perform emergency backup"""
        self.stdout.write("Performing emergency backup...")
        
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = f"emergency_backup_{timestamp}"
        
        # Create emergency backup
        call_command(
            'backup_clinical_data',
            '--backup-type', 'full',
            '--output-dir', backup_dir,
            '--compress',
            '--clinic-id', self.target_clinic if self.target_clinic else None
        )
        
        self.recovery_metadata['actions_taken'].append({
            'action': 'emergency_backup',
            'backup_dir': backup_dir,
            'timestamp': timestamp
        })

    def perform_emergency_restore(self):
        """Perform emergency restore"""
        if not self.backup_source:
            raise CommandError("Backup source required for emergency restore")
        
        self.stdout.write(f"Performing emergency restore from: {self.backup_source}")
        
        # Create pre-restore backup if not in emergency mode
        if not self.emergency_mode:
            self.perform_emergency_backup()
        
        # Perform restore
        call_command(
            'restore_clinical_data',
            self.backup_source,
            '--restore-type', 'full',
            '--backup-existing' if not self.emergency_mode else '--force',
            '--clinic-id', self.target_clinic if self.target_clinic else None
        )
        
        self.recovery_metadata['actions_taken'].append({
            'action': 'emergency_restore',
            'backup_source': self.backup_source,
            'emergency_mode': self.emergency_mode
        })

    def perform_system_recovery(self):
        """Perform comprehensive system recovery"""
        self.stdout.write("Performing system recovery...")
        
        # First, perform health check
        self.perform_health_check()
        
        # Take emergency backup
        self.perform_emergency_backup()
        
        # Attempt to fix common issues
        self.fix_common_issues()
        
        # Verify recovery
        self.perform_health_check()

    def fix_common_issues(self):
        """Fix common system issues"""
        self.stdout.write("Attempting to fix common issues...")
        
        # Clear cache
        try:
            cache.clear()
            self.stdout.write("✅ Cache cleared")
        except Exception as e:
            self.stdout.write(f"❌ Failed to clear cache: {e}")
        
        # Restart background job processing
        try:
            call_command('qcluster', '--stop')
            time.sleep(2)
            call_command('qcluster')
            self.stdout.write("✅ Background job processing restarted")
        except Exception as e:
            self.stdout.write(f"❌ Failed to restart background jobs: {e}")
        
        # Clean up temporary files
        try:
            temp_dir = Path(settings.MEDIA_ROOT) / "temp"
            if temp_dir.exists():
                import shutil
                shutil.rmtree(temp_dir)
                temp_dir.mkdir()
            self.stdout.write("✅ Temporary files cleaned")
        except Exception as e:
            self.stdout.write(f"❌ Failed to clean temporary files: {e}")

    def perform_failover_test(self):
        """Perform failover testing"""
        self.stdout.write("Performing failover test...")
        
        # Test database failover (if configured)
        # Test file storage failover (if configured)
        # Test cache failover (if configured)
        
        # This is a placeholder for actual failover testing
        self.stdout.write("Failover test completed (placeholder)")

    def generate_recovery_plan(self):
        """Generate disaster recovery plan"""
        self.stdout.write("Generating disaster recovery plan...")
        
        plan = {
            'generated_at': datetime.datetime.now().isoformat(),
            'system_info': {
                'django_version': getattr(settings, 'DJANGO_VERSION', 'unknown'),
                'database_engine': settings.DATABASES['default']['ENGINE'],
                'media_root': str(settings.MEDIA_ROOT),
                'installed_apps': settings.INSTALLED_APPS
            },
            'recovery_procedures': {
                'database_recovery': {
                    'backup_location': 'clinical_backups/',
                    'restore_command': 'python manage.py restore_clinical_data <backup_path>',
                    'estimated_time': '15-30 minutes'
                },
                'file_recovery': {
                    'backup_location': 'clinical_backups/clinical_files/',
                    'restore_command': 'python manage.py restore_clinical_data <backup_path> --restore-type files-only',
                    'estimated_time': '30-60 minutes'
                },
                'full_recovery': {
                    'backup_location': 'clinical_backups/',
                    'restore_command': 'python manage.py disaster_recovery emergency-restore --backup-source <backup_path>',
                    'estimated_time': '45-90 minutes'
                }
            },
            'emergency_contacts': {
                'system_admin': 'admin@rxdoctor.com',
                'database_admin': 'dba@rxdoctor.com',
                'infrastructure': 'infra@rxdoctor.com'
            },
            'escalation_procedures': [
                '1. Assess severity and impact',
                '2. Notify system administrator',
                '3. Create emergency backup if possible',
                '4. Implement recovery procedures',
                '5. Validate system functionality',
                '6. Document incident and lessons learned'
            ]
        }
        
        # Save recovery plan
        plan_file = Path(f"disaster_recovery_plan_{datetime.datetime.now().strftime('%Y%m%d')}.json")
        with open(plan_file, 'w') as f:
            json.dump(plan, f, indent=2, default=str)
        
        self.stdout.write(f"Recovery plan saved: {plan_file}")

    def finalize_recovery(self):
        """Finalize recovery process"""
        self.recovery_metadata['end_time'] = datetime.datetime.now().isoformat()
        self.recovery_metadata['status'] = 'completed'
        
        # Save recovery metadata
        self.save_recovery_metadata()
        
        # Send notification if configured
        if self.notification_email:
            self.send_recovery_notification()

    def save_recovery_metadata(self):
        """Save recovery metadata"""
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        metadata_file = Path(f"disaster_recovery_{self.operation}_{timestamp}.json")
        
        with open(metadata_file, 'w') as f:
            json.dump(self.recovery_metadata, f, indent=2, default=str)
        
        self.stdout.write(f"Recovery metadata saved: {metadata_file}")

    def send_emergency_notification(self, error_message):
        """Send emergency notification"""
        # Placeholder for email notification
        self.stdout.write(f"Emergency notification would be sent to: {self.notification_email}")
        self.stdout.write(f"Error: {error_message}")

    def send_recovery_notification(self):
        """Send recovery completion notification"""
        # Placeholder for email notification
        self.stdout.write(f"Recovery notification would be sent to: {self.notification_email}")
        self.stdout.write(f"Operation: {self.operation} completed successfully")