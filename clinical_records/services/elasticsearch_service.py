"""
Elasticsearch service for advanced search capabilities in clinical records.
Provides full-text search, faceted search, and analytics for clinical documents.
"""

import logging
from typing import Dict, List, Optional, Any, Union
from datetime import datetime, timedelta
from django.conf import settings
from django.utils import timezone
from elasticsearch import Elasticsearch
from elasticsearch.exceptions import ConnectionError, NotFoundError, RequestError
from elasticsearch_dsl import Document, Text, Keyword, Date, Integer, Float, Boolean, Object, connections

from ..models import ClinicalRecord, ClinicalDocument
from users.models import Patient, Clinic

logger = logging.getLogger(__name__)


class ElasticsearchService:
    """
    Service for managing Elasticsearch operations for clinical records.
    """
    
    def __init__(self):
        """Initialize Elasticsearch service."""
        self.enabled = getattr(settings, 'ELASTICSEARCH_ENABLED', False)
        self.client = None
        self.index_prefix = getattr(settings, 'ELASTICSEARCH_INDEX_PREFIX', 'clinical_records')
        
        if self.enabled:
            try:
                # Configure Elasticsearch connection
                es_config = getattr(settings, 'ELASTICSEARCH_DSL', {})
                default_config = es_config.get('default', {})
                
                self.client = Elasticsearch(
                    hosts=default_config.get('hosts', ['localhost:9200']),
                    timeout=default_config.get('timeout', 30),
                    max_retries=default_config.get('max_retries', 3),
                    retry_on_timeout=True
                )
                
                # Test connection
                if self.client.ping():
                    logger.info("Elasticsearch connection established successfully")
                else:
                    logger.error("Failed to connect to Elasticsearch")
                    self.enabled = False
                    
            except Exception as e:
                logger.error(f"Failed to initialize Elasticsearch: {e}")
                self.enabled = False
                self.client = None
    
    def is_enabled(self) -> bool:
        """Check if Elasticsearch is enabled and connected."""
        return self.enabled and self.client is not None
    
    def create_indices(self) -> Dict[str, Any]:
        """
        Create Elasticsearch indices for clinical records.
        
        Returns:
            Dict containing creation results
        """
        if not self.is_enabled():
            return {'status': 'disabled', 'message': 'Elasticsearch is not enabled'}
        
        results = {}
        
        try:
            # Clinical Records index
            records_index = f"{self.index_prefix}_records"
            records_mapping = self._get_clinical_records_mapping()
            
            if not self.client.indices.exists(index=records_index):
                self.client.indices.create(
                    index=records_index,
                    body={
                        'mappings': records_mapping,
                        'settings': {
                            'number_of_shards': 1,
                            'number_of_replicas': 0,
                            'analysis': self._get_analysis_settings()
                        }
                    }
                )
                results[records_index] = 'created'
            else:
                results[records_index] = 'exists'
            
            # Clinical Documents index
            documents_index = f"{self.index_prefix}_documents"
            documents_mapping = self._get_clinical_documents_mapping()
            
            if not self.client.indices.exists(index=documents_index):
                self.client.indices.create(
                    index=documents_index,
                    body={
                        'mappings': documents_mapping,
                        'settings': {
                            'number_of_shards': 1,
                            'number_of_replicas': 0,
                            'analysis': self._get_analysis_settings()
                        }
                    }
                )
                results[documents_index] = 'created'
            else:
                results[documents_index] = 'exists'
            
            logger.info(f"Elasticsearch indices status: {results}")
            return {'status': 'success', 'indices': results}
            
        except Exception as e:
            logger.error(f"Failed to create Elasticsearch indices: {e}")
            return {'status': 'error', 'message': str(e)}
    
    def index_clinical_record(self, record: ClinicalRecord) -> Dict[str, Any]:
        """
        Index a clinical record in Elasticsearch.
        
        Args:
            record: ClinicalRecord instance to index
            
        Returns:
            Dict containing indexing result
        """
        if not self.is_enabled():
            return {'status': 'disabled'}
        
        try:
            index_name = f"{self.index_prefix}_records"
            doc_body = self._prepare_clinical_record_document(record)
            
            result = self.client.index(
                index=index_name,
                id=str(record.id),
                body=doc_body
            )
            
            logger.debug(f"Indexed clinical record {record.id}: {result['result']}")
            return {'status': 'success', 'result': result['result']}
            
        except Exception as e:
            logger.error(f"Failed to index clinical record {record.id}: {e}")
            return {'status': 'error', 'message': str(e)}
    
    def index_clinical_document(self, document: ClinicalDocument) -> Dict[str, Any]:
        """
        Index a clinical document in Elasticsearch.
        
        Args:
            document: ClinicalDocument instance to index
            
        Returns:
            Dict containing indexing result
        """
        if not self.is_enabled():
            return {'status': 'disabled'}
        
        try:
            index_name = f"{self.index_prefix}_documents"
            doc_body = self._prepare_clinical_document_document(document)
            
            result = self.client.index(
                index=index_name,
                id=str(document.id),
                body=doc_body
            )
            
            logger.debug(f"Indexed clinical document {document.id}: {result['result']}")
            return {'status': 'success', 'result': result['result']}
            
        except Exception as e:
            logger.error(f"Failed to index clinical document {document.id}: {e}")
            return {'status': 'error', 'message': str(e)}
    
    def search_clinical_records(
        self,
        query: str,
        clinic_id: str,
        filters: Optional[Dict] = None,
        page: int = 1,
        page_size: int = 20,
        sort_by: str = '_score'
    ) -> Dict[str, Any]:
        """
        Search clinical records with full-text search and filters.
        
        Args:
            query: Search query string
            clinic_id: Clinic ID for tenant isolation
            filters: Additional filters (record_type, patient_id, date_range, etc.)
            page: Page number (1-based)
            page_size: Number of results per page
            sort_by: Sort field (_score, created_at, updated_at)
            
        Returns:
            Dict containing search results and metadata
        """
        if not self.is_enabled():
            return {'status': 'disabled', 'results': [], 'total': 0}
        
        try:
            index_name = f"{self.index_prefix}_records"
            
            # Build search query
            search_body = self._build_clinical_records_query(
                query, clinic_id, filters, sort_by
            )
            
            # Calculate pagination
            from_offset = (page - 1) * page_size
            search_body['from'] = from_offset
            search_body['size'] = page_size
            
            # Execute search
            response = self.client.search(
                index=index_name,
                body=search_body
            )
            
            # Process results
            results = self._process_search_results(response)
            
            return {
                'status': 'success',
                'results': results['hits'],
                'total': results['total'],
                'page': page,
                'page_size': page_size,
                'total_pages': (results['total'] + page_size - 1) // page_size,
                'aggregations': results.get('aggregations', {}),
                'took': response['took']
            }
            
        except Exception as e:
            logger.error(f"Clinical records search failed: {e}")
            return {'status': 'error', 'message': str(e), 'results': [], 'total': 0}
    
    def search_documents_content(
        self,
        query: str,
        clinic_id: str,
        filters: Optional[Dict] = None,
        page: int = 1,
        page_size: int = 20
    ) -> Dict[str, Any]:
        """
        Search within document content (OCR text and structured data).
        
        Args:
            query: Search query string
            clinic_id: Clinic ID for tenant isolation
            filters: Additional filters
            page: Page number
            page_size: Number of results per page
            
        Returns:
            Dict containing search results
        """
        if not self.is_enabled():
            return {'status': 'disabled', 'results': [], 'total': 0}
        
        try:
            index_name = f"{self.index_prefix}_documents"
            
            # Build search query for document content
            search_body = self._build_document_content_query(
                query, clinic_id, filters
            )
            
            # Add pagination
            from_offset = (page - 1) * page_size
            search_body['from'] = from_offset
            search_body['size'] = page_size
            
            # Add highlighting for matched content
            search_body['highlight'] = {
                'fields': {
                    'ocr_text': {'fragment_size': 150, 'number_of_fragments': 3},
                    'structured_data.medications.name': {},
                    'structured_data.diagnosis.text': {}
                }
            }
            
            # Execute search
            response = self.client.search(
                index=index_name,
                body=search_body
            )
            
            # Process results with highlights
            results = self._process_document_search_results(response)
            
            return {
                'status': 'success',
                'results': results['hits'],
                'total': results['total'],
                'page': page,
                'page_size': page_size,
                'total_pages': (results['total'] + page_size - 1) // page_size,
                'took': response['took']
            }
            
        except Exception as e:
            logger.error(f"Document content search failed: {e}")
            return {'status': 'error', 'message': str(e), 'results': [], 'total': 0}
    
    def get_search_suggestions(
        self,
        query: str,
        clinic_id: str,
        suggestion_type: str = 'medications'
    ) -> List[str]:
        """
        Get search suggestions based on indexed content.
        
        Args:
            query: Partial query string
            clinic_id: Clinic ID for tenant isolation
            suggestion_type: Type of suggestions (medications, diagnoses, patients)
            
        Returns:
            List of suggestions
        """
        if not self.is_enabled():
            return []
        
        try:
            if suggestion_type == 'medications':
                return self._get_medication_suggestions(query, clinic_id)
            elif suggestion_type == 'diagnoses':
                return self._get_diagnosis_suggestions(query, clinic_id)
            elif suggestion_type == 'patients':
                return self._get_patient_suggestions(query, clinic_id)
            else:
                return []
                
        except Exception as e:
            logger.error(f"Failed to get search suggestions: {e}")
            return []
    
    def get_search_analytics(
        self,
        clinic_id: str,
        date_range: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Get search analytics and statistics.
        
        Args:
            clinic_id: Clinic ID for tenant isolation
            date_range: Optional date range filter
            
        Returns:
            Dict containing analytics data
        """
        if not self.is_enabled():
            return {'status': 'disabled'}
        
        try:
            # Get record type distribution
            record_types = self._get_record_type_distribution(clinic_id, date_range)
            
            # Get document processing statistics
            processing_stats = self._get_processing_statistics(clinic_id, date_range)
            
            # Get top medications
            top_medications = self._get_top_medications(clinic_id, date_range)
            
            # Get top diagnoses
            top_diagnoses = self._get_top_diagnoses(clinic_id, date_range)
            
            return {
                'status': 'success',
                'record_types': record_types,
                'processing_stats': processing_stats,
                'top_medications': top_medications,
                'top_diagnoses': top_diagnoses,
                'generated_at': timezone.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to get search analytics: {e}")
            return {'status': 'error', 'message': str(e)}
    
    def delete_clinical_record(self, record_id: str) -> Dict[str, Any]:
        """
        Delete a clinical record from Elasticsearch.
        
        Args:
            record_id: ID of the record to delete
            
        Returns:
            Dict containing deletion result
        """
        if not self.is_enabled():
            return {'status': 'disabled'}
        
        try:
            index_name = f"{self.index_prefix}_records"
            
            result = self.client.delete(
                index=index_name,
                id=record_id,
                ignore=[404]  # Ignore if document doesn't exist
            )
            
            return {'status': 'success', 'result': result.get('result', 'deleted')}
            
        except Exception as e:
            logger.error(f"Failed to delete clinical record {record_id}: {e}")
            return {'status': 'error', 'message': str(e)}
    
    def delete_clinical_document(self, document_id: str) -> Dict[str, Any]:
        """
        Delete a clinical document from Elasticsearch.
        
        Args:
            document_id: ID of the document to delete
            
        Returns:
            Dict containing deletion result
        """
        if not self.is_enabled():
            return {'status': 'disabled'}
        
        try:
            index_name = f"{self.index_prefix}_documents"
            
            result = self.client.delete(
                index=index_name,
                id=document_id,
                ignore=[404]
            )
            
            return {'status': 'success', 'result': result.get('result', 'deleted')}
            
        except Exception as e:
            logger.error(f"Failed to delete clinical document {document_id}: {e}")
            return {'status': 'error', 'message': str(e)}
    
    def bulk_index_records(self, records: List[ClinicalRecord]) -> Dict[str, Any]:
        """
        Bulk index multiple clinical records.
        
        Args:
            records: List of ClinicalRecord instances
            
        Returns:
            Dict containing bulk indexing results
        """
        if not self.is_enabled():
            return {'status': 'disabled'}
        
        try:
            from elasticsearch.helpers import bulk
            
            index_name = f"{self.index_prefix}_records"
            
            # Prepare bulk actions
            actions = []
            for record in records:
                doc_body = self._prepare_clinical_record_document(record)
                actions.append({
                    '_index': index_name,
                    '_id': str(record.id),
                    '_source': doc_body
                })
            
            # Execute bulk indexing
            success_count, failed_items = bulk(
                self.client,
                actions,
                chunk_size=100,
                request_timeout=60
            )
            
            logger.info(f"Bulk indexed {success_count} clinical records")
            
            return {
                'status': 'success',
                'indexed': success_count,
                'failed': len(failed_items) if failed_items else 0,
                'failed_items': failed_items
            }
            
        except Exception as e:
            logger.error(f"Bulk indexing failed: {e}")
            return {'status': 'error', 'message': str(e)}
    
    def reindex_all_data(self, clinic_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Reindex all clinical records and documents.
        
        Args:
            clinic_id: Optional clinic ID to reindex specific clinic data
            
        Returns:
            Dict containing reindexing results
        """
        if not self.is_enabled():
            return {'status': 'disabled'}
        
        try:
            results = {'records': 0, 'documents': 0, 'errors': []}
            
            # Reindex clinical records
            records_query = ClinicalRecord.objects.filter(is_active=True)
            if clinic_id:
                records_query = records_query.filter(clinic_id=clinic_id)
            
            records = list(records_query.select_related('patient', 'clinic', 'created_by'))
            if records:
                bulk_result = self.bulk_index_records(records)
                results['records'] = bulk_result.get('indexed', 0)
                if bulk_result.get('failed_items'):
                    results['errors'].extend(bulk_result['failed_items'])
            
            # Reindex clinical documents
            documents_query = ClinicalDocument.objects.filter(
                clinical_record__is_active=True
            )
            if clinic_id:
                documents_query = documents_query.filter(clinical_record__clinic_id=clinic_id)
            
            documents = list(documents_query.select_related('clinical_record__patient', 'clinical_record__clinic'))
            for document in documents:
                doc_result = self.index_clinical_document(document)
                if doc_result['status'] == 'success':
                    results['documents'] += 1
                else:
                    results['errors'].append(f"Document {document.id}: {doc_result.get('message', 'Unknown error')}")
            
            logger.info(f"Reindexing completed: {results['records']} records, {results['documents']} documents")
            
            return {
                'status': 'success',
                'results': results
            }
            
        except Exception as e:
            logger.error(f"Reindexing failed: {e}")
            return {'status': 'error', 'message': str(e)}
    
    def _get_clinical_records_mapping(self) -> Dict:
        """Get Elasticsearch mapping for clinical records."""
        return {
            'properties': {
                'id': {'type': 'keyword'},
                'patient_id': {'type': 'keyword'},
                'clinic_id': {'type': 'keyword'},
                'record_type': {'type': 'keyword'},
                'title': {
                    'type': 'text',
                    'analyzer': 'medical_analyzer',
                    'fields': {
                        'keyword': {'type': 'keyword'}
                    }
                },
                'description': {
                    'type': 'text',
                    'analyzer': 'medical_analyzer'
                },
                'tags': {'type': 'keyword'},
                'metadata': {'type': 'object'},
                'confidentiality_level': {'type': 'keyword'},
                'created_at': {'type': 'date'},
                'updated_at': {'type': 'date'},
                'created_by': {'type': 'keyword'},
                'patient_name': {
                    'type': 'text',
                    'analyzer': 'standard',
                    'fields': {
                        'keyword': {'type': 'keyword'}
                    }
                },
                'patient_age': {'type': 'integer'},
                'patient_gender': {'type': 'keyword'},
                'document_count': {'type': 'integer'},
                'has_structured_data': {'type': 'boolean'}
            }
        }
    
    def _get_clinical_documents_mapping(self) -> Dict:
        """Get Elasticsearch mapping for clinical documents."""
        return {
            'properties': {
                'id': {'type': 'keyword'},
                'clinical_record_id': {'type': 'keyword'},
                'clinic_id': {'type': 'keyword'},
                'patient_id': {'type': 'keyword'},
                'record_type': {'type': 'keyword'},
                'original_filename': {
                    'type': 'text',
                    'fields': {
                        'keyword': {'type': 'keyword'}
                    }
                },
                'content_type': {'type': 'keyword'},
                'file_size': {'type': 'integer'},
                'processing_status': {'type': 'keyword'},
                'ocr_text': {
                    'type': 'text',
                    'analyzer': 'medical_analyzer'
                },
                'ocr_confidence': {'type': 'float'},
                'structured_data': {
                    'type': 'object',
                    'properties': {
                        'medications': {
                            'type': 'nested',
                            'properties': {
                                'name': {
                                    'type': 'text',
                                    'analyzer': 'medical_analyzer',
                                    'fields': {
                                        'keyword': {'type': 'keyword'}
                                    }
                                },
                                'dosage': {'type': 'keyword'},
                                'frequency': {'type': 'keyword'},
                                'duration': {'type': 'keyword'},
                                'confidence': {'type': 'float'}
                            }
                        },
                        'diagnosis': {
                            'type': 'object',
                            'properties': {
                                'text': {
                                    'type': 'text',
                                    'analyzer': 'medical_analyzer'
                                },
                                'confidence': {'type': 'float'}
                            }
                        },
                        'lab_tests': {
                            'type': 'nested',
                            'properties': {
                                'name': {'type': 'keyword'},
                                'value': {'type': 'keyword'},
                                'unit': {'type': 'keyword'},
                                'reference_range': {'type': 'keyword'},
                                'is_abnormal': {'type': 'boolean'}
                            }
                        },
                        'patient_info': {
                            'type': 'object',
                            'properties': {
                                'name': {'type': 'keyword'},
                                'age': {'type': 'keyword'},
                                'gender': {'type': 'keyword'}
                            }
                        }
                    }
                },
                'created_at': {'type': 'date'},
                'updated_at': {'type': 'date'},
                'processing_completed_at': {'type': 'date'}
            }
        }
    
    def _get_analysis_settings(self) -> Dict:
        """Get analysis settings for medical text processing."""
        return {
            'analyzer': {
                'medical_analyzer': {
                    'type': 'custom',
                    'tokenizer': 'standard',
                    'filter': [
                        'lowercase',
                        'medical_synonyms',
                        'medical_stemmer'
                    ]
                }
            },
            'filter': {
                'medical_synonyms': {
                    'type': 'synonym',
                    'synonyms': [
                        'tab,tablet',
                        'cap,capsule',
                        'mg,milligram',
                        'ml,milliliter',
                        'od,once daily',
                        'bd,twice daily',
                        'tds,three times daily',
                        'qid,four times daily'
                    ]
                },
                'medical_stemmer': {
                    'type': 'stemmer',
                    'language': 'english'
                }
            }
        }
    
    def _prepare_clinical_record_document(self, record: ClinicalRecord) -> Dict:
        """Prepare clinical record for Elasticsearch indexing."""
        # Get related documents count
        document_count = record.clinicaldocument_set.count()
        has_structured_data = record.clinicaldocument_set.filter(
            structured_data__isnull=False
        ).exists()
        
        return {
            'id': str(record.id),
            'patient_id': str(record.patient.id),
            'clinic_id': str(record.clinic.id),
            'record_type': record.record_type,
            'title': record.title,
            'description': record.description,
            'tags': record.tags,
            'metadata': record.metadata,
            'confidentiality_level': record.confidentiality_level,
            'created_at': record.created_at.isoformat(),
            'updated_at': record.updated_at.isoformat(),
            'created_by': str(record.created_by.id) if record.created_by else None,
            'patient_name': f"{record.patient.user.first_name} {record.patient.user.last_name}".strip(),
            'patient_age': self._calculate_age(record.patient.date_of_birth) if record.patient.date_of_birth else None,
            'patient_gender': record.patient.gender,
            'document_count': document_count,
            'has_structured_data': has_structured_data
        }
    
    def _prepare_clinical_document_document(self, document: ClinicalDocument) -> Dict:
        """Prepare clinical document for Elasticsearch indexing."""
        return {
            'id': str(document.id),
            'clinical_record_id': str(document.clinical_record.id),
            'clinic_id': str(document.clinical_record.clinic.id),
            'patient_id': str(document.clinical_record.patient.id),
            'record_type': document.clinical_record.record_type,
            'original_filename': document.original_filename,
            'content_type': document.content_type,
            'file_size': document.file_size,
            'processing_status': document.processing_status,
            'ocr_text': document.ocr_text or '',
            'ocr_confidence': document.ocr_confidence,
            'structured_data': document.structured_data or {},
            'created_at': document.created_at.isoformat(),
            'updated_at': document.updated_at.isoformat(),
            'processing_completed_at': document.processing_completed_at.isoformat() if document.processing_completed_at else None
        }
    
    def _calculate_age(self, birth_date) -> int:
        """Calculate age from birth date."""
        if not birth_date:
            return None
        
        today = timezone.now().date()
        return today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
    
    def _build_clinical_records_query(
        self,
        query: str,
        clinic_id: str,
        filters: Optional[Dict],
        sort_by: str
    ) -> Dict:
        """Build Elasticsearch query for clinical records search."""
        # Base query with tenant isolation
        must_clauses = [
            {'term': {'clinic_id': clinic_id}}
        ]
        
        # Add text search
        if query:
            must_clauses.append({
                'multi_match': {
                    'query': query,
                    'fields': [
                        'title^3',
                        'description^2',
                        'patient_name^2',
                        'tags'
                    ],
                    'type': 'best_fields',
                    'fuzziness': 'AUTO'
                }
            })
        
        # Add filters
        if filters:
            if filters.get('record_type'):
                must_clauses.append({'term': {'record_type': filters['record_type']}})
            
            if filters.get('patient_id'):
                must_clauses.append({'term': {'patient_id': filters['patient_id']}})
            
            if filters.get('date_range'):
                date_range = filters['date_range']
                range_filter = {'range': {'created_at': {}}}
                if date_range.get('from'):
                    range_filter['range']['created_at']['gte'] = date_range['from']
                if date_range.get('to'):
                    range_filter['range']['created_at']['lte'] = date_range['to']
                must_clauses.append(range_filter)
            
            if filters.get('has_structured_data') is not None:
                must_clauses.append({'term': {'has_structured_data': filters['has_structured_data']}})
        
        # Build sort
        sort_options = {
            '_score': [{'_score': {'order': 'desc'}}],
            'created_at': [{'created_at': {'order': 'desc'}}],
            'updated_at': [{'updated_at': {'order': 'desc'}}],
            'title': [{'title.keyword': {'order': 'asc'}}]
        }
        
        search_body = {
            'query': {
                'bool': {
                    'must': must_clauses
                }
            },
            'sort': sort_options.get(sort_by, sort_options['_score']),
            'aggs': {
                'record_types': {
                    'terms': {'field': 'record_type'}
                },
                'patient_genders': {
                    'terms': {'field': 'patient_gender'}
                },
                'created_by_month': {
                    'date_histogram': {
                        'field': 'created_at',
                        'calendar_interval': 'month'
                    }
                }
            }
        }
        
        return search_body
    
    def _build_document_content_query(
        self,
        query: str,
        clinic_id: str,
        filters: Optional[Dict]
    ) -> Dict:
        """Build Elasticsearch query for document content search."""
        must_clauses = [
            {'term': {'clinic_id': clinic_id}}
        ]
        
        # Add content search
        if query:
            must_clauses.append({
                'multi_match': {
                    'query': query,
                    'fields': [
                        'ocr_text^3',
                        'structured_data.medications.name^2',
                        'structured_data.diagnosis.text^2',
                        'original_filename'
                    ],
                    'type': 'best_fields',
                    'fuzziness': 'AUTO'
                }
            })
        
        # Add filters
        if filters:
            if filters.get('record_type'):
                must_clauses.append({'term': {'record_type': filters['record_type']}})
            
            if filters.get('processing_status'):
                must_clauses.append({'term': {'processing_status': filters['processing_status']}})
            
            if filters.get('content_type'):
                must_clauses.append({'term': {'content_type': filters['content_type']}})
        
        return {
            'query': {
                'bool': {
                    'must': must_clauses
                }
            },
            'sort': [{'_score': {'order': 'desc'}}]
        }
    
    def _process_search_results(self, response: Dict) -> Dict:
        """Process Elasticsearch search response."""
        hits = []
        for hit in response['hits']['hits']:
            source = hit['_source']
            source['_score'] = hit['_score']
            hits.append(source)
        
        return {
            'hits': hits,
            'total': response['hits']['total']['value'],
            'aggregations': response.get('aggregations', {})
        }
    
    def _process_document_search_results(self, response: Dict) -> Dict:
        """Process document search results with highlights."""
        hits = []
        for hit in response['hits']['hits']:
            source = hit['_source']
            source['_score'] = hit['_score']
            
            # Add highlights
            if 'highlight' in hit:
                source['_highlights'] = hit['highlight']
            
            hits.append(source)
        
        return {
            'hits': hits,
            'total': response['hits']['total']['value']
        }
    
    def _get_medication_suggestions(self, query: str, clinic_id: str) -> List[str]:
        """Get medication name suggestions."""
        search_body = {
            'query': {
                'bool': {
                    'must': [
                        {'term': {'clinic_id': clinic_id}},
                        {'nested': {
                            'path': 'structured_data.medications',
                            'query': {
                                'match': {
                                    'structured_data.medications.name': {
                                        'query': query,
                                        'fuzziness': 'AUTO'
                                    }
                                }
                            }
                        }}
                    ]
                }
            },
            'aggs': {
                'medications': {
                    'nested': {'path': 'structured_data.medications'},
                    'aggs': {
                        'medication_names': {
                            'terms': {
                                'field': 'structured_data.medications.name.keyword',
                                'size': 10
                            }
                        }
                    }
                }
            },
            'size': 0
        }
        
        try:
            response = self.client.search(
                index=f"{self.index_prefix}_documents",
                body=search_body
            )
            
            suggestions = []
            if 'aggregations' in response:
                buckets = response['aggregations']['medications']['medication_names']['buckets']
                suggestions = [bucket['key'] for bucket in buckets]
            
            return suggestions
            
        except Exception as e:
            logger.error(f"Failed to get medication suggestions: {e}")
            return []
    
    def _get_diagnosis_suggestions(self, query: str, clinic_id: str) -> List[str]:
        """Get diagnosis suggestions."""
        # Similar implementation for diagnoses
        return []
    
    def _get_patient_suggestions(self, query: str, clinic_id: str) -> List[str]:
        """Get patient name suggestions."""
        # Similar implementation for patients
        return []
    
    def _get_record_type_distribution(self, clinic_id: str, date_range: Optional[Dict]) -> Dict:
        """Get distribution of record types."""
        # Implementation for analytics
        return {}
    
    def _get_processing_statistics(self, clinic_id: str, date_range: Optional[Dict]) -> Dict:
        """Get document processing statistics."""
        # Implementation for processing stats
        return {}
    
    def _get_top_medications(self, clinic_id: str, date_range: Optional[Dict]) -> List[Dict]:
        """Get top medications by frequency."""
        # Implementation for top medications
        return []
    
    def _get_top_diagnoses(self, clinic_id: str, date_range: Optional[Dict]) -> List[Dict]:
        """Get top diagnoses by frequency."""
        # Implementation for top diagnoses
        return []


# Singleton instance
elasticsearch_service = ElasticsearchService()