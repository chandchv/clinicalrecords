# Import all view modules
from . import widget_views
from . import dashboard_views
from . import record_views
from . import sso_views

# Import SSO views directly for easy access
from .sso_views import sso_login, sso_logout, sso_status, health_check, user_profile, clinical_records_list

__all__ = [
    'widget_views',
    'dashboard_views',
    'record_views',
    'sso_views',
    'sso_login',
    'sso_logout',
    'sso_status',
    'health_check',
    'user_profile',
    'clinical_records_list',
]