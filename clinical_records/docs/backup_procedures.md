# Clinical Records Backup Procedures

## Overview

This document outlines the comprehensive backup procedures for the RxDoctor Clinical Records Management system. It covers automated backups, manual backup procedures, backup validation, and restoration processes.

## Backup Strategy

### Backup Types

1. **Full Backup**
   - Complete database dump
   - All clinical document files
   - System metadata and configuration
   - Frequency: Weekly (Sundays at 2:00 AM)

2. **Incremental Backup**
   - Changes since last backup
   - New/modified documents only
   - Updated database records
   - Frequency: Daily (2:00 AM)

3. **Emergency Backup**
   - On-demand backup before maintenance
   - Before major system changes
   - During incident response

### Backup Components

1. **Database Backup**
   - PostgreSQL database dump
   - All clinical records metadata
   - User and clinic data
   - System configuration tables

2. **File Storage Backup**
   - Clinical document files
   - Thumbnails and previews
   - DICOM images
   - OCR processed files

3. **Metadata Backup**
   - System configuration
   - Processing status
   - Audit logs
   - Backup metadata

## Automated Backup Setup

### 1. Schedule Daily Backups

```bash
# Set up automated daily incremental backups
python manage.py monitor_backups schedule --backup-type incremental --schedule-time 02:00

# Set up weekly full backups (manual cron entry)
# Add to crontab: 0 2 * * 0 cd /path/to/RxBackend && python manage.py backup_clinical_data --backup-type full --compress
```

### 2. Configure Backup Monitoring

```bash
# Set up monitoring with email alerts
python manage.py monitor_backups schedule --email-alerts admin@rxdoctor.com,backup@rxdoctor.com

# Test alert system
python manage.py monitor_backups alert-test
```

### 3. Windows Scheduled Task Setup

For Windows environments:

1. Create batch file `daily_backup.bat`:
```batch
@echo off
cd /d "C:\path\to\RxBackend"
call my_env\Scripts\activate
python manage.py monitor_backups auto-backup --backup-type incremental
```

2. Create scheduled task:
```cmd
schtasks /create /tn "RxDoctor_Daily_Backup" /tr "C:\path\to\daily_backup.bat" /sc daily /st 02:00 /ru SYSTEM
```

## Manual Backup Procedures

### 1. Full System Backup

```bash
# Create comprehensive backup
python manage.py backup_clinical_data --backup-type full --compress --output-dir clinical_backups

# With specific clinic
python manage.py backup_clinical_data --backup-type full --clinic-id <clinic_uuid> --compress
```

### 2. Database-Only Backup

```bash
# Backup database only
python manage.py backup_clinical_data --backup-type database-only --output-dir db_backups

# Quick PostgreSQL backup
pg_dump -h localhost -U postgres -d rxdoctor1 > manual_backup_$(date +%Y%m%d_%H%M%S).sql
```

### 3. Files-Only Backup

```bash
# Backup clinical files only
python manage.py backup_clinical_data --backup-type files-only --output-dir file_backups

# Manual file backup
tar -czf clinical_files_$(date +%Y%m%d_%H%M%S).tar.gz media/clinical_documents/
```

### 4. Emergency Backup

```bash
# Quick emergency backup before maintenance
python manage.py backup_clinical_data --backup-type full --output-dir emergency_backups --compress

# Or use disaster recovery command
python manage.py disaster_recovery emergency-backup
```

## Backup Validation

### 1. Daily Validation

```bash
# Check backup status
python manage.py monitor_backups status

# Validate recent backups
python manage.py monitor_backups validate
```

### 2. Weekly Validation

```bash
# Comprehensive backup validation
python manage.py monitor_backups validate

# Test restore process (dry run)
python manage.py restore_clinical_data clinical_backups/clinical_backup_YYYYMMDD_HHMMSS --dry-run
```

### 3. Monthly Validation

```bash
# Full restore test to staging environment
python manage.py restore_clinical_data clinical_backups/clinical_backup_YYYYMMDD_HHMMSS --restore-type full

# Validate restored data
python manage.py disaster_recovery health-check
```

## Backup Storage

### Local Storage

- **Primary Location**: `clinical_backups/`
- **Retention**: 30 days for daily backups, 90 days for weekly backups
- **Compression**: Enabled for space efficiency
- **Encryption**: Optional (recommended for sensitive environments)

### Offsite Storage (Recommended)

1. **Cloud Storage**
   ```bash
   # Upload to cloud storage (example with AWS S3)
   aws s3 sync clinical_backups/ s3://rxdoctor-backups/clinical/
   ```

2. **Network Storage**
   ```bash
   # Copy to network drive
   robocopy clinical_backups\ \\backup-server\rxdoctor\clinical\ /MIR
   ```

3. **External Media**
   ```bash
   # Copy to external drive
   cp -r clinical_backups/ /media/external-drive/rxdoctor-backups/
   ```

## Restoration Procedures

### 1. Full System Restore

```bash
# Complete system restoration
python manage.py restore_clinical_data clinical_backups/clinical_backup_YYYYMMDD_HHMMSS --restore-type full --backup-existing

# Verify restoration
python manage.py disaster_recovery health-check
```

### 2. Database Restore

```bash
# Database-only restore
python manage.py restore_clinical_data clinical_backups/clinical_backup_YYYYMMDD_HHMMSS --restore-type database-only

# Manual PostgreSQL restore
psql -h localhost -U postgres -d rxdoctor1 < backup_file.sql
```

### 3. File Restore

```bash
# Files-only restore
python manage.py restore_clinical_data clinical_backups/clinical_backup_YYYYMMDD_HHMMSS --restore-type files-only

# Manual file restore
tar -xzf clinical_files_backup.tar.gz -C media/
```

