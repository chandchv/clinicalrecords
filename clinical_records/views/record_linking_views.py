"""
Views for record linking interface.

This module provides both web interface views and API endpoints
for linking clinical records to prescriptions, appointments, and other records.
"""

import json
import logging
from typing import Dict, Any

from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, Http404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views import View
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from users.models import Clinic, Patient
from ..models import ClinicalRecord, RecordRelationship
from ..services.record_linking_service import record_linking_service
from ..permissions.rest_permissions import CanViewRecords, CanEditRecords
from ..decorators.audit_decorators import audit_api_call

logger = logging.getLogger(__name__)


@method_decorator(login_required, name='dispatch')
class RecordLinkingView(View):
    """Web interface view for record linking."""
    
    def get(self, request, record_id):
        """Render the record linking interface."""
        try:
            record = get_object_or_404(ClinicalRecord, id=record_id)
            
            # Get existing relationships
            relationships = record_linking_service.get_record_relationships(
                record_id=str(record.id),
                user=request.user
            )
            
            # Get linkable entities
            linkable_entities = record_linking_service.get_linkable_entities(
                patient_id=str(record.patient.id),
                user=request.user,
                exclude_record_id=str(record.id)
            )
            
            # Get relationship suggestions
            suggestions = record_linking_service.get_relationship_suggestions(
                record_id=str(record.id),
                user=request.user
            )
            
            context = {
                'record': record,
                'relationships': relationships,
                'linkable_entities': linkable_entities,
                'suggestions': suggestions,
                'relationship_types': record_linking_service.relationship_types,
                'config': {
                    'api_base_url': '/api/clinical-records/',
                    'enable_drag_drop': True,
                    'enable_bulk_operations': True,
                    'auto_save': True
                }
            }
            
            return render(request, 'clinical_records/record_linking.html', context)
            
        except Exception as e:
            logger.error(f"Error in record linking view: {e}", exc_info=True)
            context = {
                'error': 'Failed to load record linking interface',
                'record_id': record_id
            }
            return render(request, 'clinical_records/linking_error.html', context, status=500)


