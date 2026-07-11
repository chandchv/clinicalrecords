#!/usr/bin/env python3
"""
Backup monitoring management command for clinical records system.
Monitors backup health, schedules automated backups, and sends alerts.
"""

import os
import sys
import datetime
import json
import logging
import smtplib
from pathlib import Path
from email.mime.text import MimeText
from email.mime.multipart import MimeMultipart
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.core.management import call_command
from django.utils import timezone

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Monitor backup system health and schedule automated backups'

    def add_arguments(self, parser):
        parser.add_argument(
            'action',
            type=str,
            choices=[
                'status',
                'schedule',
                'validate',
                'cleanup',
                'alert-test',
                'auto-backup'
            ],
            help='Monitoring action to perform'
        )
        parser.add_argument(
            '--backup-dir',
            type=str,
            default='clinical_backups',
            help='Backup directory to monitor'
        )
        parser.add_argument(
            '--max-age-days',
            type=int,
            default=1,
            help='Maximum age for backups before alerting'
        )
        parser.add_argument(
            '--retention-days',
            type=int,
            default=30,
            help='Number of days to retain backups'
        )
        parser.add_argument(
            '--email-alerts',
            type=str,
            help='Comma-separated list of email addresses for alerts'
        )
        parser.add_argument(
            '--schedule-time',
            type=str,
            default='02:00',
            help='Time to schedule daily backups (HH:MM format)'
        )
        parser.add_argument(
            '--backup-type',
            type=str,
            choices=['full', 'incremental'],
            default='incremental',
            help='Type of scheduled backup'
        )

    def handle(self, *args, **options):
        """Main monitoring execution"""
        try:
            self.action = options['action']
            self.backup_dir = Path(options['backup_dir'])
            self.max_age_days = options['max_age_days']
            self.retention_days = options['retention_days']
            self.email_alerts = options.get('email_alerts', '').split(',') if options.get('email_alerts') else []
            self.schedule_time = options['schedule_time']
            self.backup_type = options['backup_type']
            
            self.stdout.write(f"Starting backup monitoring action: {self.action}")
            
            # Execute action
            if self.action == 'status':
                self.check_backup_status()
            elif self.action == 'schedule':
                self.schedule_backups()
            elif self.action == 'validate':
                self.validate_backups()
            elif self.action == 'cleanup':
                self.cleanup_old_backups()
            elif self.action == 'alert-test':
                self.test_alerts()
            elif self.action == 'auto-backup':
                self.perform_auto_backup()
            
            self.stdout.write(
                self.style.SUCCESS(f'Backup monitoring action completed: {self.action}')
            )
            
        except Exception as e:
            logger.error(f"Backup monitoring failed: {e}")
            self.send_alert(f"Backup monitoring failed: {e}", is_critical=True)
            raise CommandError(f'Backup monitoring failed: {e}')

    def check_backup_status(self):
        """Check current backup status"""
        self.stdout.write("Checking backup status...")
        
        if not self.backup_dir.exists():
            self.stdout.write(self.style.ERROR("❌ Backup directory does not exist"))
            self.send_alert("Backup directory does not exist", is_critical=True)
            return
        
        # Find all backup files/directories
        backup_items = list(self.backup_dir.glob("clinical_backup_*"))
        
        if not backup_items:
            self.stdout.write(self.style.ERROR("❌ No backups found"))
            self.send_alert("No backups found in backup directory", is_critical=True)
            return
        
        # Analyze backups
        backup_info = []
        for item in backup_items:
            try:
                # Extract timestamp from name
                timestamp_str = item.name.split('_')[-1]
                if len(timestamp_str) == 15:  # YYYYMMDD_HHMMSS
                    backup_time = datetime.datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
                    age = datetime.datetime.now() - backup_time
                    
                    # Get size
                    if item.is_dir():
                        size = sum(f.stat().st_size for f in item.rglob('*') if f.is_file())
                    else:
                        size = item.stat().st_size
                    
                    # Load metadata if available
                    metadata = self.load_backup_metadata(item)
                    
                    backup_info.append({
                        'name': item.name,
                        'path': str(item),
                        'timestamp': backup_time,
                        'age_days': age.days,
                        'age_hours': age.total_seconds() / 3600,
                        'size_mb': size / (1024 * 1024),
                        'metadata': metadata,
                        'is_valid': metadata.get('status') == 'completed' if metadata else None
                    })
            except (ValueError, IndexError):
                continue
        
        # Sort by timestamp (newest first)
        backup_info.sort(key=lambda x: x['timestamp'], reverse=True)
        
        # Report status
        self.stdout.write(f"Found {len(backup_info)} backups:")
        
        alerts_to_send = []
        
        for backup in backup_info[:5]:  # Show last 5 backups
            age_str = f"{backup['age_days']}d {backup['age_hours']%24:.1f}h"
            size_str = f"{backup['size_mb']:.1f}MB"
            status_str = "✅" if backup['is_valid'] else "❌" if backup['is_valid'] is False else "❓"
            
            self.stdout.write(f"  {status_str} {backup['name']} - {age_str} ago, {size_str}")
            
            # Check for issues
            if backup['age_days'] == 0 and backup['age_hours'] < 1:
                continue  # Very recent backup, skip age checks
            
            if backup == backup_info[0]:  # Most recent backup
                if backup['age_days'] > self.max_age_days:
                    alerts_to_send.append(f"Latest backup is {backup['age_days']} days old (max: {self.max_age_days})")
                
                if backup['is_valid'] is False:
                    alerts_to_send.append(f"Latest backup failed: {backup['name']}")
        
        # Check backup frequency
        if len(backup_info) >= 2:
            latest_backup = backup_info[0]
            previous_backup = backup_info[1]
            gap_days = (latest_backup['timestamp'] - previous_backup['timestamp']).days
            
            if gap_days > 2:
                alerts_to_send.append(f"Large gap between backups: {gap_days} days")
        
        # Send alerts if needed
        if alerts_to_send:
            alert_message = "Backup status alerts:\n" + "\n".join(f"- {alert}" for alert in alerts_to_send)
            self.send_alert(alert_message, is_critical=any("failed" in alert for alert in alerts_to_send))
        else:
            self.stdout.write(self.style.SUCCESS("✅ Backup status is healthy"))

    def load_backup_metadata(self, backup_path):
        """Load backup metadata if available"""
        try:
            if backup_path.is_dir():
                metadata_file = backup_path / "backup_metadata.json"
            else:
                # For compressed backups, we can't easily read metadata
                return None
            
            if metadata_file.exists():
                with open(metadata_file, 'r') as f:
                    return json.load(f)
        except Exception:
            pass
        return None

    def schedule_backups(self):
        """Schedule automated backups"""
        self.stdout.write(f"Scheduling {self.backup_type} backups at {self.schedule_time}...")
        
        # Create cron job entry
        cron_command = f"cd {os.getcwd()} && python manage.py monitor_backups auto-backup --backup-type {self.backup_type}"
        
        # For Windows, create a scheduled task
        if os.name == 'nt':
            self.create_windows_scheduled_task(cron_command)
        else:
            self.create_cron_job(cron_command)

    def create_windows_scheduled_task(self, command):
        """Create Windows scheduled task"""
        task_name = "RxDoctor_Clinical_Backup"
        
        # Create batch file
        batch_file = Path("backup_scheduler.bat")
        batch_content = f"""@echo off
cd /d "{os.getcwd()}"
{command}
"""
        batch_file.write_text(batch_content)
        
        # Create scheduled task
        hour, minute = self.schedule_time.split(':')
        schtasks_command = [
            'schtasks', '/create',
            '/tn', task_name,
            '/tr', str(batch_file.absolute()),
            '/sc', 'daily',
            '/st', self.schedule_time,
            '/f'  # Force overwrite if exists
        ]
        
        try:
            import subprocess
            result = subprocess.run(schtasks_command, capture_output=True, text=True, check=True)
            self.stdout.write(f"✅ Windows scheduled task created: {task_name}")
        except subprocess.CalledProcessError as e:
            self.stdout.write(f"❌ Failed to create scheduled task: {e}")

    def create_cron_job(self, command):
        """Create cron job for Unix systems"""
        hour, minute = self.schedule_time.split(':')
        cron_entry = f"{minute} {hour} * * * {command}\n"
        
        self.stdout.write("To schedule backups, add this line to your crontab:")
        self.stdout.write(f"  {cron_entry.strip()}")
        self.stdout.write("Run: crontab -e")

    def validate_backups(self):
        """Validate backup integrity"""
        self.stdout.write("Validating backup integrity...")
        
        backup_items = list(self.backup_dir.glob("clinical_backup_*"))
        
        if not backup_items:
            self.stdout.write(self.style.ERROR("❌ No backups to validate"))
            return
        
        # Validate most recent backups
        recent_backups = sorted(backup_items, key=lambda x: x.stat().st_mtime, reverse=True)[:3]
        
        validation_results = []
        
        for backup_path in recent_backups:
            self.stdout.write(f"Validating: {backup_path.name}")
            
            try:
                # Load metadata
                metadata = self.load_backup_metadata(backup_path)
                
                if not metadata:
                    validation_results.append({
                        'backup': backup_path.name,
                        'status': 'warning',
                        'message': 'No metadata found'
                    })
                    continue
                
                # Check backup status
                if metadata.get('status') != 'completed':
                    validation_results.append({
                        'backup': backup_path.name,
                        'status': 'error',
                        'message': f"Backup status: {metadata.get('status', 'unknown')}"
                    })
                    continue
                
                # Validate components
                components = metadata.get('components', [])
                missing_components = []
                
                for component in components:
                    if component['type'] == 'database':
                        db_file = Path(component['file'])
                        if not db_file.exists() and not (backup_path / db_file.name).exists():
                            missing_components.append('database')
                    elif component['type'] == 'clinical_files':
                        files_dir = backup_path / "clinical_files"
                        if not files_dir.exists():
                            missing_components.append('clinical_files')
                
                if missing_components:
                    validation_results.append({
                        'backup': backup_path.name,
                        'status': 'error',
                        'message': f"Missing components: {', '.join(missing_components)}"
                    })
                else:
                    validation_results.append({
                        'backup': backup_path.name,
                        'status': 'success',
                        'message': 'Validation passed'
                    })
                    
            except Exception as e:
                validation_results.append({
                    'backup': backup_path.name,
                    'status': 'error',
                    'message': f"Validation failed: {e}"
                })
        
        # Report results
        errors = [r for r in validation_results if r['status'] == 'error']
        warnings = [r for r in validation_results if r['status'] == 'warning']
        
        for result in validation_results:
            status_icon = {"success": "✅", "warning": "⚠️", "error": "❌"}[result['status']]
            self.stdout.write(f"  {status_icon} {result['backup']}: {result['message']}")
        
        if errors:
            alert_message = f"Backup validation errors found:\n" + "\n".join(
                f"- {r['backup']}: {r['message']}" for r in errors
            )
            self.send_alert(alert_message, is_critical=True)

    def cleanup_old_backups(self):
        """Clean up old backup files"""
        self.stdout.write(f"Cleaning up backups older than {self.retention_days} days...")
        
        if self.retention_days <= 0:
            self.stdout.write("Retention days is 0 or negative, skipping cleanup")
            return
        
        cutoff_date = datetime.datetime.now() - datetime.timedelta(days=self.retention_days)
        
        backup_items = list(self.backup_dir.glob("clinical_backup_*"))
        removed_count = 0
        
        for backup_path in backup_items:
            try:
                # Extract timestamp from name
                timestamp_str = backup_path.name.split('_')[-1]
                if len(timestamp_str) == 15:  # YYYYMMDD_HHMMSS
                    backup_date = datetime.datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
                    
                    if backup_date < cutoff_date:
                        if backup_path.is_dir():
                            import shutil
                            shutil.rmtree(backup_path)
                        else:
                            backup_path.unlink()
                        
                        self.stdout.write(f"Removed old backup: {backup_path.name}")
                        removed_count += 1
                        
            except (ValueError, IndexError):
                # Skip files that don't match expected format
                continue
        
        self.stdout.write(f"✅ Cleaned up {removed_count} old backups")

    def test_alerts(self):
        """Test alert system"""
        self.stdout.write("Testing alert system...")
        
        if not self.email_alerts:
            self.stdout.write("No email addresses configured for alerts")
            return
        
        test_message = f"Test alert from RxDoctor backup monitoring system at {datetime.datetime.now()}"
        self.send_alert(test_message, is_critical=False, subject_prefix="TEST")

    def perform_auto_backup(self):
        """Perform automated backup"""
        self.stdout.write(f"Performing automated {self.backup_type} backup...")
        
        try:
            # Determine if we should do full or incremental
            backup_type = self.backup_type
            
            # If incremental, check if we need a full backup
            if backup_type == 'incremental':
                backup_items = list(self.backup_dir.glob("clinical_backup_*"))
                full_backups = []
                
                for item in backup_items:
                    metadata = self.load_backup_metadata(item)
                    if metadata and metadata.get('backup_type') == 'full':
                        full_backups.append(item)
                
                # If no full backup in last 7 days, do full backup
                if not full_backups:
                    backup_type = 'full'
                else:
                    latest_full = max(full_backups, key=lambda x: x.stat().st_mtime)
                    age = datetime.datetime.now() - datetime.datetime.fromtimestamp(latest_full.stat().st_mtime)
                    if age.days >= 7:
                        backup_type = 'full'
            
            # Perform backup
            call_command(
                'backup_clinical_data',
                '--backup-type', backup_type,
                '--output-dir', str(self.backup_dir),
                '--compress',
                '--retention-days', str(self.retention_days)
            )
            
            self.stdout.write(f"✅ Automated {backup_type} backup completed")
            
            # Send success notification
            self.send_alert(
                f"Automated {backup_type} backup completed successfully",
                is_critical=False,
                subject_prefix="SUCCESS"
            )
            
        except Exception as e:
            error_msg = f"Automated backup failed: {e}"
            self.stdout.write(self.style.ERROR(f"❌ {error_msg}"))
            self.send_alert(error_msg, is_critical=True)
            raise

    def send_alert(self, message, is_critical=False, subject_prefix="ALERT"):
        """Send alert notification"""
        if not self.email_alerts:
            return
        
        subject = f"[{subject_prefix}] RxDoctor Clinical Backup System"
        if is_critical:
            subject = f"[CRITICAL] {subject}"
        
        body = f"""
RxDoctor Clinical Records Backup System Alert

Time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Severity: {'CRITICAL' if is_critical else 'INFO'}

Message:
{message}

System Information:
- Backup Directory: {self.backup_dir}
- Max Age Days: {self.max_age_days}
- Retention Days: {self.retention_days}

This is an automated message from the RxDoctor backup monitoring system.
"""
        
        try:
            # Use Django's email backend if configured
            from django.core.mail import send_mail
            
            send_mail(
                subject=subject,
                message=body,
                from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@rxdoctor.com'),
                recipient_list=self.email_alerts,
                fail_silently=False
            )
            
            self.stdout.write(f"Alert sent to: {', '.join(self.email_alerts)}")
            
        except Exception as e:
            self.stdout.write(f"Failed to send alert: {e}")
            logger.error(f"Failed to send backup alert: {e}")