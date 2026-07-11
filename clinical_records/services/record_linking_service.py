"""
Record linking service for clinical records.

This service handles linking clinical records to prescriptions, appointments,
and other related entities with visual relationship mapping and history tracking.
"""

import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
from django.db import transaction
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db.models import Q, Count, Prefetch

from users.models import Clinic, Patient
from ..models import ClinicalRecord, RecordRelationship
from .audit_service import audit_service
from .access_control_service import access_control_service

# Import related models from other apps
try:
    from scheduling.models import Appointment
except ImportError:
    Appointment = None

try:
    from pharmacy.models import Prescription
except ImportError:
    Prescription = None

User = get_user_model()
logger = logging.getLogger(__name__)


class RecordLinkingService:
    """Service for managing clinical record relationships and linking."""
    
    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        
        # Define linkable entity types
        self.linkable_types = {
            'prescription': {
                'model': Prescription,
                'display_name': 'Prescription',
                'icon': 'fas fa-pills',
                'color': '#28a745'
            },
            'appointment': {
                'model': Appointment,
                'display_name': 'Appointment',
                'icon': 'fas fa-calendar-check',
                'color': '#007bff'
            },
            'clinical_record': {
                'model': ClinicalRecord,
                'display_name': 'Clinical Record',
                'icon': 'fas fa-file-medical',
                'color': '#6c757d'
            }
        }
        
        # Relationship types
        self.relationship_types = {
            'RELATED_TO': 'Related to',
            'FOLLOWS_UP': 'Follows up',
            'REFERENCES': 'References',
            'SUPERSEDES': 'Supersedes',
            'AMENDS': 'Amends',
            'DERIVED_FROM': 'Derived from',
            'SUPPORTS': 'Supports'
        }
    
    def get_linkable_entities(self, patient_id: str, user: User, 
                            entity_type: Optional[str] = None,
                            exclude_record_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get entities that can be linked to clinical records.
        
        Args:
            patient_id: ID of the patient
            user: User requesting the data
            entity_type: Filter by specific entity type
            exclude_record_id: Exclude specific record from results
            
        Returns:
            List of linkable entities
        """
        try:
            entities = []
            
            # Get patient
            patient = Patient.objects.get(id=patient_id)
            
            # Check access
            has_access, _ = access_control_service.check_patient_access(
                user=user,
                patient=patient,
                action='view'
            )
            
            if not has_access:
                return []
            
            # Get prescriptions if available and requested
            if (not entity_type or entity_type == 'prescription') and Prescription:
                prescriptions = Prescription.objects.filter(
                    patient=patient,
                    clinic=user.clinic
                ).order_by('-created_at')[:50]  # Limit results
                
                for prescription in prescriptions:
                    entities.append({
                        'id': str(prescription.id),
                        'type': 'prescription',
                        'title': f"Prescription - {prescription.created_at.strftime('%Y-%m-%d')}",
                        'subtitle': f"Dr. {prescription.doctor.get_full_name()}" if prescription.doctor else "",
                        'date': prescription.created_at.isoformat(),
                        'status': getattr(prescription, 'status', 'active'),
                        'icon': self.linkable_types['prescription']['icon'],
                        'color': self.linkable_types['prescription']['color'],
                        'metadata': {
                            'doctor': prescription.doctor.get_full_name() if prescription.doctor else None,
                            'medications_count': getattr(prescription, 'medications', []).count() if hasattr(prescription, 'medications') else 0
                        }
                    })
            
            # Get appointments if available and requested
            if (not entity_type or entity_type == 'appointment') and Appointment:
                appointments = Appointment.objects.filter(
                    patient=patient,
                    clinic=user.clinic
                ).order_by('-appointment_date')[:50]  # Limit results
                
                for appointment in appointments:
                    entities.append({
                        'id': str(appointment.id),
                        'type': 'appointment',
                        'title': f"Appointment - {appointment.appointment_date.strftime('%Y-%m-%d %H:%M')}",
                        'subtitle': f"Dr. {appointment.doctor.get_full_name()}" if appointment.doctor else "",
                        'date': appointment.appointment_date.isoformat(),
                        'status': getattr(appointment, 'status', 'scheduled'),
                        'icon': self.linkable_types['appointment']['icon'],
                        'color': self.linkable_types['appointment']['color'],
                        'metadata': {
                            'doctor': appointment.doctor.get_full_name() if appointment.doctor else None,
                            'duration': getattr(appointment, 'duration', 30),
                            'type': getattr(appointment, 'appointment_type', 'consultation')
                        }
                    })
            
            # Get other clinical records if requested
            if not entity_type or entity_type == 'clinical_record':
                records_query = ClinicalRecord.objects.filter(
                    patient=patient,
                    clinic=user.clinic
                ).order_by('-created_at')
                
                if exclude_record_id:
                    records_query = records_query.exclude(id=exclude_record_id)
                
                records = records_query[:50]  # Limit results
                
                for record in records:
                    entities.append({
                        'id': str(record.id),
                        'type': 'clinical_record',
                        'title': record.title,
                        'subtitle': f"{record.get_record_type_display()} - {record.created_at.strftime('%Y-%m-%d')}",
                        'date': record.created_at.isoformat(),
                        'status': 'active',
                        'icon': self.linkable_types['clinical_record']['icon'],
                        'color': self.linkable_types['clinical_record']['color'],
                        'metadata': {
                            'record_type': record.record_type,
                            'created_by': record.created_by.get_full_name() if record.created_by else None,
                            'documents_count': record.documents.count()
                        }
                    })
            
            # Sort by date (most recent first)
            entities.sort(key=lambda x: x['date'], reverse=True)
            
            return entities
            
        except Exception as e:
            self.logger.error(f"Error getting linkable entities: {e}")
            return []
    
    def get_record_relationships(self, record_id: str, user: User) -> Dict[str, Any]:
        """
        Get all relationships for a clinical record.
        
        Args:
            record_id: ID of the clinical record
            user: User requesting the data
            
        Returns:
            Dictionary containing relationship data
        """
        try:
            # Get record
            record = ClinicalRecord.objects.select_related(
                'patient', 'clinic', 'created_by'
            ).get(id=record_id)
            
            # Check access
            has_access, _ = access_control_service.check_record_access(
                user=user,
                record=record,
                action='view'
            )
            
            if not has_access:
                return {'relationships': [], 'total_count': 0}
            
            # Get relationships where this record is the source
            outgoing_relationships = RecordRelationship.objects.filter(
                source_record=record
            ).select_related(
                'target_record', 'created_by'
            ).order_by('-created_at')
            
            # Get relationships where this record is the target
            incoming_relationships = RecordRelationship.objects.filter(
                target_record=record
            ).select_related(
                'source_record', 'created_by'
            ).order_by('-created_at')
            
            relationships = []
            
            # Process outgoing relationships
            for rel in outgoing_relationships:
                relationships.append({
                    'id': str(rel.id),
                    'type': rel.relationship_type,
                    'type_display': self.relationship_types.get(rel.relationship_type, rel.relationship_type),
                    'direction': 'outgoing',
                    'related_entity': {
                        'id': str(rel.target_record.id),
                        'type': 'clinical_record',
                        'title': rel.target_record.title,
                        'subtitle': f"{rel.target_record.get_record_type_display()} - {rel.target_record.created_at.strftime('%Y-%m-%d')}",
                        'date': rel.target_record.created_at.isoformat(),
                        'icon': self.linkable_types['clinical_record']['icon'],
                        'color': self.linkable_types['clinical_record']['color']
                    },
                    'created_at': rel.created_at.isoformat(),
                    'created_by': rel.created_by.get_full_name() if rel.created_by else None,
                    'notes': rel.notes
                })
            
            # Process incoming relationships
            for rel in incoming_relationships:
                relationships.append({
                    'id': str(rel.id),
                    'type': rel.relationship_type,
                    'type_display': self.relationship_types.get(rel.relationship_type, rel.relationship_type),
                    'direction': 'incoming',
                    'related_entity': {
                        'id': str(rel.source_record.id),
                        'type': 'clinical_record',
                        'title': rel.source_record.title,
                        'subtitle': f"{rel.source_record.get_record_type_display()} - {rel.source_record.created_at.strftime('%Y-%m-%d')}",
                        'date': rel.source_record.created_at.isoformat(),
                        'icon': self.linkable_types['clinical_record']['icon'],
                        'color': self.linkable_types['clinical_record']['color']
                    },
                    'created_at': rel.created_at.isoformat(),
                    'created_by': rel.created_by.get_full_name() if rel.created_by else None,
                    'notes': rel.notes
                })
            
            # Sort by creation date (most recent first)
            relationships.sort(key=lambda x: x['created_at'], reverse=True)
            
            return {
                'relationships': relationships,
                'total_count': len(relationships),
                'outgoing_count': len(outgoing_relationships),
                'incoming_count': len(incoming_relationships)
            }
            
        except ClinicalRecord.DoesNotExist:
            return {'relationships': [], 'total_count': 0}
        except Exception as e:
            self.logger.error(f"Error getting record relationships: {e}")
            return {'relationships': [], 'total_count': 0}
    
    @transaction.atomic
    def create_relationship(self, source_record_id: str, target_entity_id: str,
                          target_entity_type: str, relationship_type: str,
                          user: User, notes: Optional[str] = None) -> Dict[str, Any]:
        """
        Create a relationship between a clinical record and another entity.
        
        Args:
            source_record_id: ID of the source clinical record
            target_entity_id: ID of the target entity
            target_entity_type: Type of target entity
            relationship_type: Type of relationship
            user: User creating the relationship
            notes: Optional notes about the relationship
            
        Returns:
            Result dictionary with success status and relationship data
        """
        try:
            # Get source record
            source_record = ClinicalRecord.objects.get(id=source_record_id)
            
            # Check access to source record
            has_access, access_reason = access_control_service.check_record_access(
                user=user,
                record=source_record,
                action='edit'
            )
            
            if not has_access:
                return {
                    'success': False,
                    'error': f'Access denied to source record: {access_reason}'
                }
            
            # Handle different target entity types
            if target_entity_type == 'clinical_record':
                # Get target record
                target_record = ClinicalRecord.objects.get(id=target_entity_id)
                
                # Check access to target record
                has_target_access, target_access_reason = access_control_service.check_record_access(
                    user=user,
                    record=target_record,
                    action='view'
                )
                
                if not has_target_access:
                    return {
                        'success': False,
                        'error': f'Access denied to target record: {target_access_reason}'
                    }
                
                # Check if relationship already exists
                existing_relationship = RecordRelationship.objects.filter(
                    source_record=source_record,
                    target_record=target_record,
                    relationship_type=relationship_type
                ).first()
                
                if existing_relationship:
                    return {
                        'success': False,
                        'error': 'Relationship already exists'
                    }
                
                # Create relationship
                relationship = RecordRelationship.objects.create(
                    source_record=source_record,
                    target_record=target_record,
                    relationship_type=relationship_type,
                    notes=notes,
                    created_by=user
                )
                
                # Log the relationship creation
                audit_service.log_clinical_action(
                    action='RECORD_RELATIONSHIP_CREATED',
                    user=user,
                    resource_type='RECORD_RELATIONSHIP',
                    resource_id=str(relationship.id),
                    clinic=source_record.clinic,
                    patient_id=str(source_record.patient.id),
                    details={
                        'source_record_id': str(source_record.id),
                        'target_record_id': str(target_record.id),
                        'relationship_type': relationship_type,
                        'notes': notes
                    }
                )
                
                return {
                    'success': True,
                    'relationship': {
                        'id': str(relationship.id),
                        'type': relationship_type,
                        'type_display': self.relationship_types.get(relationship_type, relationship_type),
                        'target_entity': {
                            'id': str(target_record.id),
                            'type': 'clinical_record',
                            'title': target_record.title,
                            'subtitle': f"{target_record.get_record_type_display()} - {target_record.created_at.strftime('%Y-%m-%d')}"
                        },
                        'created_at': relationship.created_at.isoformat(),
                        'created_by': user.get_full_name(),
                        'notes': notes
                    }
                }
            
            else:
                # Handle other entity types (prescriptions, appointments)
                # For now, we'll store these as metadata in the relationship
                # This would need to be extended based on actual models
                return {
                    'success': False,
                    'error': f'Linking to {target_entity_type} not yet implemented'
                }
                
        except ClinicalRecord.DoesNotExist:
            return {
                'success': False,
                'error': 'Clinical record not found'
            }
        except Exception as e:
            self.logger.error(f"Error creating relationship: {e}")
            return {
                'success': False,
                'error': 'Failed to create relationship'
            }
    
    @transaction.atomic
    def delete_relationship(self, relationship_id: str, user: User) -> Dict[str, Any]:
        """
        Delete a relationship between records.
        
        Args:
            relationship_id: ID of the relationship to delete
            user: User deleting the relationship
            
        Returns:
            Result dictionary with success status
        """
        try:
            # Get relationship
            relationship = RecordRelationship.objects.select_related(
                'source_record', 'target_record'
            ).get(id=relationship_id)
            
            # Check access to source record
            has_access, access_reason = access_control_service.check_record_access(
                user=user,
                record=relationship.source_record,
                action='edit'
            )
            
            if not has_access:
                return {
                    'success': False,
                    'error': f'Access denied: {access_reason}'
                }
            
            # Store relationship data for audit log
            relationship_data = {
                'source_record_id': str(relationship.source_record.id),
                'target_record_id': str(relationship.target_record.id),
                'relationship_type': relationship.relationship_type,
                'notes': relationship.notes
            }
            
            # Delete relationship
            relationship.delete()
            
            # Log the relationship deletion
            audit_service.log_clinical_action(
                action='RECORD_RELATIONSHIP_DELETED',
                user=user,
                resource_type='RECORD_RELATIONSHIP',
                resource_id=relationship_id,
                clinic=relationship.source_record.clinic,
                patient_id=str(relationship.source_record.patient.id),
                details=relationship_data
            )
            
            return {
                'success': True,
                'message': 'Relationship deleted successfully'
            }
            
        except RecordRelationship.DoesNotExist:
            return {
                'success': False,
                'error': 'Relationship not found'
            }
        except Exception as e:
            self.logger.error(f"Error deleting relationship: {e}")
            return {
                'success': False,
                'error': 'Failed to delete relationship'
            }
    
    def get_relationship_suggestions(self, record_id: str, user: User) -> List[Dict[str, Any]]:
        """
        Get suggested relationships for a clinical record based on various factors.
        
        Args:
            record_id: ID of the clinical record
            user: User requesting suggestions
            
        Returns:
            List of suggested relationships
        """
        try:
            # Get record
            record = ClinicalRecord.objects.select_related('patient').get(id=record_id)
            
            # Check access
            has_access, _ = access_control_service.check_record_access(
                user=user,
                record=record,
                action='view'
            )
            
            if not has_access:
                return []
            
            suggestions = []
            
            # Get recent records for the same patient
            recent_records = ClinicalRecord.objects.filter(
                patient=record.patient,
                clinic=record.clinic
            ).exclude(
                id=record.id
            ).order_by('-created_at')[:10]
            
            for recent_record in recent_records:
                # Calculate suggestion score based on various factors
                score = self._calculate_relationship_score(record, recent_record)
                
                if score > 0.3:  # Threshold for suggestions
                    suggestions.append({
                        'target_entity': {
                            'id': str(recent_record.id),
                            'type': 'clinical_record',
                            'title': recent_record.title,
                            'subtitle': f"{recent_record.get_record_type_display()} - {recent_record.created_at.strftime('%Y-%m-%d')}",
                            'icon': self.linkable_types['clinical_record']['icon'],
                            'color': self.linkable_types['clinical_record']['color']
                        },
                        'suggested_relationship_type': self._suggest_relationship_type(record, recent_record),
                        'confidence_score': score,
                        'reason': self._get_suggestion_reason(record, recent_record, score)
                    })
            
            # Sort by confidence score
            suggestions.sort(key=lambda x: x['confidence_score'], reverse=True)
            
            return suggestions[:5]  # Return top 5 suggestions
            
        except ClinicalRecord.DoesNotExist:
            return []
        except Exception as e:
            self.logger.error(f"Error getting relationship suggestions: {e}")
            return []
    
    def _calculate_relationship_score(self, record1: ClinicalRecord, record2: ClinicalRecord) -> float:
        """Calculate relationship score between two records."""
        score = 0.0
        
        # Time proximity (records created close in time are more likely related)
        time_diff = abs((record1.created_at - record2.created_at).days)
        if time_diff <= 1:
            score += 0.5
        elif time_diff <= 7:
            score += 0.3
        elif time_diff <= 30:
            score += 0.1
        
        # Record type compatibility
        if record1.record_type == record2.record_type:
            score += 0.2
        elif (record1.record_type, record2.record_type) in [
            ('CONSULTATION', 'LAB_RESULT'),
            ('LAB_RESULT', 'CONSULTATION'),
            ('CONSULTATION', 'PRESCRIPTION'),
            ('PRESCRIPTION', 'CONSULTATION')
        ]:
            score += 0.3
        
        # Same creator
        if record1.created_by == record2.created_by:
            score += 0.2
        
        return min(score, 1.0)  # Cap at 1.0
    
    def _suggest_relationship_type(self, record1: ClinicalRecord, record2: ClinicalRecord) -> str:
        """Suggest relationship type based on record characteristics."""
        # If record1 is newer, it might follow up on record2
        if record1.created_at > record2.created_at:
            if record1.record_type == 'CONSULTATION' and record2.record_type == 'LAB_RESULT':
                return 'REFERENCES'
            elif record1.record_type == 'LAB_RESULT' and record2.record_type == 'CONSULTATION':
                return 'FOLLOWS_UP'
            else:
                return 'FOLLOWS_UP'
        else:
            return 'RELATED_TO'
    
    def _get_suggestion_reason(self, record1: ClinicalRecord, record2: ClinicalRecord, score: float) -> str:
        """Get human-readable reason for the suggestion."""
        reasons = []
        
        time_diff = abs((record1.created_at - record2.created_at).days)
        if time_diff <= 1:
            reasons.append("created on the same day")
        elif time_diff <= 7:
            reasons.append("created within a week")
        
        if record1.created_by == record2.created_by:
            reasons.append("same doctor")
        
        if record1.record_type != record2.record_type:
            reasons.append(f"complementary record types ({record1.get_record_type_display()} and {record2.get_record_type_display()})")
        
        if not reasons:
            reasons.append("similar characteristics")
        
        return f"Records {', '.join(reasons)}"
    
    def get_relationship_history(self, patient_id: str, user: User, 
                               days: int = 30) -> List[Dict[str, Any]]:
        """
        Get relationship history for a patient.
        
        Args:
            patient_id: ID of the patient
            user: User requesting the data
            days: Number of days to look back
            
        Returns:
            List of relationship history entries
        """
        try:
            # Get patient
            patient = Patient.objects.get(id=patient_id)
            
            # Check access
            has_access, _ = access_control_service.check_patient_access(
                user=user,
                patient=patient,
                action='view'
            )
            
            if not has_access:
                return []
            
            # Get relationships for patient's records
            since_date = timezone.now() - timedelta(days=days)
            
            relationships = RecordRelationship.objects.filter(
                Q(source_record__patient=patient) | Q(target_record__patient=patient),
                created_at__gte=since_date
            ).select_related(
                'source_record', 'target_record', 'created_by'
            ).order_by('-created_at')
            
            history = []
            for rel in relationships:
                history.append({
                    'id': str(rel.id),
                    'type': rel.relationship_type,
                    'type_display': self.relationship_types.get(rel.relationship_type, rel.relationship_type),
                    'source_record': {
                        'id': str(rel.source_record.id),
                        'title': rel.source_record.title,
                        'type': rel.source_record.record_type
                    },
                    'target_record': {
                        'id': str(rel.target_record.id),
                        'title': rel.target_record.title,
                        'type': rel.target_record.record_type
                    },
                    'created_at': rel.created_at.isoformat(),
                    'created_by': rel.created_by.get_full_name() if rel.created_by else None,
                    'notes': rel.notes
                })
            
            return history
            
        except Patient.DoesNotExist:
            return []
        except Exception as e:
            self.logger.error(f"Error getting relationship history: {e}")
            return []


# Global service instance
record_linking_service = RecordLinkingService()