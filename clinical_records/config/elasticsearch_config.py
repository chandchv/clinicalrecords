"""
Elasticsearch configuration for clinical records search capabilities.
"""

from django.conf import settings
import os


# Elasticsearch Configuration
ELASTICSEARCH_CONFIG = {
    # Enable/disable Elasticsearch
    'ELASTICSEARCH_ENABLED': getattr(settings, 'ELASTICSEARCH_ENABLED', False),
    
    # Elasticsearch connection settings
    'ELASTICSEARCH_DSL': getattr(settings, 'ELASTICSEARCH_DSL', {
        'default': {
            'hosts': [os.environ.get('ELASTICSEARCH_URL', 'localhost:9200')],
            'timeout': 30,
            'max_retries': 3,
            'retry_on_timeout': True,
            'http_auth': None,  # Set to ('username', 'password') if needed
            'use_ssl': False,
            'verify_certs': False,
            'ssl_show_warn': False,
        }
    }),
    
    # Index configuration
    'ELASTICSEARCH_INDEX_PREFIX': getattr(settings, 'ELASTICSEARCH_INDEX_PREFIX', 'clinical_records'),
    'ELASTICSEARCH_AUTO_CREATE_INDEX': getattr(settings, 'ELASTICSEARCH_AUTO_CREATE_INDEX', True),
    'ELASTICSEARCH_AUTO_SYNC': getattr(settings, 'ELASTICSEARCH_AUTO_SYNC', True),
    
    # Search configuration
    'ELASTICSEARCH_DEFAULT_PAGE_SIZE': getattr(settings, 'ELASTICSEARCH_DEFAULT_PAGE_SIZE', 20),
    'ELASTICSEARCH_MAX_PAGE_SIZE': getattr(settings, 'ELASTICSEARCH_MAX_PAGE_SIZE', 100),
    'ELASTICSEARCH_SEARCH_TIMEOUT': getattr(settings, 'ELASTICSEARCH_SEARCH_TIMEOUT', 30),
    
    # Indexing configuration
    'ELASTICSEARCH_BULK_CHUNK_SIZE': getattr(settings, 'ELASTICSEARCH_BULK_CHUNK_SIZE', 100),
    'ELASTICSEARCH_BULK_TIMEOUT': getattr(settings, 'ELASTICSEARCH_BULK_TIMEOUT', 60),
    'ELASTICSEARCH_INDEX_REFRESH': getattr(settings, 'ELASTICSEARCH_INDEX_REFRESH', 'wait_for'),
    
    # Performance settings
    'ELASTICSEARCH_NUMBER_OF_SHARDS': getattr(settings, 'ELASTICSEARCH_NUMBER_OF_SHARDS', 1),
    'ELASTICSEARCH_NUMBER_OF_REPLICAS': getattr(settings, 'ELASTICSEARCH_NUMBER_OF_REPLICAS', 0),
    'ELASTICSEARCH_REFRESH_INTERVAL': getattr(settings, 'ELASTICSEARCH_REFRESH_INTERVAL', '1s'),
    
    # Security settings
    'ELASTICSEARCH_REQUIRE_AUTH': getattr(settings, 'ELASTICSEARCH_REQUIRE_AUTH', False),
    'ELASTICSEARCH_USERNAME': getattr(settings, 'ELASTICSEARCH_USERNAME', os.environ.get('ELASTICSEARCH_USERNAME')),
    'ELASTICSEARCH_PASSWORD': getattr(settings, 'ELASTICSEARCH_PASSWORD', os.environ.get('ELASTICSEARCH_PASSWORD')),
    
    # SSL/TLS settings
    'ELASTICSEARCH_USE_SSL': getattr(settings, 'ELASTICSEARCH_USE_SSL', False),
    'ELASTICSEARCH_VERIFY_CERTS': getattr(settings, 'ELASTICSEARCH_VERIFY_CERTS', False),
    'ELASTICSEARCH_CA_CERTS': getattr(settings, 'ELASTICSEARCH_CA_CERTS', None),
    
    # AWS Elasticsearch/OpenSearch settings
    'ELASTICSEARCH_AWS_REGION': getattr(settings, 'ELASTICSEARCH_AWS_REGION', None),
    'ELASTICSEARCH_AWS_ACCESS_KEY': getattr(settings, 'ELASTICSEARCH_AWS_ACCESS_KEY', None),
    'ELASTICSEARCH_AWS_SECRET_KEY': getattr(settings, 'ELASTICSEARCH_AWS_SECRET_KEY', None),
    'ELASTICSEARCH_USE_AWS_IAM': getattr(settings, 'ELASTICSEARCH_USE_AWS_IAM', False),
    
    # Logging settings
    'ELASTICSEARCH_LOG_REQUESTS': getattr(settings, 'ELASTICSEARCH_LOG_REQUESTS', False),
    'ELASTICSEARCH_LOG_RESPONSES': getattr(settings, 'ELASTICSEARCH_LOG_RESPONSES', False),
    'ELASTICSEARCH_LOG_LEVEL': getattr(settings, 'ELASTICSEARCH_LOG_LEVEL', 'INFO'),
}


