"""
AWS Lambda Cost Optimization Service

This service provides intelligent cost optimization for Lambda functions,
including usage analysis, cost forecasting, and optimization recommendations.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from django.conf import settings
from django.core.cache import cache
import boto3
from decimal import Decimal, ROUND_HALF_UP

logger = logging.getLogger(__name__)


@dataclass
class CostMetrics:
    """Data class for cost metrics"""
    period_start: datetime
    period_end: datetime
    total_cost: float
    execution_cost: float
    provisioned_concurrency_cost: float
    request_cost: float
    total_invocations: int
    total_duration_ms: int
    average_duration_ms: float
    memory_size_mb: int
    cost_per_invocation: float
    cost_per_gb_second: float


@dataclass
class OptimizationRecommendation:
    """Data class for optimization recommendations"""
    recommendation_type: str
    current_value: Any
    recommended_value: Any
    estimated_savings_monthly: float
    estimated_savings_percentage: float
    impact_description: str
    confidence_level: str
    implementation_effort: str


class LambdaCostOptimizer:
    """
    Service for optimizing Lambda function costs
    """
    
    def __init__(self):
        """Initialize cost optimizer"""
        self.cloudwatch_client = boto3.client('cloudwatch')
        self.lambda_client = boto3.client('lambda')
        self.pricing_client = boto3.client('pricing', region_name='us-east-1')  # Pricing API only in us-east-1
        
        # AWS Lambda pricing (approximate, should be fetched from Pricing API)
        self.pricing = {
            'request_cost': 0.0000002,  # $0.0000002 per request
            'gb_second_cost': 0.0000166667,  # $0.0000166667 per GB-second
            'provisioned_concurrency_cost': 0.0000041667,  # $0.0000041667 per GB-second
            'free_tier_requests': 1000000,  # 1M free requests per month
            'free_tier_gb_seconds': 400000  # 400,000 GB-seconds per month
        }
        
        self.function_name = getattr(settings, 'LAMBDA_DOCUMENT_PROCESSOR_NAME', 
                                   'clinical-document-processor')
    
    def analyze_cost_metrics(self, days: int = 30) -> CostMetrics:
        """
        Analyze Lambda function cost metrics for the specified period
        
        Args:
            days: Number of days to analyze
            
        Returns:
            CostMetrics object with cost analysis
        """
        try:
            end_time = datetime.now(timezone.utc)
            start_time = end_time - timedelta(days=days)
            
            # Get CloudWatch metrics
            metrics = self._get_cloudwatch_metrics(start_time, end_time)
            
            # Get function configuration
            function_config = self.lambda_client.get_function(
                FunctionName=self.function_name
            )['Configuration']
            
            memory_size_mb = function_config['MemorySize']
            memory_size_gb = memory_size_mb / 1024
            
            # Calculate costs
            total_invocations = metrics.get('invocations', 0)
            total_duration_ms = metrics.get('duration_ms', 0)
            total_duration_seconds = total_duration_ms / 1000
            
            # Request cost
            billable_requests = max(0, total_invocations - self.pricing['free_tier_requests'])
            request_cost = billable_requests * self.pricing['request_cost']
            
            # Execution cost
            total_gb_seconds = (total_duration_seconds * memory_size_gb)
            billable_gb_seconds = max(0, total_gb_seconds - self.pricing['free_tier_gb_seconds'])
            execution_cost = billable_gb_seconds * self.pricing['gb_second_cost']
            
            # Provisioned concurrency cost
            provisioned_concurrency = self._get_provisioned_concurrency()
            provisioned_gb_seconds = provisioned_concurrency * memory_size_gb * (days * 24 * 3600)
            provisioned_concurrency_cost = provisioned_gb_seconds * self.pricing['provisioned_concurrency_cost']
            
            total_cost = request_cost + execution_cost + provisioned_concurrency_cost
            
            # Calculate averages
            average_duration_ms = total_duration_ms / max(total_invocations, 1)
            cost_per_invocation = total_cost / max(total_invocations, 1)
            cost_per_gb_second = total_cost / max(total_gb_seconds, 1)
            
            return CostMetrics(
                period_start=start_time,
                period_end=end_time,
                total_cost=total_cost,
                execution_cost=execution_cost,
                provisioned_concurrency_cost=provisioned_concurrency_cost,
                request_cost=request_cost,
                total_invocations=total_invocations,
                total_duration_ms=total_duration_ms,
                average_duration_ms=average_duration_ms,
                memory_size_mb=memory_size_mb,
                cost_per_invocation=cost_per_invocation,
                cost_per_gb_second=cost_per_gb_second
            )
            
        except Exception as e:
            logger.error(f"Error analyzing cost metrics: {str(e)}")
            # Return default metrics
            return CostMetrics(
                period_start=datetime.now(timezone.utc) - timedelta(days=days),
                period_end=datetime.now(timezone.utc),
                total_cost=0.0,
                execution_cost=0.0,
                provisioned_concurrency_cost=0.0,
                request_cost=0.0,
                total_invocations=0,
                total_duration_ms=0,
                average_duration_ms=0.0,
                memory_size_mb=1024,
                cost_per_invocation=0.0,
                cost_per_gb_second=0.0
            )
    
    def generate_optimization_recommendations(self, cost_metrics: CostMetrics) -> List[OptimizationRecommendation]:
        """
        Generate cost optimization recommendations
        
        Args:
            cost_metrics: Current cost metrics
            
        Returns:
            List of optimization recommendations
        """
        recommendations = []
        
        try:
            # Memory optimization
            memory_rec = self._analyze_memory_optimization(cost_metrics)
            if memory_rec:
                recommendations.append(memory_rec)
            
            # Provisioned concurrency optimization
            concurrency_rec = self._analyze_concurrency_optimization(cost_metrics)
            if concurrency_rec:
                recommendations.append(concurrency_rec)
            
            # Timeout optimization
            timeout_rec = self._analyze_timeout_optimization(cost_metrics)
            if timeout_rec:
                recommendations.append(timeout_rec)
            
            # Architecture optimization
            arch_rec = self._analyze_architecture_optimization(cost_metrics)
            if arch_rec:
                recommendations.append(arch_rec)
            
            # Usage pattern optimization
            usage_rec = self._analyze_usage_patterns(cost_metrics)
            if usage_rec:
                recommendations.append(usage_rec)
            
            return recommendations
            
        except Exception as e:
            logger.error(f"Error generating optimization recommendations: {str(e)}")
            return []
    
    def _analyze_memory_optimization(self, metrics: CostMetrics) -> Optional[OptimizationRecommendation]:
        """Analyze memory allocation optimization"""
        try:
            current_memory = metrics.memory_size_mb
            avg_duration = metrics.average_duration_ms
            
            # Get memory utilization data (would need CloudWatch Insights or X-Ray)
            # For now, use heuristics based on duration
            
            if avg_duration > 60000:  # > 1 minute
                # Likely memory-bound, recommend increase
                recommended_memory = min(current_memory * 2, 3008)
                
                # Calculate cost impact
                current_cost_per_invocation = metrics.cost_per_invocation
                new_cost_per_invocation = current_cost_per_invocation * (recommended_memory / current_memory) * 0.7  # Assume 30% duration reduction
                
                monthly_savings = (current_cost_per_invocation - new_cost_per_invocation) * metrics.total_invocations * (30 / ((metrics.period_end - metrics.period_start).days))
                
                if monthly_savings > 0:
                    return OptimizationRecommendation(
                        recommendation_type='memory_increase',
                        current_value=current_memory,
                        recommended_value=recommended_memory,
                        estimated_savings_monthly=monthly_savings,
                        estimated_savings_percentage=(monthly_savings / (metrics.total_cost * 30 / ((metrics.period_end - metrics.period_start).days))) * 100,
                        impact_description=f'Increase memory to reduce execution time and overall cost',
                        confidence_level='medium',
                        implementation_effort='low'
                    )
            
            elif avg_duration < 5000 and current_memory > 512:  # < 5 seconds and high memory
                # Likely over-provisioned, recommend decrease
                recommended_memory = max(current_memory // 2, 128)
                
                # Calculate cost impact
                memory_ratio = recommended_memory / current_memory
                monthly_cost = metrics.total_cost * (30 / ((metrics.period_end - metrics.period_start).days))
                monthly_savings = monthly_cost * (1 - memory_ratio)
                
                return OptimizationRecommendation(
                    recommendation_type='memory_decrease',
                    current_value=current_memory,
                    recommended_value=recommended_memory,
                    estimated_savings_monthly=monthly_savings,
                    estimated_savings_percentage=(monthly_savings / monthly_cost) * 100,
                    impact_description=f'Reduce memory allocation to save costs without impacting performance',
                    confidence_level='high',
                    implementation_effort='low'
                )
            
            return None
            
        except Exception as e:
            logger.error(f"Error analyzing memory optimization: {str(e)}")
            return None
    
    def _analyze_concurrency_optimization(self, metrics: CostMetrics) -> Optional[OptimizationRecommendation]:
        """Analyze provisioned concurrency optimization"""
        try:
            current_concurrency = self._get_provisioned_concurrency()
            
            if current_concurrency == 0:
                return None
            
            # Analyze usage patterns
            daily_invocations = metrics.total_invocations / ((metrics.period_end - metrics.period_start).days)
            peak_concurrency_needed = self._estimate_peak_concurrency(daily_invocations)
            
            if current_concurrency > peak_concurrency_needed * 1.5:
                # Over-provisioned
                recommended_concurrency = max(peak_concurrency_needed, 1)
                
                # Calculate savings
                concurrency_reduction = current_concurrency - recommended_concurrency
                memory_gb = metrics.memory_size_mb / 1024
                daily_savings = concurrency_reduction * memory_gb * 24 * 3600 * self.pricing['provisioned_concurrency_cost']
                monthly_savings = daily_savings * 30
                
                return OptimizationRecommendation(
                    recommendation_type='concurrency_reduction',
                    current_value=current_concurrency,
                    recommended_value=recommended_concurrency,
                    estimated_savings_monthly=monthly_savings,
                    estimated_savings_percentage=(monthly_savings / (metrics.total_cost * 30 / ((metrics.period_end - metrics.period_start).days))) * 100,
                    impact_description=f'Reduce provisioned concurrency to match actual usage patterns',
                    confidence_level='high',
                    implementation_effort='low'
                )
            
            elif metrics.provisioned_concurrency_cost / metrics.total_cost > 0.8:
                # Provisioned concurrency is too expensive, recommend removal
                return OptimizationRecommendation(
                    recommendation_type='remove_provisioned_concurrency',
                    current_value=current_concurrency,
                    recommended_value=0,
                    estimated_savings_monthly=metrics.provisioned_concurrency_cost * 30 / ((metrics.period_end - metrics.period_start).days),
                    estimated_savings_percentage=(metrics.provisioned_concurrency_cost / metrics.total_cost) * 100,
                    impact_description='Remove provisioned concurrency and accept cold start latency',
                    confidence_level='medium',
                    implementation_effort='low'
                )
            
            return None
            
        except Exception as e:
            logger.error(f"Error analyzing concurrency optimization: {str(e)}")
            return None
    
    def _analyze_timeout_optimization(self, metrics: CostMetrics) -> Optional[OptimizationRecommendation]:
        """Analyze timeout configuration optimization"""
        try:
            function_config = self.lambda_client.get_function(
                FunctionName=self.function_name
            )['Configuration']
            
            current_timeout = function_config['Timeout']
            max_duration_seconds = metrics.total_duration_ms / 1000 / max(metrics.total_invocations, 1)
            
            # If timeout is much higher than actual usage, recommend reduction
            if current_timeout > max_duration_seconds * 2 and current_timeout > 30:
                recommended_timeout = max(int(max_duration_seconds * 1.5), 30)
                
                # Timeout doesn't directly affect cost, but prevents runaway executions
                return OptimizationRecommendation(
                    recommendation_type='timeout_reduction',
                    current_value=current_timeout,
                    recommended_value=recommended_timeout,
                    estimated_savings_monthly=0.0,  # Indirect savings from preventing runaway executions
                    estimated_savings_percentage=0.0,
                    impact_description='Reduce timeout to prevent runaway executions and improve error detection',
                    confidence_level='high',
                    implementation_effort='low'
                )
            
            return None
            
        except Exception as e:
            logger.error(f"Error analyzing timeout optimization: {str(e)}")
            return None
    
    def _analyze_architecture_optimization(self, metrics: CostMetrics) -> Optional[OptimizationRecommendation]:
        """Analyze architecture optimization opportunities"""
        try:
            # If cost per invocation is very high, suggest architectural changes
            if metrics.cost_per_invocation > 0.01:  # $0.01 per invocation is quite high
                return OptimizationRecommendation(
                    recommendation_type='architecture_review',
                    current_value='lambda_processing',
                    recommended_value='hybrid_processing',
                    estimated_savings_monthly=metrics.total_cost * 0.3 * 30 / ((metrics.period_end - metrics.period_start).days),
                    estimated_savings_percentage=30.0,
                    impact_description='Consider hybrid approach: Lambda for small files, EC2/ECS for large files',
                    confidence_level='medium',
                    implementation_effort='high'
                )
            
            # If very high volume, suggest batch processing
            daily_invocations = metrics.total_invocations / ((metrics.period_end - metrics.period_start).days)
            if daily_invocations > 10000:
                return OptimizationRecommendation(
                    recommendation_type='batch_processing',
                    current_value='individual_processing',
                    recommended_value='batch_processing',
                    estimated_savings_monthly=metrics.total_cost * 0.2 * 30 / ((metrics.period_end - metrics.period_start).days),
                    estimated_savings_percentage=20.0,
                    impact_description='Implement batch processing to reduce per-document overhead',
                    confidence_level='high',
                    implementation_effort='medium'
                )
            
            return None
            
        except Exception as e:
            logger.error(f"Error analyzing architecture optimization: {str(e)}")
            return None
    
    def _analyze_usage_patterns(self, metrics: CostMetrics) -> Optional[OptimizationRecommendation]:
        """Analyze usage patterns for optimization"""
        try:
            # Get hourly usage patterns
            usage_patterns = self._get_usage_patterns(metrics.period_start, metrics.period_end)
            
            # If usage is very spiky, recommend different scaling strategy
            if usage_patterns.get('peak_to_average_ratio', 1) > 5:
                return OptimizationRecommendation(
                    recommendation_type='scaling_strategy',
                    current_value='reactive_scaling',
                    recommended_value='predictive_scaling',
                    estimated_savings_monthly=metrics.total_cost * 0.15 * 30 / ((metrics.period_end - metrics.period_start).days),
                    estimated_savings_percentage=15.0,
                    impact_description='Implement predictive scaling based on usage patterns',
                    confidence_level='medium',
                    implementation_effort='medium'
                )
            
            return None
            
        except Exception as e:
            logger.error(f"Error analyzing usage patterns: {str(e)}")
            return None
    
    def forecast_costs(self, days_ahead: int = 30) -> Dict[str, Any]:
        """
        Forecast Lambda costs for the specified period
        
        Args:
            days_ahead: Number of days to forecast
            
        Returns:
            Dict containing cost forecast
        """
        try:
            # Get historical metrics
            historical_metrics = self.analyze_cost_metrics(days=30)
            
            # Calculate daily averages
            historical_days = (historical_metrics.period_end - historical_metrics.period_start).days
            daily_cost = historical_metrics.total_cost / historical_days
            daily_invocations = historical_metrics.total_invocations / historical_days
            
            # Apply growth factors (could be made more sophisticated)
            growth_factor = self._estimate_growth_factor()
            
            # Forecast
            forecasted_daily_cost = daily_cost * growth_factor
            forecasted_total_cost = forecasted_daily_cost * days_ahead
            forecasted_daily_invocations = daily_invocations * growth_factor
            forecasted_total_invocations = forecasted_daily_invocations * days_ahead
            
            return {
                'forecast_period_days': days_ahead,
                'historical_daily_cost': daily_cost,
                'forecasted_daily_cost': forecasted_daily_cost,
                'forecasted_total_cost': forecasted_total_cost,
                'historical_daily_invocations': daily_invocations,
                'forecasted_daily_invocations': forecasted_daily_invocations,
                'forecasted_total_invocations': forecasted_total_invocations,
                'growth_factor': growth_factor,
                'confidence_level': 'medium',
                'generated_at': datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error forecasting costs: {str(e)}")
            return {'error': str(e)}
    
    def get_cost_breakdown(self, days: int = 30) -> Dict[str, Any]:
        """
        Get detailed cost breakdown
        
        Args:
            days: Number of days to analyze
            
        Returns:
            Dict containing detailed cost breakdown
        """
        try:
            metrics = self.analyze_cost_metrics(days)
            
            return {
                'period': {
                    'start': metrics.period_start.isoformat(),
                    'end': metrics.period_end.isoformat(),
                    'days': days
                },
                'total_cost': {
                    'amount': round(metrics.total_cost, 6),
                    'currency': 'USD'
                },
                'cost_breakdown': {
                    'execution_cost': {
                        'amount': round(metrics.execution_cost, 6),
                        'percentage': round((metrics.execution_cost / max(metrics.total_cost, 0.000001)) * 100, 2)
                    },
                    'request_cost': {
                        'amount': round(metrics.request_cost, 6),
                        'percentage': round((metrics.request_cost / max(metrics.total_cost, 0.000001)) * 100, 2)
                    },
                    'provisioned_concurrency_cost': {
                        'amount': round(metrics.provisioned_concurrency_cost, 6),
                        'percentage': round((metrics.provisioned_concurrency_cost / max(metrics.total_cost, 0.000001)) * 100, 2)
                    }
                },
                'usage_metrics': {
                    'total_invocations': metrics.total_invocations,
                    'total_duration_ms': metrics.total_duration_ms,
                    'average_duration_ms': round(metrics.average_duration_ms, 2),
                    'memory_size_mb': metrics.memory_size_mb
                },
                'efficiency_metrics': {
                    'cost_per_invocation': round(metrics.cost_per_invocation, 6),
                    'cost_per_gb_second': round(metrics.cost_per_gb_second, 6),
                    'invocations_per_dollar': round(1 / max(metrics.cost_per_invocation, 0.000001), 2)
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting cost breakdown: {str(e)}")
            return {'error': str(e)}
    
    def _get_cloudwatch_metrics(self, start_time: datetime, end_time: datetime) -> Dict[str, Any]:
        """Get CloudWatch metrics for the function"""
        try:
            # Get invocations
            invocations_response = self.cloudwatch_client.get_metric_statistics(
                Namespace='AWS/Lambda',
                MetricName='Invocations',
                Dimensions=[
                    {
                        'Name': 'FunctionName',
                        'Value': self.function_name
                    }
                ],
                StartTime=start_time,
                EndTime=end_time,
                Period=3600,  # 1 hour
                Statistics=['Sum']
            )
            
            total_invocations = sum(point['Sum'] for point in invocations_response['Datapoints'])
            
            # Get duration
            duration_response = self.cloudwatch_client.get_metric_statistics(
                Namespace='AWS/Lambda',
                MetricName='Duration',
                Dimensions=[
                    {
                        'Name': 'FunctionName',
                        'Value': self.function_name
                    }
                ],
                StartTime=start_time,
                EndTime=end_time,
                Period=3600,  # 1 hour
                Statistics=['Sum']
            )
            
            total_duration_ms = sum(point['Sum'] for point in duration_response['Datapoints'])
            
            return {
                'invocations': int(total_invocations),
                'duration_ms': int(total_duration_ms)
            }
            
        except Exception as e:
            logger.error(f"Error getting CloudWatch metrics: {str(e)}")
            return {'invocations': 0, 'duration_ms': 0}
    
    def _get_provisioned_concurrency(self) -> int:
        """Get current provisioned concurrency"""
        try:
            response = self.lambda_client.get_provisioned_concurrency_config(
                FunctionName=self.function_name
            )
            return response['RequestedProvisionedConcurrencyUnits']
        except:
            return 0
    
    def _estimate_peak_concurrency(self, daily_invocations: float) -> int:
        """Estimate peak concurrency needed based on daily invocations"""
        # Simple heuristic: assume peak hour has 20% of daily traffic
        peak_hour_invocations = daily_invocations * 0.2
        # Assume average execution time of 30 seconds
        peak_concurrency = max(1, int(peak_hour_invocations * 30 / 3600))
        return peak_concurrency
    
    def _get_usage_patterns(self, start_time: datetime, end_time: datetime) -> Dict[str, Any]:
        """Get usage patterns for the specified period"""
        try:
            # Get hourly invocation data
            response = self.cloudwatch_client.get_metric_statistics(
                Namespace='AWS/Lambda',
                MetricName='Invocations',
                Dimensions=[
                    {
                        'Name': 'FunctionName',
                        'Value': self.function_name
                    }
                ],
                StartTime=start_time,
                EndTime=end_time,
                Period=3600,  # 1 hour
                Statistics=['Sum']
            )
            
            hourly_invocations = [point['Sum'] for point in response['Datapoints']]
            
            if not hourly_invocations:
                return {'peak_to_average_ratio': 1}
            
            peak_invocations = max(hourly_invocations)
            average_invocations = sum(hourly_invocations) / len(hourly_invocations)
            
            peak_to_average_ratio = peak_invocations / max(average_invocations, 1)
            
            return {
                'peak_to_average_ratio': peak_to_average_ratio,
                'peak_invocations': peak_invocations,
                'average_invocations': average_invocations
            }
            
        except Exception as e:
            logger.error(f"Error getting usage patterns: {str(e)}")
            return {'peak_to_average_ratio': 1}
    
    def _estimate_growth_factor(self) -> float:
        """Estimate growth factor for cost forecasting"""
        # Simple heuristic - could be made more sophisticated with ML
        # For now, assume 10% monthly growth
        return 1.1
    
    def apply_optimization_recommendation(self, recommendation: OptimizationRecommendation) -> bool:
        """
        Apply an optimization recommendation
        
        Args:
            recommendation: Recommendation to apply
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            if recommendation.recommendation_type == 'memory_increase' or recommendation.recommendation_type == 'memory_decrease':
                # Update memory size
                self.lambda_client.update_function_configuration(
                    FunctionName=self.function_name,
                    MemorySize=recommendation.recommended_value
                )
                logger.info(f"Updated memory size to {recommendation.recommended_value}MB")
                return True
            
            elif recommendation.recommendation_type == 'timeout_reduction':
                # Update timeout
                self.lambda_client.update_function_configuration(
                    FunctionName=self.function_name,
                    Timeout=recommendation.recommended_value
                )
                logger.info(f"Updated timeout to {recommendation.recommended_value} seconds")
                return True
            
            elif recommendation.recommendation_type == 'concurrency_reduction':
                # Update provisioned concurrency
                if recommendation.recommended_value > 0:
                    self.lambda_client.put_provisioned_concurrency_config(
                        FunctionName=self.function_name,
                        ProvisionedConcurrencyUnits=recommendation.recommended_value
                    )
                else:
                    self.lambda_client.delete_provisioned_concurrency_config(
                        FunctionName=self.function_name
                    )
                logger.info(f"Updated provisioned concurrency to {recommendation.recommended_value}")
                return True
            
            elif recommendation.recommendation_type == 'remove_provisioned_concurrency':
                # Remove provisioned concurrency
                try:
                    self.lambda_client.delete_provisioned_concurrency_config(
                        FunctionName=self.function_name
                    )
                    logger.info("Removed provisioned concurrency")
                    return True
                except:
                    # Already removed
                    return True
            
            else:
                logger.warning(f"Cannot automatically apply recommendation type: {recommendation.recommendation_type}")
                return False
                
        except Exception as e:
            logger.error(f"Error applying optimization recommendation: {str(e)}")
            return False
    
    def get_optimization_report(self, days: int = 30) -> Dict[str, Any]:
        """
        Generate comprehensive optimization report
        
        Args:
            days: Number of days to analyze
            
        Returns:
            Dict containing optimization report
        """
        try:
            # Get cost metrics
            cost_metrics = self.analyze_cost_metrics(days)
            
            # Get recommendations
            recommendations = self.generate_optimization_recommendations(cost_metrics)
            
            # Get cost breakdown
            cost_breakdown = self.get_cost_breakdown(days)
            
            # Get forecast
            forecast = self.forecast_costs(30)
            
            # Calculate potential savings
            total_potential_savings = sum(rec.estimated_savings_monthly for rec in recommendations)
            
            return {
                'report_generated_at': datetime.now(timezone.utc).isoformat(),
                'analysis_period_days': days,
                'current_costs': cost_breakdown,
                'forecast': forecast,
                'recommendations': [
                    {
                        'type': rec.recommendation_type,
                        'current_value': rec.current_value,
                        'recommended_value': rec.recommended_value,
                        'estimated_monthly_savings': round(rec.estimated_savings_monthly, 4),
                        'estimated_savings_percentage': round(rec.estimated_savings_percentage, 2),
                        'impact_description': rec.impact_description,
                        'confidence_level': rec.confidence_level,
                        'implementation_effort': rec.implementation_effort
                    }
                    for rec in recommendations
                ],
                'summary': {
                    'total_recommendations': len(recommendations),
                    'total_potential_monthly_savings': round(total_potential_savings, 4),
                    'potential_savings_percentage': round((total_potential_savings / max(cost_metrics.total_cost * 30 / days, 0.000001)) * 100, 2),
                    'high_impact_recommendations': len([r for r in recommendations if r.estimated_savings_percentage > 10]),
                    'low_effort_recommendations': len([r for r in recommendations if r.implementation_effort == 'low'])
                }
            }
            
        except Exception as e:
            logger.error(f"Error generating optimization report: {str(e)}")
            return {'error': str(e)}