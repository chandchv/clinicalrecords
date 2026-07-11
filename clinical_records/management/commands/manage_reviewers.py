"""
Management command to manage reviewer profiles.

This command helps with:
- Creating reviewer profiles for users
- Updating reviewer capabilities and settings
- Viewing reviewer statistics
- Managing reviewer assignments
"""
import logging
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django.db.models import Q

from users.models import Clinic
from clinical_records.models import ReviewerProfile, ManualReview

User = get_user_model()
logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Manage reviewer profiles for clinical document review'
    
    def add_arguments(self, parser):
        subparsers = parser.add_subparsers(dest='action', help='Available actions')
        
        # Create reviewer profile
        create_parser = subparsers.add_parser('create', help='Create a new reviewer profile')
        create_parser.add_argument('--username', required=True, help='Username of the user')
        create_parser.add_argument('--clinic-id', required=True, help='Clinic ID (UUID)')
        create_parser.add_argument('--qualification', required=True, 
                                 choices=[choice[0] for choice in ReviewerProfile.QUALIFICATION_CHOICES],
                                 help='Reviewer qualification')
        create_parser.add_argument('--specializations', nargs='*', 
                                 choices=[choice[0] for choice in ReviewerProfile.SPECIALIZATION_CHOICES],
                                 help='Reviewer specializations')
        create_parser.add_argument('--years-experience', type=int, default=0,
                                 help='Years of experience')
        create_parser.add_argument('--max-concurrent', type=int, default=5,
                                 help='Maximum concurrent reviews')
        
        # Update reviewer profile
        update_parser = subparsers.add_parser('update', help='Update an existing reviewer profile')
        update_parser.add_argument('--username', required=True, help='Username of the user')
        update_parser.add_argument('--clinic-id', required=True, help='Clinic ID (UUID)')
        update_parser.add_argument('--qualification', 
                                 choices=[choice[0] for choice in ReviewerProfile.QUALIFICATION_CHOICES],
                                 help='Reviewer qualification')
        update_parser.add_argument('--specializations', nargs='*', 
                                 choices=[choice[0] for choice in ReviewerProfile.SPECIALIZATION_CHOICES],
                                 help='Reviewer specializations')
        update_parser.add_argument('--years-experience', type=int,
                                 help='Years of experience')
        update_parser.add_argument('--max-concurrent', type=int,
                                 help='Maximum concurrent reviews')
        update_parser.add_argument('--active', type=bool, help='Whether reviewer is active')
        
        # List reviewers
        list_parser = subparsers.add_parser('list', help='List reviewer profiles')
        list_parser.add_argument('--clinic-id', help='Filter by clinic ID (UUID)')
        list_parser.add_argument('--active-only', action='store_true', 
                               help='Show only active reviewers')
        list_parser.add_argument('--with-stats', action='store_true',
                               help='Include performance statistics')
        
        # Show reviewer details
        show_parser = subparsers.add_parser('show', help='Show detailed reviewer information')
        show_parser.add_argument('--username', required=True, help='Username of the user')
        show_parser.add_argument('--clinic-id', required=True, help='Clinic ID (UUID)')
        
        # Update performance metrics
        metrics_parser = subparsers.add_parser('update-metrics', 
                                             help='Update performance metrics for reviewers')
        metrics_parser.add_argument('--clinic-id', help='Update for specific clinic only')
        metrics_parser.add_argument('--username', help='Update for specific user only')
        
        # Assign reviews
        assign_parser = subparsers.add_parser('assign', help='Manually assign reviews')
        assign_parser.add_argument('--username', required=True, help='Username to assign to')
        assign_parser.add_argument('--clinic-id', required=True, help='Clinic ID (UUID)')
        assign_parser.add_argument('--count', type=int, default=1, 
                                 help='Number of reviews to assign')
        assign_parser.add_argument('--priority', 
                                 choices=[choice[0] for choice in ManualReview.PRIORITY_CHOICES],
                                 help='Filter by priority')
    
    def handle(self, *args, **options):
        """Main command handler"""
        action = options['action']
        
        if not action:
            self.print_help('manage_reviewers', '')
            return
        
        try:
            if action == 'create':
                self._create_reviewer(options)
            elif action == 'update':
                self._update_reviewer(options)
            elif action == 'list':
                self._list_reviewers(options)
            elif action == 'show':
                self._show_reviewer(options)
            elif action == 'update-metrics':
                self._update_metrics(options)
            elif action == 'assign':
                self._assign_reviews(options)
            else:
                raise CommandError(f'Unknown action: {action}')
                
        except Exception as e:
            raise CommandError(f'Command failed: {e}')
    
    def _create_reviewer(self, options):
        """Create a new reviewer profile"""
        username = options['username']
        clinic_id = options['clinic_id']
        
        # Get user and clinic
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            raise CommandError(f'User {username} not found')
        
        try:
            clinic = Clinic.objects.get(id=clinic_id)
        except Clinic.DoesNotExist:
            raise CommandError(f'Clinic {clinic_id} not found')
        
        # Check if profile already exists
        if ReviewerProfile.objects.filter(user=user, clinic=clinic).exists():
            raise CommandError(f'Reviewer profile already exists for {username} in {clinic.name}')
        
        # Create the profile
        profile = ReviewerProfile.objects.create(
            user=user,
            clinic=clinic,
            qualification=options['qualification'],
            specializations=options.get('specializations', []),
            years_experience=options.get('years_experience', 0),
            max_concurrent_reviews=options.get('max_concurrent', 5)
        )
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Created reviewer profile for {username} in {clinic.name}'
            )
        )
        self._print_reviewer_info(profile)
    
    def _update_reviewer(self, options):
        """Update an existing reviewer profile"""
        username = options['username']
        clinic_id = options['clinic_id']
        
        # Get the profile
        try:
            user = User.objects.get(username=username)
            clinic = Clinic.objects.get(id=clinic_id)
            profile = ReviewerProfile.objects.get(user=user, clinic=clinic)
        except User.DoesNotExist:
            raise CommandError(f'User {username} not found')
        except Clinic.DoesNotExist:
            raise CommandError(f'Clinic {clinic_id} not found')
        except ReviewerProfile.DoesNotExist:
            raise CommandError(f'Reviewer profile not found for {username} in clinic {clinic_id}')
        
        # Update fields
        updated_fields = []
        
        if options.get('qualification'):
            profile.qualification = options['qualification']
            updated_fields.append('qualification')
        
        if options.get('specializations') is not None:
            profile.specializations = options['specializations']
            updated_fields.append('specializations')
        
        if options.get('years_experience') is not None:
            profile.years_experience = options['years_experience']
            updated_fields.append('years_experience')
        
        if options.get('max_concurrent') is not None:
            profile.max_concurrent_reviews = options['max_concurrent']
            updated_fields.append('max_concurrent_reviews')
        
        if options.get('active') is not None:
            profile.is_active = options['active']
            updated_fields.append('is_active')
        
        if updated_fields:
            profile.save(update_fields=updated_fields)
            self.stdout.write(
                self.style.SUCCESS(
                    f'Updated reviewer profile for {username}: {", ".join(updated_fields)}'
                )
            )
            self._print_reviewer_info(profile)
        else:
            self.stdout.write('No fields to update')
    
    def _list_reviewers(self, options):
        """List reviewer profiles"""
        queryset = ReviewerProfile.objects.select_related('user', 'clinic')
        
        # Apply filters
        if options.get('clinic_id'):
            try:
                clinic = Clinic.objects.get(id=options['clinic_id'])
                queryset = queryset.filter(clinic=clinic)
            except Clinic.DoesNotExist:
                raise CommandError(f'Clinic {options[\"clinic_id\"]} not found')
        
        if options.get('active_only'):
            queryset = queryset.filter(is_active=True)
        
        reviewers = queryset.order_by('clinic__name', 'user__username')
        
        if not reviewers:
            self.stdout.write('No reviewer profiles found')
            return
        
        self.stdout.write(f'Found {reviewers.count()} reviewer profile(s):\\n')
        
        current_clinic = None
        for reviewer in reviewers:
            if reviewer.clinic != current_clinic:
                current_clinic = reviewer.clinic
                self.stdout.write(f'\\n{self.style.HTTP_INFO(f\"Clinic: {current_clinic.name}\")}')
                self.stdout.write('-' * 50)
            
            status = '✓' if reviewer.is_active else '✗'
            workload = f'{reviewer.current_review_count}/{reviewer.max_concurrent_reviews}'
            
            self.stdout.write(
                f'  {status} {reviewer.user.get_full_name()} (@{reviewer.user.username})'
            )
            self.stdout.write(
                f'    Qualification: {reviewer.get_qualification_display()}'
            )
            self.stdout.write(
                f'    Workload: {workload} | Specializations: {", ".join(reviewer.specializations) or "None"}'
            )
            
            if options.get('with_stats'):
                stats = reviewer.get_performance_stats(30)
                self.stdout.write(
                    f'    30-day stats: {stats[\"reviews_completed\"]} completed, '
                    f'{stats[\"average_time_minutes\"]:.1f}min avg'
                )
    
    def _show_reviewer(self, options):
        """Show detailed reviewer information"""
        username = options['username']
        clinic_id = options['clinic_id']
        
        try:
            user = User.objects.get(username=username)
            clinic = Clinic.objects.get(id=clinic_id)
            profile = ReviewerProfile.objects.get(user=user, clinic=clinic)
        except User.DoesNotExist:
            raise CommandError(f'User {username} not found')
        except Clinic.DoesNotExist:
            raise CommandError(f'Clinic {clinic_id} not found')
        except ReviewerProfile.DoesNotExist:
            raise CommandError(f'Reviewer profile not found for {username} in clinic {clinic_id}')
        
        self._print_reviewer_info(profile, detailed=True)
    
    def _update_metrics(self, options):
        """Update performance metrics for reviewers"""
        queryset = ReviewerProfile.objects.all()
        
        # Apply filters
        if options.get('clinic_id'):
            try:
                clinic = Clinic.objects.get(id=options['clinic_id'])
                queryset = queryset.filter(clinic=clinic)
            except Clinic.DoesNotExist:
                raise CommandError(f'Clinic {options[\"clinic_id\"]} not found')
        
        if options.get('username'):
            try:
                user = User.objects.get(username=options['username'])
                queryset = queryset.filter(user=user)
            except User.DoesNotExist:
                raise CommandError(f'User {options[\"username\"]} not found')
        
        updated_count = 0
        for profile in queryset:
            try:
                profile.update_performance_metrics()
                updated_count += 1
                self.stdout.write(f'Updated metrics for {profile.user.username}')
            except Exception as e:
                self.stderr.write(f'Failed to update metrics for {profile.user.username}: {e}')
        
        self.stdout.write(
            self.style.SUCCESS(f'Updated performance metrics for {updated_count} reviewer(s)')
        )
    
    def _assign_reviews(self, options):
        """Manually assign reviews to a reviewer"""
        username = options['username']
        clinic_id = options['clinic_id']
        count = options['count']
        
        try:
            user = User.objects.get(username=username)
            clinic = Clinic.objects.get(id=clinic_id)
            profile = ReviewerProfile.objects.get(user=user, clinic=clinic)
        except User.DoesNotExist:
            raise CommandError(f'User {username} not found')
        except Clinic.DoesNotExist:
            raise CommandError(f'Clinic {clinic_id} not found')
        except ReviewerProfile.DoesNotExist:
            raise CommandError(f'Reviewer profile not found for {username} in clinic {clinic_id}')
        
        if not profile.can_accept_new_reviews:
            raise CommandError(f'Reviewer {username} cannot accept new reviews (inactive or at capacity)')
        
        # Find unassigned reviews
        reviews = ManualReview.objects.filter(
            document__clinical_record__clinic=clinic,
            assigned_to__isnull=True,
            status='pending'
        )
        
        # Apply priority filter if specified
        if options.get('priority'):
            reviews = reviews.filter(priority=options['priority'])
        
        reviews = reviews.order_by('-priority', 'created_at')[:count]
        
        if not reviews:
            self.stdout.write('No unassigned reviews found matching criteria')
            return
        
        assigned_count = 0
        for review in reviews:
            try:
                review.assign_to_user(user)
                assigned_count += 1
                self.stdout.write(f'Assigned review {review.id} to {username}')
            except Exception as e:
                self.stderr.write(f'Failed to assign review {review.id}: {e}')
        
        self.stdout.write(
            self.style.SUCCESS(f'Assigned {assigned_count} review(s) to {username}')
        )
    
    def _print_reviewer_info(self, profile, detailed=False):
        """Print reviewer profile information"""
        self.stdout.write(f'\\nReviewer Profile:')
        self.stdout.write(f'  User: {profile.user.get_full_name()} (@{profile.user.username})')
        self.stdout.write(f'  Clinic: {profile.clinic.name}')
        self.stdout.write(f'  Qualification: {profile.get_qualification_display()}')
        self.stdout.write(f'  Specializations: {", ".join(profile.specializations) or "None"}')
        self.stdout.write(f'  Years Experience: {profile.years_experience}')
        self.stdout.write(f'  Active: {"Yes" if profile.is_active else "No"}')
        self.stdout.write(f'  Current Workload: {profile.current_review_count}/{profile.max_concurrent_reviews}')
        
        if detailed:
            self.stdout.write(f'\\nCapabilities:')
            self.stdout.write(f'  OCR Review: {"Yes" if profile.can_review_ocr else "No"}')
            self.stdout.write(f'  Structured Data: {"Yes" if profile.can_review_structured_data else "No"}')
            self.stdout.write(f'  Compliance: {"Yes" if profile.can_review_compliance else "No"}')
            self.stdout.write(f'  Can Escalate: {"Yes" if profile.can_escalate_reviews else "No"}')
            
            self.stdout.write(f'\\nPerformance Metrics:')
            self.stdout.write(f'  Total Reviews Completed: {profile.total_reviews_completed}')
            if profile.average_review_time_minutes:
                self.stdout.write(f'  Average Review Time: {profile.average_review_time_minutes:.1f} minutes')
            if profile.accuracy_score:
                self.stdout.write(f'  Accuracy Score: {profile.accuracy_score:.2f}')
            
            # Recent performance stats
            stats_7d = profile.get_performance_stats(7)
            stats_30d = profile.get_performance_stats(30)
            
            self.stdout.write(f'\\nRecent Performance:')
            self.stdout.write(f'  Last 7 days: {stats_7d[\"reviews_completed\"]} reviews')
            self.stdout.write(f'  Last 30 days: {stats_30d[\"reviews_completed\"]} reviews')
            
            if profile.overdue_review_count > 0:
                self.stdout.write(
                    self.style.WARNING(f'  Overdue Reviews: {profile.overdue_review_count}')
                )"