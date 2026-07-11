"""
AWS Lambda Auto-scaling Service

This service provides intelligent auto-scaling for Lambda functions based on
queue depth, processing patterns, and cost optimization strategies.
"""

import logging
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone as django_timezone

from .lambda_sqs_service import LambdaSQSService
from .comprehensive_monitoring import ComprehensiveMonitoringService

logger = logging.getLogger(__name__)


@dataclass
class ScalingMetrics:
    """Data class for scaling metrics"""
    queue_depth: int
    processing_rate: float
    average_processing_time: float
    error_rate: float
    cost_per_hour: float
    current_concurrency: int
    recommended_concurrency: int
    confidence_score: float


@dataclass
class ScalingDecision:
    """Data class for scaling decisions"""
    action: str  # 'scale_up', 'scale_down', 'maintain'
    target_concurrency: int
    reason: str
    confidence: float
    estimated_cost_impact: float
    estimated_performance_impact: str


class LambdaAutoScaler:
    """
    Intelligent auto-scaling service for Lambda functions
    """
    
    def __init__(self):
        """Initialize the auto-scaler"""
        self.lambda_sqs_service = LambdaSQSService()
        self.monitoring_service = ComprehensiveMonitoringService()
        
        # Scaling configuration
        self.min_concurrency = getattr(settings, 'LAMBDA_MIN_CONCURRENCY', 0)
        self.max_concurrency = getattr(settings, 'LAMBDA_MAX_CONCURRENCY', 100)
        self.scale_up_threshold = getattr(settings, 'LAMBDA_SCALE_UP_THRESHOLD', 10)
        self.scale_down_threshold = getattr(settings, 'LAMBDA_SCALE_DOWN_THRESHOLD', 2)
        self.cost_optimization_enabled = getattr(settings, 'LAMBDA_COST_OPTIMIZATION', True)
        
        # Scaling parameters
        self.scale_up_factor = 2.0
        self.scale_down_factor = 0.5
        self.max_scale_up_per_minute = 20
        self.max_scale_down_per_minute = 10
        self.cooldown_period_minutes = 5
        
        # Cost parameters (approximate AWS Lambda pricing)
        self.cost_per_gb_second = 0.0000166667  # $0.0000166667 per GB-second
        self.cost_per_request = 0.0000002  # $0.0000002 per request
        self.provisioned_concurrency_cost = 0.0000041667  # $0.0000041667 per GB-second
    
    def analyze_scaling_metrics(self) -> ScalingMetrics:
        """
        Analyze current metrics to determine scaling needs
        
        Returns:
            ScalingMetrics object with current system state
        """
        try:
            # Get queue metrics
            queue_metrics = self.lambda_sqs_service.get_queue_metrics()
            lambda_metrics = self.lambda_sqs_service.get_lambda_metrics()
            
            # Get historical processing data
            processing_stats = self._get_processing_statistics()
            
            # Calculate current metrics
            queue_depth = queue_metrics.get('processing_queue', {}).get('approximate_number_of_messages', 0)
            current_concurrency = lambda_metrics.get('provisioned_concurrency', 0)
            
            # Calculate processing rate (documents per minute)
            processing_rate = processing_stats.get('processing_rate', 0.0)
            
            # Calculate average processing time
            avg_processing_time = processing_stats.get('average_processing_time', 30.0)
            
            # Calculate error rate
            error_rate = processing_stats.get('error_rate', 0.0)
            
            # Estimate current cost per hour
            cost_per_hour = self._calculate_current_cost(current_concurrency, processing_rate)
            
            # Calculate recommended concurrency
            recommended_concurrency = self._calculate_optimal_concurrency(
                queue_depth, processing_rate, avg_processing_time
            )
            
            # Calculate confidence score
            confidence_score = self._calculate_confidence_score(processing_stats)
            
            return ScalingMetrics(
                queue_depth=queue_depth,
                processing_rate=processing_rate,
                average_processing_time=avg_processing_time,
                error_rate=error_rate,
                cost_per_hour=cost_per_hour,
                current_concurrency=current_concurrency,
                recommended_concurrency=recommended_concurrency,
                confidence_score=confidence_score
            )
            
        except Exception as e:
            logger.error(f"Error analyzing scaling metrics: {str(e)}")
            # Return default metrics
            return ScalingMetrics(
                queue_depth=0,
                processing_rate=0.0,
                average_processing_time=30.0,
                error_rate=0.0,
                cost_per_hour=0.0,
                current_concurrency=0,
                recommended_concurrency=0,
                confidence_score=0.0
            )
    
    def make_scaling_decision(self, metrics: ScalingMetrics) -> ScalingDecision:
        """
        Make intelligent scaling decision based on metrics
        
        Args:
            metrics: Current scaling metrics
            
        Returns:
            ScalingDecision object with recommended action
        """
        try:
            current_concurrency = metrics.current_concurrency
            recommended_concurrency = metrics.recommended_concurrency
            queue_depth = metrics.queue_depth
            
            # Check cooldown period
            if self._is_in_cooldown():
                return ScalingDecision(
                    action='maintain',
                    target_concurrency=current_concurrency,
                    reason='Cooldown period active',
                    confidence=1.0,
                    estimated_cost_impact=0.0,
                    estimated_performance_impact='none'
                )
            
            # Determine scaling action
            if queue_depth >= self.scale_up_threshold and recommended_concurrency > current_concurrency:
                # Scale up
                target_concurrency = min(
                    int(current_concurrency * self.scale_up_factor),
                    recommended_concurrency,
                    self.max_concurrency,
                    current_concurrency + self.max_scale_up_per_minute
                )
                
                if target_concurrency <= current_concurrency:
                    target_concurrency = min(current_concurrency + 1, self.max_concurrency)
                
                cost_impact = self._calculate_cost_impact(current_concurrency, target_concurrency)
                performance_impact = self._estimate_performance_impact('scale_up', target_concurrency - current_concurrency)
                
                return ScalingDecision(
                    action='scale_up',
                    target_concurrency=target_concurrency,
                    reason=f'Queue depth ({queue_depth}) exceeds threshold ({self.scale_up_threshold})',
                    confidence=metrics.confidence_score,
                    estimated_cost_impact=cost_impact,
                    estimated_performance_impact=performance_impact
                )
            
            elif queue_depth <= self.scale_down_threshold and recommended_concurrency < current_concurrency:
                # Scale down
                target_concurrency = max(
                    int(current_concurrency * self.scale_down_factor),
                    recommended_concurrency,
                    self.min_concurrency,
                    current_concurrency - self.max_scale_down_per_minute
                )
                
                if target_concurrency >= current_concurrency:
                    target_concurrency = max(current_concurrency - 1, self.min_concurrency)
                
                # Apply cost optimization
                if self.cost_optimization_enabled and queue_depth == 0:
                    target_concurrency = self.min_concurrency
                
                cost_impact = self._calculate_cost_impact(current_concurrency, target_concurrency)
                performance_impact = self._estimate_performance_impact('scale_down', current_concurrency - target_concurrency)
                
                return ScalingDecision(
                    action='scale_down',
                    target_concurrency=target_concurrency,
                    reason=f'Queue depth ({queue_depth}) below threshold ({self.scale_down_threshold})',
                    confidence=metrics.confidence_score,
                    estimated_cost_impact=cost_impact,
                    estimated_performance_impact=performance_impact
                )
            
            else:
                # Maintain current level
                return ScalingDecision(
                    action='maintain',
                    target_concurrency=current_concurrency,
                    reason='Current concurrency is optimal',
                    confidence=metrics.confidence_score,
                    estimated_cost_impact=0.0,
                    estimated_performance_impact='none'
                )
                
        except Exception as e:
            logger.error(f"Error making scaling decision: {str(e)}")
            return ScalingDecision(
                action='maintain',
                target_concurrency=metrics.current_concurrency,
                reason=f'Error in decision making: {str(e)}',
                confidence=0.0,
                estimated_cost_impact=0.0,
                estimated_performance_impact='unknown'
            )
    
    def execute_scaling_decision(self, decision: ScalingDecision) -> bool:
        """
        Execute the scaling decision
        
        Args:
            decision: ScalingDecision to execute
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            if decision.action == 'maintain':
                logger.info(f"Maintaining current concurrency: {decision.reason}")
                return True
            
            # Execute scaling
            success = self.lambda_sqs_service.scale_lambda_concurrency(decision.target_concurrency)
            
            if success:
                # Record scaling action
                self._record_scaling_action(decision)
                
                # Set cooldown period
                self._set_cooldown()
                
                logger.info(
                    f"Scaling {decision.action} executed: "
                    f"target={decision.target_concurrency}, "
                    f"reason={decision.reason}, "
                    f"cost_impact=${decision.estimated_cost_impact:.4f}/hour"
                )
                
                return True
            else:
                logger.error(f"Failed to execute scaling decision: {decision.action}")
                return False
                
        except Exception as e:
            logger.error(f"Error executing scaling decision: {str(e)}")
            return False
    
    def run_auto_scaling_cycle(self) -> Dict[str, Any]:
        """
        Run a complete auto-scaling cycle
        
        Returns:
            Dict containing cycle results
        """
        try:
            start_time = datetime.now(timezone.utc)
            
            # Analyze metrics
            metrics = self.analyze_scaling_metrics()
            
            # Make scaling decision
            decision = self.make_scaling_decision(metrics)
            
            # Execute decision
            execution_success = self.execute_scaling_decision(decision)
            
            end_time = datetime.now(timezone.utc)
            cycle_duration = (end_time - start_time).total_seconds()
            
            result = {
                'timestamp': start_time.isoformat(),
                'cycle_duration_seconds': cycle_duration,
                'metrics': {
                    'queue_depth': metrics.queue_depth,
                    'processing_rate': metrics.processing_rate,
                    'current_concurrency': metrics.current_concurrency,
                    'error_rate': metrics.error_rate,
                    'cost_per_hour': metrics.cost_per_hour
                },
                'decision': {
                    'action': decision.action,
                    'target_concurrency': decision.target_concurrency,
                    'reason': decision.reason,
                    'confidence': decision.confidence,
                    'estimated_cost_impact': decision.estimated_cost_impact,
                    'estimated_performance_impact': decision.estimated_performance_impact
                },
                'execution_success': execution_success
            }
            
            # Store result for historical analysis
            self._store_scaling_result(result)
            
            return result
            
        except Exception as e:
            logger.error(f"Error in auto-scaling cycle: {str(e)}")
            return {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'error': str(e),
                'execution_success': False
            }
    
    def get_scaling_recommendations(self, time_horizon_hours: int = 24) -> Dict[str, Any]:
        """
        Get scaling recommendations for future time periods
        
        Args:
            time_horizon_hours: Hours to look ahead
            
        Returns:
            Dict containing recommendations
        """
        try:
            # Get historical patterns
            historical_data = self._get_historical_processing_patterns(time_horizon_hours)
            
            # Predict future load
            predicted_load = self._predict_future_load(historical_data, time_horizon_hours)
            
            # Generate recommendations
            recommendations = []
            
            for hour in range(time_horizon_hours):
                predicted_queue_depth = predicted_load.get(hour, 0)
                recommended_concurrency = self._calculate_optimal_concurrency(
                    predicted_queue_depth, 
                    historical_data.get('average_processing_rate', 1.0),
                    historical_data.get('average_processing_time', 30.0)
                )
                
                recommendations.append({
                    'hour': hour,
                    'predicted_queue_depth': predicted_queue_depth,
                    'recommended_concurrency': recommended_concurrency,
                    'estimated_cost': self._calculate_current_cost(recommended_concurrency, predicted_queue_depth / 60)
                })
            
            return {
                'time_horizon_hours': time_horizon_hours,
                'recommendations': recommendations,
                'total_estimated_cost': sum(r['estimated_cost'] for r in recommendations),
                'generated_at': datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error generating scaling recommendations: {str(e)}")
            return {'error': str(e)}
    
    def _get_processing_statistics(self) -> Dict[str, Any]:
        """Get processing statistics from monitoring service"""
        try:
            # Get recent processing data (last hour)
            end_time = datetime.now(timezone.utc)
            start_time = end_time - timedelta(hours=1)
            
            # This would integrate with your monitoring service
            # For now, return mock data
            return {
                'processing_rate': 5.0,  # documents per minute
                'average_processing_time': 30.0,  # seconds
                'error_rate': 0.05,  # 5% error rate
                'total_processed': 300,
                'total_errors': 15
            }
            
        except Exception as e:
            logger.error(f"Error getting processing statistics: {str(e)}")
            return {
                'processing_rate': 0.0,
                'average_processing_time': 30.0,
                'error_rate': 0.0,
                'total_processed': 0,
                'total_errors': 0
            }
    
    def _calculate_optimal_concurrency(self, queue_depth: int, processing_rate: float, avg_processing_time: float) -> int:
        """Calculate optimal concurrency based on queue and processing metrics"""
        if processing_rate <= 0:
            return self.min_concurrency
        
        # Calculate required concurrency to process queue in reasonable time
        target_processing_time_minutes = 10  # Process queue in 10 minutes
        required_rate = queue_depth / target_processing_time_minutes
        
        # Calculate concurrency needed for required rate
        # Each Lambda can process 60/avg_processing_time documents per minute
        docs_per_lambda_per_minute = 60 / max(avg_processing_time, 1)
        required_concurrency = int(required_rate / docs_per_lambda_per_minute) + 1
        
        # Apply bounds
        return max(self.min_concurrency, min(required_concurrency, self.max_concurrency))
    
    def _calculate_current_cost(self, concurrency: int, processing_rate: float) -> float:
        """Calculate current cost per hour"""
        # Provisioned concurrency cost
        memory_gb = 1.0  # Assume 1GB memory
        provisioned_cost = concurrency * memory_gb * 3600 * self.provisioned_concurrency_cost
        
        # Request cost
        requests_per_hour = processing_rate * 60
        request_cost = requests_per_hour * self.cost_per_request
        
        # Execution cost (approximate)
        execution_cost = requests_per_hour * memory_gb * 30 * self.cost_per_gb_second  # 30 seconds avg
        
        return provisioned_cost + request_cost + execution_cost
    
    def _calculate_cost_impact(self, current_concurrency: int, target_concurrency: int) -> float:
        """Calculate cost impact of scaling change"""
        current_cost = self._calculate_current_cost(current_concurrency, 5.0)  # Assume 5 docs/min
        target_cost = self._calculate_current_cost(target_concurrency, 5.0)
        return target_cost - current_cost
    
    def _estimate_performance_impact(self, action: str, concurrency_change: int) -> str:
        """Estimate performance impact of scaling change"""
        if action == 'scale_up':
            if concurrency_change >= 10:
                return 'significant_improvement'
            elif concurrency_change >= 5:
                return 'moderate_improvement'
            else:
                return 'minor_improvement'
        elif action == 'scale_down':
            if concurrency_change >= 10:
                return 'potential_degradation'
            elif concurrency_change >= 5:
                return 'minor_degradation'
            else:
                return 'minimal_impact'
        else:
            return 'none'
    
    def _calculate_confidence_score(self, processing_stats: Dict[str, Any]) -> float:
        """Calculate confidence score for scaling decisions"""
        total_processed = processing_stats.get('total_processed', 0)
        error_rate = processing_stats.get('error_rate', 0.0)
        
        # Base confidence on data volume and error rate
        data_confidence = min(total_processed / 100, 1.0)  # Full confidence at 100+ documents
        error_confidence = max(1.0 - error_rate * 2, 0.0)  # Reduce confidence with errors
        
        return (data_confidence + error_confidence) / 2
    
    def _is_in_cooldown(self) -> bool:
        """Check if we're in cooldown period"""
        last_scaling = cache.get('lambda_last_scaling_time')
        if not last_scaling:
            return False
        
        cooldown_end = last_scaling + timedelta(minutes=self.cooldown_period_minutes)
        return datetime.now(timezone.utc) < cooldown_end
    
    def _set_cooldown(self):
        """Set cooldown period"""
        cache.set('lambda_last_scaling_time', datetime.now(timezone.utc), 
                 timeout=self.cooldown_period_minutes * 60)
    
    def _record_scaling_action(self, decision: ScalingDecision):
        """Record scaling action for historical analysis"""
        scaling_history = cache.get('lambda_scaling_history', [])
        
        scaling_history.append({
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'action': decision.action,
            'target_concurrency': decision.target_concurrency,
            'reason': decision.reason,
            'confidence': decision.confidence,
            'cost_impact': decision.estimated_cost_impact
        })
        
        # Keep only last 100 entries
        scaling_history = scaling_history[-100:]
        
        cache.set('lambda_scaling_history', scaling_history, timeout=86400 * 7)  # 7 days
    
    def _store_scaling_result(self, result: Dict[str, Any]):
        """Store scaling cycle result"""
        scaling_results = cache.get('lambda_scaling_results', [])
        
        scaling_results.append(result)
        
        # Keep only last 100 results
        scaling_results = scaling_results[-100:]
        
        cache.set('lambda_scaling_results', scaling_results, timeout=86400 * 7)  # 7 days
    
    def _get_historical_processing_patterns(self, hours: int) -> Dict[str, Any]:
        """Get historical processing patterns"""
        # This would integrate with your monitoring/analytics system
        # For now, return mock data
        return {
            'average_processing_rate': 5.0,
            'average_processing_time': 30.0,
            'peak_hours': [9, 10, 11, 14, 15, 16],
            'low_hours': [0, 1, 2, 3, 4, 5, 22, 23]
        }
    
    def _predict_future_load(self, historical_data: Dict[str, Any], hours: int) -> Dict[int, int]:
        """Predict future load based on historical patterns"""
        current_hour = datetime.now().hour
        peak_hours = historical_data.get('peak_hours', [])
        low_hours = historical_data.get('low_hours', [])
        
        predictions = {}
        
        for hour in range(hours):
            future_hour = (current_hour + hour) % 24
            
            if future_hour in peak_hours:
                predictions[hour] = 50  # High load
            elif future_hour in low_hours:
                predictions[hour] = 5   # Low load
            else:
                predictions[hour] = 20  # Medium load
        
        return predictions
    
    def get_scaling_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get scaling history"""
        scaling_history = cache.get('lambda_scaling_history', [])
        return scaling_history[-limit:]
    
    def get_scaling_statistics(self) -> Dict[str, Any]:
        """Get scaling statistics"""
        try:
            scaling_results = cache.get('lambda_scaling_results', [])
            
            if not scaling_results:
                return {'message': 'No scaling data available'}
            
            # Calculate statistics
            total_cycles = len(scaling_results)
            successful_cycles = sum(1 for r in scaling_results if r.get('execution_success', False))
            
            actions = [r.get('decision', {}).get('action', 'unknown') for r in scaling_results]
            action_counts = {
                'scale_up': actions.count('scale_up'),
                'scale_down': actions.count('scale_down'),
                'maintain': actions.count('maintain')
            }
            
            # Average metrics
            avg_queue_depth = sum(r.get('metrics', {}).get('queue_depth', 0) for r in scaling_results) / total_cycles
            avg_cost_per_hour = sum(r.get('metrics', {}).get('cost_per_hour', 0) for r in scaling_results) / total_cycles
            
            return {
                'total_cycles': total_cycles,
                'successful_cycles': successful_cycles,
                'success_rate': successful_cycles / total_cycles if total_cycles > 0 else 0,
                'action_counts': action_counts,
                'average_queue_depth': avg_queue_depth,
                'average_cost_per_hour': avg_cost_per_hour,
                'last_cycle': scaling_results[-1] if scaling_results else None
            }
            
        except Exception as e:
            logger.error(f"Error getting scaling statistics: {str(e)}")
            return {'error': str(e)}