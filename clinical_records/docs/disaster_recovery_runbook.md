# Clinical Records Disaster Recovery Runbook

## Overview

This runbook provides step-by-step procedures for recovering the RxDoctor Clinical Records Management system from various disaster scenarios. It covers database failures, file storage corruption, system outages, and complete system recovery.

## Emergency Contacts

- **System Administrator**: admin@rxdoctor.com
- **Database Administrator**: dba@rxdoctor.com  
- **Infrastructure Team**: infra@rxdoctor.com
- **On-call Support**: +1-XXX-XXX-XXXX

## Severity Levels

### Critical (P1)
- Complete system outage
- Data corruption affecting patient safety
- Security breach with data exposure
- **Response Time**: Immediate (< 15 minutes)

### High (P2)
- Partial system outage
- Performance degradation affecting operations
- Backup system failures
- **Response Time**: < 1 hour

### Medium (P3)
- Non-critical feature failures
- Monitoring alerts
- Scheduled maintenance issues
- **Response Time**: < 4 hours

## Pre-Recovery Checklist

Before starting any recovery procedure:

1. **Assess the Situation**
   - [ ] Identify the scope and impact of the issue
   - [ ] Determine if this is a planned or unplanned outage
   - [ ] Check if other systems are affected

2. **Communication**
   - [ ] Notify stakeholders about the incident
   - [ ] Set up communication channels for updates
   - [ ] Document the incident start time

3. **Safety Checks**
   - [ ] Ensure no ongoing data corruption
   - [ ] Stop any processes that might worsen the situation
   - [ ] Create emergency backup if possible

## Recovery Procedures

### 1. Database Recovery

#### 1.1 Database Connection Issues

**Symptoms**: Application cannot connect to database, connection timeouts

**Quick Diagnosis**:
```bash
# Check database connectivity
python manage.py disaster_recovery health-check

# Check database process
pg_isready -h localhost -p 5432
```

**Recovery Steps**:
1. Check database service status
   ```bash
   # Windows
   sc query postgresql-x64-13
   
   # Linux
   systemctl status postgresql
   ```

2. Restart database service if needed
   ```bash
   # Windows
   sc stop postgresql-x64-13
   sc start postgresql-x64-13
   
   # Linux
   sudo systemctl restart postgresql
   ```

3. Verify connection
   ```bash
   python manage.py disaster_recovery health-check
   ```

**Estimated Recovery Time**: 5-15 minutes

#### 1.2 Database Corruption

**Symptoms**: Database errors, data inconsistency, failed queries

**Recovery Steps**:
1. **Immediate Actions**
   ```bash
   # Stop application to prevent further corruption
   # Create emergency backup if possible
   python manage.py backup_clinical_data --backup-type emergency
   ```

2. **Assess Corruption**
   ```bash
   # Check database integrity
   psql -d rxdoctor1 -c "SELECT pg_database_size('rxdoctor1');"
   psql -d rxdoctor1 -c "VACUUM ANALYZE;"
   ```

3. **Restore from Backup**
   ```bash
   # Find latest good backup
   python manage.py monitor_backups status
   
   # Restore database
   python manage.py disaster_recovery emergency-restore --backup-source /path/to/backup
   ```

**Estimated Recovery Time**: 30-60 minutes

#### 1.3 Complete Database Loss

**Symptoms**: Database files missing, cannot start database service

**Recovery Steps**:
1. **Emergency Response**
   ```bash
   # Notify all stakeholders immediately
   # Stop all application services
   ```

2. **Restore Database**
   ```bash
   # Find latest backup
   ls -la clinical_backups/
   
   # Restore complete database
   python manage.py restore_clinical_data clinical_backups/clinical_backup_YYYYMMDD_HHMMSS --restore-type database-only
   ```

3. **Verify Restoration**
   ```bash
   python manage.py disaster_recovery health-check
   ```

**Estimated Recovery Time**: 45-90 minutes

### 2. File Storage Recovery

#### 2.1 File Access Issues

**Symptoms**: Cannot read/write files, permission errors

**Quick Diagnosis**:
```bash
# Check file system permissions
ls -la /path/to/media/root/

# Check disk space
df -h /path/to/media/root/

# Test file operations
python manage.py disaster_recovery health-check
```

**Recovery Steps**:
1. **Check Disk Space**
   ```bash
   # Free up space if needed
   python manage.py monitor_backups cleanup --retention-days 7
   ```

