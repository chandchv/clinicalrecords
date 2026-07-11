"""
Enhanced OCR Processing Service for Clinical Records

This service extends the existing OCR functionality to work with clinical documents,
providing confidence scoring, quality assessment, and fallback mechanisms.
"""
import os
import cv2
import pytesseract
import re
import json
import logging
import time
from typing import Dict, List, Tuple, Optional, Any
from PIL import Image
import numpy as np
from django.conf import settings
from django.utils import timezone

# Import existing OCR utilities from users app
from users.views.ocr_views import (
    preprocess_image_for_medical_ocr,
    apply_medical_corrections,
    extract_medical_entities,
    _get_ocr_text_from_image
)

logger = logging.getLogger(__name__)


class ClinicalOCRProcessor:
    """
    Enhanced OCR processor specifically designed for clinical documents.
    Integrates with ClinicalDocument model and provides advanced processing capabilities.
    """
    
    def __init__(self):
        self.tesseract_path = getattr(settings, 'TESSERACT_PATH', r'C:\Program Files\Tesseract-OCR\tesseract.exe')
        self.cloud_ocr_enabled = getattr(settings, 'CLOUD_OCR_ENABLED', False)
        self.min_confidence_threshold = 0.7
        self.max_retries = 3
        
        # Configure Tesseract
        if os.path.exists(self.tesseract_path):
            pytesseract.pytesseract.tesseract_cmd = self.tesseract_path
        else:
            logger.error(f"Tesseract executable not found at {self.tesseract_path}")
    
    def process_clinical_document(self, clinical_document) -> Dict[str, Any]:
        """
        Main entry point for processing a clinical document.
        
        Args:
            clinical_document: ClinicalDocument instance
            
        Returns:
            Dict containing OCR results, confidence scores, and structured data
        """
        try:
            # Update processing status
            clinical_document.start_processing()
            
            # Determine processing strategy based on document type
            if clinical_document.document_type == 'pdf':
                result = self._process_pdf_document(clinical_document)
            elif clinical_document.document_type == 'image':
                result = self._process_image_document(clinical_document)
            elif clinical_document.document_type == 'dicom':
                result = self._process_dicom_document(clinical_document)
            else:
                result = self._process_generic_document(clinical_document)
            
            # Apply quality assessment and confidence scoring
            result = self._assess_quality_and_confidence(result, clinical_document)
            
            # Check if manual review is needed
            requires_review = result['overall_confidence'] < self.min_confidence_threshold
            
            # Update document with results
            clinical_document.complete_processing(
                ocr_text=result.get('raw_text', ''),
                structured_data=result.get('structured_data', {}),
                confidence=result.get('overall_confidence', 0.0)
            )
            
            if requires_review:
                clinical_document.requires_manual_review = True
                clinical_document.save(update_fields=['requires_manual_review'])
            
            # Log processing completion
            self._log_processing_result(clinical_document, result)
            
            return result
            
        except Exception as e:
            logger.error(f"OCR processing failed for document {clinical_document.id}: {e}")
            clinical_document.fail_processing(str(e))
            raise OCRProcessingError(f"OCR processing failed: {e}")
    
    def _process_pdf_document(self, clinical_document) -> Dict[str, Any]:
        """Process PDF documents by converting to images first."""
        try:
            # Convert PDF to images (using pdf2image or similar)
            # For now, we'll use a placeholder implementation
            logger.info(f"Processing PDF document: {clinical_document.original_filename}")
            
            # TODO: Implement PDF to image conversion
            # This would typically involve:
            # 1. Convert PDF pages to images using pdf2image
            # 2. Process each page with OCR
            # 3. Combine results from all pages
            
            return {
                'raw_text': 'PDF processing not yet implemented',
                'structured_data': {},
                'overall_confidence': 0.0,
                'processing_method': 'pdf_placeholder'
            }
            
        except Exception as e:
            logger.error(f"PDF processing failed: {e}")
            raise
    
    def _process_image_document(self, clinical_document) -> Dict[str, Any]:
        """Process image documents using enhanced OCR."""
        try:
            logger.info(f"Processing image document: {clinical_document.original_filename}")
            
            # Load image from file
            image = Image.open(clinical_document.file.path).convert('RGB')
            image_np = np.array(image)
            
            # Apply multiple OCR strategies with retry logic
            ocr_result = self._extract_text_with_retry(image_np)
            
            if not ocr_result['text']:
                # Try cloud OCR as fallback if enabled
                if self.cloud_ocr_enabled:
                    ocr_result = self._try_cloud_ocr(clinical_document.file.path)
                else:
                    logger.warning("No text extracted and cloud OCR not enabled")
            
            # Extract structured data based on record type
            structured_data = self._extract_structured_data(
                ocr_result['text'], 
                clinical_document.clinical_record.record_type
            )
            
            return {
                'raw_text': ocr_result['text'],
                'structured_data': structured_data,
                'ocr_confidence': ocr_result['confidence'],
                'processing_method': ocr_result['method'],
                'preprocessing_applied': ocr_result.get('preprocessing', [])
            }
            
        except Exception as e:
            logger.error(f"Image processing failed: {e}")
            raise
    
    def _process_dicom_document(self, clinical_document) -> Dict[str, Any]:
        """Process DICOM documents (medical images) with comprehensive metadata extraction."""
        try:
            logger.info(f"Processing DICOM document: {clinical_document.original_filename}")
            
            # Import DICOM processor
            from ..utils.dicom_utils import DICOMProcessor
            dicom_processor = DICOMProcessor()
            
            # Read DICOM file
            dataset = dicom_processor.read_dicom_file(clinical_document.file.path)
            if not dataset:
                return {
                    'raw_text': 'Failed to read DICOM file',
                    'structured_data': {},
                    'overall_confidence': 0.0,
                    'processing_method': 'dicom_read_failed',
                    'error': 'Could not read DICOM dataset'
                }
            
            # Extract comprehensive metadata
            metadata = dicom_processor.extract_metadata(dataset)
            
            # Extract text content from DICOM fields
            text_data = dicom_processor.extract_text_from_dicom(dataset)
            
            # Generate preview and thumbnail images
            preview_bytes = dicom_processor.generate_preview_image(dataset)
            thumbnail_bytes = dicom_processor.generate_thumbnail(dataset)
            
            # Get DICOM summary for structured data
            dicom_summary = dicom_processor.get_dicom_summary(dataset)
            
            # Validate DICOM file
            validation_result = dicom_processor.validate_dicom_file(clinical_document.file.path)
            
            # Create structured data combining all DICOM information
            structured_data = {
                'report_type': 'dicom_imaging',
                'dicom_metadata': metadata,
                'dicom_summary': dicom_summary,
                'validation_result': validation_result,
                'text_content': text_data,
                'image_info': {
                    'has_pixel_data': hasattr(dataset, 'pixel_array'),
                    'can_generate_preview': preview_bytes is not None,
                    'can_generate_thumbnail': thumbnail_bytes is not None,
                    'modality': metadata.get('modality', 'Unknown'),
                    'body_part': metadata.get('body_part_examined', 'Unknown'),
                    'study_description': metadata.get('study_description', 'Unknown')
                },
                'processing_info': {
                    'anonymization_available': True,
                    'metadata_extracted': len(metadata) > 0,
                    'text_sources': text_data.get('text_sources', []),
                    'file_size_mb': round(clinical_document.file_size / (1024 * 1024), 2) if clinical_document.file_size else 0
                }
            }
            
            # Store preview and thumbnail data if generated
            if preview_bytes:
                # Save preview image (in a real implementation, you'd save to file storage)
                structured_data['preview_available'] = True
                structured_data['preview_size_bytes'] = len(preview_bytes)
            
            if thumbnail_bytes:
                # Save thumbnail image (in a real implementation, you'd save to file storage)
                structured_data['thumbnail_available'] = True
                structured_data['thumbnail_size_bytes'] = len(thumbnail_bytes)
            
            # Calculate confidence based on successful processing steps
            confidence_factors = []
            
            # Metadata extraction confidence
            if metadata and len(metadata) > 10:
                confidence_factors.append(0.9)
            elif metadata and len(metadata) > 5:
                confidence_factors.append(0.7)
            else:
                confidence_factors.append(0.3)
            
            # Validation confidence
            if validation_result.get('is_valid', False):
                confidence_factors.append(0.9)
            elif validation_result.get('is_dicom', False):
                confidence_factors.append(0.6)
            else:
                confidence_factors.append(0.1)
            
            # Image processing confidence
            if preview_bytes and thumbnail_bytes:
                confidence_factors.append(0.8)
            elif preview_bytes or thumbnail_bytes:
                confidence_factors.append(0.6)
            else:
                confidence_factors.append(0.4)
            
            # Text extraction confidence
            confidence_factors.append(text_data.get('confidence', 0.5))
            
            overall_confidence = sum(confidence_factors) / len(confidence_factors)
            
            return {
                'raw_text': text_data.get('extracted_text', ''),
                'structured_data': structured_data,
                'overall_confidence': overall_confidence,
                'processing_method': 'dicom_comprehensive',
                'dicom_metadata': metadata,
                'preview_generated': preview_bytes is not None,
                'thumbnail_generated': thumbnail_bytes is not None,
                'validation_passed': validation_result.get('is_valid', False)
            }
            
        except Exception as e:
            logger.error(f"DICOM processing failed: {e}")
            return {
                'raw_text': f'DICOM processing error: {str(e)}',
                'structured_data': {'error': str(e), 'report_type': 'dicom_error'},
                'overall_confidence': 0.0,
                'processing_method': 'dicom_error'
            }
    
    def _process_generic_document(self, clinical_document) -> Dict[str, Any]:
        """Process other document types."""
        try:
            logger.info(f"Processing generic document: {clinical_document.original_filename}")
            
            # For text files, read directly
            if clinical_document.content_type.startswith('text/'):
                with open(clinical_document.file.path, 'r', encoding='utf-8') as f:
                    text = f.read()
                
                structured_data = self._extract_structured_data(
                    text, 
                    clinical_document.clinical_record.record_type
                )
                
                return {
                    'raw_text': text,
                    'structured_data': structured_data,
                    'overall_confidence': 0.9,  # High confidence for text files
                    'processing_method': 'direct_text_read'
                }
            
            # For other types, return placeholder
            return {
                'raw_text': f'Processing not implemented for {clinical_document.content_type}',
                'structured_data': {},
                'overall_confidence': 0.0,
                'processing_method': 'unsupported_type'
            }
            
        except Exception as e:
            logger.error(f"Generic document processing failed: {e}")
            raise
    
    def _extract_text_with_retry(self, image_np: np.ndarray) -> Dict[str, Any]:
        """Extract text from image with retry logic and multiple strategies."""
        strategies = [
            {'name': 'standard', 'preprocess': True, 'config': '--oem 3 --psm 6'},
            {'name': 'sparse_text', 'preprocess': True, 'config': '--oem 3 --psm 11'},
            {'name': 'single_block', 'preprocess': True, 'config': '--oem 3 --psm 4'},
            {'name': 'high_dpi', 'preprocess': True, 'config': '--oem 3 --psm 6 --dpi 300'},
        ]
        
        best_result = {'text': '', 'confidence': 0.0, 'method': 'none'}
        
        for strategy in strategies:
            try:
                if strategy['preprocess']:
                    processed_images = preprocess_image_for_medical_ocr(image_np)
                else:
                    processed_images = [image_np]
                
                for i, img in enumerate(processed_images):
                    try:
                        # Extract text with confidence data
                        data = pytesseract.image_to_data(img, config=strategy['config'], output_type=pytesseract.Output.DICT)
                        
                        # Calculate confidence
                        confidences = [int(conf) for conf in data['conf'] if int(conf) > 0]
                        avg_confidence = sum(confidences) / len(confidences) if confidences else 0
                        
                        # Extract text
                        text = pytesseract.image_to_string(img, config=strategy['config'])
                        
                        if text and len(text.strip()) > best_result['text'].count(' '):
                            best_result = {
                                'text': text.strip(),
                                'confidence': avg_confidence / 100.0,  # Convert to 0-1 scale
                                'method': f"{strategy['name']}_preprocessing_{i}",
                                'preprocessing': strategy['name']
                            }
                            
                    except Exception as e:
                        logger.warning(f"OCR strategy {strategy['name']} failed: {e}")
                        continue
                        
            except Exception as e:
                logger.warning(f"OCR strategy {strategy['name']} failed completely: {e}")
                continue
        
        return best_result
    
    def _try_cloud_ocr(self, file_path: str) -> Dict[str, Any]:
        """
        Fallback to cloud OCR services for better accuracy.
        This is a placeholder for cloud OCR integration.
        """
        logger.info("Attempting cloud OCR fallback")
        
        # TODO: Implement cloud OCR integration
        # This could integrate with:
        # - Google Cloud Vision API
        # - AWS Textract
        # - Azure Computer Vision
        # - Other cloud OCR services
        
        return {
            'text': 'Cloud OCR not yet implemented',
            'confidence': 0.0,
            'method': 'cloud_ocr_placeholder'
        }
    
    def _extract_structured_data(self, text: str, record_type: str) -> Dict[str, Any]:
        """
        Extract structured data based on the clinical record type.
        
        Args:
            text: Raw OCR text
            record_type: Type of clinical record (lab_report, prescription, etc.)
            
        Returns:
            Dictionary containing structured data specific to the record type
        """
        if not text or not text.strip():
            return {}
        
        try:
            if record_type == 'lab_report':
                return self._extract_lab_report_data(text)
            elif record_type == 'prescription':
                return self._extract_prescription_data(text)
            elif record_type == 'imaging':
                return self._extract_imaging_report_data(text)
            elif record_type == 'discharge_summary':
                return self._extract_discharge_summary_data(text)
            elif record_type == 'consultation':
                return self._extract_consultation_data(text)
            else:
                return self._extract_generic_medical_data(text)
                
        except Exception as e:
            logger.error(f"Structured data extraction failed for {record_type}: {e}")
            return {'extraction_error': str(e)}
    
    def _extract_lab_report_data(self, text: str) -> Dict[str, Any]:
        """Extract structured data from lab reports with enhanced pattern matching."""
        # Use existing lab report extraction logic
        corrected_text = apply_medical_corrections(text)
        
        # Extract lab values with reference ranges
        lab_data = {
            'tests': [],
            'patient_info': {},
            'lab_info': {},
            'test_date': None,
            'abnormal_values': [],
            'report_type': 'lab_report'
        }
        
        # Enhanced Indian lab format patterns with more variations
        test_patterns = [
            # Standard format: Test Name: Value Unit (Min-Max)
            r'(\w+(?:\s+\w+)*)\s*:?\s*([0-9.]+)\s*([a-zA-Z/µ%]+)?\s*\(([0-9.-]+)\s*-\s*([0-9.-]+)\)',
            # Tabular format: Test Name  Value  Unit  Range
            r'(\w+(?:\s+\w+)*)\s+([0-9.]+)\s+([a-zA-Z/µ%]+)\s+([0-9.-]+)\s*-\s*([0-9.-]+)',
            # Simple format: Test Name: Value Unit
            r'(\w+(?:\s+\w+)*)\s*:?\s*([0-9.]+)\s*([a-zA-Z/µ%]+)?',
            # With decimal values and scientific notation
            r'(\w+(?:\s+\w+)*)\s*:?\s*([0-9.]+(?:e[+-]?[0-9]+)?)\s*([a-zA-Z/µ%]+)?\s*\(([0-9.-]+(?:e[+-]?[0-9]+)?)\s*-\s*([0-9.-]+(?:e[+-]?[0-9]+)?)\)',
            # Common Indian lab patterns
            r'(\w+(?:\s+\w+)*)\s*[-:]\s*([0-9.]+)\s*([a-zA-Z/µ%]+)?\s*\[([0-9.-]+)\s*-\s*([0-9.-]+)\]',
            # With "Normal" or "Abnormal" indicators
            r'(\w+(?:\s+\w+)*)\s*:?\s*([0-9.]+)\s*([a-zA-Z/µ%]+)?\s*\(([0-9.-]+)\s*-\s*([0-9.-]+)\)\s*(Normal|Abnormal|High|Low)?'
        ]
        
        # Extract patient information
        patient_patterns = [
            r'(?i)patient\s*name\s*:?\s*([A-Za-z\s]+)',
            r'(?i)name\s*:?\s*([A-Za-z\s]+)',
            r'(?i)age\s*:?\s*(\d+)',
            r'(?i)sex\s*:?\s*(male|female|m|f)',
            r'(?i)gender\s*:?\s*(male|female|m|f)',
            r'(?i)ref\w*\s*by\s*:?\s*([A-Za-z\s.]+)',
            r'(?i)doctor\s*:?\s*([A-Za-z\s.]+)'
        ]
        
        # Extract lab information
        lab_patterns = [
            r'(?i)lab\s*name\s*:?\s*([A-Za-z\s]+)',
            r'(?i)laboratory\s*:?\s*([A-Za-z\s]+)',
            r'(?i)report\s*date\s*:?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
            r'(?i)collection\s*date\s*:?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
            r'(?i)sample\s*type\s*:?\s*([A-Za-z\s]+)'
        ]
        
        lines = corrected_text.split('\n')
        processed_tests = set()  # To avoid duplicates
        
        # Extract patient and lab information
        for line in lines:
            # Patient info
            for pattern in patient_patterns:
                match = re.search(pattern, line)
                if match:
                    if 'patient' in pattern.lower() or 'name' in pattern.lower():
                        lab_data['patient_info']['name'] = match.group(1).strip()
                    elif 'age' in pattern.lower():
                        lab_data['patient_info']['age'] = match.group(1).strip()
                    elif 'sex' in pattern.lower() or 'gender' in pattern.lower():
                        lab_data['patient_info']['gender'] = match.group(1).strip()
                    elif 'ref' in pattern.lower() or 'doctor' in pattern.lower():
                        lab_data['patient_info']['referring_doctor'] = match.group(1).strip()
            
            # Lab info
            for pattern in lab_patterns:
                match = re.search(pattern, line)
                if match:
                    if 'lab' in pattern.lower() or 'laboratory' in pattern.lower():
                        lab_data['lab_info']['name'] = match.group(1).strip()
                    elif 'report' in pattern.lower() or 'collection' in pattern.lower():
                        lab_data['test_date'] = match.group(1).strip()
                    elif 'sample' in pattern.lower():
                        lab_data['lab_info']['sample_type'] = match.group(1).strip()
        
        # Extract test results
        for line in lines:
            line = line.strip()
            if not line or len(line) < 5:  # Skip very short lines
                continue
                
            for pattern in test_patterns:
                matches = re.findall(pattern, line, re.IGNORECASE)
                for match in matches:
                    if len(match) >= 2:
                        test_name = match[0].strip()
                        
                        # Skip if already processed or if it's not a valid test name
                        if (test_name.lower() in processed_tests or 
                            len(test_name) < 2 or 
                            test_name.lower() in ['name', 'age', 'sex', 'date', 'lab', 'report']):
                            continue
                        
                        try:
                            value = float(match[1]) if match[1] else 0
                        except ValueError:
                            continue  # Skip if value is not numeric
                        
                        unit = match[2].strip() if len(match) > 2 and match[2] else ''
                        
                        test_data = {
                            'name': test_name,
                            'value': value,
                            'unit': unit,
                            'status': 'normal'  # Default status
                        }
                        
                        # Add reference range if available
                        if len(match) >= 5 and match[3] and match[4]:
                            try:
                                ref_min = float(match[3])
                                ref_max = float(match[4])
                                test_data['reference_range'] = {
                                    'min': ref_min,
                                    'max': ref_max,
                                    'text': f"{ref_min}-{ref_max}"
                                }
                                
                                # Check if abnormal
                                if value < ref_min:
                                    test_data['status'] = 'low'
                                    test_data['is_abnormal'] = True
                                    lab_data['abnormal_values'].append({
                                        'name': test_name,
                                        'value': value,
                                        'status': 'low',
                                        'reference': f"{ref_min}-{ref_max}"
                                    })
                                elif value > ref_max:
                                    test_data['status'] = 'high'
                                    test_data['is_abnormal'] = True
                                    lab_data['abnormal_values'].append({
                                        'name': test_name,
                                        'value': value,
                                        'status': 'high',
                                        'reference': f"{ref_min}-{ref_max}"
                                    })
                                else:
                                    test_data['is_abnormal'] = False
                                    
                            except ValueError:
                                # If reference range parsing fails, just store as text
                                test_data['reference_range'] = {
                                    'text': f"{match[3]}-{match[4]}"
                                }
                        
                        # Check for explicit status indicators
                        if len(match) >= 6 and match[5]:
                            status_indicator = match[5].lower()
                            if status_indicator in ['abnormal', 'high', 'low']:
                                test_data['status'] = status_indicator
                                test_data['is_abnormal'] = True
                                if test_name not in [item['name'] for item in lab_data['abnormal_values']]:
                                    lab_data['abnormal_values'].append({
                                        'name': test_name,
                                        'value': value,
                                        'status': status_indicator,
                                        'reference': test_data.get('reference_range', {}).get('text', '')
                                    })
                        
                        lab_data['tests'].append(test_data)
                        processed_tests.add(test_name.lower())
        
        # Add summary statistics
        lab_data['summary'] = {
            'total_tests': len(lab_data['tests']),
            'abnormal_count': len(lab_data['abnormal_values']),
            'normal_count': len(lab_data['tests']) - len(lab_data['abnormal_values']),
            'has_critical_values': any(item['status'] in ['high', 'low'] for item in lab_data['abnormal_values'])
        }
        
        return lab_data
    
    def _extract_prescription_data(self, text: str) -> Dict[str, Any]:
        """Extract structured data from prescriptions with enhanced integration."""
        # Use existing prescription extraction logic
        entities = extract_medical_entities(text)
        corrected_text = apply_medical_corrections(text)
        
        # Enhanced prescription data structure
        prescription_data = {
            'report_type': 'prescription',
            'diagnosis': {},
            'medications': [],
            'lab_tests': [],
            'advice': {},
            'patient_info': {},
            'doctor_info': {},
            'prescription_date': None,
            'template_used': entities.get('template_used', False),
            'summary': {}
        }
        
        # Process diagnosis information
        if entities.get('diagnosis'):
            if isinstance(entities['diagnosis'], dict):
                prescription_data['diagnosis'] = entities['diagnosis']
            else:
                prescription_data['diagnosis'] = {
                    'text': str(entities['diagnosis']),
                    'confidence': 0.8,
                    'standardized': str(entities['diagnosis'])
                }
        
        # Process medications with enhanced structure
        medications = entities.get('medicines', [])
        for med in medications:
            if isinstance(med, dict):
                # Enhance medication data structure
                enhanced_med = {
                    'name': med.get('name', ''),
                    'original_name': med.get('original_name', med.get('name', '')),
                    'dosage': med.get('dosage', ''),
                    'strength': med.get('dosage', ''),  # Alias for compatibility
                    'frequency': med.get('frequency', ''),
                    'duration': med.get('duration', ''),
                    'instructions': med.get('instructions', ''),
                    'category': med.get('category', ''),
                    'confidence': med.get('confidence', 0.7),
                    'route': self._extract_medication_route(med.get('instructions', '')),
                    'timing': self._extract_medication_timing(med.get('instructions', ''))
                }
                prescription_data['medications'].append(enhanced_med)
            else:
                # Handle string format
                prescription_data['medications'].append({
                    'name': str(med),
                    'confidence': 0.5
                })
        
        # Process lab tests
        lab_tests = entities.get('lab_tests', [])
        for test in lab_tests:
            if isinstance(test, dict):
                prescription_data['lab_tests'].append(test)
            else:
                prescription_data['lab_tests'].append({
                    'name': str(test),
                    'confidence': 0.8
                })
        
        # Process advice
        advice = entities.get('advice', '')
        if isinstance(advice, dict):
            prescription_data['advice'] = advice
        else:
            prescription_data['advice'] = {
                'text': str(advice),
                'confidence': 0.8 if advice else 0.0
            }
        
        # Extract additional patient and doctor information
        lines = corrected_text.split('\n')
        
        # Patient information patterns
        patient_patterns = [
            r'(?i)patient\s*name\s*:?\s*([A-Za-z\s]+)',
            r'(?i)name\s*:?\s*([A-Za-z\s]+)',
            r'(?i)age\s*:?\s*(\d+)',
            r'(?i)sex\s*:?\s*(male|female|m|f)',
            r'(?i)gender\s*:?\s*(male|female|m|f)',
            r'(?i)mobile\s*:?\s*(\d{10})',
            r'(?i)phone\s*:?\s*(\d{10})'
        ]
        
        # Doctor information patterns
        doctor_patterns = [
            r'(?i)dr\.?\s*([A-Za-z\s.]+)',
            r'(?i)doctor\s*:?\s*([A-Za-z\s.]+)',
            r'(?i)consultant\s*:?\s*([A-Za-z\s.]+)',
            r'(?i)reg\w*\s*no\w*\s*:?\s*([A-Z0-9]+)',
            r'(?i)qualification\s*:?\s*([A-Za-z\s.,]+)'
        ]
        
        # Date patterns
        date_patterns = [
            r'(?i)date\s*:?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
            r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})'
        ]
        
        # Extract information from text
        for line in lines:
            # Patient info
            for pattern in patient_patterns:
                match = re.search(pattern, line)
                if match:
                    if 'name' in pattern.lower():
                        prescription_data['patient_info']['name'] = match.group(1).strip()
                    elif 'age' in pattern.lower():
                        prescription_data['patient_info']['age'] = match.group(1).strip()
                    elif 'sex' in pattern.lower() or 'gender' in pattern.lower():
                        prescription_data['patient_info']['gender'] = match.group(1).strip()
                    elif 'mobile' in pattern.lower() or 'phone' in pattern.lower():
                        prescription_data['patient_info']['phone'] = match.group(1).strip()
            
            # Doctor info
            for pattern in doctor_patterns:
                match = re.search(pattern, line)
                if match:
                    if 'dr' in pattern.lower() or 'doctor' in pattern.lower() or 'consultant' in pattern.lower():
                        prescription_data['doctor_info']['name'] = match.group(1).strip()
                    elif 'reg' in pattern.lower():
                        prescription_data['doctor_info']['registration_number'] = match.group(1).strip()
                    elif 'qualification' in pattern.lower():
                        prescription_data['doctor_info']['qualification'] = match.group(1).strip()
            
            # Date info
            for pattern in date_patterns:
                match = re.search(pattern, line)
                if match and not prescription_data['prescription_date']:
                    prescription_data['prescription_date'] = match.group(1).strip()
        
        # Add summary statistics
        prescription_data['summary'] = {
            'total_medications': len(prescription_data['medications']),
            'has_diagnosis': bool(prescription_data['diagnosis'].get('text')),
            'has_lab_tests': len(prescription_data['lab_tests']) > 0,
            'has_advice': bool(prescription_data['advice'].get('text')),
            'overall_confidence': self._calculate_prescription_confidence(prescription_data)
        }
        
        return prescription_data
    
    def _extract_medication_route(self, instructions: str) -> str:
        """Extract medication route from instructions."""
        if not instructions:
            return ''
        
        route_patterns = [
            r'(?i)\b(oral|po|by mouth)\b',
            r'(?i)\b(topical|apply)\b',
            r'(?i)\b(injection|iv|im|sc)\b',
            r'(?i)\b(inhaler|inhalation)\b',
            r'(?i)\b(drops|instill)\b'
        ]
        
        for pattern in route_patterns:
            match = re.search(pattern, instructions)
            if match:
                return match.group(1).lower()
        
        return 'oral'  # Default assumption
    
    def _extract_medication_timing(self, instructions: str) -> str:
        """Extract medication timing from instructions."""
        if not instructions:
            return ''
        
        timing_patterns = [
            r'(?i)\b(before meals|before food|ac)\b',
            r'(?i)\b(after meals|after food|pc)\b',
            r'(?i)\b(with meals|with food)\b',
            r'(?i)\b(at bedtime|hs|night)\b',
            r'(?i)\b(morning|am)\b',
            r'(?i)\b(evening|pm)\b'
        ]
        
        for pattern in timing_patterns:
            match = re.search(pattern, instructions)
            if match:
                return match.group(1).lower()
        
        return ''
    
    def _calculate_prescription_confidence(self, prescription_data: Dict[str, Any]) -> float:
        """Calculate overall confidence for prescription data."""
        confidence_factors = []
        
        # Diagnosis confidence
        if prescription_data['diagnosis'].get('confidence'):
            confidence_factors.append(prescription_data['diagnosis']['confidence'])
        
        # Medications confidence
        if prescription_data['medications']:
            med_confidences = [med.get('confidence', 0.5) for med in prescription_data['medications']]
            avg_med_confidence = sum(med_confidences) / len(med_confidences)
            confidence_factors.append(avg_med_confidence)
        
        # Advice confidence
        if prescription_data['advice'].get('confidence'):
            confidence_factors.append(prescription_data['advice']['confidence'])
        
        # Overall confidence
        if confidence_factors:
            return sum(confidence_factors) / len(confidence_factors)
        else:
            return 0.5
    
    def _extract_imaging_report_data(self, text: str) -> Dict[str, Any]:
        """Extract structured data from imaging reports."""
        imaging_data = {
            'study_type': '',
            'findings': '',
            'impression': '',
            'recommendations': '',
            'technique': ''
        }
        
        lines = text.split('\n')
        current_section = None
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # Identify sections
            if re.match(r'(?i)(study|examination|scan)\s*type', line):
                current_section = 'study_type'
            elif re.match(r'(?i)technique', line):
                current_section = 'technique'
            elif re.match(r'(?i)findings?', line):
                current_section = 'findings'
            elif re.match(r'(?i)(impression|conclusion)', line):
                current_section = 'impression'
            elif re.match(r'(?i)(recommendation|advice)', line):
                current_section = 'recommendations'
            elif current_section and ':' in line:
                # Extract content after colon
                content = line.split(':', 1)[1].strip()
                if content:
                    imaging_data[current_section] = content
            elif current_section:
                # Continue adding to current section
                if imaging_data[current_section]:
                    imaging_data[current_section] += ' ' + line
                else:
                    imaging_data[current_section] = line
        
        return imaging_data
    
    def _extract_discharge_summary_data(self, text: str) -> Dict[str, Any]:
        """Extract structured data from discharge summaries."""
        discharge_data = {
            'admission_date': None,
            'discharge_date': None,
            'primary_diagnosis': '',
            'secondary_diagnoses': [],
            'procedures': [],
            'medications_on_discharge': [],
            'follow_up_instructions': '',
            'discharge_condition': ''
        }
        
        # Extract dates
        date_patterns = [
            r'admission\s*date\s*:?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
            r'discharge\s*date\s*:?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})'
        ]
        
        for pattern in date_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                if 'admission' in pattern:
                    discharge_data['admission_date'] = matches[0]
                else:
                    discharge_data['discharge_date'] = matches[0]
        
        # Extract diagnoses
        diagnosis_patterns = [
            r'(?i)primary\s*diagnosis\s*:?\s*(.*?)(?=secondary|procedure|medication|follow|$)',
            r'(?i)final\s*diagnosis\s*:?\s*(.*?)(?=secondary|procedure|medication|follow|$)'
        ]
        
        for pattern in diagnosis_patterns:
            match = re.search(pattern, text, re.DOTALL)
            if match:
                discharge_data['primary_diagnosis'] = match.group(1).strip()
                break
        
        return discharge_data
    
    def _extract_consultation_data(self, text: str) -> Dict[str, Any]:
        """Extract structured data from consultation notes."""
        consultation_data = {
            'chief_complaint': '',
            'history_of_present_illness': '',
            'past_medical_history': '',
            'physical_examination': '',
            'assessment': '',
            'plan': '',
            'vital_signs': {}
        }
        
        # Extract vital signs
        vital_patterns = {
            'blood_pressure': r'(?i)b\.?p\.?\s*:?\s*(\d+/\d+)',
            'pulse': r'(?i)pulse\s*:?\s*(\d+)',
            'temperature': r'(?i)temp\w*\s*:?\s*(\d+\.?\d*)',
            'respiratory_rate': r'(?i)r\.?r\.?\s*:?\s*(\d+)',
            'oxygen_saturation': r'(?i)spo2\s*:?\s*(\d+)'
        }
        
        for vital, pattern in vital_patterns.items():
            match = re.search(pattern, text)
            if match:
                consultation_data['vital_signs'][vital] = match.group(1)
        
        return consultation_data
    
    def _extract_generic_medical_data(self, text: str) -> Dict[str, Any]:
        """Extract generic medical information from any clinical document."""
        generic_data = {
            'patient_identifiers': [],
            'dates_mentioned': [],
            'medical_terms': [],
            'medications_mentioned': [],
            'procedures_mentioned': []
        }
        
        # Extract dates
        date_pattern = r'\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b'
        generic_data['dates_mentioned'] = re.findall(date_pattern, text)
        
        # Extract potential patient identifiers (MRN, etc.)
        id_patterns = [
            r'(?i)mrn\s*:?\s*([A-Z0-9]+)',
            r'(?i)patient\s*id\s*:?\s*([A-Z0-9]+)',
            r'(?i)reg\w*\s*no\w*\s*:?\s*([A-Z0-9]+)'
        ]
        
        for pattern in id_patterns:
            matches = re.findall(pattern, text)
            generic_data['patient_identifiers'].extend(matches)
        
        return generic_data
    
    def _assess_quality_and_confidence(self, result: Dict[str, Any], clinical_document) -> Dict[str, Any]:
        """
        Assess the quality of OCR results and calculate overall confidence.
        
        Args:
            result: OCR processing result
            clinical_document: ClinicalDocument instance
            
        Returns:
            Updated result with quality assessment and confidence scores
        """
        quality_metrics = {
            'text_length': len(result.get('raw_text', '')),
            'word_count': len(result.get('raw_text', '').split()),
            'has_structured_data': bool(result.get('structured_data')),
            'ocr_confidence': result.get('ocr_confidence', 0.0),
            'processing_method': result.get('processing_method', 'unknown')
        }
        
        # Calculate quality score based on multiple factors
        quality_score = 0.0
        
        # Text length factor (longer text usually indicates better OCR)
        if quality_metrics['text_length'] > 100:
            quality_score += 0.3
        elif quality_metrics['text_length'] > 50:
            quality_score += 0.2
        elif quality_metrics['text_length'] > 20:
            quality_score += 0.1
        
        # Word count factor
        if quality_metrics['word_count'] > 20:
            quality_score += 0.2
        elif quality_metrics['word_count'] > 10:
            quality_score += 0.1
        
        # Structured data factor
        if quality_metrics['has_structured_data']:
            structured_data = result.get('structured_data', {})
            if isinstance(structured_data, dict) and len(structured_data) > 0:
                quality_score += 0.3
        
        # OCR confidence factor
        quality_score += quality_metrics['ocr_confidence'] * 0.2
        
        # Ensure score is between 0 and 1
        quality_score = min(1.0, max(0.0, quality_score))
        
        # Add quality assessment to result
        result['quality_assessment'] = {
            'metrics': quality_metrics,
            'quality_score': quality_score,
            'overall_confidence': quality_score,
            'requires_manual_review': quality_score < self.min_confidence_threshold
        }
        
        result['overall_confidence'] = quality_score
        
        return result
    
    def _log_processing_result(self, clinical_document, result: Dict[str, Any]):
        """Log the processing result for audit and debugging purposes."""
        log_data = {
            'document_id': str(clinical_document.id),
            'document_type': clinical_document.document_type,
            'record_type': clinical_document.clinical_record.record_type,
            'processing_method': result.get('processing_method', 'unknown'),
            'overall_confidence': result.get('overall_confidence', 0.0),
            'text_length': len(result.get('raw_text', '')),
            'has_structured_data': bool(result.get('structured_data')),
            'requires_manual_review': result.get('quality_assessment', {}).get('requires_manual_review', False)
        }
        
        logger.info(f"OCR processing completed: {json.dumps(log_data)}")


class OCRProcessingError(Exception):
    """Custom exception for OCR processing errors."""
    pass


# Convenience function for easy import
def process_clinical_document_ocr(clinical_document):
    """
    Convenience function to process a clinical document with OCR.
    
    Args:
        clinical_document: ClinicalDocument instance
        
    Returns:
        Dict containing OCR results and structured data
    """
    processor = ClinicalOCRProcessor()
    return processor.process_clinical_document(clinical_document)