@api_view(['GET'])
@permission_classes([IsAuthenticated, CanViewRecords])
def linkable_entities_api(request, patient_id):
    """
    API endpoint to get entities that can be linked to records.
    
    Args:
        patient_id: ID of the patient
    
    Query parameters:
        - type: Filter by entity type
        - exclude_record: Exclude specific record ID
        - limit: Limit number of results
    """
    try:
        entity_type = request.query_params.get('type')
        exclude_record_id = request.query_params.get('exclude_record')
        limit = int(request.query_params.get('limit', 50))
        
        entities = record_linking_service.get_linkable_entities(
            patient_id=patient_id,
            user=request.user,
            entity_type=entity_type,
            exclude_record_id=exclude_record_id
        )
        
        # Apply limit
        entities = entities[:limit]
        
        return Response({
            'entities': entities,
            'total_count': len(entities),
            'entity_types': list(record_linking_service.linkable_types.keys())
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"Error getting linkable entities: {e}")
        return Response(
            {'error': 'Failed to get linkable entities'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated, CanViewRecords])
def record_relationships_api(request, record_id):
    """
    API endpoint to get relationships for a clinical record.
    
    Args:
        record_id: ID of the clinical record
    """
    try:
        relationships = record_linking_service.get_record_relationships(
            record_id=record_id,
            user=request.user
        )
        
        return Response(relationships, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"Error getting record relationships: {e}")
        return Response(
            {'error': 'Failed to get record relationships'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated, CanEditRecords])
@audit_api_call
def create_relationship_api(request):
    """
    API endpoint to create a relationship between records.
    
    Expected payload:
    {
        "source_record_id": "uuid",
        "target_entity_id": "uuid",
        "target_entity_type": "clinical_record|prescription|appointment",
        "relationship_type": "RELATED_TO|FOLLOWS_UP|...",
        "notes": "optional notes"
    }
    """
    try:
        data = request.data
        
        # Validate required fields
        required_fields = ['source_record_id', 'target_entity_id', 'target_entity_type', 'relationship_type']
        for field in required_fields:
            if field not in data:
                return Response(
                    {'error': f'Missing required field: {field}'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        # Validate relationship type
        if data['relationship_type'] not in record_linking_service.relationship_types:
            return Response(
                {'error': 'Invalid relationship type'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Create relationship
        result = record_linking_service.create_relationship(
            source_record_id=data['source_record_id'],
            target_entity_id=data['target_entity_id'],
            target_entity_type=data['target_entity_type'],
            relationship_type=data['relationship_type'],
            user=request.user,
            notes=data.get('notes')
        )
        
        if result['success']:
            return Response(result, status=status.HTTP_201_CREATED)
        else:
            return Response(result, status=status.HTTP_400_BAD_REQUEST)
        
    except Exception as e:
        logger.error(f"Error creating relationship: {e}")
        return Response(
            {'error': 'Failed to create relationship'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['DELETE'])
@permission_classes([IsAuthenticated, CanEditRecords])
@audit_api_call
def delete_relationship_api(request, relationship_id):
    """
    API endpoint to delete a relationship.
    
    Args:
        relationship_id: ID of the relationship to delete
    """
    try:
        result = record_linking_service.delete_relationship(
            relationship_id=relationship_id,
            user=request.user
        )
        
        if result['success']:
            return Response(result, status=status.HTTP_200_OK)
        else:
            return Response(result, status=status.HTTP_400_BAD_REQUEST)
        
    except Exception as e:
        logger.error(f"Error deleting relationship: {e}")
        return Response(
            {'error': 'Failed to delete relationship'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated, CanViewRecords])
def relationship_suggestions_api(request, record_id):
    """
    API endpoint to get relationship suggestions for a record.
    
    Args:
        record_id: ID of the clinical record
    """
    try:
        suggestions = record_linking_service.get_relationship_suggestions(
            record_id=record_id,
            user=request.user
        )
        
        return Response({
            'suggestions': suggestions,
            'count': len(suggestions)
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"Error getting relationship suggestions: {e}")
        return Response(
            {'error': 'Failed to get relationship suggestions'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated, CanViewRecords])
def relationship_history_api(request, patient_id):
    """
    API endpoint to get relationship history for a patient.
    
    Args:
        patient_id: ID of the patient
    
    Query parameters:
        - days: Number of days to look back (default: 30)
    """
    try:
        days = int(request.query_params.get('days', 30))
        
        history = record_linking_service.get_relationship_history(
            patient_id=patient_id,
            user=request.user,
            days=days
        )
        
        return Response({
            'history': history,
            'count': len(history),
            'days': days
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"Error getting relationship history: {e}")
        return Response(
            {'error': 'Failed to get relationship history'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated, CanEditRecords])
@audit_api_call
def bulk_create_relationships_api(request):
    """
    API endpoint to create multiple relationships at once.
    
    Expected payload:
    {
        "relationships": [
            {
                "source_record_id": "uuid",
                "target_entity_id": "uuid",
                "target_entity_type": "clinical_record",
                "relationship_type": "RELATED_TO",
                "notes": "optional"
            },
            ...
        ]
    }
    """
    try:
        data = request.data
        
        if 'relationships' not in data or not isinstance(data['relationships'], list):
            return Response(
                {'error': 'Invalid payload: relationships array required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        results = []
        success_count = 0
        error_count = 0
        
        for rel_data in data['relationships']:
            # Validate required fields
            required_fields = ['source_record_id', 'target_entity_id', 'target_entity_type', 'relationship_type']
            missing_fields = [field for field in required_fields if field not in rel_data]
            
            if missing_fields:
                results.append({
                    'success': False,
                    'error': f'Missing required fields: {", ".join(missing_fields)}',
                    'data': rel_data
                })
                error_count += 1
                continue
            
            # Create relationship
            result = record_linking_service.create_relationship(
                source_record_id=rel_data['source_record_id'],
                target_entity_id=rel_data['target_entity_id'],
                target_entity_type=rel_data['target_entity_type'],
                relationship_type=rel_data['relationship_type'],
                user=request.user,
                notes=rel_data.get('notes')
            )
            
            results.append(result)
            if result['success']:
                success_count += 1
            else:
                error_count += 1
        
        return Response({
            'results': results,
            'summary': {
                'total': len(data['relationships']),
                'success': success_count,
                'errors': error_count
            }
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"Error in bulk create relationships: {e}")
        return Response(
            {'error': 'Failed to create relationships'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated, CanViewRecords])
def relationship_types_api(request):
    """
    API endpoint to get available relationship types.
    """
    try:
        return Response({
            'relationship_types': record_linking_service.relationship_types,
            'linkable_types': record_linking_service.linkable_types
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"Error getting relationship types: {e}")
        return Response(
            {'error': 'Failed to get relationship types'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@method_decorator(login_required, name='dispatch')
class RelationshipMapView(View):
    """Visual relationship mapping view."""
    
    def get(self, request, patient_id):
        """Render the relationship map interface."""
        try:
            patient = get_object_or_404(Patient, id=patient_id)
            
            # Get relationship history
            history = record_linking_service.get_relationship_history(
                patient_id=str(patient.id),
                user=request.user,
                days=90  # Show 3 months of history
            )
            
            # Get all records for the patient
            records = ClinicalRecord.objects.filter(
                patient=patient,
                clinic=request.user.clinic
            ).order_by('-created_at')[:50]  # Limit for performance
            
            context = {
                'patient': patient,
                'records': records,
                'relationship_history': history,
                'config': {
                    'enable_interactive_map': True,
                    'show_timeline': True,
                    'group_by_type': True
                }
            }
            
            return render(request, 'clinical_records/relationship_map.html', context)
            
        except Exception as e:
            logger.error(f"Error in relationship map view: {e}", exc_info=True)
            context = {
                'error': 'Failed to load relationship map',
                'patient_id': patient_id
            }
            return render(request, 'clinical_records/linking_error.html', context, status=500)


@method_decorator(login_required, name='dispatch')
class BulkLinkingView(View):
    """Bulk linking interface view."""
    
    def get(self, request, patient_id):
        """Render the bulk linking interface."""
        try:
            patient = get_object_or_404(Patient, id=patient_id)
            
            # Get all records for the patient
            records = ClinicalRecord.objects.filter(
                patient=patient,
                clinic=request.user.clinic
            ).order_by('-created_at')
            
            # Get linkable entities
            linkable_entities = record_linking_service.get_linkable_entities(
                patient_id=str(patient.id),
                user=request.user
            )
            
            context = {
                'patient': patient,
                'records': records,
                'linkable_entities': linkable_entities,
                'relationship_types': record_linking_service.relationship_types,
                'config': {
                    'enable_multi_select': True,
                    'enable_batch_operations': True,
                    'auto_suggest': True
                }
            }
            
            return render(request, 'clinical_records/bulk_linking.html', context)
            
        except Exception as e:
            logger.error(f"Error in bulk linking view: {e}", exc_info=True)
            context = {
                'error': 'Failed to load bulk linking interface',
                'patient_id': patient_id
            }
            return render(request, 'clinical_records/linking_error.html', context, status=500)