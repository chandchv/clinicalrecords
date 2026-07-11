#!/usr/bin/env python
"""
Migration script to convert Clinical Records Service from SQLite to PostgreSQL
"""
import os
import sys
import django
import sqlite3
import psycopg2
from psycopg2.extras import RealDictCursor
import json
from datetime import datetime
import logging

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'clinical_records_api.settings')
django.setup()

from django.conf import settings
from django.core.management import execute_from_command_line
from clinical_records.models import (
    ClinicalRecord, ClinicalDocument, ImagingStudy, 
    RecordRelationship, ShareToken, ManualReview, ReviewerProfile
)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('migration.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class ClinicalRecordsMigrator:
    """
    Migrator class to handle SQLite to PostgreSQL migration
    """
    
    def __init__(self):
        self.sqlite_db_path = 'db.sqlite3'
        self.pg_config = settings.DATABASES['default']
        self.migration_stats = {
            'clinical_records': 0,
            'clinical_documents': 0,
            'imaging_studies': 0,
            'record_relationships': 0,
            'share_tokens': 0,
            'manual_reviews': 0,
            'reviewer_profiles': 0,
            'errors': []
        }
    
    def check_prerequisites(self):
        """
        Check if prerequisites are met for migration
        """
        logger.info("Checking migration prerequisites...")
        
        # Check if SQLite database exists
        if not os.path.exists(self.sqlite_db_path):
            logger.error(f"SQLite database not found: {self.sqlite_db_path}")
            return False
        
        # Check PostgreSQL connection
        try:
            conn = psycopg2.connect(
                host=self.pg_config['HOST'],
                port=self.pg_config['PORT'],
                database='postgres',  # Connect to default database first
                user=self.pg_config['USER'],
                password=self.pg_config['PASSWORD']
            )
            conn.close()
            logger.info("PostgreSQL connection successful")
        except Exception as e:
            logger.error(f"PostgreSQL connection failed: {e}")
            return False
        
        return True
    
    def create_postgresql_database(self):
        """
        Create the PostgreSQL database if it doesn't exist
        """
        logger.info("Creating PostgreSQL database...")
        
        try:
            # Connect to default postgres database
            conn = psycopg2.connect(
                host=self.pg_config['HOST'],
                port=self.pg_config['PORT'],
                database='postgres',
                user=self.pg_config['USER'],
                password=self.pg_config['PASSWORD']
            )
            conn.autocommit = True
            cursor = conn.cursor()
            
            # Check if database exists
            cursor.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s",
                (self.pg_config['NAME'],)
            )
            
            if not cursor.fetchone():
                # Create database
                cursor.execute(f"CREATE DATABASE {self.pg_config['NAME']}")
                logger.info(f"Created database: {self.pg_config['NAME']}")
            else:
                logger.info(f"Database already exists: {self.pg_config['NAME']}")
            
            cursor.close()
            conn.close()
            
        except Exception as e:
            logger.error(f"Error creating PostgreSQL database: {e}")
            raise
    
    def run_django_migrations(self):
        """
        Run Django migrations to create tables in PostgreSQL
        """
        logger.info("Running Django migrations...")
        
        try:
            # Make migrations
            execute_from_command_line(['manage.py', 'makemigrations'])
            
            # Apply migrations
            execute_from_command_line(['manage.py', 'migrate'])
            
            logger.info("Django migrations completed successfully")
            
        except Exception as e:
            logger.error(f"Error running Django migrations: {e}")
            raise
    
    def backup_sqlite_data(self):
        """
        Create a backup of SQLite data
        """
        logger.info("Creating SQLite data backup...")
        
        try:
            backup_file = f"sqlite_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sql"
            
            # Create SQL dump of SQLite database
            with open(backup_file, 'w') as f:
                conn = sqlite3.connect(self.sqlite_db_path)
                for line in conn.iterdump():
                    f.write(f"{line}\n")
                conn.close()
            
            logger.info(f"SQLite backup created: {backup_file}")
            return backup_file
            
        except Exception as e:
            logger.error(f"Error creating SQLite backup: {e}")
            raise
    
    def migrate_data(self):
        """
        Migrate data from SQLite to PostgreSQL
        """
        logger.info("Starting data migration...")
        
        try:
            # Connect to SQLite
            sqlite_conn = sqlite3.connect(self.sqlite_db_path)
            sqlite_conn.row_factory = sqlite3.Row
            sqlite_cursor = sqlite_conn.cursor()
            
            # Migrate each table
            self._migrate_clinical_records(sqlite_cursor)
            self._migrate_clinical_documents(sqlite_cursor)
            self._migrate_imaging_studies(sqlite_cursor)
            self._migrate_record_relationships(sqlite_cursor)
            self._migrate_share_tokens(sqlite_cursor)
            self._migrate_manual_reviews(sqlite_cursor)
            self._migrate_reviewer_profiles(sqlite_cursor)
            
            sqlite_conn.close()
            
            logger.info("Data migration completed successfully")
            
        except Exception as e:
            logger.error(f"Error during data migration: {e}")
            self.migration_stats['errors'].append(str(e))
            raise
    
    def _migrate_clinical_records(self, cursor):
        """
        Migrate clinical records
        """
        logger.info("Migrating clinical records...")
        
        try:
            cursor.execute("SELECT * FROM clinical_records")
            records = cursor.fetchall()
            
            for record in records:
                try:
                    ClinicalRecord.objects.create(
                        id=record['id'],
                        title=record['title'],
                        description=record['description'] or '',
                        record_type=record['record_type'],
                        status=record['status'],
                        priority=record['priority'],
                        is_active=bool(record['is_active']),
                        is_confidential=bool(record['is_confidential']),
                        record_date=record['record_date'],
                        created_at=record['created_at'],
                        updated_at=record['updated_at'],
                        created_by_id=record['created_by_id'],
                        tenant_id=record.get('tenant_id', 1)
                    )
                    self.migration_stats['clinical_records'] += 1
                    
                except Exception as e:
                    error_msg = f"Error migrating clinical record {record['id']}: {e}"
                    logger.error(error_msg)
                    self.migration_stats['errors'].append(error_msg)
            
            logger.info(f"Migrated {self.migration_stats['clinical_records']} clinical records")
            
        except Exception as e:
            logger.error(f"Error migrating clinical records: {e}")
            raise
    
    def _migrate_clinical_documents(self, cursor):
        """
        Migrate clinical documents
        """
        logger.info("Migrating clinical documents...")
        
        try:
            cursor.execute("SELECT * FROM clinical_documents")
            documents = cursor.fetchall()
            
            for doc in documents:
                try:
                    ClinicalDocument.objects.create(
                        id=doc['id'],
                        clinical_record_id=doc['clinical_record_id'],
                        title=doc['title'],
                        file_path=doc['file_path'],
                        file_type=doc['file_type'],
                        file_size=doc['file_size'],
                        mime_type=doc['mime_type'],
                        is_encrypted=bool(doc['is_encrypted']),
                        is_processed=bool(doc['is_processed']),
                        created_at=doc['created_at'],
                        updated_at=doc['updated_at'],
                        created_by_id=doc['created_by_id'],
                        tenant_id=doc.get('tenant_id', 1)
                    )
                    self.migration_stats['clinical_documents'] += 1
                    
                except Exception as e:
                    error_msg = f"Error migrating clinical document {doc['id']}: {e}"
                    logger.error(error_msg)
                    self.migration_stats['errors'].append(error_msg)
            
            logger.info(f"Migrated {self.migration_stats['clinical_documents']} clinical documents")
            
        except Exception as e:
            logger.error(f"Error migrating clinical documents: {e}")
            raise
    
    def _migrate_imaging_studies(self, cursor):
        """
        Migrate imaging studies
        """
        logger.info("Migrating imaging studies...")
        
        try:
            cursor.execute("SELECT * FROM imaging_studies")
            studies = cursor.fetchall()
            
            for study in studies:
                try:
                    ImagingStudy.objects.create(
                        id=study['id'],
                        clinical_record_id=study['clinical_record_id'],
                        study_type=study['study_type'],
                        modality=study['modality'],
                        study_date=study['study_date'],
                        study_description=study['study_description'] or '',
                        created_at=study['created_at'],
                        tenant_id=study.get('tenant_id', 1)
                    )
                    self.migration_stats['imaging_studies'] += 1
                    
                except Exception as e:
                    error_msg = f"Error migrating imaging study {study['id']}: {e}"
                    logger.error(error_msg)
                    self.migration_stats['errors'].append(error_msg)
            
            logger.info(f"Migrated {self.migration_stats['imaging_studies']} imaging studies")
            
        except Exception as e:
            logger.error(f"Error migrating imaging studies: {e}")
            raise
    
    def _migrate_record_relationships(self, cursor):
        """
        Migrate record relationships
        """
        logger.info("Migrating record relationships...")
        
        try:
            cursor.execute("SELECT * FROM record_relationships")
            relationships = cursor.fetchall()
            
            for rel in relationships:
                try:
                    RecordRelationship.objects.create(
                        id=rel['id'],
                        source_record_id=rel['source_record_id'],
                        target_record_id=rel['target_record_id'],
                        relationship_type=rel['relationship_type'],
                        description=rel['description'] or '',
                        created_at=rel['created_at'],
                        created_by_id=rel['created_by_id'],
                        tenant_id=rel.get('tenant_id', 1)
                    )
                    self.migration_stats['record_relationships'] += 1
                    
                except Exception as e:
                    error_msg = f"Error migrating record relationship {rel['id']}: {e}"
                    logger.error(error_msg)
                    self.migration_stats['errors'].append(error_msg)
            
            logger.info(f"Migrated {self.migration_stats['record_relationships']} record relationships")
            
        except Exception as e:
            logger.error(f"Error migrating record relationships: {e}")
            raise
    
    def _migrate_share_tokens(self, cursor):
        """
        Migrate share tokens
        """
        logger.info("Migrating share tokens...")
        
        try:
            cursor.execute("SELECT * FROM share_tokens")
            tokens = cursor.fetchall()
            
            for token in tokens:
                try:
                    ShareToken.objects.create(
                        id=token['id'],
                        clinical_record_id=token['clinical_record_id'],
                        token=token['token'],
                        expires_at=token['expires_at'],
                        is_active=bool(token['is_active']),
                        access_count=token['access_count'],
                        created_at=token['created_at'],
                        created_by_id=token['created_by_id'],
                        tenant_id=token.get('tenant_id', 1)
                    )
                    self.migration_stats['share_tokens'] += 1
                    
                except Exception as e:
                    error_msg = f"Error migrating share token {token['id']}: {e}"
                    logger.error(error_msg)
                    self.migration_stats['errors'].append(error_msg)
            
            logger.info(f"Migrated {self.migration_stats['share_tokens']} share tokens")
            
        except Exception as e:
            logger.error(f"Error migrating share tokens: {e}")
            raise
    
    def _migrate_manual_reviews(self, cursor):
        """
        Migrate manual reviews
        """
        logger.info("Migrating manual reviews...")
        
        try:
            cursor.execute("SELECT * FROM manual_reviews")
            reviews = cursor.fetchall()
            
            for review in reviews:
                try:
                    ManualReview.objects.create(
                        id=review['id'],
                        clinical_record_id=review['clinical_record_id'],
                        reviewer_id=review['reviewer_id'],
                        status=review['status'],
                        priority=review['priority'],
                        assigned_at=review['assigned_at'],
                        completed_at=review['completed_at'],
                        notes=review['notes'] or '',
                        tenant_id=review.get('tenant_id', 1)
                    )
                    self.migration_stats['manual_reviews'] += 1
                    
                except Exception as e:
                    error_msg = f"Error migrating manual review {review['id']}: {e}"
                    logger.error(error_msg)
                    self.migration_stats['errors'].append(error_msg)
            
            logger.info(f"Migrated {self.migration_stats['manual_reviews']} manual reviews")
            
        except Exception as e:
            logger.error(f"Error migrating manual reviews: {e}")
            raise
    
    def _migrate_reviewer_profiles(self, cursor):
        """
        Migrate reviewer profiles
        """
        logger.info("Migrating reviewer profiles...")
        
        try:
            cursor.execute("SELECT * FROM reviewer_profiles")
            profiles = cursor.fetchall()
            
            for profile in profiles:
                try:
                    ReviewerProfile.objects.create(
                        id=profile['id'],
                        user_id=profile['user_id'],
                        specialization=profile['specialization'],
                        max_daily_reviews=profile['max_daily_reviews'],
                        is_active=bool(profile['is_active']),
                        created_at=profile['created_at'],
                        tenant_id=profile.get('tenant_id', 1)
                    )
                    self.migration_stats['reviewer_profiles'] += 1
                    
                except Exception as e:
                    error_msg = f"Error migrating reviewer profile {profile['id']}: {e}"
                    logger.error(error_msg)
                    self.migration_stats['errors'].append(error_msg)
            
            logger.info(f"Migrated {self.migration_stats['reviewer_profiles']} reviewer profiles")
            
        except Exception as e:
            logger.error(f"Error migrating reviewer profiles: {e}")
            raise
    
    def print_migration_summary(self):
        """
        Print migration summary
        """
        logger.info("\n" + "="*50)
        logger.info("MIGRATION SUMMARY")
        logger.info("="*50)
        
        for table, count in self.migration_stats.items():
            if table != 'errors':
                logger.info(f"{table}: {count} records migrated")
        
        if self.migration_stats['errors']:
            logger.info(f"\nErrors encountered: {len(self.migration_stats['errors'])}")
            for error in self.migration_stats['errors'][:10]:  # Show first 10 errors
                logger.error(f"  - {error}")
            
            if len(self.migration_stats['errors']) > 10:
                logger.info(f"  ... and {len(self.migration_stats['errors']) - 10} more errors")
        else:
            logger.info("\nNo errors encountered during migration!")
        
        logger.info("="*50)
    
    def run_migration(self):
        """
        Run the complete migration process
        """
        logger.info("Starting Clinical Records Service migration from SQLite to PostgreSQL")
        
        try:
            # Check prerequisites
            if not self.check_prerequisites():
                logger.error("Prerequisites not met. Aborting migration.")
                return False
            
            # Create PostgreSQL database
            self.create_postgresql_database()
            
            # Backup SQLite data
            backup_file = self.backup_sqlite_data()
            
            # Run Django migrations
            self.run_django_migrations()
            
            # Migrate data
            self.migrate_data()
            
            # Print summary
            self.print_migration_summary()
            
            logger.info("Migration completed successfully!")
            return True
            
        except Exception as e:
            logger.error(f"Migration failed: {e}")
            return False


def main():
    """
    Main function to run the migration
    """
    migrator = ClinicalRecordsMigrator()
    success = migrator.run_migration()
    
    if success:
        print("\nMigration completed successfully!")
        print("You can now start the Clinical Records Service with PostgreSQL.")
    else:
        print("\nMigration failed. Please check the logs for details.")
        sys.exit(1)


if __name__ == '__main__':
    main()