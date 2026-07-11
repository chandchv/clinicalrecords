"""
Django management command for running security and penetration tests.

This command provides a convenient way to run comprehensive security tests
from the Django management interface with various options and reporting.
"""

import os
import sys
import time
import json
from pathlib import Path
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

# Add the tests directory to Python path
tests_dir = Path(__file__).parent.parent.parent / 'tests'
sys.path.insert(0, str(tests_dir))

try:
    from run_security_tests import SecurityTestRunner
except ImportError:
    SecurityTestRunner = None


class Command(BaseCommand):
    """Management command for security and penetration testing."""
    
    help = 'Run comprehensive security and penetration tests'
    
    def add_arguments(self, parser):
        """Add command line arguments."""
        parser.add_argument(
            '--module',
            type=str,
            help='Run specific test module (e.g., test_security_penetration)'
        )
        
        parser.add_argument(
            '--report',
            action='store_true',
            help='Generate detailed security report'
        )
        
        parser.add_argument(
            '--output',
            type=str,
            help='Output file for security report'
        )
        
        parser.add_argument(
            '--risk-assessment',
            action='store_true',
            help='Include comprehensive risk assessment'
        )
        
        parser.add_argument(
            '--penetration-only',
            action='store_true',
            help='Run only penetration tests'
        )
        
        parser.add_argument(
            '--compliance-check',
            action='store_true',
            help='Focus on compliance-related security tests'
        )
        
        parser.add_argument(
            '--list-modules',
            action='store_true',
            help='List available security test modules'
        )
        
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Enable verbose output'
        )
    
    def handle(self, *args, **options):
        """Handle the management command."""
        if SecurityTestRunner is None:
            raise CommandError(
                "Security test runner not available. "
                "Please ensure run_security_tests.py is in the tests directory."
            )
        
        # List modules if requested
        if options['list_modules']:
            self.list_security_modules()
            return
        
        # Initialize security test runner
        runner = SecurityTestRunner()
        
        # Configure test modules based on options
        if options['penetration_only']:
            runner.test_modules = [
                'clinical_records.tests.test_security_penetration'
            ]
            self.stdout.write(
                self.style.WARNING("Running penetration tests only")
            )
        
        elif options['compliance_check']:
            runner.test_modules = [
                'clinical_records.tests.test_access_control_system',
                'clinical_records.tests.test_audit_system',
                'clinical_records.tests.test_encryption_system'
            ]
            self.stdout.write(
                self.style.WARNING("Running compliance-focused security tests")
            )
        
        elif options['module']:
            module_name = options['module']
            if not module_name.startswith('clinical_records.tests.'):
                module_name = f'clinical_records.tests.{module_name}'
            
            if module_name in runner.test_modules:
                runner.test_modules = [module_name]
                self.stdout.write(
                    self.style.SUCCESS(f"Running specific module: {module_name}")
                )
            else:
                raise CommandError(
                    f"Module '{module_name}' not found. "
                    f"Available modules: {', '.join(runner.test_modules)}"
                )
        
        # Set verbosity
        if options['verbose']:
            self.stdout.write(
                self.style.SUCCESS("Verbose mode enabled")
            )
        
        # Run security tests
        self.stdout.write(
            self.style.SUCCESS("🔒 Starting comprehensive security tests...")
        )
        
        start_time = time.time()
        
        try:
            success = runner.run_all_tests()
            execution_time = time.time() - start_time
            
            # Print results with appropriate styling
            if success:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"\\n🎉 All security tests passed! "
                        f"({execution_time:.2f}s)"
                    )
                )
                self.stdout.write(
                    self.style.SUCCESS(
                        "✅ System appears secure against tested attack vectors"
                    )
                )
            else:
                self.stdout.write(
                    self.style.ERROR(
                        f"\\n❌ Security tests failed! "
                        f"({execution_time:.2f}s)"
                    )
                )
                self.stdout.write(
                    self.style.ERROR(
                        "🚨 SECURITY VULNERABILITIES DETECTED"
                    )
                )
                
                # Show summary of failures
                if runner.results['security_issues']:
                    self.stdout.write(
                        self.style.WARNING("\\nSecurity issues found:")
                    )
                    for issue in runner.results['security_issues']:
                        self.stdout.write(
                            self.style.ERROR(f"  - {issue['module']}")
                        )
            
            # Generate report if requested
            if options['report'] or options['risk_assessment']:
                output_file = options.get('output')
                report_file = runner.generate_security_report(output_file)
                
                self.stdout.write(
                    self.style.SUCCESS(
                        f"\\n📄 Security report generated: {report_file}"
                    )
                )
            
            # Print security recommendations
            self.print_security_recommendations(runner.results, success)
            
            # Print compliance status
            if options['compliance_check'] or options['risk_assessment']:
                self.print_compliance_status(runner.results)
            
        except Exception as e:
            raise CommandError(f"Error running security tests: {str(e)}")
    
    def list_security_modules(self):
        """List available security test modules."""
        runner = SecurityTestRunner()
        
        self.stdout.write(
            self.style.SUCCESS("Available security test modules:")
        )
        
        module_descriptions = {
            'test_security_penetration': 'Comprehensive penetration testing suite',
            'test_encryption_system': 'Encryption and data protection tests',
            'test_access_control_system': 'Access control and authorization tests',
            'test_audit_system': 'Audit logging and monitoring tests'
        }
        
        for i, module in enumerate(runner.test_modules, 1):
            module_short = module.replace('clinical_records.tests.', '')
            description = module_descriptions.get(module_short, 'Security tests')
            
            self.stdout.write(f"  {i}. {module_short}")
            self.stdout.write(
                self.style.WARNING(f"     → {description}")
            )
        
        self.stdout.write(
            self.style.SUCCESS(
                "\\nUse --module <module_name> to run specific tests"
            )
        )
    
    def print_security_recommendations(self, results, success):
        """Print security recommendations based on test results."""
        self.stdout.write(
            self.style.SUCCESS("\\n🔒 SECURITY RECOMMENDATIONS:")
        )
        
        if not success:
            self.stdout.write(
                self.style.ERROR("\\nIMMEDIATE ACTIONS REQUIRED:")
            )
            self.stdout.write(
                "  1. Review and fix all failed security tests"
            )
            self.stdout.write(
                "  2. Conduct security code review"
            )
            self.stdout.write(
                "  3. Re-run tests to verify fixes"
            )
            self.stdout.write(
                "  4. Consider external security audit"
            )
        
        self.stdout.write(
            self.style.SUCCESS("\\nONGOING SECURITY PRACTICES:")
        )
        self.stdout.write(
            "  1. Run security tests regularly (weekly/monthly)"
        )
        self.stdout.write(
            "  2. Keep all dependencies updated"
        )
        self.stdout.write(
            "  3. Monitor security advisories and CVEs"
        )
        self.stdout.write(
            "  4. Implement continuous security monitoring"
        )
        self.stdout.write(
            "  5. Train staff on security best practices"
        )
        
        # Risk-based recommendations
        risk_level = results.get('risk_level', 'UNKNOWN')
        if risk_level == 'HIGH':
            self.stdout.write(
                self.style.ERROR("\\n🚨 HIGH RISK DETECTED:")
            )
            self.stdout.write(
                "  - Immediate remediation required"
            )
            self.stdout.write(
                "  - Consider taking system offline until fixed"
            )
            self.stdout.write(
                "  - Notify security team and management"
            )
        elif risk_level == 'MEDIUM':
            self.stdout.write(
                self.style.WARNING("\\n⚠️  MEDIUM RISK DETECTED:")
            )
            self.stdout.write(
                "  - Address issues within 48 hours"
            )
            self.stdout.write(
                "  - Increase monitoring and logging"
            )
            self.stdout.write(
                "  - Review access controls"
            )
    
    def print_compliance_status(self, results):
        """Print compliance status assessment."""
        self.stdout.write(
            self.style.SUCCESS("\\n📋 COMPLIANCE STATUS:")
        )
        
        # Simulate compliance assessment based on test results
        compliance_items = [
            ('HIPAA Compliance', 'COMPLIANT' if results['failed_modules'] == 0 else 'NON_COMPLIANT'),
            ('Data Protection', 'ADEQUATE' if results.get('risk_level') in ['LOW', 'MEDIUM'] else 'INADEQUATE'),
            ('Access Controls', 'IMPLEMENTED' if results['failed_modules'] == 0 else 'NEEDS_IMPROVEMENT'),
            ('Audit Logging', 'FUNCTIONAL' if results['failed_modules'] == 0 else 'REQUIRES_ATTENTION'),
            ('Encryption', 'ACTIVE' if results['failed_modules'] == 0 else 'COMPROMISED')
        ]
        
        for item, status in compliance_items:
            if status in ['COMPLIANT', 'ADEQUATE', 'IMPLEMENTED', 'FUNCTIONAL', 'ACTIVE']:
                style = self.style.SUCCESS
                icon = "✅"
            else:
                style = self.style.ERROR
                icon = "❌"
            
            self.stdout.write(
                style(f"  {icon} {item}: {status}")
            )
        
        # Overall compliance assessment
        failed_compliance = sum(1 for _, status in compliance_items 
                              if status not in ['COMPLIANT', 'ADEQUATE', 'IMPLEMENTED', 'FUNCTIONAL', 'ACTIVE'])
        
        if failed_compliance == 0:
            self.stdout.write(
                self.style.SUCCESS("\\n🏆 OVERALL COMPLIANCE: SATISFACTORY")
            )
        elif failed_compliance <= 2:
            self.stdout.write(
                self.style.WARNING("\\n⚠️  OVERALL COMPLIANCE: NEEDS IMPROVEMENT")
            )
        else:
            self.stdout.write(
                self.style.ERROR("\\n🚨 OVERALL COMPLIANCE: CRITICAL ISSUES")
            )