2. **Fix Permissions**
   ```bash
   # Linux
   sudo chown -R www-data:www-data /path/to/media/root/
   sudo chmod -R 755 /path/to/media/root/
   
   # Windows
   # Use File Explorer to set appropriate permissions
   ```

3. **Verify Access**
   ```bash
   python manage.py disaster_recovery health-check
   ```

**Estimated Recovery Time**: 10-30 minutes

#### 2.2 File Corruption or Loss

**Symptoms**: Files cannot be opened, checksum mismatches, missing files

**Recovery Steps**:
1. **Assess Damage**
   ```bash
   # Check file integrity
   python manage.py disaster_recovery health-check
   ```

2. **Restore Files**
   ```bash
   # Restore from latest backup
   python manage.py restore_clinical_data clinical_backups/clinical_backup_YYYYMMDD_HHMMSS --restore-type files-only
   ```

3. **Verify Restoration**
   ```bash
   # Validate restored files
   python manage.py monitor_backups validate
   ```

**Estimated Recovery Time**: 30-120 minutes (depending on file volume)

### 3. Application Recovery

#### 3.1 Application Crashes

**Symptoms**: HTTP 500 errors, application won't start, memory errors

**Quick Diagnosis**:
```bash
# Check application logs
tail -f logs/django.log

# Check system resources
python manage.py disaster_recovery health-check
```

**Recovery Steps**:
1. **Restart Application**
   ```bash
   # Stop application
   pkill -f "python manage.py runserver"
   
   # Clear cache
   python manage.py shell -c "from django.core.cache import cache; cache.clear()"
   
   # Restart application
   python manage.py runserver
   ```

2. **Check Dependencies**
   ```bash
   # Verify database connection
   python manage.py dbshell
   
   # Check background jobs
   python manage.py qmonitor
   ```

**Estimated Recovery Time**: 5-15 minutes

#### 3.2 Performance Issues

**Symptoms**: Slow response times, timeouts, high resource usage

**Recovery Steps**:
1. **Immediate Relief**
   ```bash
   # Clear cache
   python manage.py shell -c "from django.core.cache import cache; cache.clear()"
   
   # Restart background workers
   python manage.py qcluster --stop
   python manage.py qcluster
   ```

2. **Resource Optimization**
   ```bash
   # Check system resources
   python manage.py disaster_recovery health-check
   
   # Clean temporary files
   find /tmp -name "*.tmp" -mtime +1 -delete
   ```

**Estimated Recovery Time**: 15-30 minutes

### 4. Complete System Recovery

#### 4.1 Full System Restore

**Use Case**: Complete server failure, data center outage, major corruption

**Recovery Steps**:

1. **Preparation** (5-10 minutes)
   ```bash
   # Set up new server/environment
   # Install required software (Python, PostgreSQL, etc.)
   # Clone application code
   git clone <repository_url>
   cd RxBackend
   ```

2. **Environment Setup** (10-15 minutes)
   ```bash
   # Create virtual environment
   python -m venv my_env
   my_env\Scripts\activate  # Windows
   # source my_env/bin/activate  # Linux
   
   # Install dependencies
   pip install -r requirements.txt
   
   # Configure environment variables
   cp .env.example .env
   # Edit .env with appropriate values
   ```

3. **Database Restoration** (20-45 minutes)
   ```bash
   # Create database
   createdb rxdoctor1
   
   # Restore from backup
   python manage.py restore_clinical_data /path/to/backup/clinical_backup_YYYYMMDD_HHMMSS
   ```

4. **File Restoration** (15-60 minutes)
   ```bash
   # Files are restored as part of the full restore above
   # Verify file access
   python manage.py disaster_recovery health-check
   ```

5. **Application Startup** (5-10 minutes)
   ```bash
   # Run migrations (if needed)
   python manage.py migrate
   
   # Collect static files
   python manage.py collectstatic --noinput
   
   # Start application
   python manage.py runserver
   
   # Start background workers
   python manage.py qcluster
   ```

6. **Verification** (10-15 minutes)
   ```bash
   # Comprehensive health check
   python manage.py disaster_recovery health-check
   
   # Validate data integrity
   python manage.py monitor_backups validate
   
   # Test critical functionality
   # - User login
   # - Document upload
   # - Document retrieval
   # - FHIR export
   ```

**Total Estimated Recovery Time**: 65-155 minutes

## Post-Recovery Procedures

### 1. Verification Checklist

After any recovery procedure:

- [ ] **System Health Check**
  ```bash
  python manage.py disaster_recovery health-check
  ```

