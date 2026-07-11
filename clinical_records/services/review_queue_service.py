"""
Review Queue Management Service

This service manages the manual review queue, including automatic assignment,
workload balancing, and notification systems for clinical document reviews.
"""
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from django.utils import timezone
from django.db.models import Q, Count, Avg
from django.contrib.auth import get_user_model

from ..models import ManualReview, ClinicalDocument, ReviewerProfile
from users.models import AuditLog

User = get_user_model()
logger = logging.getLogger(__name__)


class ReviewQueueService:
    """
    Service for managing the manual review queue system.
    """
    
    def __init__(self):
        self.confidence_threshold = 0.7  # Documents below this need review
        self.auto_assignment_enabled = True
        self.max_queue_time_hours = 24  # Max time before escalation
    
    def create_review_for_document(self, 
                                 document: ClinicalDocument,
                                 review_type: str = 'ocr_verification',
                                 priority: str = None,
                                 created_by: User = None,
                                 auto_assign: bool = True) -> ManualReview:
        """
        Create a manual review for a document that needs human verification.
        
        Args:
            document: The clinical document to review
            review_type: Type of review needed
            priority: Priority level (auto-determined if None)
            created_by: User who created the review request
            auto_assign: Whether to automatically assign to available reviewer
            
        Returns:
            Created ManualReview instance
        """
        try:
            # Determine priority if not specified
            if not priority:
                priority = self._determine_review_priority(document)
            
            # Create the review
            review = ManualReview.create_for_document(
                document=document,
                review_type=review_type,
                priority=priority,
                created_by=created_by
            )
            
            logger.info(f"Created manual review {review.id} for document {document.id}")
            
            # Auto-assign if enabled and requested
            if auto_assign and self.auto_assignment_enabled:
                assigned_reviewer = self._auto_assign_review(review)
                if assigned_reviewer:
                    logger.info(f"Auto-assigned review {review.id} to {assigned_reviewer.user.username}")
                else:
                    logger.warning(f"Could not auto-assign review {review.id} - no available reviewers")
            
            # Log the creation
            if created_by:
                AuditLog.log_action(
                    user=created_by,
                    action='REVIEW_CREATED',
                    resource_type='MANUAL_REVIEW',
                    resource_id=str(review.id),
                    details={
                        'document_id': str(document.id),
                        'review_type': review_type,
                        'priority': priority,
                        'auto_assigned': auto_assign and assigned_reviewer is not None
                    },
                    tenant=document.clinic
                )
            
            return review
            
        except Exception as e:
            logger.error(f"Failed to create review for document {document.id}: {e}")
            raise
    
    def _determine_review_priority(self, document: ClinicalDocument) -> str:
        """
        Automatically determine review priority based on document characteristics.
        
        Args:
            document: The clinical document
            
        Returns:
            Priority level string
        """
        # High priority conditions
        if document.clinical_record.priority == 'urgent':
            return 'urgent'
        
        if document.clinical_record.record_type in ['prescription', 'lab_report']:
            return 'high'
        
        # Check OCR confidence
        if document.ocr_confidence is not None:
            if document.ocr_confidence < 0.3:
                return 'high'  # Very low confidence
            elif document.ocr_confidence < 0.5:
                return 'normal'
        
        # Check document age
        age_hours = (timezone.now() - document.created_at).total_seconds() / 3600
        if age_hours > 48:  # Older than 2 days
            return 'high'
        
        return 'normal'
    
    def _auto_assign_review(self, review: ManualReview) -> Optional[ReviewerProfile]:
        """
        Automatically assign a review to the best available reviewer.
        
        Args:
            review: The manual review to assign
            
        Returns:
            ReviewerProfile of assigned reviewer, or None if no one available
        """
        try:
            # Get document type for specialization matching
            document_type = review.document.clinical_record.record_type
            
            # Find available reviewers
            available_reviewers = ReviewerProfile.get_available_reviewers(
                clinic=review.clinic,
                document_type=document_type,
                review_type=review.review_type
            )
            
            if not available_reviewers:
                return None
            
            # Score reviewers based on various factors
            scored_reviewers = []
            for reviewer in available_reviewers:
                score = self._calculate_reviewer_score(reviewer, review)
                scored_reviewers.append((reviewer, score))
            
            # Sort by score (highest first)
            scored_reviewers.sort(key=lambda x: x[1], reverse=True)
            
            # Assign to best reviewer
            best_reviewer = scored_reviewers[0][0]
            
            # Set due date based on priority
            due_date = self._calculate_due_date(review.priority)
            review.assign_to_user(best_reviewer.user, due_date)
            
            return best_reviewer
            
        except Exception as e:
            logger.error(f"Auto-assignment failed for review {review.id}: {e}")
            return None
    
    def _calculate_reviewer_score(self, reviewer: ReviewerProfile, review: ManualReview) -> float:
        """
        Calculate a score for how suitable a reviewer is for a specific review.
        
        Args:
            reviewer: The reviewer profile
            review: The manual review
            
        Returns:
            Score (higher is better)
        """
        score = 0.0
        
        # Base score from qualification level
        qualification_scores = {
            'data_entry': 1.0,
            'medical_assistant': 2.0,
            'nurse': 3.0,
            'lab_technician': 2.5,
            'doctor': 4.0,
            'radiologist': 3.5,
            'supervisor': 5.0,
        }
        score += qualification_scores.get(reviewer.qualification, 1.0)
        
        # Specialization bonus
        document_type = review.document.clinical_record.record_type
        specialization_map = {
            'lab_report': 'laboratory',
            'prescription': 'prescriptions',
            'imaging': 'radiology',
            'pathology': 'pathology',
        }
        
        required_spec = specialization_map.get(document_type)
        if required_spec and required_spec in reviewer.specializations:
            score += 2.0
        elif 'general' in reviewer.specializations:
            score += 1.0
        
        # Experience bonus
        score += min(reviewer.years_experience * 0.1, 1.0)
        
        # Performance bonus (accuracy and speed)
        if reviewer.accuracy_score:
            score += reviewer.accuracy_score * 2.0
        
        if reviewer.average_review_time_minutes:
            # Bonus for faster reviewers (but not too fast)
            avg_time = reviewer.average_review_time_minutes
            if 10 <= avg_time <= 30:  # Sweet spot
                score += 1.0
            elif avg_time < 10:  # Too fast, might be careless
                score -= 0.5
        
        # Workload penalty (prefer less busy reviewers)
        workload_score = reviewer.get_workload_score()
        score -= workload_score * 2.0
        
        # Priority matching
        if review.priority == 'urgent' and reviewer.can_escalate_reviews:
            score += 1.0
        
        return score
    
    def _calculate_due_date(self, priority: str) -> datetime:
        """
        Calculate due date based on priority level.
        
        Args:
            priority: Priority level
            
        Returns:
            Due date
        """
        hours_map = {
            'urgent': 4,
            'high': 12,
            'normal': 24,
            'low': 72,
        }
        
        hours = hours_map.get(priority, 24)
        return timezone.now() + timedelta(hours=hours)
    
    def process_low_confidence_documents(self, confidence_threshold: float = None) -> Dict[str, int]:
        """
        Process documents with low OCR confidence and create reviews as needed.
        
        Args:
            confidence_threshold: Confidence threshold (uses default if None)
            
        Returns:
            Dictionary with processing statistics
        """
        if confidence_threshold is None:
            confidence_threshold = self.confidence_threshold
        
        # Find documents that need review
        documents_needing_review = ClinicalDocument.objects.filter(
            processing_status='completed',
            requires_manual_review=False,
            ocr_confidence__lt=confidence_threshold
        ).exclude(
            # Don't create duplicate reviews
            manual_reviews__status__in=['pending', 'in_progress']
        )
        
        stats = {
            'documents_found': documents_needing_review.count(),
            'reviews_created': 0,
            'reviews_assigned': 0,
            'errors': 0
        }
        
        for document in documents_needing_review:
            try:
                review = self.create_review_for_document(
                    document=document,
                    review_type='ocr_verification',
                    auto_assign=True
                )
                
                stats['reviews_created'] += 1
                
                if review.assigned_to:
                    stats['reviews_assigned'] += 1
                    
            except Exception as e:
                logger.error(f"Failed to create review for document {document.id}: {e}")
                stats['errors'] += 1
        
        logger.info(f"Processed low confidence documents: {stats}")
        return stats
    
    def escalate_overdue_reviews(self, max_age_hours: int = None) -> Dict[str, int]:
        """
        Escalate reviews that have been in queue too long.
        
        Args:
            max_age_hours: Maximum age before escalation (uses default if None)
            
        Returns:
            Dictionary with escalation statistics
        """
        if max_age_hours is None:
            max_age_hours = self.max_queue_time_hours
        
        cutoff_time = timezone.now() - timedelta(hours=max_age_hours)
        
        # Find overdue reviews
        overdue_reviews = ManualReview.objects.filter(
            status__in=['pending', 'in_progress'],
            created_at__lt=cutoff_time,
            requires_escalation=False
        )
        
        stats = {
            'reviews_found': overdue_reviews.count(),
            'reviews_escalated': 0,
            'errors': 0
        }
        
        for review in overdue_reviews:
            try:
                review.escalate_review(
                    user=None,  # System escalation
                    reason=f"Automatically escalated after {max_age_hours} hours in queue"
                )
                
                stats['reviews_escalated'] += 1
                
                # Log the escalation
                AuditLog.log_action(
                    user=None,
                    action='REVIEW_AUTO_ESCALATED',
                    resource_type='MANUAL_REVIEW',
                    resource_id=str(review.id),
                    details={
                        'document_id': str(review.document.id),
                        'hours_in_queue': max_age_hours,
                        'original_priority': review.priority
                    },
                    tenant=review.clinic
                )
                
            except Exception as e:
                logger.error(f"Failed to escalate review {review.id}: {e}")
                stats['errors'] += 1
        
        logger.info(f"Escalated overdue reviews: {stats}")
        return stats
    
    def rebalance_workload(self, clinic) -> Dict[str, int]:
        """
        Rebalance workload by reassigning reviews from overloaded reviewers.
        
        Args:
            clinic: Clinic to rebalance
            
        Returns:
            Dictionary with rebalancing statistics
        """
        stats = {
            'reviews_reassigned': 0,
            'reviewers_affected': 0,
            'errors': 0
        }
        
        try:
            # Get all active reviewers for the clinic
            reviewers = ReviewerProfile.objects.filter(
                clinic=clinic,
                is_active=True
            ).select_related('user')
            
            if len(reviewers) < 2:
                return stats  # Need at least 2 reviewers to rebalance
            
            # Calculate workload for each reviewer
            reviewer_workloads = []
            for reviewer in reviewers:
                workload = reviewer.current_review_count
                capacity = reviewer.max_concurrent_reviews
                utilization = workload / capacity if capacity > 0 else 1.0
                
                reviewer_workloads.append({
                    'reviewer': reviewer,
                    'workload': workload,
                    'capacity': capacity,
                    'utilization': utilization
                })
            
            # Sort by utilization (highest first)
            reviewer_workloads.sort(key=lambda x: x['utilization'], reverse=True)
            
            # Find overloaded and underloaded reviewers
            overloaded = [r for r in reviewer_workloads if r['utilization'] > 0.8]
            underloaded = [r for r in reviewer_workloads if r['utilization'] < 0.6]
            
            if not overloaded or not underloaded:
                return stats
            
            # Reassign reviews from overloaded to underloaded
            for overloaded_reviewer in overloaded:
                if not underloaded:
                    break
                
                # Get pending reviews from overloaded reviewer
                pending_reviews = ManualReview.objects.filter(
                    assigned_to=overloaded_reviewer['reviewer'].user,
                    status='pending',
                    document__clinical_record__clinic=clinic
                ).order_by('priority', 'created_at')
                
                reviews_to_move = min(
                    pending_reviews.count(),
                    overloaded_reviewer['workload'] - overloaded_reviewer['capacity']
                )
                
                for review in pending_reviews[:reviews_to_move]:
                    if not underloaded:
                        break
                    
                    # Find best underloaded reviewer
                    target_reviewer = None
                    best_score = -1
                    
                    for underloaded_reviewer in underloaded:
                        if underloaded_reviewer['workload'] >= underloaded_reviewer['capacity']:
                            continue
                        
                        score = self._calculate_reviewer_score(
                            underloaded_reviewer['reviewer'], 
                            review
                        )
                        
                        if score > best_score:
                            best_score = score
                            target_reviewer = underloaded_reviewer
                    
                    if target_reviewer:
                        # Reassign the review
                        old_assignee = review.assigned_to
                        review.assign_to_user(target_reviewer['reviewer'].user)
                        
                        stats['reviews_reassigned'] += 1
                        
                        # Update workload tracking
                        target_reviewer['workload'] += 1
                        if target_reviewer['workload'] >= target_reviewer['capacity']:
                            underloaded.remove(target_reviewer)
                        
                        # Log the reassignment
                        AuditLog.log_action(
                            user=None,
                            action='REVIEW_REASSIGNED',
                            resource_type='MANUAL_REVIEW',
                            resource_id=str(review.id),
                            details={
                                'from_user': old_assignee.username if old_assignee else None,
                                'to_user': target_reviewer['reviewer'].user.username,
                                'reason': 'workload_rebalancing'
                            },
                            tenant=clinic
                        )
            
            stats['reviewers_affected'] = len(overloaded)
            
        except Exception as e:
            logger.error(f"Workload rebalancing failed for clinic {clinic.id}: {e}")
            stats['errors'] += 1
        
        logger.info(f"Rebalanced workload for clinic {clinic.name}: {stats}")
        return stats
    
    def get_queue_statistics(self, clinic) -> Dict[str, Any]:
        """
        Get comprehensive statistics about the review queue.
        
        Args:
            clinic: Clinic to get statistics for
            
        Returns:
            Dictionary with queue statistics
        """
        reviews = ManualReview.objects.filter(
            document__clinical_record__clinic=clinic
        )
        
        now = timezone.now()
        today = now.date()
        week_ago = now - timedelta(days=7)
        
        stats = {
            'queue_status': {
                'total_pending': reviews.filter(status='pending').count(),
                'total_in_progress': reviews.filter(status='in_progress').count(),
                'total_overdue': reviews.filter(
                    due_date__lt=now,
                    status__in=['pending', 'in_progress']
                ).count(),
            },
            'completion_stats': {
                'completed_today': reviews.filter(
                    status='completed',
                    completed_at__date=today
                ).count(),
                'completed_this_week': reviews.filter(
                    status='completed',
                    completed_at__gte=week_ago
                ).count(),
                'average_completion_time': reviews.filter(
                    status='completed',
                    time_spent_minutes__isnull=False
                ).aggregate(Avg('time_spent_minutes'))['time_spent_minutes__avg'],
            },
            'priority_breakdown': {},
            'type_breakdown': {},
            'reviewer_stats': {}
        }
        
        # Priority breakdown
        for priority, _ in ManualReview.PRIORITY_CHOICES:
            stats['priority_breakdown'][priority] = reviews.filter(
                priority=priority,
                status__in=['pending', 'in_progress']
            ).count()
        
        # Type breakdown
        for review_type, _ in ManualReview.REVIEW_TYPE_CHOICES:
            stats['type_breakdown'][review_type] = reviews.filter(
                review_type=review_type,
                status__in=['pending', 'in_progress']
            ).count()
        
        # Reviewer statistics
        reviewers = ReviewerProfile.objects.filter(
            clinic=clinic,
            is_active=True
        ).select_related('user')
        
        for reviewer in reviewers:
            stats['reviewer_stats'][reviewer.user.username] = {
                'current_assigned': reviewer.current_review_count,
                'capacity': reviewer.max_concurrent_reviews,
                'utilization': reviewer.get_workload_score(),
                'completed_this_week': reviews.filter(
                    completed_by=reviewer.user,
                    status='completed',
                    completed_at__gte=week_ago
                ).count(),
            }
        
        return stats
    
    def send_review_notifications(self, clinic) -> Dict[str, int]:
        """
        Send notifications for review queue events.
        
        Args:
            clinic: Clinic to send notifications for
            
        Returns:
            Dictionary with notification statistics
        """
        from notifications.models import Notification
        
        stats = {
            'overdue_notifications': 0,
            'assignment_notifications': 0,
            'escalation_notifications': 0,
        }
        
        try:
            # Get overdue reviews
            overdue_reviews = ManualReview.objects.filter(
                document__clinical_record__clinic=clinic,
                due_date__lt=timezone.now(),
                status__in=['pending', 'in_progress']
            ).select_related('assigned_to', 'document')
            
            # Send overdue notifications
            for review in overdue_reviews:
                if review.assigned_to:
                    # Create notification for assigned reviewer
                    Notification.objects.create(
                        user=review.assigned_to,
                        title="Overdue Review",
                        message=f"Review for document {review.document.id} is overdue",
                        notification_type='review_overdue',
                        data={
                            'review_id': str(review.id),
                            'document_id': str(review.document.id),
                            'due_date': review.due_date.isoformat(),
                        }
                    )
                    stats['overdue_notifications'] += 1
            
            # Get recently assigned reviews (last hour)
            recent_assignments = ManualReview.objects.filter(
                document__clinical_record__clinic=clinic,
                assigned_at__gte=timezone.now() - timedelta(hours=1),
                assigned_to__isnull=False
            ).select_related('assigned_to', 'document')
            
            # Send assignment notifications
            for review in recent_assignments:
                Notification.objects.create(
                    user=review.assigned_to,
                    title="New Review Assignment",
                    message=f"You have been assigned a new review for document {review.document.id}",
                    notification_type='review_assigned',
                    data={
                        'review_id': str(review.id),
                        'document_id': str(review.document.id),
                        'priority': review.priority,
                        'review_type': review.review_type,
                    }
                )
                stats['assignment_notifications'] += 1
            
            # Get recent escalations
            recent_escalations = ManualReview.objects.filter(
                document__clinical_record__clinic=clinic,
                status='escalated',
                escalated_at__gte=timezone.now() - timedelta(hours=1)
            ).select_related('document')
            
            # Send escalation notifications to supervisors
            for review in recent_escalations:
                # Get supervisors for this clinic
                supervisors = ReviewerProfile.objects.filter(
                    clinic=clinic,
                    is_supervisor=True,
                    is_active=True
                ).select_related('user')
                
                for supervisor_profile in supervisors:
                    Notification.objects.create(
                        user=supervisor_profile.user,
                        title="Review Escalated",
                        message=f"Review for document {review.document.id} has been escalated",
                        notification_type='review_escalated',
                        data={
                            'review_id': str(review.id),
                            'document_id': str(review.document.id),
                            'escalation_reason': review.escalation_reason,
                        }
                    )
                    stats['escalation_notifications'] += 1
                    
        except Exception as e:
            logger.error(f"Error sending review notifications: {e}")
        
        return stats


