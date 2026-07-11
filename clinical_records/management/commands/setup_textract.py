"""
Management command to set up and test AWS Textract integration.
"""

import os
import json
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from clinical_records.services.textract_service import textract_service
from clinical_records.services.enhanced_ocr_service import enhanced_ocr_service
from clinical_records.config.textract_config import get_textract_config, is_textract_enabled


class Command(BaseCommand):
    help = 'Set up and test AWS Textract integration for clinical records OCR'

    def add_arguments(self, parser):
        parser.add_argument(
            '--test',
            action='store_true',
            help='Test Textract connection and functionality',
        )
        parser.add_argument(
            '--configure',
            action='store_true',
            help='Configure Textract settings interactively',
        )
        parser.add_argument(
            '--status',
            action='store_true',
            help='Show current Textract configuration status',
        )
        parser.add_argument(
            '--test-image',
            type=str,
            help='Path to test image file for OCR testing',
        )
        parser.add_argument(
            '--enable',
            action='store_true',
            help='Enable Textract service',
        )
        parser.add_argument(
            '--disable',
            action='store_true',
            help='Disable Textract service',
        )

    def handle(self, *args, **options):
        """Handle the management command."""
        
        if options['status']:
            self.show_status()
        elif options['configure']:
            self.configure_textract()
        elif options['test']:
            self.test_textract(options.get('test_image'))
        elif options['enable']:
            self.enable_textract()
        elif options['disable']:
            self.disable_textract()
        else:
            self.show_help()

    def show_status(self):
        """Show current Textract configuration status."""
        self.stdout.write(self.style.SUCCESS('AWS Textract Configuration Status'))
        self.stdout.write('=' * 50)
        
        config = get_textract_config()
        
        # Basic configuration
        self.stdout.write(f"Textract Enabled: {config['TEXTRACT_ENABLED']}")
        self.stdout.write(f"AWS Region: {config['AWS_REGION']}")
        self.stdout.write(f"AWS Access Key ID: {'***' + config['AWS_ACCESS_KEY_ID'][-4:] if config['AWS_ACCESS_KEY_ID'] else 'Not set'}")
        self.stdout.write(f"AWS Secret Key: {'Set' if config['AWS_SECRET_ACCESS_KEY'] else 'Not set'}")
        
        # Service status
        self.stdout.write(f"\nService Status:")
        self.stdout.write(f"Textract Service Enabled: {textract_service.is_enabled()}")
        self.stdout.write(f"Enhanced OCR Service: Available")
        
        # Processing settings
        self.stdout.write(f"\nProcessing Settings:")
        self.stdout.write(f"Confidence Threshold: {config['TEXTRACT_CONFIDENCE_THRESHOLD']}")
        self.stdout.write(f"Cost Optimization: {config['TEXTRACT_COST_OPTIMIZATION']}")
        self.stdout.write(f"Prescription OCR: {config['TEXTRACT_PRESCRIPTION_ENABLED']}")
        self.stdout.write(f"Lab Report OCR: {config['TEXTRACT_LAB_REPORT_ENABLED']}")
        
        # Cost limits
        self.stdout.write(f"\nCost Management:")
        self.stdout.write(f"Daily Cost Limit: ${config['TEXTRACT_DAILY_COST_LIMIT']}")
        self.stdout.write(f"Monthly Cost Limit: ${config['TEXTRACT_MONTHLY_COST_LIMIT']}")
        
        # Enhanced OCR stats
        stats = enhanced_ocr_service.get_processing_stats()
        self.stdout.write(f"\nEnhanced OCR Stats:")
        for key, value in stats.items():
            self.stdout.write(f"{key}: {value}")

    def configure_textract(self):
        """Configure Textract settings interactively."""
        self.stdout.write(self.style.SUCCESS('Configuring AWS Textract'))
        self.stdout.write('=' * 40)
        
        # Get current settings
        current_enabled = getattr(settings, 'TEXTRACT_ENABLED', False)
        current_region = getattr(settings, 'AWS_REGION', 'us-east-1')
        current_access_key = getattr(settings, 'AWS_ACCESS_KEY_ID', '')
        
        # Interactive configuration
        enabled = input(f"Enable Textract? (y/n) [current: {'y' if current_enabled else 'n'}]: ").lower()
        if enabled in ['y', 'yes']:
            enabled = True
        elif enabled in ['n', 'no']:
            enabled = False
        else:
            enabled = current_enabled
        
        if enabled:
            region = input(f"AWS Region [current: {current_region}]: ").strip()
            if not region:
                region = current_region
            
            access_key = input(f"AWS Access Key ID [current: {'***' + current_access_key[-4:] if current_access_key else 'Not set'}]: ").strip()
            if not access_key:
                access_key = current_access_key
            
            secret_key = input("AWS Secret Access Key [leave blank to keep current]: ").strip()
            if not secret_key:
                secret_key = getattr(settings, 'AWS_SECRET_ACCESS_KEY', '')
            
            confidence_threshold = input("Confidence threshold for Textract fallback (0.0-1.0) [0.7]: ").strip()
            try:
                confidence_threshold = float(confidence_threshold) if confidence_threshold else 0.7
            except ValueError:
                confidence_threshold = 0.7
            
            # Generate settings
            settings_content = f"""
# AWS Textract Configuration
TEXTRACT_ENABLED = {enabled}
AWS_REGION = '{region}'
AWS_ACCESS_KEY_ID = '{access_key}'
AWS_SECRET_ACCESS_KEY = '{secret_key}'
TEXTRACT_CONFIDENCE_THRESHOLD = {confidence_threshold}
TEXTRACT_COST_OPTIMIZATION = True
TEXTRACT_PRESCRIPTION_ENABLED = True
TEXTRACT_LAB_REPORT_ENABLED = True
TEXTRACT_FALLBACK_TO_LOCAL = True
"""
            
            self.stdout.write("\nGenerated configuration:")
            self.stdout.write(settings_content)
            
            save = input("\nAdd this configuration to your settings? (y/n): ").lower()
            if save in ['y', 'yes']:
                self.stdout.write(self.style.SUCCESS("Please add the above configuration to your Django settings.py file"))
                self.stdout.write("Or set the environment variables:")
                self.stdout.write(f"export AWS_ACCESS_KEY_ID='{access_key}'")
                self.stdout.write(f"export AWS_SECRET_ACCESS_KEY='{secret_key}'")
                self.stdout.write(f"export AWS_REGION='{region}'")
        else:
            self.stdout.write("Textract will be disabled")

    def test_textract(self, test_image_path=None):
        """Test Textract functionality."""
        self.stdout.write(self.style.SUCCESS('Testing AWS Textract Integration'))
        self.stdout.write('=' * 45)
        
        # Check configuration
        if not is_textract_enabled():
            self.stdout.write(self.style.ERROR("Textract is not enabled or not properly configured"))
            self.stdout.write("Run with --configure to set up Textract")
            return
        
        # Test connection
        self.stdout.write("Testing Textract connection...")
        try:
            if textract_service.is_enabled():
                self.stdout.write(self.style.SUCCESS("✓ Textract service is available"))
            else:
                self.stdout.write(self.style.ERROR("✗ Textract service is not available"))
                return
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"✗ Connection test failed: {e}"))
            return
        
        # Test with sample image if provided
        if test_image_path:
            self.test_image_processing(test_image_path)
        else:
            self.stdout.write("\nTo test image processing, provide --test-image path/to/image.jpg")
        
        # Test enhanced OCR service
        self.stdout.write("\nTesting Enhanced OCR Service...")
        try:
            stats = enhanced_ocr_service.get_processing_stats()
            self.stdout.write(self.style.SUCCESS("✓ Enhanced OCR service is available"))
            self.stdout.write(f"  Local OCR: {stats['local_ocr_enabled']}")
            self.stdout.write(f"  Textract: {stats['textract_enabled']}")
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"✗ Enhanced OCR test failed: {e}"))

    def test_image_processing(self, image_path):
        """Test image processing with Textract."""
        if not os.path.exists(image_path):
            self.stdout.write(self.style.ERROR(f"Image file not found: {image_path}"))
            return
        
        self.stdout.write(f"\nTesting image processing: {image_path}")
        
        try:
            # Read image file
            with open(image_path, 'rb') as f:
                image_data = f.read()
            
            # Test basic text extraction
            self.stdout.write("Testing basic text extraction...")
            text, confidence, _ = textract_service.extract_text_from_image(image_data)
            self.stdout.write(f"✓ Extracted {len(text)} characters with {confidence:.2f} confidence")
            
            if text:
                self.stdout.write(f"Sample text: {text[:100]}...")
            
            # Test document analysis
            self.stdout.write("\nTesting document analysis...")
            analysis = textract_service.analyze_document(image_data)
            self.stdout.write(f"✓ Found {len(analysis.get('forms', []))} forms and {len(analysis.get('tables', []))} tables")
            
            # Test enhanced OCR
            self.stdout.write("\nTesting enhanced OCR processing...")
            result = enhanced_ocr_service.process_document(image_data, document_type='prescription')
            self.stdout.write(f"✓ Enhanced OCR completed:")
            self.stdout.write(f"  Method: {result.get('processing_method', 'unknown')}")
            self.stdout.write(f"  Confidence: {result.get('confidence', 0):.2f}")
            self.stdout.write(f"  Textract used: {result.get('textract_used', False)}")
            self.stdout.write(f"  Processing time: {result.get('processing_time', 0):.2f}s")
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"✗ Image processing test failed: {e}"))

    def enable_textract(self):
        """Enable Textract service."""
        self.stdout.write("Enabling Textract service...")
        self.stdout.write(self.style.WARNING("Note: You need to set AWS credentials in your settings or environment variables"))
        self.stdout.write("Add to settings.py:")
        self.stdout.write("TEXTRACT_ENABLED = True")

    def disable_textract(self):
        """Disable Textract service."""
        self.stdout.write("Disabling Textract service...")
        self.stdout.write("Add to settings.py:")
        self.stdout.write("TEXTRACT_ENABLED = False")

    def show_help(self):
        """Show help information."""
        self.stdout.write(self.style.SUCCESS('AWS Textract Setup and Testing'))
        self.stdout.write('=' * 40)
        self.stdout.write("Available options:")
        self.stdout.write("  --status          Show current configuration")
        self.stdout.write("  --configure       Interactive configuration")
        self.stdout.write("  --test            Test Textract functionality")
        self.stdout.write("  --test-image PATH Test with specific image")
        self.stdout.write("  --enable          Enable Textract")
        self.stdout.write("  --disable         Disable Textract")
        self.stdout.write("\nExamples:")
        self.stdout.write("  python manage.py setup_textract --status")
        self.stdout.write("  python manage.py setup_textract --configure")
        self.stdout.write("  python manage.py setup_textract --test --test-image sample.jpg")