- [ ] **Data Integrity Verification**
  ```bash
  python manage.py monitor_backups validate
  ```

- [ ] **Functional Testing**
  - [ ] User authentication works
  - [ ] Document upload/download works
  - [ ] Database queries execute properly
  - [ ] Background jobs are processing
  - [ ] FHIR exports function correctly

- [ ] **Performance Verification**
  - [ ] Response times are acceptable
  - [ ] System resources are normal
  - [ ] No error messages in logs

### 2. Communication

- [ ] Notify stakeholders that system is restored
- [ ] Update status page/communication channels
- [ ] Schedule post-incident review meeting

### 3. Documentation

- [ ] Document what caused the incident
- [ ] Record recovery steps taken
- [ ] Note any deviations from this runbook
- [ ] Update runbook if needed

## Backup Verification

### Daily Backup Checks

```bash
# Check backup status
python manage.py monitor_backups status

# Validate recent backups
python manage.py monitor_backups validate
```

### Weekly Backup Tests

```bash
# Perform test restore (to test environment)
python manage.py restore_clinical_data /path/to/backup --dry-run

# Test disaster recovery procedures
python manage.py disaster_recovery failover-test
```

### Monthly Backup Audits

```bash
# Generate backup report
python manage.py monitor_backups status > backup_report_$(date +%Y%m%d).txt

# Review backup retention policy
python manage.py monitor_backups cleanup --retention-days 30
```

## Monitoring and Alerting

### Automated Monitoring

Set up automated monitoring for:

- Database connectivity and performance
- File system health and space
- Application response times
- Backup success/failure
- System resource utilization

### Alert Configuration

```bash
# Set up backup monitoring with alerts
python manage.py monitor_backups schedule --email-alerts admin@rxdoctor.com,dba@rxdoctor.com

# Test alert system
python manage.py monitor_backups alert-test
```

## Escalation Procedures

### Level 1: Automated Response
- Automated monitoring detects issue
- System attempts self-healing
- Alerts sent to on-call team

### Level 2: On-Call Response
- On-call engineer investigates
- Follows appropriate recovery procedure
- Escalates if needed

### Level 3: Team Response
- Multiple team members involved
- Management notified
- External resources engaged if needed

### Level 4: Executive Response
- C-level executives involved
- External vendors/consultants engaged
- Public communication may be required

## Recovery Time Objectives (RTO)

| Scenario | Target RTO | Maximum RTO |
|----------|------------|-------------|
| Database connection issues | 15 minutes | 30 minutes |
| Application restart | 10 minutes | 20 minutes |
| File system issues | 30 minutes | 60 minutes |
| Database corruption | 60 minutes | 120 minutes |
| Complete system failure | 120 minutes | 240 minutes |

## Recovery Point Objectives (RPO)

| Data Type | Target RPO | Maximum RPO |
|-----------|------------|-------------|
| Clinical records | 4 hours | 24 hours |
| Document files | 4 hours | 24 hours |
| System configuration | 24 hours | 72 hours |
| User data | 4 hours | 24 hours |

## Testing Schedule

### Monthly Tests
- [ ] Backup restoration test
- [ ] Database failover test
- [ ] Application recovery test

### Quarterly Tests
- [ ] Complete system recovery test
- [ ] Disaster recovery drill
- [ ] Runbook review and update

### Annual Tests
- [ ] Full disaster simulation
- [ ] Third-party recovery service test
- [ ] Business continuity plan review

## Lessons Learned Template

After each incident, document:

1. **Incident Summary**
   - What happened?
   - When did it happen?
   - How long did it last?

2. **Root Cause Analysis**
   - What was the underlying cause?
   - What factors contributed?
   - Could it have been prevented?

3. **Response Evaluation**
   - What went well?
   - What could be improved?
   - Were procedures followed correctly?

4. **Action Items**
   - Process improvements
   - Technology changes
   - Training needs
   - Runbook updates

## Contact Information

For questions about this runbook or disaster recovery procedures:

- **Primary Contact**: System Administrator (admin@rxdoctor.com)
- **Secondary Contact**: Infrastructure Team (infra@rxdoctor.com)
- **Emergency Contact**: On-call Support (+1-XXX-XXX-XXXX)

---

**Document Version**: 1.0  
**Last Updated**: $(date +%Y-%m-%d)  
**Next Review Date**: $(date -d "+3 months" +%Y-%m-%d)  
**Owner**: System Administration Team