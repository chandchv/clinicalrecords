#!/usr/bin/env python3
"""
Django Management Command: Run Performance Tests

This command runs comprehensive performance and load tests for the clinical
records management system, including database performance, API response times,
file processing performance, and concurrent user simulation.

Usage:
    python manage.py run_performance_tests
    python manage.py run_performance_tests --load-users 20 --load-duration 60
    python manage.py run_performance_tests --skip-stress --output results.json
"""

import os
import sys
import time
import json
from datetime import datetime
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.test.utils import get_runner

from clinical_records.tests.run_performance_tests import PerformanceTestRunner


class Command(BaseCommand):
    help = 'Run comprehensive performance and load tests for clinical records system'
    
    def add_arguments(self, parser):
        """Add command line arguments."""
        parser.add_argument(
            '--load-users',
            type=int,
            default=10,
            help='Number of concurrent users for load test (default: 10)'
        )
        
        parser.add_argument(
            '--load-duration',
            type=int,
            default=30,
            help='Duration of load test in seconds (default: 30)'
        )
        
        parser.add_argument(
            '--endurance-minutes',
            type=int,
            default=2,
            help='Duration of endurance test in minutes (default: 2)'
        )
        
        parser.add_argument(
            '--skip-basic',
            action='store_true',
            help='Skip basic performance tests'
        )
        
        parser.add_argument(
            '--skip-load',
            action='store_true',
            help='Skip load testing'
        )
        
        parser.add_argument(
            '--skip-stress',
            action='store_true',
            help='Skip stress testing'
        )
        
        parser.add_argument(
            '--skip-endurance',
            action='store_true',
            help='Skip endurance testing'
        )
        
        parser.add_argument(
            '--output',
            type=str,
            help='Output file for test results (JSON format)'
        )
        
        parser.add_argument(
            '--report-dir',
            type=str,
            default='performance_reports',
            help='Directory to save performance reports (default: performance_reports)'
        )
        
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Enable verbose output'
        )
        
        parser.add_argument(
            '--quick',
            action='store_true',
            help='Run quick performance tests (reduced duration and users)'
        )
    
    def handle(self, *args, **options):
        """Handle the management command."""
        self.stdout.write(
            self.style.SUCCESS('🚀 Starting Performance & Load Tests')
        )
        
        # Adjust parameters for quick mode
        if options['quick']:
            options['load_users'] = min(options['load_users'], 5)
            options['load_duration'] = min(options['load_duration'], 15)
            options['endurance_minutes'] = min(options['endurance_minutes'], 1)
            self.stdout.write(
                self.style.WARNING('⚡ Quick mode enabled - reduced test parameters')
            )
        
        # Create report directory
        report_dir = Path(options['report_dir'])
        report_dir.mkdir(exist_ok=True)
        
        try:
            # Initialize performance test runner
            runner = PerformanceTestRunner()
            
            # Configure test parameters
            test_config = {
                'load_users': options['load_users'],
                'load_duration': options['load_duration'],
                'endurance_minutes': options['endurance_minutes'],
                'skip_basic': options['skip_basic'],
                'skip_load': options['skip_load'],
                'skip_stress': options['skip_stress'],
                'skip_endurance': options['skip_endurance'],
                'verbose': options['verbose']
            }
            
            self.stdout.write(f"Test Configuration: {test_config}")
            
            # Run performance tests
            start_time = time.time()
            success = self.run_performance_tests(runner, test_config)
            end_time = time.time()
            
            # Generate and save results
            output_file = self.save_results(
                runner, 
                options.get('output'), 
                report_dir,
                test_config,
                end_time - start_time
            )
            
            # Print summary
            self.print_summary(runner, success, end_time - start_time, output_file)
            
            if not success:
                raise CommandError('Performance tests completed with failures')
            
            self.stdout.write(
                self.style.SUCCESS('✅ Performance tests completed successfully')
            )
            
        except KeyboardInterrupt:
            self.stdout.write(
                self.style.ERROR('⚠️  Performance tests interrupted by user')
            )
            sys.exit(1)
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Performance tests failed: {str(e)}')
            )
            if options['verbose']:
                import traceback
                traceback.print_exc()
            raise CommandError(f'Performance test execution failed: {str(e)}')
    
    def run_performance_tests(self, runner, config):
        """Run the performance tests based on configuration."""
        success = True
        
        try:
            # 1. Run basic performance tests
            if not config['skip_basic']:
                self.stdout.write('🧪 Running basic performance tests...')
                basic_success = self.run_basic_tests(config['verbose'])
                if not basic_success:
                    success = False
                    self.stdout.write(
                        self.style.ERROR('❌ Basic performance tests failed')
                    )
                else:
                    self.stdout.write(
                        self.style.SUCCESS('✅ Basic performance tests passed')
                    )
            
            # 2. Run load tests
            if not config['skip_load']:
                self.stdout.write(
                    f"🔥 Running load test: {config['load_users']} users, "
                    f"{config['load_duration']}s duration..."
                )
                load_result = runner.run_load_simulation(
                    concurrent_users=config['load_users'],
                    duration_seconds=config['load_duration']
                )
                if load_result['success_rate'] < 90:
                    success = False
                    self.stdout.write(
                        self.style.ERROR(
                            f"❌ Load test failed: {load_result['success_rate']:.1f}% success rate"
                        )
                    )
            
            # 3. Run stress tests
            if not config['skip_stress']:
                self.stdout.write('💪 Running stress tests...')
                try:
                    runner.run_stress_test()
                    self.stdout.write(
                        self.style.SUCCESS('✅ Stress tests completed')
                    )
                except Exception as e:
                    success = False
                    self.stdout.write(
                        self.style.ERROR(f'❌ Stress tests failed: {str(e)}')
                    )
            
            # 4. Run endurance tests
            if not config['skip_endurance']:
                self.stdout.write(
                    f"⏰ Running endurance test: {config['endurance_minutes']} minutes..."
                )
                try:
                    runner.run_endurance_test(duration_minutes=config['endurance_minutes'])
                    self.stdout.write(
                        self.style.SUCCESS('✅ Endurance tests completed')
                    )
                except Exception as e:
                    success = False
                    self.stdout.write(
                        self.style.ERROR(f'❌ Endurance tests failed: {str(e)}')
                    )
            
            # 5. Analyze bottlenecks
            self.stdout.write('🔍 Analyzing performance bottlenecks...')
            runner.analyze_bottlenecks()
            
            # 6. Generate recommendations
            self.stdout.write('💡 Generating performance recommendations...')
            runner.generate_recommendations()
            
        except Exception as e:
            success = False
            self.stdout.write(
                self.style.ERROR(f'❌ Performance test execution error: {str(e)}')
            )
        
        return success
    
    def run_basic_tests(self, verbose=False):
        """Run basic Django unit tests for performance modules."""
        try:
            import subprocess
            
            cmd = [
                sys.executable, 'manage.py', 'test',
                'clinical_records.tests.test_performance_load',
                '--keepdb'
            ]
            
            if verbose:
                cmd.append('--verbosity=2')
            else:
                cmd.append('--verbosity=1')
            
            result = subprocess.run(
                cmd,
                capture_output=not verbose,
                text=True,
                cwd=settings.BASE_DIR
            )
            
            return result.returncode == 0
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error running basic tests: {str(e)}')
            )
            return False
    
    def save_results(self, runner, output_file, report_dir, config, duration):
        """Save performance test results."""
        if not output_file:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = report_dir / f'performance_results_{timestamp}.json'
        else:
            output_file = Path(output_file)
        
        # Add command metadata to results
        runner.results['command_metadata'] = {
            'executed_at': datetime.now().isoformat(),
            'execution_duration': duration,
            'configuration': config,
            'django_settings': {
                'debug': settings.DEBUG,
                'database_engine': settings.DATABASES['default']['ENGINE'],
                'cache_backend': getattr(settings, 'CACHES', {}).get('default', {}).get('BACKEND', 'None')
            }
        }
        
        # Save results
        with open(output_file, 'w') as f:
            json.dump(runner.results, f, indent=2, default=str)
        
        self.stdout.write(f"📄 Results saved to: {output_file}")
        return output_file
    
    def print_summary(self, runner, success, duration, output_file):
        """Print performance test summary."""
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write("📊 PERFORMANCE TEST SUMMARY")
        self.stdout.write("=" * 60)
        
        # Execution summary
        self.stdout.write(f"Execution time: {duration:.2f} seconds")
        self.stdout.write(f"Overall result: {'✅ PASSED' if success else '❌ FAILED'}")
        
        # Load test results
        if 'load_test_results' in runner.results:
            load_results = runner.results['load_test_results']
            self.stdout.write(f"\n🔥 Load Test Results:")
            self.stdout.write(f"   Success rate: {load_results['success_rate']:.1f}%")
            self.stdout.write(f"   Requests/second: {load_results['requests_per_second']:.1f}")
            self.stdout.write(f"   Avg response time: {load_results['avg_response_time']:.3f}s")
        
        # Stress test results
        if 'stress_test_results' in runner.results:
            stress_results = runner.results['stress_test_results']
            self.stdout.write(f"\n💪 Stress Test Results:")
            self.stdout.write(f"   Max concurrent users: {stress_results['max_concurrent_users']}")
            self.stdout.write(f"   Max requests/second: {stress_results['max_requests_per_second']:.1f}")
        
        # Bottlenecks
        bottlenecks = runner.results.get('bottlenecks', [])
        if bottlenecks:
            self.stdout.write(f"\n⚠️  Performance Issues: {len(bottlenecks)}")
            for bottleneck in bottlenecks[:3]:
                severity_color = self.style.ERROR if bottleneck['severity'] == 'HIGH' else self.style.WARNING
                self.stdout.write(
                    severity_color(f"   • {bottleneck['type']}: {bottleneck['description']}")
                )
        else:
            self.stdout.write(self.style.SUCCESS("\n✅ No significant performance issues detected"))
        
        # High priority recommendations
        recommendations = runner.results.get('recommendations', [])
        high_priority = [r for r in recommendations if r.get('priority') == 'HIGH']
        if high_priority:
            self.stdout.write(f"\n🔴 High Priority Actions: {len(high_priority)}")
            for rec in high_priority[:2]:
                self.stdout.write(f"   • {rec['category']}: {rec['action']}")
        
        self.stdout.write(f"\n📄 Detailed results: {output_file}")
        self.stdout.write("=" * 60)