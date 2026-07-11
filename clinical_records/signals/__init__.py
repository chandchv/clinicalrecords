"""
Clinical Records Signals Package
"""

# Import all signal handlers to ensure they are registered
from .elasticsearch_signals import *

# Import the notify_record_accessed function from elasticsearch_signals
from .elasticsearch_signals import notify_record_accessed

__all__ = [
    'notify_record_accessed',
]