def get_elasticsearch_config():
    """Get Elasticsearch configuration dictionary."""
    return ELASTICSEARCH_CONFIG.copy()


def is_elasticsearch_enabled():
    """Check if Elasticsearch is enabled and properly configured."""
    config = get_elasticsearch_config()
    return config['ELASTICSEARCH_ENABLED']


def get_elasticsearch_connection_config():
    """Get Elasticsearch connection configuration."""
    config = get_elasticsearch_config()
    connection_config = config['ELASTICSEARCH_DSL']['default'].copy()
    
    # Add authentication if required
    if config['ELASTICSEARCH_REQUIRE_AUTH']:
        username = config['ELASTICSEARCH_USERNAME']
        password = config['ELASTICSEARCH_PASSWORD']
        if username and password:
            connection_config['http_auth'] = (username, password)
    
    # Add SSL settings
    if config['ELASTICSEARCH_USE_SSL']:
        connection_config['use_ssl'] = True
        connection_config['verify_certs'] = config['ELASTICSEARCH_VERIFY_CERTS']
        if config['ELASTICSEARCH_CA_CERTS']:
            connection_config['ca_certs'] = config['ELASTICSEARCH_CA_CERTS']
    
    # Add AWS settings if using AWS Elasticsearch/OpenSearch
    if config['ELASTICSEARCH_USE_AWS_IAM']:
        try:
            from requests_aws4auth import AWS4Auth
            import boto3
            
            region = config['ELASTICSEARCH_AWS_REGION']
            service = 'es'
            
            if config['ELASTICSEARCH_AWS_ACCESS_KEY'] and config['ELASTICSEARCH_AWS_SECRET_KEY']:
                # Use explicit credentials
                awsauth = AWS4Auth(
                    config['ELASTICSEARCH_AWS_ACCESS_KEY'],
                    config['ELASTICSEARCH_AWS_SECRET_KEY'],
                    region,
                    service
                )
            else:
                # Use IAM role or default credentials
                credentials = boto3.Session().get_credentials()
                awsauth = AWS4Auth(
                    credentials.access_key,
                    credentials.secret_key,
                    region,
                    service,
                    session_token=credentials.token
                )
            
            connection_config['http_auth'] = awsauth
            connection_config['use_ssl'] = True
            connection_config['verify_certs'] = True
            
        except ImportError:
            raise ImportError("requests-aws4auth and boto3 are required for AWS Elasticsearch")
    
    return connection_config


def get_index_settings():
    """Get index settings for Elasticsearch indices."""
    config = get_elasticsearch_config()
    
    return {
        'number_of_shards': config['ELASTICSEARCH_NUMBER_OF_SHARDS'],
        'number_of_replicas': config['ELASTICSEARCH_NUMBER_OF_REPLICAS'],
        'refresh_interval': config['ELASTICSEARCH_REFRESH_INTERVAL'],
        'analysis': {
            'analyzer': {
                'medical_analyzer': {
                    'type': 'custom',
                    'tokenizer': 'standard',
                    'filter': [
                        'lowercase',
                        'medical_synonyms',
                        'medical_stemmer',
                        'stop'
                    ]
                },
                'medication_analyzer': {
                    'type': 'custom',
                    'tokenizer': 'keyword',
                    'filter': [
                        'lowercase',
                        'medication_normalizer'
                    ]
                }
            },
            'filter': {
                'medical_synonyms': {
                    'type': 'synonym',
                    'synonyms': [
                        # Common medical abbreviations
                        'tab,tablet,tablets',
                        'cap,capsule,capsules',
                        'syp,syrup',
                        'inj,injection',
                        'oint,ointment',
                        
                        # Dosage abbreviations
                        'mg,milligram,milligrams',
                        'ml,milliliter,milliliters',
                        'mcg,microgram,micrograms',
                        'g,gram,grams',
                        'iu,international unit,international units',
                        
                        # Frequency abbreviations
                        'od,once daily,once a day',
                        'bd,twice daily,twice a day',
                        'tds,three times daily,three times a day',
                        'qid,four times daily,four times a day',
                        'hs,at bedtime,before sleep',
                        'prn,as needed,when required',
                        'sos,if necessary,as required',
                        
                        # Medical conditions
                        'dm,diabetes mellitus,diabetes',
                        'htn,hypertension,high blood pressure',
                        'cad,coronary artery disease',
                        'copd,chronic obstructive pulmonary disease',
                        'uti,urinary tract infection',
                        'uri,upper respiratory infection',
                        
                        # Common medications
                        'aspirin,acetylsalicylic acid',
                        'paracetamol,acetaminophen,tylenol',
                        'ibuprofen,advil,motrin',
                        'metformin,glucophage',
                        'amlodipine,norvasc'
                    ]
                },
                'medical_stemmer': {
                    'type': 'stemmer',
                    'language': 'english'
                },
                'medication_normalizer': {
                    'type': 'pattern_replace',
                    'pattern': '[^a-zA-Z0-9]',
                    'replacement': ''
                }
            },
            'normalizer': {
                'keyword_normalizer': {
                    'type': 'custom',
                    'filter': ['lowercase']
                }
            }
        }
    }


