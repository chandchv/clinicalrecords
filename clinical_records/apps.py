"""
Clinical Records Django App Configuration
"""

from django.apps import AppConfig


class ClinicalRecordsConfig(AppConfig):
    """Configuration for the Clinical Records app."""
    
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'clinical_records'
    verbose_name = 'Clinical Records Management'
    
    def ready(self):
        """
        Perform initialization tasks when the app is ready.
        This includes registering signal handlers.
        """
        # Temporarily disabled for debugging
        pass
        
        # # Import signal handlers to register them
        # try:
        #     from . import signals
        #     from .signals import elasticsearch_signals  # Import Elasticsearch signals
        # except ImportError:
        #     pass
        
        # # Import and initialize Elasticsearch service
        # try:
        #     from .services.elasticsearch_service import elasticsearch_service
        #     if elasticsearch_service.is_enabled():
        #         # Ensure indices are created on startup
        #         from .signals.elasticsearch_signals import setup_elasticsearch_indices
        #         setup_elasticsearch_indices()
        # except Exception as e:
        #     # Log the error but don't prevent app startup
        #     import logging
        #     logger = logging.getLogger(__name__)
        #     logger.warning(f"Failed to initialize Elasticsearch on startup: {e}")