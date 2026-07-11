"""
Django-Q Worker Management and Monitoring Service
"""

import os
import time
import psutil
import logging
from datetime import datetime, timedelta
from django.conf import settings
from django.core.mail import send_mail
from django.db import connection
from django_q.models import Task, Schedule
from django_q.cluster import Cluster
from django_q.tasks import async_task
from django_q.tasks import result
import redis

logger = logging.getLogger(__name__)

class DjangoQManager:
    """
    Manages Django-Q workers and provides monitoring capabilities.
    """
    
    def __init__(self):
        self.redis_client = self._get_redis_client()
        self.cluster_config = settings.Q_CLUSTER
        
    def _get_redis_client(self):
        """Get Redis client for queue monitoring."""
        redis_config = settings.Q_CLUSTER['redis']
        return redis.Redis(
            host=redis_config['host'],
            port=redis_config['port'],
            db=redis_config['db'],
            password=redis_config.get('password'),
            socket_timeout=redis_config.get('socket_timeout', 30),
            decode_responses=True
        )
    
    def get_worker_status(self):
        """Get current status of Django-Q workers."""
        try:
            # Get Redis queue information
            queue_info = self._get_queue_info()
            
            # Get worker processes
            worker_processes = self._get_worker_processes()
            
            # Get task statistics
            task_stats = self._get_task_statistics()
            
            return {
                'timestamp': datetime.now().isoformat(),
                'queue_info': queue_info,
                'worker_processes': worker_processes,
                'task_statistics': task_stats,
                'cluster_config': {
                    'workers': self.cluster_config.get('workers', 4),
                    'timeout': self.cluster_config.get('timeout', 300),
                    'recycle': self.cluster_config.get('recycle', 500),
                    'queue_limit': self.cluster_config.get('queue_limit', 50)
                }
            }
        except Exception as e:
            logger.error(f"Error getting worker status: {str(e)}")
            return {
                'timestamp': datetime.now().isoformat(),
                'error': str(e),
                'status': 'error'
            }
    
    def _get_queue_info(self):
        """Get Redis queue information."""
        try:
            # Get queue length
            queue_length = self.redis_client.llen(f"{self.cluster_config['name']}:q")
            
            # Get processing queue length
            processing_length = self.redis_client.llen(f"{self.cluster_config['name']}:p")
            
            # Get failed queue length
            failed_length = self.redis_client.llen(f"{self.cluster_config['name']}:f")
            
            # Get Redis memory usage
            redis_info = self.redis_client.info('memory')
            
            return {
                'queue_length': queue_length,
                'processing_length': processing_length,
                'failed_length': failed_length,
                'redis_memory_used': redis_info.get('used_memory_human', 'unknown'),
                'redis_memory_peak': redis_info.get('used_memory_peak_human', 'unknown'),
                'redis_connected_clients': self.redis_client.info('clients').get('connected_clients', 0)
            }
        except Exception as e:
            logger.error(f"Error getting queue info: {str(e)}")
            return {'error': str(e)}
    
    def _get_worker_processes(self):
        """Get information about worker processes."""
        worker_processes = []
        
        try:
            # Find Django-Q worker processes
            for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'cpu_percent', 'memory_info', 'create_time']):
                try:
                    cmdline = ' '.join(proc.info['cmdline']) if proc.info['cmdline'] else ''
                    
                    # Check if this is a Django-Q worker process
                    if 'qcluster' in cmdline or 'django_q' in cmdline:
                        worker_processes.append({
                            'pid': proc.info['pid'],
                            'name': proc.info['name'],
                            'cpu_percent': proc.info['cpu_percent'],
                            'memory_mb': proc.info['memory_info'].rss / (1024 * 1024),
                            'created': datetime.fromtimestamp(proc.info['create_time']).isoformat(),
                            'cmdline': cmdline[:100] + '...' if len(cmdline) > 100 else cmdline
                        })
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
                    
        except Exception as e:
            logger.error(f"Error getting worker processes: {str(e)}")
            
        return worker_processes
    
    def _get_task_statistics(self):
        """Get task execution statistics."""
        try:
            now = datetime.now()
            one_hour_ago = now - timedelta(hours=1)
            one_day_ago = now - timedelta(days=1)
            
            # Get task counts for different time periods
            stats = {
                'total_tasks': Task.objects.count(),
                'last_hour': {
                    'total': Task.objects.filter(started__gte=one_hour_ago).count(),
                    'successful': Task.objects.filter(started__gte=one_hour_ago, success=True).count(),
                    'failed': Task.objects.filter(started__gte=one_hour_ago, success=False).count(),
                },
                'last_24_hours': {
                    'total': Task.objects.filter(started__gte=one_day_ago).count(),
                    'successful': Task.objects.filter(started__gte=one_day_ago, success=True).count(),
                    'failed': Task.objects.filter(started__gte=one_day_ago, success=False).count(),
                },
                'pending_tasks': Task.objects.filter(started__isnull=True).count(),
                'running_tasks': Task.objects.filter(started__isnull=False, stopped__isnull=True).count()
            }
            
            # Calculate failure rates
            if stats['last_hour']['total'] > 0:
                stats['last_hour']['failure_rate'] = (stats['last_hour']['failed'] / stats['last_hour']['total']) * 100
            else:
                stats['last_hour']['failure_rate'] = 0
                
            if stats['last_24_hours']['total'] > 0:
                stats['last_24_hours']['failure_rate'] = (stats['last_24_hours']['failed'] / stats['last_24_hours']['total']) * 100
            else:
                stats['last_24_hours']['failure_rate'] = 0
            
            # Get average task duration
            recent_successful_tasks = Task.objects.filter(
                started__gte=one_hour_ago,
                success=True,
                stopped__isnull=False
            )
            
            if recent_successful_tasks.exists():
                durations = []
                for task in recent_successful_tasks:
                    if task.started and task.stopped:
                        duration = (task.stopped - task.started).total_seconds()
                        durations.append(duration)
                
                if durations:
                    stats['average_duration_seconds'] = sum(durations) / len(durations)
                else:
                    stats['average_duration_seconds'] = 0
            else:
                stats['average_duration_seconds'] = 0
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting task statistics: {str(e)}")
            return {'error': str(e)}
    
    def check_worker_health(self):
        """Check the health of Django-Q workers."""
        health_status = {
            'healthy': True,
            'issues': [],
            'warnings': [],
            'timestamp': datetime.now().isoformat()
        }
        
        try:
            status = self.get_worker_status()
            
            # Check if workers are running
            if not status.get('worker_processes'):
                health_status['healthy'] = False
                health_status['issues'].append('No Django-Q worker processes found')
            
            # Check queue length
            queue_info = status.get('queue_info', {})
            queue_length = queue_info.get('queue_length', 0)
            
            if queue_length > 100:
                health_status['healthy'] = False
                health_status['issues'].append(f'Queue length too high: {queue_length}')
            elif queue_length > 50:
                health_status['warnings'].append(f'Queue length elevated: {queue_length}')
            
            # Check failed tasks
            failed_length = queue_info.get('failed_length', 0)
            if failed_length > 10:
                health_status['healthy'] = False
                health_status['issues'].append(f'Too many failed tasks: {failed_length}')
            elif failed_length > 5:
                health_status['warnings'].append(f'Failed tasks detected: {failed_length}')
            
            # Check task failure rate
            task_stats = status.get('task_statistics', {})
            failure_rate = task_stats.get('last_hour', {}).get('failure_rate', 0)
            
            if failure_rate > 25:
                health_status['healthy'] = False
                health_status['issues'].append(f'High failure rate: {failure_rate:.1f}%')
            elif failure_rate > 10:
                health_status['warnings'].append(f'Elevated failure rate: {failure_rate:.1f}%')
            
            # Check worker resource usage
            worker_processes = status.get('worker_processes', [])
            for worker in worker_processes:
                if worker.get('memory_mb', 0) > 1000:  # 1GB
                    health_status['warnings'].append(f'Worker {worker["pid"]} using high memory: {worker["memory_mb"]:.1f}MB')
                
                if worker.get('cpu_percent', 0) > 80:
                    health_status['warnings'].append(f'Worker {worker["pid"]} using high CPU: {worker["cpu_percent"]:.1f}%')
            
            # Check Redis connectivity
            try:
                self.redis_client.ping()
            except Exception as e:
                health_status['healthy'] = False
                health_status['issues'].append(f'Redis connectivity issue: {str(e)}')
            
        except Exception as e:
            health_status['healthy'] = False
            health_status['issues'].append(f'Health check error: {str(e)}')
        
        return health_status
    
    def restart_workers(self, force=False):
        """Restart Django-Q workers."""
        try:
            # Get current worker processes
            worker_processes = self._get_worker_processes()
            
            if not worker_processes and not force:
                return {
                    'success': False,
                    'message': 'No worker processes found to restart'
                }
            
            # Kill existing worker processes
            killed_pids = []
            for worker in worker_processes:
                try:
                    proc = psutil.Process(worker['pid'])
                    proc.terminate()
                    killed_pids.append(worker['pid'])
                    logger.info(f"Terminated worker process {worker['pid']}")
                except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                    logger.warning(f"Could not terminate worker {worker['pid']}: {str(e)}")
            
            # Wait for processes to terminate
            time.sleep(2)
            
            # Force kill if necessary
            for pid in killed_pids:
                try:
                    proc = psutil.Process(pid)
                    if proc.is_running():
                        proc.kill()
                        logger.info(f"Force killed worker process {pid}")
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            
            return {
                'success': True,
                'message': f'Restarted {len(killed_pids)} worker processes',
                'killed_pids': killed_pids
            }
            
        except Exception as e:
            logger.error(f"Error restarting workers: {str(e)}")
            return {
                'success': False,
                'message': f'Error restarting workers: {str(e)}'
            }
    
    def scale_workers(self, target_workers):
        """Scale the number of Django-Q workers."""
        try:
            current_workers = len(self._get_worker_processes())
            
            if target_workers == current_workers:
                return {
                    'success': True,
                    'message': f'Already running {current_workers} workers'
                }
            
            # Update cluster configuration (this would require restart)
            # For now, just return the scaling recommendation
            return {
                'success': True,
                'message': f'Scaling from {current_workers} to {target_workers} workers requires cluster restart',
                'current_workers': current_workers,
                'target_workers': target_workers,
                'action_required': 'restart_cluster_with_new_config'
            }
            
        except Exception as e:
            logger.error(f"Error scaling workers: {str(e)}")
            return {
                'success': False,
                'message': f'Error scaling workers: {str(e)}'
            }
    
    def clear_failed_tasks(self):
        """Clear failed tasks from the queue."""
        try:
            # Clear failed tasks from Redis
            failed_key = f"{self.cluster_config['name']}:f"
            failed_count = self.redis_client.llen(failed_key)
            
            if failed_count > 0:
                self.redis_client.delete(failed_key)
                logger.info(f"Cleared {failed_count} failed tasks from queue")
            
            # Also clean up old failed tasks from database
            one_week_ago = datetime.now() - timedelta(days=7)
            old_failed_tasks = Task.objects.filter(
                success=False,
                stopped__lt=one_week_ago
            )
            
            deleted_count = old_failed_tasks.count()
            old_failed_tasks.delete()
            
            return {
                'success': True,
                'message': f'Cleared {failed_count} failed tasks from queue and {deleted_count} old failed tasks from database'
            }
            
        except Exception as e:
            logger.error(f"Error clearing failed tasks: {str(e)}")
            return {
                'success': False,
                'message': f'Error clearing failed tasks: {str(e)}'
            }
    
    def send_health_alert(self, health_status):
        """Send health alert email if issues are detected."""
        if not health_status['healthy'] or health_status['warnings']:
            try:
                subject = "RxDoctor Django-Q Worker Alert"
                
                if not health_status['healthy']:
                    subject = "CRITICAL: " + subject
                else:
                    subject = "WARNING: " + subject
                
                message = f"""
Django-Q Worker Health Alert

Status: {'UNHEALTHY' if not health_status['healthy'] else 'WARNING'}
Timestamp: {health_status['timestamp']}

Issues:
{chr(10).join('- ' + issue for issue in health_status['issues'])}

Warnings:
{chr(10).join('- ' + warning for warning in health_status['warnings'])}

Please check the Django-Q worker status and take appropriate action.

Server: {os.uname().nodename if hasattr(os, 'uname') else 'Unknown'}
                """
                
                admin_email = getattr(settings, 'ADMIN_EMAIL', 'admin@rxdoctor.com')
                
                send_mail(
                    subject,
                    message,
                    settings.DEFAULT_FROM_EMAIL,
                    [admin_email],
                    fail_silently=False
                )
                
                logger.info(f"Health alert sent to {admin_email}")
                return True
                
            except Exception as e:
                logger.error(f"Error sending health alert: {str(e)}")
                return False
        
        return False
    
    def get_task_details(self, task_id):
        """Get detailed information about a specific task."""
        try:
            task = Task.objects.get(id=task_id)
            
            return {
                'id': task.id,
                'name': task.name,
                'func': task.func,
                'args': task.args,
                'kwargs': task.kwargs,
                'started': task.started.isoformat() if task.started else None,
                'stopped': task.stopped.isoformat() if task.stopped else None,
                'success': task.success,
                'result': task.result,
                'group': task.group,
                'attempt_count': task.attempt_count,
                'duration_seconds': (task.stopped - task.started).total_seconds() if task.started and task.stopped else None
            }
            
        except Task.DoesNotExist:
            return {'error': 'Task not found'}
        except Exception as e:
            logger.error(f"Error getting task details: {str(e)}")
            return {'error': str(e)}
    
    def retry_failed_tasks(self, max_retries=3):
        """Retry failed tasks."""
        try:
            # Get recent failed tasks
            one_hour_ago = datetime.now() - timedelta(hours=1)
            failed_tasks = Task.objects.filter(
                success=False,
                stopped__gte=one_hour_ago,
                attempt_count__lt=max_retries
            )
            
            retried_count = 0
            for task in failed_tasks:
                try:
                    # Re-queue the task
                    async_task(
                        task.func,
                        *task.args,
                        **task.kwargs,
                        group=task.group
                    )
                    retried_count += 1
                    logger.info(f"Retried failed task {task.id}: {task.name}")
                except Exception as e:
                    logger.error(f"Error retrying task {task.id}: {str(e)}")
            
            return {
                'success': True,
                'message': f'Retried {retried_count} failed tasks',
                'retried_count': retried_count
            }
            
        except Exception as e:
            logger.error(f"Error retrying failed tasks: {str(e)}")
            return {
                'success': False,
                'message': f'Error retrying failed tasks: {str(e)}'
            }