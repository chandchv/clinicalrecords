"""
Management command to set up and manage Elasticsearch for clinical records search.
"""

import os
import json
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from clinical_records.services.elasticsearch_service import elasticsearch_service
from clinical_records.config.elasticsearch_config import get_elasticsearch_config, is_elasticsearch_enabled
from clinical_records.signals.elasticsearch_signals import (
    setup_elasticsearch_indices,
    bulk_sync_to_elasticsearch,
    check_elasticsearch_health
)


class Command(BaseCommand):
    help = 'Set up and manage Elasticsearch for clinical records search'

    def add_arguments(self, parser):
        parser.add_argument(
            '--setup',
            action='store_true',
            help='Set up Elasticsearch indices and mappings',
        )
        parser.add_argument(
            '--status',
            action='store_true',
            help='Show Elasticsearch configuration and health status',
        )
        parser.add_argument(
            '--reindex',
            action='store_true',
            help='Reindex all clinical records and documents',
        )
        parser.add_argument(
            '--clinic-id',
            type=str,
            help='Clinic ID for clinic-specific operations',
        )
        parser.add_argument(
            '--test-search',
            type=str,
            help='Test search functionality with given query',
        )
        parser.add_argument(
            '--configure',
            action='store_true',
            help='Configure Elasticsearch settings interactively',
        )
        parser.add_argument(
            '--enable',
            action='store_true',
            help='Enable Elasticsearch service',
        )
        parser.add_argument(
            '--disable',
            action='store_true',
            help='Disable Elasticsearch service',
        )
        parser.add_argument(
            '--delete-indices',
            action='store_true',
            help='Delete all Elasticsearch indices (WARNING: This will delete all search data)',
        )

    def handle(self, *args, **options):
        """Handle the management command."""
        
        if options['status']:
            self.show_status()
        elif options['setup']:
            self.setup_elasticsearch()
        elif options['configure']:
            self.configure_elasticsearch()
        elif options['reindex']:
            self.reindex_data(options.get('clinic_id'))
        elif options['test_search']:
            self.test_search(options['test_search'], options.get('clinic_id'))
        elif options['enable']:
            self.enable_elasticsearch()
        elif options['disable']:
            self.disable_elasticsearch()
        elif options['delete_indices']:
            self.delete_indices()
        else:
            self.show_help()

    def show_status(self):
        """Show current Elasticsearch configuration and health status."""
        self.stdout.write(self.style.SUCCESS('Elasticsearch Configuration Status'))
        self.stdout.write('=' * 50)
        
        config = get_elasticsearch_config()
        
        # Basic configuration
        self.stdout.write(f"Elasticsearch Enabled: {config['ELASTICSEARCH_ENABLED']}")
        
        if config['ELASTICSEARCH_DSL']:
            hosts = config['ELASTICSEARCH_DSL']['default'].get('hosts', [])
            self.stdout.write(f"Elasticsearch Hosts: {', '.join(hosts)}")
        
        self.stdout.write(f"Index Prefix: {config['ELASTICSEARCH_INDEX_PREFIX']}")
        self.stdout.write(f"Auto Sync: {config['ELASTICSEARCH_AUTO_SYNC']}")
        self.stdout.write(f"Auto Create Index: {config['ELASTICSEARCH_AUTO_CREATE_INDEX']}")
        
        # Service status
        self.stdout.write(f"\nService Status:")
        self.stdout.write(f"Service Enabled: {elasticsearch_service.is_enabled()}")
        
        if elasticsearch_service.is_enabled():
            # Health check
            health_status = check_elasticsearch_health()
            
            if health_status['status'] == 'healthy':
                self.stdout.write(self.style.SUCCESS("✓ Elasticsearch is healthy"))
                self.stdout.write(f"Cluster Name: {health_status['cluster_name']}")
                self.stdout.write(f"Cluster Status: {health_status['cluster_status']}")
                self.stdout.write(f"Number of Nodes: {health_status['number_of_nodes']}")
                self.stdout.write(f"Active Shards: {health_status['active_shards']}")
                
                # Indices information
                if 'indices' in health_status:
                    self.stdout.write(f"\nIndices Status:")
                    for index_type, info in health_status['indices'].items():
                        if info.get('exists'):
                            self.stdout.write(f"{index_type.title()}: {info['doc_count']} documents, {info['size']} bytes")
                        else:
                            self.stdout.write(f"{index_type.title()}: Not created")
            else:
                self.stdout.write(self.style.ERROR(f"✗ Elasticsearch health check failed: {health_status.get('message', 'Unknown error')}"))
        else:
            self.stdout.write(self.style.WARNING("Elasticsearch service is not enabled or not configured"))
        
        # Performance settings
        self.stdout.write(f"\nPerformance Settings:")
        self.stdout.write(f"Default Page Size: {config['ELASTICSEARCH_DEFAULT_PAGE_SIZE']}")
        self.stdout.write(f"Max Page Size: {config['ELASTICSEARCH_MAX_PAGE_SIZE']}")
        self.stdout.write(f"Search Timeout: {config['ELASTICSEARCH_SEARCH_TIMEOUT']}s")
        self.stdout.write(f"Bulk Chunk Size: {config['ELASTICSEARCH_BULK_CHUNK_SIZE']}")

    def setup_elasticsearch(self):
        """Set up Elasticsearch indices and mappings."""
        self.stdout.write(self.style.SUCCESS('Setting up Elasticsearch'))
        self.stdout.write('=' * 40)
        
        if not is_elasticsearch_enabled():
            self.stdout.write(self.style.ERROR("Elasticsearch is not enabled. Use --configure to set it up."))
            return
        
        if not elasticsearch_service.is_enabled():
            self.stdout.write(self.style.ERROR("Elasticsearch service is not available. Check your configuration."))
            return
        
        # Set up indices
        self.stdout.write("Creating Elasticsearch indices...")
        result = setup_elasticsearch_indices()
        
        if result['status'] == 'success':
            self.stdout.write(self.style.SUCCESS("✓ Elasticsearch indices created successfully"))
            for index_name, status in result['indices'].items():
                self.stdout.write(f"  {index_name}: {status}")
        else:
            self.stdout.write(self.style.ERROR(f"✗ Failed to create indices: {result.get('message', 'Unknown error')}"))
            return
        
        # Ask if user wants to reindex existing data
        reindex = input("\nReindex existing clinical records and documents? (y/n): ").lower()
        if reindex in ['y', 'yes']:
            self.stdout.write("Reindexing existing data...")
            sync_result = bulk_sync_to_elasticsearch()
            
            if sync_result['status'] == 'success':
                self.stdout.write(self.style.SUCCESS(f"✓ Reindexing completed"))
                self.stdout.write(f"  Records indexed: {sync_result['records_synced']}")
                self.stdout.write(f"  Documents indexed: {sync_result['documents_synced']}")
                if sync_result['errors']:
                    self.stdout.write(self.style.WARNING(f"  Errors: {len(sync_result['errors'])}"))
            else:
                self.stdout.write(self.style.ERROR(f"✗ Reindexing failed: {sync_result.get('message', 'Unknown error')}"))

    def configure_elasticsearch(self):
        """Configure Elasticsearch settings interactively."""
        self.stdout.write(self.style.SUCCESS('Configuring Elasticsearch'))
        self.stdout.write('=' * 40)
        
        # Get current settings
        current_enabled = getattr(settings, 'ELASTICSEARCH_ENABLED', False)
        current_hosts = getattr(settings, 'ELASTICSEARCH_DSL', {}).get('default', {}).get('hosts', ['localhost:9200'])
        
        # Interactive configuration
        enabled = input(f"Enable Elasticsearch? (y/n) [current: {'y' if current_enabled else 'n'}]: ").lower()
        if enabled in ['y', 'yes']:
            enabled = True
        elif enabled in ['n', 'no']:
            enabled = False
        else:
            enabled = current_enabled
        
        if enabled:
            hosts_input = input(f"Elasticsearch hosts (comma-separated) [current: {','.join(current_hosts)}]: ").strip()
            if hosts_input:
                hosts = [h.strip() for h in hosts_input.split(',')]
            else:
                hosts = current_hosts
            
            # Authentication settings
            require_auth = input("Require authentication? (y/n) [n]: ").lower() in ['y', 'yes']
            username = password = None
            
            if require_auth:
                username = input("Username: ").strip()
                password = input("Password: ").strip()
            
            # SSL settings
            use_ssl = input("Use SSL/TLS? (y/n) [n]: ").lower() in ['y', 'yes']
            
            # Index prefix
            index_prefix = input("Index prefix [clinical_records]: ").strip() or 'clinical_records'
            
            # Generate settings
            settings_content = f"""
# Elasticsearch Configuration
ELASTICSEARCH_ENABLED = {enabled}
ELASTICSEARCH_DSL = {{
    'default': {{
        'hosts': {hosts},
        'timeout': 30,
        'max_retries': 3,
        'retry_on_timeout': True,"""
            
            if require_auth and username and password:
                settings_content += f"""
        'http_auth': ('{username}', '{password}'),"""
            
            if use_ssl:
                settings_content += f"""
        'use_ssl': True,
        'verify_certs': True,"""
            
            settings_content += f"""
    }}
}}
ELASTICSEARCH_INDEX_PREFIX = '{index_prefix}'
ELASTICSEARCH_AUTO_SYNC = True
ELASTICSEARCH_AUTO_CREATE_INDEX = True
"""
            
            self.stdout.write("\nGenerated configuration:")
            self.stdout.write(settings_content)
            
            save = input("\nAdd this configuration to your settings? (y/n): ").lower()
            if save in ['y', 'yes']:
                self.stdout.write(self.style.SUCCESS("Please add the above configuration to your Django settings.py file"))
                self.stdout.write("Or set the environment variables:")
                self.stdout.write(f"export ELASTICSEARCH_URL='{hosts[0] if hosts else 'localhost:9200'}'")
                if require_auth:
                    self.stdout.write(f"export ELASTICSEARCH_USERNAME='{username}'")
                    self.stdout.write(f"export ELASTICSEARCH_PASSWORD='{password}'")
        else:
            self.stdout.write("Elasticsearch will be disabled")

    def reindex_data(self, clinic_id=None):
        """Reindex all clinical records and documents."""
        self.stdout.write(self.style.SUCCESS('Reindexing Clinical Records Data'))
        self.stdout.write('=' * 45)
        
        if not elasticsearch_service.is_enabled():
            self.stdout.write(self.style.ERROR("Elasticsearch service is not available"))
            return
        
        if clinic_id:
            self.stdout.write(f"Reindexing data for clinic: {clinic_id}")
        else:
            self.stdout.write("Reindexing all clinical records data...")
        
        # Confirm destructive operation
        confirm = input("This will reindex all data. Continue? (y/n): ").lower()
        if confirm not in ['y', 'yes']:
            self.stdout.write("Operation cancelled")
            return
        
        # Perform reindexing
        result = bulk_sync_to_elasticsearch(clinic_id=clinic_id, force_reindex=True)
        
        if result['status'] == 'success':
            self.stdout.write(self.style.SUCCESS("✓ Reindexing completed successfully"))
            self.stdout.write(f"Records indexed: {result['records_synced']}")
            self.stdout.write(f"Documents indexed: {result['documents_synced']}")
            
            if result['errors']:
                self.stdout.write(self.style.WARNING(f"Errors encountered: {len(result['errors'])}"))
                for error in result['errors'][:5]:  # Show first 5 errors
                    self.stdout.write(f"  - {error}")
                if len(result['errors']) > 5:
                    self.stdout.write(f"  ... and {len(result['errors']) - 5} more errors")
        else:
            self.stdout.write(self.style.ERROR(f"✗ Reindexing failed: {result.get('message', 'Unknown error')}"))

    def test_search(self, query, clinic_id=None):
        """Test search functionality."""
        self.stdout.write(self.style.SUCCESS(f'Testing Search: "{query}"'))
        self.stdout.write('=' * 50)
        
        if not elasticsearch_service.is_enabled():
            self.stdout.write(self.style.ERROR("Elasticsearch service is not available"))
            return
        
        if not clinic_id:
            # Try to get a clinic ID from the database
            from users.models import Clinic
            try:
                clinic = Clinic.objects.first()
                if clinic:
                    clinic_id = str(clinic.id)
                    self.stdout.write(f"Using clinic: {clinic.name} ({clinic_id})")
                else:
                    self.stdout.write(self.style.ERROR("No clinics found in database"))
                    return
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Failed to get clinic: {e}"))
                return
        
        # Test clinical records search
        self.stdout.write("\nTesting clinical records search...")
        try:
            records_result = elasticsearch_service.search_clinical_records(
                query=query,
                clinic_id=clinic_id,
                filters={},
                page=1,
                page_size=5
            )
            
            if records_result['status'] == 'success':
                self.stdout.write(self.style.SUCCESS(f"✓ Found {records_result['total']} clinical records"))
                for i, record in enumerate(records_result['results'][:3], 1):
                    self.stdout.write(f"  {i}. {record.get('title', 'Untitled')} (Score: {record.get('_score', 0):.2f})")
            else:
                self.stdout.write(self.style.ERROR(f"✗ Records search failed: {records_result.get('message', 'Unknown error')}"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"✗ Records search error: {e}"))
        
        # Test document content search
        self.stdout.write("\nTesting document content search...")
        try:
            content_result = elasticsearch_service.search_documents_content(
                query=query,
                clinic_id=clinic_id,
                filters={},
                page=1,
                page_size=5
            )
            
            if content_result['status'] == 'success':
                self.stdout.write(self.style.SUCCESS(f"✓ Found {content_result['total']} documents with matching content"))
                for i, doc in enumerate(content_result['results'][:3], 1):
                    filename = doc.get('original_filename', 'Unknown file')
                    score = doc.get('_score', 0)
                    self.stdout.write(f"  {i}. {filename} (Score: {score:.2f})")
                    
                    # Show highlights if available
                    if '_highlights' in doc:
                        for field, highlights in doc['_highlights'].items():
                            for highlight in highlights[:1]:  # Show first highlight
                                self.stdout.write(f"     Highlight: ...{highlight}...")
            else:
                self.stdout.write(self.style.ERROR(f"✗ Content search failed: {content_result.get('message', 'Unknown error')}"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"✗ Content search error: {e}"))
        
        # Test suggestions
        self.stdout.write("\nTesting search suggestions...")
        try:
            suggestions = elasticsearch_service.get_search_suggestions(
                query=query,
                clinic_id=clinic_id,
                suggestion_type='medications'
            )
            
            if suggestions:
                self.stdout.write(self.style.SUCCESS(f"✓ Found {len(suggestions)} medication suggestions"))
                for suggestion in suggestions[:5]:
                    self.stdout.write(f"  - {suggestion}")
            else:
                self.stdout.write("No medication suggestions found")
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"✗ Suggestions error: {e}"))

    def enable_elasticsearch(self):
        """Enable Elasticsearch service."""
        self.stdout.write("Enabling Elasticsearch service...")
        self.stdout.write(self.style.WARNING("Note: You need to configure Elasticsearch settings in your Django settings"))
        self.stdout.write("Add to settings.py:")
        self.stdout.write("ELASTICSEARCH_ENABLED = True")

    def disable_elasticsearch(self):
        """Disable Elasticsearch service."""
        self.stdout.write("Disabling Elasticsearch service...")
        self.stdout.write("Add to settings.py:")
        self.stdout.write("ELASTICSEARCH_ENABLED = False")

    def delete_indices(self):
        """Delete all Elasticsearch indices."""
        self.stdout.write(self.style.WARNING('Deleting Elasticsearch Indices'))
        self.stdout.write('=' * 40)
        
        if not elasticsearch_service.is_enabled():
            self.stdout.write(self.style.ERROR("Elasticsearch service is not available"))
            return
        
        # Confirm destructive operation
        self.stdout.write(self.style.ERROR("WARNING: This will delete all search indices and data!"))
        confirm = input("Are you sure you want to continue? Type 'DELETE' to confirm: ")
        
        if confirm != 'DELETE':
            self.stdout.write("Operation cancelled")
            return
        
        try:
            # Delete indices
            index_prefix = elasticsearch_service.index_prefix
            indices_to_delete = [
                f"{index_prefix}_records",
                f"{index_prefix}_documents"
            ]
            
            deleted_count = 0
            for index_name in indices_to_delete:
                if elasticsearch_service.client.indices.exists(index=index_name):
                    elasticsearch_service.client.indices.delete(index=index_name)
                    self.stdout.write(f"✓ Deleted index: {index_name}")
                    deleted_count += 1
                else:
                    self.stdout.write(f"Index does not exist: {index_name}")
            
            if deleted_count > 0:
                self.stdout.write(self.style.SUCCESS(f"Successfully deleted {deleted_count} indices"))
            else:
                self.stdout.write("No indices found to delete")
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Failed to delete indices: {e}"))

    def show_help(self):
        """Show help information."""
        self.stdout.write(self.style.SUCCESS('Elasticsearch Setup and Management'))
        self.stdout.write('=' * 40)
        self.stdout.write("Available options:")
        self.stdout.write("  --status              Show current configuration and health")
        self.stdout.write("  --setup               Set up indices and mappings")
        self.stdout.write("  --configure           Interactive configuration")
        self.stdout.write("  --reindex             Reindex all data")
        self.stdout.write("  --clinic-id ID        Specify clinic for operations")
        self.stdout.write("  --test-search QUERY   Test search functionality")
        self.stdout.write("  --enable              Enable Elasticsearch")
        self.stdout.write("  --disable             Disable Elasticsearch")
        self.stdout.write("  --delete-indices      Delete all indices (WARNING)")
        self.stdout.write("\nExamples:")
        self.stdout.write("  python manage.py setup_elasticsearch --status")
        self.stdout.write("  python manage.py setup_elasticsearch --setup")
        self.stdout.write("  python manage.py setup_elasticsearch --test-search 'aspirin'")
        self.stdout.write("  python manage.py setup_elasticsearch --reindex --clinic-id abc123")