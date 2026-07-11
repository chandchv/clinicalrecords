"""
Django-Q Auto-scaling Service
Automatically scales Django-Q workers based on queue length and system load.
"""

import os
import time
import psutil
import logging
import subprocess
from datetime import datetime, timedelta
from django.conf import settings
from django.core.mail import send_mail
from clinical_records.services.django_q_manager import DjangoQManager

logger = logging.getLogger(__name__)

class DjangoQAutoScaler:
    """
    Automatically scales Django-Q workers based on load and queue metrics.
    """
    
    def __init__(self):
        self.manager = DjangoQManager()
        self.config = self._load_config()
        self.scaling_history = []
        
    def _load_config(self):
        """Load auto-scaling configuration."""
        return {
            'min_workers': getattr(settings, 'DJANGO_Q_MIN_WORKERS', 2),
            'max_workers': getattr(settings, 'DJANGO_Q_MAX_WORKERS', 12),
            'scale_up_threshold': getattr(settings, 'DJANGO_Q_SCALE_UP_THRESHOLD', 50),
            'scale_down_threshold': getattr(settings, 'DJANGO_Q_SCALE_DOWN_THRESHOLD', 10),
            'cpu_threshold': getattr(settings, 'DJANGO_Q_CPU_THRESHOLD', 70),
            'memory_threshold': getattr(settings, 'DJANGO_Q_MEMORY_THRESHOLD', 80),
            'scale_up_cooldown': getattr(settings, 'DJANGO_Q_SCALE_UP_COOLDOWN', 300),  # 5 minutes
            'scale_down_cooldown': getattr(settings, 'DJANGO_Q_SCALE_DOWN_COOLDOWN', 600),  # 10 minutes
            'check_interval': getattr(settings, 'DJANGO_Q_CHECK_INTERVAL', 60),  # 1 minute
            'enabled': getattr(settings, 'DJANGO_Q_AUTOSCALING_ENABLED', False)
        }
    
    def should_scale_up(self, metrics):
        """Determine if workers should be scaled up."""
        queue_length = metrics.get('queue_length', 0)
        current_workers = metrics.get('worker_count', 0)
        cpu_usage = metrics.get('avg_cpu_usage', 0)
        memory_usage = metrics.get('avg_memory_usage', 0)
        
        # Check if we're already at max workers
        if current_workers >= self.config['max_workers']:
            return False, "Already at maximum workers"
        
        # Check cooldown period
        if not self._check_cooldown('scale_up'):
            return False, "Scale up cooldown period active"
        
        # Check queue length threshold
        if queue_length > self.config['scale_up_threshold']:
            return True, f"Queue length ({queue_length}) exceeds threshold ({self.config['scale_up_threshold']})"
        
        # Check CPU usage
        if cpu_usage > self.config['cpu_threshold']:
            return True, f"CPU usage ({cpu_usage:.1f}%) exceeds threshold ({self.config['cpu_threshold']}%)"
        
        # Check memory usage
        if memory_usage > self.config['memory_threshold']:
            return True, f"Memory usage ({memory_usage:.1f}%) exceeds threshold ({self.config['memory_threshold']}%)"
        
        return False, "No scale up conditions met"
    
    def should_scale_down(self, metrics):
        """Determine if workers should be scaled down."""
        queue_length = metrics.get('queue_length', 0)
        current_workers = metrics.get('worker_count', 0)
        cpu_usage = metrics.get('avg_cpu_usage', 0)
        memory_usage = metrics.get('avg_memory_usage', 0)
        
        # Check if we're already at min workers
        if current_workers <= self.config['min_workers']:
            return False, "Already at minimum workers"
        
        # Check cooldown period
        if not self._check_cooldown('scale_down'):
            return False, "Scale down cooldown period active"
        
        # Only scale down if queue is low AND resource usage is low
        if (queue_length < self.config['scale_down_threshold'] and 
            cpu_usage < self.config['cpu_threshold'] * 0.5 and 
            memory_usage < self.config['memory_threshold'] * 0.5):
            return True, f"Low queue ({queue_length}) and resource usage (CPU: {cpu_usage:.1f}%, Memory: {memory_usage:.1f}%)"
        
        return False, "No scale down conditions met"
    
    def _check_cooldown(self, action):
        """Check if cooldown period has passed for the given action."""
        cooldown_key = f"{action}_cooldown"
        cooldown_seconds = self.config[cooldown_key]
        
        # Find the last scaling action of this type
        for entry in reversed(self.scaling_history):
            if entry['action'] == action:
                time_since = (datetime.now() - entry['timestamp']).total_seconds()
                return time_since >= cooldown_seconds
        
        # No previous action found, cooldown is satisfied
        return True
    
    def get_scaling_metrics(self):
        """Get metrics for scaling decisions."""
        try:
            status = self.manager.get_worker_status()
            
            # Get queue metrics
            queue_info = status.get('queue_info', {})
            queue_length = queue_info.get('queue_length', 0)
            processing_length = queue_info.get('processing_length', 0)
            failed_length = queue_info.get('failed_length', 0)
            
            # Get worker metrics
            worker_processes = status.get('worker_processes', [])
            worker_count = len(worker_processes)
            
            # Calculate average resource usage
            total_cpu = 0
            total_memory = 0
            
            for worker in worker_processes:
                total_cpu += worker.get('cpu_percent', 0)
                total_memory += worker.get('memory_mb', 0)
            
            avg_cpu_usage = total_cpu / worker_count if worker_count > 0 else 0
            avg_memory_usage = total_memory / worker_count if worker_count > 0 else 0
            
            # Get task statistics
            task_stats = status.get('task_statistics', {})
            failure_rate = task_stats.get('last_hour', {}).get('failure_rate', 0)
            
            return {
                'queue_length': queue_length,
                'processing_length': processing_length,
                'failed_length': failed_length,
                'worker_count': worker_count,
                'avg_cpu_usage': avg_cpu_usage,
                'avg_memory_usage': avg_memory_usage,
                'failure_rate': failure_rate,
                'timestamp': datetime.now()
            }
            
        except Exception as e:
            logger.error(f"Error getting scaling metrics: {str(e)}")
            return None
    
    def scale_workers(self, target_workers, reason):
        """Scale workers to target count."""
        try:
            current_status = self.manager.get_worker_status()
            current_workers = len(current_status.get('worker_processes', []))
            
            if target_workers == current_workers:
                return {
                    'success': True,
                    'message': f'Already running {current_workers} workers',
                    'action': 'none'
                }
            
            action = 'scale_up' if target_workers > current_workers else 'scale_down'
            
            # For production, we would use supervisor or systemd to manage workers
            # This is a simplified implementation
            if self._use_supervisor_scaling(target_workers):
                # Record scaling action
                self.scaling_history.append({
                    'timestamp': datetime.now(),
                    'action': action,
                    'from_workers': current_workers,
                    'to_workers': target_workers,
                    'reason': reason
                })
                
                # Keep only last 100 scaling actions
                if len(self.scaling_history) > 100:
                    self.scaling_history = self.scaling_history[-100:]
                
                logger.info(f"Scaled workers from {current_workers} to {target_workers}: {reason}")
                
                return {
                    'success': True,
                    'message': f'Scaled workers from {current_workers} to {target_workers}',
                    'action': action,
                    'reason': reason
                }
            else:
                return {
                    'success': False,
                    'message': 'Failed to scale workers',
                    'action': action
                }
                
        except Exception as e:
            logger.error(f"Error scaling workers: {str(e)}")
            return {
                'success': False,
                'message': f'Error scaling workers: {str(e)}',
                'action': 'error'
            }
    
    def _use_supervisor_scaling(self, target_workers):
        """Scale workers using supervisor."""
        try:
            # Get current supervisor status
            result = subprocess.run(['supervisorctl', 'status'], 
                                  capture_output=True, text=True)
            
            if result.returncode != 0:
                logger.error("Failed to get supervisor status")
                return False
            
            # Parse supervisor status to find Django-Q workers
            current_workers = []
            for line in result.stdout.split('\n'):
                if 'rxdoctor-qcluster' in line:
                    parts = line.split()
                    if len(parts) >= 2:
                        current_workers.append(parts[0])
            
            current_count = len(current_workers)
            
            if target_workers > current_count:
                # Start additional workers
                for i in range(current_count, target_workers):
                    worker_name = f'rxdoctor-qcluster-worker-{i}'
                    subprocess.run(['supervisorctl', 'start', worker_name], 
                                 capture_output=True)
            elif target_workers < current_count:
                # Stop excess workers
                for i in range(target_workers, current_count):
                    worker_name = f'rxdoctor-qcluster-worker-{i}'
                    subprocess.run(['supervisorctl', 'stop', worker_name], 
                                 capture_output=True)
            
            return True
            
        except Exception as e:
            logger.error(f"Error using supervisor scaling: {str(e)}")
            return False
    
    def run_autoscaling_check(self):
        """Run a single autoscaling check."""
        if not self.config['enabled']:
            return {
                'success': False,
                'message': 'Autoscaling is disabled'
            }
        
        try:
            # Get current metrics
            metrics = self.get_scaling_metrics()
            if not metrics:
                return {
                    'success': False,
                    'message': 'Failed to get scaling metrics'
                }
            
            current_workers = metrics['worker_count']
            
            # Check if we should scale up
            should_up, up_reason = self.should_scale_up(metrics)
            if should_up:
                target_workers = min(current_workers + 1, self.config['max_workers'])
                return self.scale_workers(target_workers, up_reason)
            
            # Check if we should scale down
            should_down, down_reason = self.should_scale_down(metrics)
            if should_down:
                target_workers = max(current_workers - 1, self.config['min_workers'])
                return self.scale_workers(target_workers, down_reason)
            
            return {
                'success': True,
                'message': 'No scaling action needed',
                'action': 'none',
                'metrics': metrics
            }
            
        except Exception as e:
            logger.error(f"Error in autoscaling check: {str(e)}")
            return {
                'success': False,
                'message': f'Error in autoscaling check: {str(e)}'
            }
    
    def run_continuous_autoscaling(self):
        """Run continuous autoscaling monitoring."""
        logger.info("Starting Django-Q autoscaling service")
        
        while True:
            try:
                result = self.run_autoscaling_check()
                
                if result.get('action') in ['scale_up', 'scale_down']:
                    self._send_scaling_notification(result)
                
                # Log result
                if result['success']:
                    if result.get('action') != 'none':
                        logger.info(f"Autoscaling result: {result['message']}")
                else:
                    logger.error(f"Autoscaling error: {result['message']}")
                
                # Wait for next check
                time.sleep(self.config['check_interval'])
                
            except KeyboardInterrupt:
                logger.info("Autoscaling service stopped by user")
                break
            except Exception as e:
                logger.error(f"Unexpected error in autoscaling loop: {str(e)}")
                time.sleep(self.config['check_interval'])
    
    def _send_scaling_notification(self, result):
        """Send email notification about scaling action."""
        try:
            subject = f"RxDoctor Django-Q Auto-scaling: {result['action'].replace('_', ' ').title()}"
            
            message = f"""
Django-Q workers have been automatically scaled.

Action: {result['action'].replace('_', ' ').title()}
Result: {result['message']}
Reason: {result.get('reason', 'Not specified')}
Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Server: {os.uname().nodename if hasattr(os, 'uname') else 'Unknown'}

This is an automated notification from the Django-Q autoscaling service.
            """
            
            admin_email = getattr(settings, 'ADMIN_EMAIL', 'admin@rxdoctor.com')
            
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                [admin_email],
                fail_silently=True
            )
            
            logger.info(f"Scaling notification sent to {admin_email}")
            
        except Exception as e:
            logger.error(f"Error sending scaling notification: {str(e)}")
    
    def get_scaling_history(self, limit=50):
        """Get recent scaling history."""
        return self.scaling_history[-limit:] if self.scaling_history else []
    
    def get_autoscaling_status(self):
        """Get current autoscaling configuration and status."""
        return {
            'enabled': self.config['enabled'],
            'config': self.config,
            'recent_history': self.get_scaling_history(10),
            'last_check': datetime.now().isoformat()
        }