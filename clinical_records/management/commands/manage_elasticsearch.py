"""
Management command for Elasticsearch maintenance and monitoring operations.
"""

import json
import time
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from datetime import timedelta

from clinical_records.services.elasticsearch_service import elasticsearch_service
from clinical_records.models import ClinicalDocument, ClinicalRecord
from clinical_records.config.elasticsearch_config import get_elasticsearch_config, is_elasticsearch_enabled


class Command(BaseCommand):
    help = 'Manage Elasticsearch operations for clinical records'

    def add_arguments(self, parser):
        parser.add_argument(
            '--status',
            action='store_true',
            help='Show Elasticsearch cluster and index status',
        )
        parser.add_argument(
            '--health',
            action='store_true',
            help='Check Elasticsearch cluster health',
        )
        parser.add_argument(
            '--reindex',
            action='store_true',
            help='Reindex all clinical documents',
        )
        parser.add_argument(
            '--reindex-recent',
            type=int,
            metavar='DAYS',
            help='Reindex documents from the last N days',
        )
        parser.add_argument(
            '--optimize',
            action='store_true',
            help='Optimize Elasticsearch indices',
        )
        parser.add_argument(
            '--cleanup',
            action='store_true',
            help='Clean up old or orphaned index entries',
        )
        parser.add_argument(
            '--stats',
            action='store_true',
            help='Show search and indexing statistics',
        )
        parser.add_argument(
            '--test-search',
            type=str,
            metavar='QUERY',
            help='Test search functionality with a query',
        )
        parser.add_argument(
            '--clinic-id',
            type=str,
            help='Limit operations to specific clinic',
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=100,
            help='Batch size for bulk operations (default: 100)',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force operations without confirmation',
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Enable verbose output',
        )

    def handle(self, *args, **options):
        """Handle the management command."""
        
        # Check if Elasticsearch is enabled
        if not is_elasticsearch_enabled():
            self.stdout.write(
                self.style.ERROR('Elasticsearch is not enabled in settings')
            )
            return
        
        # Check if Elasticsearch service is available
        if not elasticsearch_service.is_available():
            self.stdout.write(
                self.style.ERROR('Elasticsearch service is not available')
            )
            return
        
        self.verbose = options['verbose']
        
        if options['status']:
            self.show_status()
        elif options['health']:
            self.check_health()
        elif options['reindex']:
            self.reindex_all(options)
        elif options['reindex_recent']:
            self.reindex_recent(options['reindex_recent'], options)
        elif options['optimize']:
            self.optimize_indices(options)
        elif options['cleanup']:
            self.cleanup_indices(options)
        elif options['stats']:
            self.show_statistics(options)
        elif options['test_search']:
            self.test_search(options['test_search'], options)
        else:
            self.show_help()

    def show_status(self):
        """Show Elasticsearch cluster and index status."""
        self.stdout.write(self.style.SUCCESS('Elasticsearch Status'))
        self.stdout.write('=' * 50)
        
        try:
            # Cluster info
            cluster_info = elasticsearch_service.get_cluster_info()
            self.stdout.write(f"Cluster Name: {cluster_info.get('cluster_name', 'Unknown')}")
            self.stdout.write(f"Elasticsearch Version: {cluster_info.get('version', {}).get('number', 'Unknown')}")
            
            # Index info
            index_info = elasticsearch_service.get_index_info()
            self.stdout.write(f"\nIndex Name: {index_info.get('index_name', 'Unknown')}")
            self.stdout.write(f"Document Count: {index_info.get('doc_count', 0):,}")
            self.stdout.write(f"Index Size: {index_info.get('store_size', 'Unknown')}")
            
            # Configuration
            config = get_elasticsearch_config()
            self.stdout.write(f"\nConfiguration:")
            self.stdout.write(f"  Host: {config['ELASTICSEARCH_HOST']}:{config['ELASTICSEARCH_PORT']}")
            self.stdout.write(f"  Index: {config['ELASTICSEARCH_INDEX_NAME']}")
            self.stdout.write(f"  Timeout: {config['ELASTICSEARCH_TIMEOUT']}s")
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Failed to get status: {e}"))

    def check_health(self):
        """Check Elasticsearch cluster health."""
        self.stdout.write(self.style.SUCCESS('Elasticsearch Health Check'))
        self.stdout.write('=' * 40)
        
        try:
            health = elasticsearch_service.get_cluster_health()
            
            status = health.get('status', 'unknown')
            if status == 'green':
                status_style = self.style.SUCCESS
            elif status == 'yellow':
                status_style = self.style.WARNING
            else:
                status_style = self.style.ERROR
            
            self.stdout.write(f"Cluster Status: {status_style(status.upper())}")
            self.stdout.write(f"Active Nodes: {health.get('number_of_nodes', 0)}")
            self.stdout.write(f"Active Shards: {health.get('active_shards', 0)}")
            self.stdout.write(f"Relocating Shards: {health.get('relocating_shards', 0)}")
            self.stdout.write(f"Initializing Shards: {health.get('initializing_shards', 0)}")
            self.stdout.write(f"Unassigned Shards: {health.get('unassigned_shards', 0)}")
            
            if health.get('unassigned_shards', 0) > 0:
                self.stdout.write(
                    self.style.WARNING('Warning: There are unassigned shards')
                )
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Health check failed: {e}"))

    def reindex_all(self, options):
        """Reindex all clinical documents."""
        self.stdout.write(self.style.SUCCESS('Reindexing All Documents'))
        self.stdout.write('=' * 35)
        
        try:
            # Get document count
            queryset = ClinicalDocument.objects.filter(processing_status='completed')
            if options['clinic_id']:
                queryset = queryset.filter(clinical_record__clinic_id=options['clinic_id'])
            
            total_docs = queryset.count()
            
            if total_docs == 0:
                self.stdout.write("No documents to reindex")
                return
            
            self.stdout.write(f"Found {total_docs:,} documents to reindex")
            
            if not options['force']:
                confirm = input("Continue with reindexing? (y/N): ")
                if confirm.lower() != 'y':
                    self.stdout.write("Reindexing cancelled")
                    return
            
            # Perform reindexing
            start_time = time.time()
            batch_size = options['batch_size']
            
            result = elasticsearch_service.reindex_all_documents(
                queryset=queryset,
                batch_size=batch_size,
                progress_callback=self._progress_callback if self.verbose else None
            )
            
            elapsed_time = time.time() - start_time
            
            if result['success']:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"✓ Reindexed {result['indexed_count']:,} documents in {elapsed_time:.2f}s"
                    )
                )
                if result.get('failed_count', 0) > 0:
                    self.stdout.write(
                        self.style.WARNING(f"⚠ {result['failed_count']} documents failed to index")
                    )
            else:
                self.stdout.write(
                    self.style.ERROR(f"✗ Reindexing failed: {result.get('error', 'Unknown error')}")
                )
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Reindexing failed: {e}"))

    def reindex_recent(self, days, options):
        """Reindex documents from the last N days."""
        self.stdout.write(self.style.SUCCESS(f'Reindexing Documents from Last {days} Days'))
        self.stdout.write('=' * 50)
        
        try:
            cutoff_date = timezone.now() - timedelta(days=days)
            
            queryset = ClinicalDocument.objects.filter(
                processing_status='completed',
                updated_at__gte=cutoff_date
            )
            
            if options['clinic_id']:
                queryset = queryset.filter(clinical_record__clinic_id=options['clinic_id'])
            
            total_docs = queryset.count()
            
            if total_docs == 0:
                self.stdout.write(f"No documents updated in the last {days} days")
                return
            
            self.stdout.write(f"Found {total_docs:,} documents to reindex")
            
            # Perform reindexing
            result = elasticsearch_service.bulk_index_documents(
                queryset,
                batch_size=options['batch_size']
            )
            
            if result['success']:
                self.stdout.write(
                    self.style.SUCCESS(f"✓ Reindexed {result['indexed_count']:,} recent documents")
                )
            else:
                self.stdout.write(
                    self.style.ERROR(f"✗ Reindexing failed: {result.get('error', 'Unknown error')}")
                )
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Recent reindexing failed: {e}"))

    def optimize_indices(self, options):
        """Optimize Elasticsearch indices."""
        self.stdout.write(self.style.SUCCESS('Optimizing Elasticsearch Indices'))
        self.stdout.write('=' * 40)
        
        try:
            if not options['force']:
                confirm = input("This may take a while and affect performance. Continue? (y/N): ")
                if confirm.lower() != 'y':
                    self.stdout.write("Optimization cancelled")
                    return
            
            result = elasticsearch_service.optimize_index()
            
            if result['success']:
                self.stdout.write(self.style.SUCCESS("✓ Index optimization completed"))
                if 'details' in result:
                    for detail in result['details']:
                        self.stdout.write(f"  {detail}")
            else:
                self.stdout.write(
                    self.style.ERROR(f"✗ Optimization failed: {result.get('error', 'Unknown error')}")
                )
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Optimization failed: {e}"))

    def cleanup_indices(self, options):
        """Clean up old or orphaned index entries."""
        self.stdout.write(self.style.SUCCESS('Cleaning Up Elasticsearch Indices'))
        self.stdout.write('=' * 40)
        
        try:
            result = elasticsearch_service.cleanup_orphaned_documents()
            
            if result['success']:
                self.stdout.write(
                    self.style.SUCCESS(f"✓ Cleaned up {result['removed_count']} orphaned documents")
                )
                if result.get('errors'):
                    for error in result['errors']:
                        self.stdout.write(self.style.WARNING(f"⚠ {error}"))
            else:
                self.stdout.write(
                    self.style.ERROR(f"✗ Cleanup failed: {result.get('error', 'Unknown error')}")
                )
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Cleanup failed: {e}"))

    def show_statistics(self, options):
        """Show search and indexing statistics."""
        self.stdout.write(self.style.SUCCESS('Elasticsearch Statistics'))
        self.stdout.write('=' * 30)
        
        try:
            stats = elasticsearch_service.get_search_statistics(
                clinic_id=options.get('clinic_id')
            )
            
            # Index statistics
            self.stdout.write("Index Statistics:")
            self.stdout.write(f"  Total Documents: {stats.get('total_documents', 0):,}")
            self.stdout.write(f"  Index Size: {stats.get('index_size', 'Unknown')}")
            self.stdout.write(f"  Last Updated: {stats.get('last_updated', 'Unknown')}")
            
            # Search statistics
            if 'search_stats' in stats:
                search_stats = stats['search_stats']
                self.stdout.write("\nSearch Statistics:")
                self.stdout.write(f"  Total Searches: {search_stats.get('total_searches', 0):,}")
                self.stdout.write(f"  Average Response Time: {search_stats.get('avg_response_time', 0):.2f}ms")
                self.stdout.write(f"  Most Popular Terms: {', '.join(search_stats.get('popular_terms', []))}")
            
            # Document type breakdown
            if 'document_types' in stats:
                self.stdout.write("\nDocument Types:")
                for doc_type, count in stats['document_types'].items():
                    self.stdout.write(f"  {doc_type}: {count:,}")
            
            # Recent activity
            if 'recent_activity' in stats:
                activity = stats['recent_activity']
                self.stdout.write("\nRecent Activity (Last 24h):")
                self.stdout.write(f"  Documents Indexed: {activity.get('indexed_24h', 0):,}")
                self.stdout.write(f"  Searches Performed: {activity.get('searches_24h', 0):,}")
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Failed to get statistics: {e}"))

    def test_search(self, query, options):
        """Test search functionality with a query."""
        self.stdout.write(self.style.SUCCESS(f'Testing Search: "{query}"'))
        self.stdout.write('=' * 50)
        
        try:
            start_time = time.time()
            
            results = elasticsearch_service.search_documents(
                query=query,
                clinic_id=options.get('clinic_id'),
                size=10
            )
            
            response_time = (time.time() - start_time) * 1000  # Convert to milliseconds
            
            self.stdout.write(f"Response Time: {response_time:.2f}ms")
            self.stdout.write(f"Total Results: {results.get('total', 0):,}")
            
            if results.get('documents'):
                self.stdout.write("\nTop Results:")
                for i, doc in enumerate(results['documents'][:5], 1):
                    self.stdout.write(f"  {i}. {doc.get('title', 'Untitled')} (Score: {doc.get('score', 0):.2f})")
                    if self.verbose:
                        self.stdout.write(f"     ID: {doc.get('id')}")
                        self.stdout.write(f"     Type: {doc.get('record_type', 'Unknown')}")
                        content_preview = doc.get('content', '')[:100]
                        if len(content_preview) == 100:
                            content_preview += "..."
                        self.stdout.write(f"     Preview: {content_preview}")
                        self.stdout.write("")
            
            # Show facets if available
            if results.get('facets'):
                self.stdout.write("\nFacets:")
                for facet_name, facet_data in results['facets'].items():
                    self.stdout.write(f"  {facet_name}:")
                    if isinstance(facet_data, list):
                        for item in facet_data[:5]:  # Show top 5
                            self.stdout.write(f"    {item.get('key', 'Unknown')}: {item.get('count', 0)}")
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Search test failed: {e}"))

    def _progress_callback(self, current, total):
        """Progress callback for verbose operations."""
        if current % 100 == 0 or current == total:
            percentage = (current / total) * 100
            self.stdout.write(f"Progress: {current:,}/{total:,} ({percentage:.1f}%)")

    def show_help(self):
        """Show help information."""
        self.stdout.write(self.style.SUCCESS('Elasticsearch Management Commands'))
        self.stdout.write('=' * 40)
        self.stdout.write("Available operations:")
        self.stdout.write("  --status              Show cluster and index status")
        self.stdout.write("  --health              Check cluster health")
        self.stdout.write("  --reindex             Reindex all documents")
        self.stdout.write("  --reindex-recent N    Reindex documents from last N days")
        self.stdout.write("  --optimize            Optimize indices")
        self.stdout.write("  --cleanup             Clean up orphaned documents")
        self.stdout.write("  --stats               Show statistics")
        self.stdout.write("  --test-search QUERY   Test search functionality")
        self.stdout.write("\nOptions:")
        self.stdout.write("  --clinic-id ID        Limit to specific clinic")
        self.stdout.write("  --batch-size N        Batch size for operations")
        self.stdout.write("  --force               Skip confirmations")
        self.stdout.write("  --verbose             Verbose output")
        self.stdout.write("\nExamples:")
        self.stdout.write("  python manage.py manage_elasticsearch --status")
        self.stdout.write("  python manage.py manage_elasticsearch --reindex --clinic-id 123")
        self.stdout.write("  python manage.py manage_elasticsearch --test-search 'aspirin prescription'")
        self.stdout.write("  python manage.py manage_elasticsearch --cleanup --force")