def get_search_templates():
    """Get predefined search templates."""
    return {
        'medication_search': {
            'template': {
                'query': {
                    'bool': {
                        'must': [
                            {'term': {'clinic_id': '{{clinic_id}}'}},
                            {'nested': {
                                'path': 'structured_data.medications',
                                'query': {
                                    'multi_match': {
                                        'query': '{{medication_name}}',
                                        'fields': [
                                            'structured_data.medications.name^2',
                                            'structured_data.medications.name.keyword'
                                        ],
                                        'fuzziness': 'AUTO'
                                    }
                                }
                            }}
                        ]
                    }
                },
                'aggs': {
                    'dosages': {
                        'nested': {'path': 'structured_data.medications'},
                        'aggs': {
                            'dosage_terms': {
                                'terms': {
                                    'field': 'structured_data.medications.dosage',
                                    'size': 10
                                }
                            }
                        }
                    }
                }
            }
        },
        'diagnosis_search': {
            'template': {
                'query': {
                    'bool': {
                        'must': [
                            {'term': {'clinic_id': '{{clinic_id}}'}},
                            {'match': {
                                'structured_data.diagnosis.text': {
                                    'query': '{{diagnosis}}',
                                    'fuzziness': 'AUTO'
                                }
                            }}
                        ]
                    }
                }
            }
        },
        'patient_records_search': {
            'template': {
                'query': {
                    'bool': {
                        'must': [
                            {'term': {'clinic_id': '{{clinic_id}}'}},
                            {'term': {'patient_id': '{{patient_id}}'}}
                        ],
                        'should': [
                            {'match': {'title': '{{query}}'}},
                            {'match': {'description': '{{query}}'}},
                            {'match': {'ocr_text': '{{query}}'}}
                        ]
                    }
                },
                'sort': [
                    {'created_at': {'order': 'desc'}}
                ]
            }
        }
    }


# Environment-specific configurations
DEVELOPMENT_CONFIG = {
    'ELASTICSEARCH_ENABLED': False,  # Disabled by default in development
    'ELASTICSEARCH_DSL': {
        'default': {
            'hosts': ['localhost:9200'],
            'timeout': 30
        }
    },
    'ELASTICSEARCH_LOG_REQUESTS': True,
    'ELASTICSEARCH_AUTO_CREATE_INDEX': True,
}

PRODUCTION_CONFIG = {
    'ELASTICSEARCH_ENABLED': True,
    'ELASTICSEARCH_DSL': {
        'default': {
            'hosts': [os.environ.get('ELASTICSEARCH_URL', 'localhost:9200')],
            'timeout': 30,
            'max_retries': 3,
            'retry_on_timeout': True
        }
    },
    'ELASTICSEARCH_REQUIRE_AUTH': True,
    'ELASTICSEARCH_USE_SSL': True,
    'ELASTICSEARCH_VERIFY_CERTS': True,
    'ELASTICSEARCH_LOG_REQUESTS': False,
    'ELASTICSEARCH_NUMBER_OF_REPLICAS': 1,
}

TESTING_CONFIG = {
    'ELASTICSEARCH_ENABLED': False,  # Use mock service for testing
    'ELASTICSEARCH_AUTO_SYNC': False,
    'ELASTICSEARCH_LOG_REQUESTS': False,
}


def get_environment_config():
    """Get configuration based on current environment."""
    env = getattr(settings, 'ENVIRONMENT', 'development').lower()
    
    if env == 'production':
        return PRODUCTION_CONFIG
    elif env == 'testing':
        return TESTING_CONFIG
    else:
        return DEVELOPMENT_CONFIG


def apply_environment_config():
    """Apply environment-specific configuration to global config."""
    env_config = get_environment_config()
    ELASTICSEARCH_CONFIG.update(env_config)


# Apply environment configuration on import
apply_environment_config()