# Global service instance
_review_queue_service = None


def get_review_queue_service() -> ReviewQueueService:
    """Get the global review queue service instance."""
    global _review_queue_service
    if _review_queue_service is None:
        _review_queue_service = ReviewQueueService()
    return _review_queue_service


# Convenience functions
def create_review_for_low_confidence_document(document: ClinicalDocument, 
                                            created_by: User = None) -> ManualReview:
    """
    Convenience function to create a review for a low-confidence document.
    
    Args:
        document: The clinical document
        created_by: User who created the review request
        
    Returns:
        Created ManualReview instance
    """
    service = get_review_queue_service()
    return service.create_review_for_document(
        document=document,
        review_type='ocr_verification',
        created_by=created_by,
        auto_assign=True
    )


def process_pending_reviews(clinic) -> Dict[str, int]:
    """
    Process all pending review queue tasks for a clinic.
    
    Args:
        clinic: Clinic to process
        
    Returns:
        Dictionary with processing statistics
    """
    service = get_review_queue_service()
    
    # Process low confidence documents
    low_confidence_stats = service.process_low_confidence_documents()
    
    # Escalate overdue reviews
    escalation_stats = service.escalate_overdue_reviews()
    
    # Rebalance workload
    rebalance_stats = service.rebalance_workload(clinic)
    
    # Send notifications
    notification_stats = service.send_review_notifications(clinic)
    
    return {
        'low_confidence_processing': low_confidence_stats,
        'escalations': escalation_stats,
        'workload_rebalancing': rebalance_stats,
        'notifications': notification_stats,
    }