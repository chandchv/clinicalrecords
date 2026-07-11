"""
Record Relationship Management API Views

This module provides REST API endpoints for managing relationships between
clinical records, prescriptions, and appointments.
"""
import logging
from django.db.models import Q, Prefetch
from django.http import Http404
from django.core.exceptions import ValidationError
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError as DRFValidationError

from ..models import ClinicalRecord, RecordRelationship
from ..serializers import RecordRelationshipSerializer, RecordRelationshipCreateSerializer
from ..permissions import ClinicalRecordPermission
from users.models import AuditLog

logger = logging.getLogger(__name__)


class RecordRelationshipViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing record relationships with tenant filtering.
    
    Provides CRUD operations for relationships between clinical records,
    prescriptions, and appointments with proper tenant isolation.
    """
    serializer_class = RecordRelationshipSerializer
    permission_classes = [permissions.IsAuthenticated, ClinicalRecordPermission]
    
    def get_queryset(self):
        """Get relationships filtered by tenant"""
        user = self.request.user
        if not hasattr(user, 'current_tenant') or not user.current_tenant:
            return RecordRelationship.objects.none()
        
        return RecordRelationship.objects.filter(
            clinic=user.current_tenant,
            is_active=True
        ).select_related(
            'source_record', 'target_record', 'created_by'
        ).prefetch_related(
            'source_record__patient',
            'target_record__patient'
        )
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action"""
        if self.action == 'create':
            return RecordRelationshipCreateSerializer
        return RecordRelationshipSerializer
    
    def perform_create(self, serializer):
        """Create relationship with proper tenant and user context"""
        user = self.request.user
        
        # Set the clinic from user's current tenant
        serializer.save(
            created_by=user,
            clinic=user.current_tenant
        )
        
        # Log the creation
        relationship = serializer.instance
        AuditLog.log_action(
            user=user,
            action='RECORD_RELATIONSHIP_CREATED',
            resource_type='RECORD_RELATIONSHIP',
            resource_id=str(relationship.id),
            details={
                'source_record_id': str(relationship.source_record.id),
                'target_summary': relationship.target_summary,
                'relationship_type': relationship.relationship_type,
                'strength': relationship.strength
            },
            tenant=user.current_tenant
        )
    
    def perform_update(self, serializer):
        """Update relationship with audit logging"""
        user = self.request.user
        old_instance = self.get_object()
        
        # Store old values for audit
        old_values = {
            'relationship_type': old_instance.relationship_type,
            'strength': old_instance.strength,
            'confidence': old_instance.confidence,
            'notes': old_instance.notes
        }
        
        serializer.save()
        
        # Log the update
        relationship = serializer.instance
        AuditLog.log_action(
            user=user,
            action='RECORD_RELATIONSHIP_UPDATED',
            resource_type='RECORD_RELATIONSHIP',
            resource_id=str(relationship.id),
            details={
                'old_values': old_values,
                'new_values': {
                    'relationship_type': relationship.relationship_type,
                    'strength': relationship.strength,
                    'confidence': relationship.confidence,
                    'notes': relationship.notes
                }
            },
            tenant=user.current_tenant
        )
    
    def perform_destroy(self, instance):
        """Soft delete relationship instead of hard delete"""
        user = self.request.user
        
        # Deactivate instead of delete
        instance.deactivate(deactivated_by=user, reason="Deleted via API")
        
        # Log the deletion
        AuditLog.log_action(
            user=user,
            action='RECORD_RELATIONSHIP_DELETED',
            resource_type='RECORD_RELATIONSHIP',
            resource_id=str(instance.id),
            details={
                'source_record_id': str(instance.source_record.id),
                'target_summary': instance.target_summary,
                'relationship_type': instance.relationship_type
            },
            tenant=user.current_tenant
        )
    
    @action(detail=False, methods=['get'])
    def by_record(self, request):
        """Get all relationships for a specific clinical record"""
        record_id = request.query_params.get('record_id')
        if not record_id:
            return Response(
                {'error': 'record_id parameter is required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Verify the record exists and user has access
            record = ClinicalRecord.objects.get(
                id=record_id,
                clinic=request.user.current_tenant,
                is_active=True
            )
        except ClinicalRecord.DoesNotExist:
            raise Http404("Clinical record not found")
        
        # Get all relationships for this record
        relationships = RecordRelationship.get_related_records(
            record, include_inactive=False
        )
        
        serializer = self.get_serializer(relationships, many=True)
        return Response({
            'record': {
                'id': str(record.id),
                'title': record.title,
                'record_type': record.get_record_type_display()
            },
            'relationships': serializer.data
        })
    
    @action(detail=False, methods=['post'])
    def create_record_to_record(self, request):
        """Create a relationship between two clinical records"""
        source_id = request.data.get('source_record_id')
        target_id = request.data.get('target_record_id')
        relationship_type = request.data.get('relationship_type')
        
        if not all([source_id, target_id, relationship_type]):
            return Response(
                {'error': 'source_record_id, target_record_id, and relationship_type are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Verify both records exist and user has access
            source_record = ClinicalRecord.objects.get(
                id=source_id,
                clinic=request.user.current_tenant,
                is_active=True
            )
            target_record = ClinicalRecord.objects.get(
                id=target_id,
                clinic=request.user.current_tenant,
                is_active=True
            )
        except ClinicalRecord.DoesNotExist:
            return Response(
                {'error': 'One or both clinical records not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Check if relationship already exists
        existing = RecordRelationship.objects.filter(
            source_record=source_record,
            target_record=target_record,
            relationship_type=relationship_type,
            is_active=True
        ).exists()
        
        if existing:
            return Response(
                {'error': 'Relationship already exists'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Create the relationship
        try:
            relationship = RecordRelationship.create_record_to_record_relationship(
                source_record=source_record,
                target_record=target_record,
                relationship_type=relationship_type,
                created_by=request.user,
                notes=request.data.get('notes', ''),
                strength=request.data.get('strength', 'moderate'),
                confidence=request.data.get('confidence', 1.0),
                create_reverse=request.data.get('create_reverse', False)
            )
            
            # Handle tuple return if reverse relationship was created
            if isinstance(relationship, tuple):
                relationship, reverse_relationship = relationship
                serializer = self.get_serializer([relationship, reverse_relationship], many=True)
                return Response({
                    'message': 'Bidirectional relationships created successfully',
                    'relationships': serializer.data
                }, status=status.HTTP_201_CREATED)
            else:
                serializer = self.get_serializer(relationship)
                return Response({
                    'message': 'Relationship created successfully',
                    'relationship': serializer.data
                }, status=status.HTTP_201_CREATED)
                
        except Exception as e:
            logger.error(f"Error creating record relationship: {e}")
            return Response(
                {'error': 'Failed to create relationship'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['post'])
    def create_record_to_prescription(self, request):
        """Create a relationship between a clinical record and a prescription"""
        record_id = request.data.get('record_id')
        prescription_id = request.data.get('prescription_id')
        relationship_type = request.data.get('relationship_type')
        
        if not all([record_id, prescription_id, relationship_type]):
            return Response(
                {'error': 'record_id, prescription_id, and relationship_type are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Verify the record exists and user has access
            record = ClinicalRecord.objects.get(
                id=record_id,
                clinic=request.user.current_tenant,
                is_active=True
            )
        except ClinicalRecord.DoesNotExist:
            return Response(
                {'error': 'Clinical record not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Check if relationship already exists
        existing = RecordRelationship.objects.filter(
            source_record=record,
            prescription_id=prescription_id,
            relationship_type=relationship_type,
            is_active=True
        ).exists()
        
        if existing:
            return Response(
                {'error': 'Relationship already exists'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Create the relationship
        try:
            relationship = RecordRelationship.objects.create(
                source_record=record,
                prescription_id=prescription_id,
                relationship_type=relationship_type,
                created_by=request.user,
                clinic=request.user.current_tenant,
                notes=request.data.get('notes', ''),
                strength=request.data.get('strength', 'moderate'),
                confidence=request.data.get('confidence', 1.0)
            )
            
            serializer = self.get_serializer(relationship)
            return Response({
                'message': 'Record-to-prescription relationship created successfully',
                'relationship': serializer.data
            }, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            logger.error(f"Error creating record-to-prescription relationship: {e}")
            return Response(
                {'error': 'Failed to create relationship'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['post'])
    def create_record_to_appointment(self, request):
        """Create a relationship between a clinical record and an appointment"""
        record_id = request.data.get('record_id')
        appointment_id = request.data.get('appointment_id')
        relationship_type = request.data.get('relationship_type')
        
        if not all([record_id, appointment_id, relationship_type]):
            return Response(
                {'error': 'record_id, appointment_id, and relationship_type are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Verify the record exists and user has access
            record = ClinicalRecord.objects.get(
                id=record_id,
                clinic=request.user.current_tenant,
                is_active=True
            )
        except ClinicalRecord.DoesNotExist:
            return Response(
                {'error': 'Clinical record not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Check if relationship already exists
        existing = RecordRelationship.objects.filter(
            source_record=record,
            appointment_id=appointment_id,
            relationship_type=relationship_type,
            is_active=True
        ).exists()
        
        if existing:
            return Response(
                {'error': 'Relationship already exists'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Create the relationship
        try:
            relationship = RecordRelationship.objects.create(
                source_record=record,
                appointment_id=appointment_id,
                relationship_type=relationship_type,
                created_by=request.user,
                clinic=request.user.current_tenant,
                notes=request.data.get('notes', ''),
                strength=request.data.get('strength', 'moderate'),
                confidence=request.data.get('confidence', 1.0)
            )
            
            serializer = self.get_serializer(relationship)
            return Response({
                'message': 'Record-to-appointment relationship created successfully',
                'relationship': serializer.data
            }, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            logger.error(f"Error creating record-to-appointment relationship: {e}")
            return Response(
                {'error': 'Failed to create relationship'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        """Deactivate a relationship"""
        relationship = self.get_object()
        reason = request.data.get('reason', 'Deactivated via API')
        
        relationship.deactivate(deactivated_by=request.user, reason=reason)
        
        return Response({
            'message': 'Relationship deactivated successfully',
            'relationship_id': str(relationship.id)
        })
    
    @action(detail=True, methods=['post'])
    def reactivate(self, request, pk=None):
        """Reactivate a relationship"""
        relationship = self.get_object()
        reason = request.data.get('reason', 'Reactivated via API')
        
        relationship.reactivate(reactivated_by=request.user, reason=reason)
        
        return Response({
            'message': 'Relationship reactivated successfully',
            'relationship_id': str(relationship.id)
        })
    
    @action(detail=True, methods=['patch'])
    def update_strength(self, request, pk=None):
        """Update the strength of a relationship"""
        relationship = self.get_object()
        new_strength = request.data.get('strength')
        reason = request.data.get('reason', '')
        
        if not new_strength:
            return Response(
                {'error': 'strength parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if new_strength not in ['weak', 'moderate', 'strong']:
            return Response(
                {'error': 'strength must be one of: weak, moderate, strong'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        relationship.update_strength(
            new_strength=new_strength,
            updated_by=request.user,
            reason=reason
        )
        
        serializer = self.get_serializer(relationship)
        return Response({
            'message': 'Relationship strength updated successfully',
            'relationship': serializer.data
        })
    
    @action(detail=False, methods=['get'])
    def relationship_history(self, request):
        """Get relationship history for a clinical record"""
        record_id = request.query_params.get('record_id')
        if not record_id:
            return Response(
                {'error': 'record_id parameter is required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Verify the record exists and user has access
            record = ClinicalRecord.objects.get(
                id=record_id,
                clinic=request.user.current_tenant
            )
        except ClinicalRecord.DoesNotExist:
            raise Http404("Clinical record not found")
        
        # Get all relationships (including inactive) for history
        relationships = RecordRelationship.get_related_records(
            record, include_inactive=True
        ).order_by('-created_at')
        
        serializer = self.get_serializer(relationships, many=True)
        return Response({
            'record': {
                'id': str(record.id),
                'title': record.title,
                'record_type': record.get_record_type_display()
            },
            'relationship_history': serializer.data
        })
    
    @action(detail=False, methods=['get'])
    def bidirectional_query(self, request):
        """Query relationships bidirectionally for a record"""
        record_id = request.query_params.get('record_id')
        relationship_types = request.query_params.getlist('relationship_type')
        
        if not record_id:
            return Response(
                {'error': 'record_id parameter is required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Verify the record exists and user has access
            record = ClinicalRecord.objects.get(
                id=record_id,
                clinic=request.user.current_tenant,
                is_active=True
            )
        except ClinicalRecord.DoesNotExist:
            raise Http404("Clinical record not found")
        
        # Build query for bidirectional relationships
        query = Q(source_record=record) | Q(target_record=record)
        
        if relationship_types:
            query &= Q(relationship_type__in=relationship_types)
        
        relationships = RecordRelationship.objects.filter(
            query,
            clinic=request.user.current_tenant,
            is_active=True
        ).select_related(
            'source_record', 'target_record', 'created_by'
        ).order_by('-created_at')
        
        # Organize results by direction
        outgoing = []
        incoming = []
        
        for rel in relationships:
            serialized = self.get_serializer(rel).data
            if rel.source_record == record:
                outgoing.append(serialized)
            else:
                incoming.append(serialized)
        
        return Response({
            'record': {
                'id': str(record.id),
                'title': record.title,
                'record_type': record.get_record_type_display()
            },
            'outgoing_relationships': outgoing,
            'incoming_relationships': incoming,
            'total_count': len(outgoing) + len(incoming)
        })