### 4. Selective Restore

```bash
# Restore specific clinic data
python manage.py restore_clinical_data clinical_backups/clinical_backup_YYYYMMDD_HHMMSS --clinic-id <clinic_uuid>

# Restore with validation
python manage.py restore_clinical_data clinical_backups/clinical_backup_YYYYMMDD_HHMMSS --dry-run
```

## Backup Monitoring

### Health Checks

```bash
# Daily backup health check
python manage.py monitor_backups status

# Check for backup failures
python manage.py monitor_backups status | grep -i "failed\|error"

# Validate backup integrity
python manage.py monitor_backups validate
```

### Automated Alerts

Configure alerts for:
- Backup failures
- Missing backups (> 24 hours old)
- Storage space issues
- Validation failures

```bash
# Configure email alerts
python manage.py monitor_backups schedule --email-alerts admin@rxdoctor.com --max-age-days 1
```

### Monitoring Dashboard

Create monitoring dashboard with:
- Backup success/failure rates
- Backup sizes and trends
- Storage utilization
- Recovery time metrics

## Backup Cleanup

### Automated Cleanup

```bash
# Clean up old backups (30-day retention)
python manage.py monitor_backups cleanup --retention-days 30

# Clean up with custom retention
python manage.py backup_clinical_data --retention-days 14
```

### Manual Cleanup

```bash
# List old backups
find clinical_backups/ -name "clinical_backup_*" -mtime +30

# Remove old backups
find clinical_backups/ -name "clinical_backup_*" -mtime +30 -delete

# Clean up failed backups
find clinical_backups/ -name "*_failed" -delete
```

## Backup Security

### Encryption

```bash
# Enable backup encryption (when implemented)
python manage.py backup_clinical_data --encrypt --backup-type full

# Manual encryption with GPG
gpg --symmetric --cipher-algo AES256 backup_file.tar.gz
```

### Access Control

- Restrict backup directory permissions
- Use service accounts for automated backups
- Implement backup access logging
- Regular security audits

### Compliance

- HIPAA compliance for healthcare data
- Data retention policies
- Audit trail maintenance
- Secure disposal of old backups

## Troubleshooting

### Common Issues

1. **Backup Fails with "Disk Full" Error**
   ```bash
   # Check disk space
   df -h
   
   # Clean up old backups
   python manage.py monitor_backups cleanup --retention-days 7
   
   # Use compression
   python manage.py backup_clinical_data --compress
   ```

2. **Database Backup Fails**
   ```bash
   # Check database connectivity
   python manage.py dbshell
   
   # Check PostgreSQL service
   pg_isready -h localhost -p 5432
   
   # Use Django backup as fallback
   python manage.py dumpdata > django_backup.json
   ```

3. **File Backup Incomplete**
   ```bash
   # Check file permissions
   ls -la media/clinical_documents/
   
   # Check for locked files
   lsof +D media/clinical_documents/
   
   # Retry with force option
   python manage.py backup_clinical_data --backup-type files-only --force
   ```

4. **Restore Fails**
   ```bash
   # Validate backup first
   python manage.py monitor_backups validate
   
   # Check target system space
   df -h
   
   # Use dry-run to test
   python manage.py restore_clinical_data backup_path --dry-run
   ```

### Log Analysis

```bash
# Check backup logs
tail -f logs/backup.log

# Search for errors
grep -i error logs/backup.log

# Monitor backup progress
tail -f logs/backup.log | grep -i "progress\|completed\|failed"
```

## Performance Optimization

### Backup Performance

1. **Parallel Processing**
   - Use multiple threads for file backup
   - Parallel database dump (if supported)
   - Concurrent compression

2. **Incremental Backups**
   - Only backup changed files
   - Use file modification timestamps
   - Database change tracking

3. **Compression**
   - Enable compression for large files
   - Use appropriate compression levels
   - Balance compression vs. speed

### Storage Optimization

1. **Deduplication**
   - Identify duplicate files
   - Use hard links for identical files
   - Implement file-level deduplication

2. **Compression Strategies**
   - Different compression for different file types
   - Adaptive compression based on file size
   - Pre-compression analysis

## Backup Testing

### Test Schedule

- **Daily**: Backup completion verification
- **Weekly**: Backup validation and integrity checks
- **Monthly**: Partial restore testing
- **Quarterly**: Full disaster recovery drill

### Test Procedures

1. **Backup Integrity Test**
   ```bash
   python manage.py monitor_backups validate
   ```

2. **Restore Test**
   ```bash
   # Test restore to staging environment
   python manage.py restore_clinical_data backup_path --dry-run
   ```

3. **Performance Test**
   ```bash
   # Measure backup time and size
   time python manage.py backup_clinical_data --backup-type full
   ```

## Documentation and Reporting

### Backup Reports

Generate regular reports including:
- Backup success/failure rates
- Storage utilization trends
- Recovery time objectives
- Compliance status

```bash
# Generate backup status report
python manage.py monitor_backups status > backup_report_$(date +%Y%m%d).txt
```

### Change Management

- Document all backup procedure changes
- Version control for backup scripts
- Change approval process
- Impact assessment for modifications

## Contact Information

For backup-related issues:

- **Primary**: System Administrator (admin@rxdoctor.com)
- **Secondary**: Database Administrator (dba@rxdoctor.com)
- **Emergency**: On-call Support (+1-XXX-XXX-XXXX)

---

**Document Version**: 1.0  
**Last Updated**: $(date +%Y-%m-%d)  
**Next Review Date**: $(date -d "+3 months" +%Y-%m-%d)  
**Owner**: System Administration Team