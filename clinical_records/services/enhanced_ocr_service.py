"""
Enhanced OCR service that combines local Tesseract with AWS Textract for optimal results.
Provides intelligent fallback and cost optimization.
"""

import os
import logging
import cv2
import numpy as np
from PIL import Image
from typing import Dict, List, Optional, Tuple, Any
from django.conf import settings

from .textract_service import textract_service
from users.views.ocr_views import (
    preprocess_image_for_medical_ocr,
    apply_medical_corrections,
    extract_medical_entities,
    _get_ocr_text_from_image,
    _calculate_confidence
)

logger = logging.getLogger(__name__)


class EnhancedOCRService:
    """
    Enhanced OCR service that intelligently combines local Tesseract with AWS Textract.
    Provides cost optimization and improved accuracy for clinical documents.
    """
    
    def __init__(self):
        """Initialize the enhanced OCR service."""
        self.local_ocr_enabled = True
        self.textract_enabled = textract_service.is_enabled()
        
        # Configuration
        self.confidence_threshold = getattr(settings, 'TEXTRACT_CONFIDENCE_THRESHOLD', 0.7)
        self.cost_optimization = getattr(settings, 'TEXTRACT_COST_OPTIMIZATION', True)
        self.prescription_textract_enabled = getattr(settings, 'TEXTRACT_PRESCRIPTION_ENABLED', True)
        
        logger.info(f"Enhanced OCR initialized - Local: {self.local_ocr_enabled}, Textract: {self.textract_enabled}")
    
    def process_document(self, image_data: bytes, document_type: str = None, 
                        force_textract: bool = False) -> Dict[str, Any]:
        """
        Process document with intelligent OCR selection.
        
        Args:
            image_data: Image data as bytes
            document_type: Type of document (prescription, lab_report, etc.)
            force_textract: Force use of Textract regardless of other factors
            
        Returns:
            Dict containing OCR results with metadata
        """
        result = {
            'text': '',
            'confidence': 0.0,
            'structured_data': {},
            'processing_method': 'none',
            'textract_used': False,
            'local_ocr_used': False,
            'cost_estimate': 0.0,
            'processing_time': 0.0
        }
        
        import time
        start_time = time.time()
        
        try:
            # Convert bytes to image for local processing
            image = Image.open(io.BytesIO(image_data))
            image_np = np.array(image.convert('RGB'))
            
            # Step 1: Try local OCR first (unless forced to use Textract)
            local_result = None
            if not force_textract and self.local_ocr_enabled:
                local_result = self._process_with_local_ocr(image_np, document_type)
                result.update(local_result)
                result['local_ocr_used'] = True
                result['processing_method'] = 'local'
            
            # Step 2: Determine if Textract should be used
            use_textract = (
                force_textract or
                (self.textract_enabled and self._should_use_textract(
                    local_result.get('confidence', 0.0) if local_result else 0.0,
                    document_type
                ))
            )
            
            # Step 3: Process with Textract if needed
            if use_textract:
                textract_result = self._process_with_textract(image_data, document_type)
                
                # Choose best result or combine results
                if local_result:
                    result = self._combine_results(local_result, textract_result)
                else:
                    result.update(textract_result)
                
                result['textract_used'] = True
                result['processing_method'] = 'hybrid' if local_result else 'textract'
                result['cost_estimate'] = self._estimate_textract_cost(image_data)
            
            result['processing_time'] = time.time() - start_time
            
            logger.info(f"Document processed: method={result['processing_method']}, "
                       f"confidence={result['confidence']:.2f}, time={result['processing_time']:.2f}s")
            
            return result
            
        except Exception as e:
            logger.error(f"Enhanced OCR processing failed: {e}")
            result['error'] = str(e)
            result['processing_time'] = time.time() - start_time
            return result
    
    def process_prescription(self, image_data: bytes, use_textract: bool = None) -> Dict[str, Any]:
        """
        Process prescription with specialized handling.
        
        Args:
            image_data: Image data as bytes
            use_textract: Override Textract usage decision
            
        Returns:
            Dict containing structured prescription data
        """
        if use_textract is None:
            use_textract = self.prescription_textract_enabled
        
        result = self.process_document(
            image_data, 
            document_type='prescription',
            force_textract=use_textract
        )
        
        # Add prescription-specific processing
        if result.get('textract_used') and textract_service.is_enabled():
            try:
                prescription_data = textract_service.extract_prescription_data(image_data)
                result['structured_data'].update(prescription_data)
            except Exception as e:
                logger.warning(f"Textract prescription extraction failed: {e}")
        
        return result
    
    def process_lab_report(self, image_data: bytes) -> Dict[str, Any]:
        """
        Process lab report with table and form extraction.
        
        Args:
            image_data: Image data as bytes
            
        Returns:
            Dict containing structured lab report data
        """
        result = self.process_document(image_data, document_type='lab_report')
        
        # Add lab-specific processing with Textract
        if result.get('textract_used') and textract_service.is_enabled():
            try:
                lab_data = textract_service.extract_lab_report_data(image_data)
                result['structured_data'].update(lab_data)
            except Exception as e:
                logger.warning(f"Textract lab report extraction failed: {e}")
        
        return result
    
    def _process_with_local_ocr(self, image_np: np.ndarray, document_type: str = None) -> Dict[str, Any]:
        """
        Process document with local Tesseract OCR.
        
        Args:
            image_np: Image as numpy array
            document_type: Type of document
            
        Returns:
            Dict containing local OCR results
        """
        try:
            # Use existing local OCR processing
            text = _get_ocr_text_from_image(image_np)
            
            if not text:
                return {
                    'text': '',
                    'confidence': 0.0,
                    'structured_data': {},
                    'error': 'Local OCR returned no text'
                }
            
            # Extract structured data
            entities = extract_medical_entities(text)
            final_result = _calculate_confidence(entities)
            
            return {
                'text': text,
                'confidence': final_result.get('overall_confidence', 0.0),
                'structured_data': final_result,
                'raw_entities': entities
            }
            
        except Exception as e:
            logger.error(f"Local OCR processing failed: {e}")
            return {
                'text': '',
                'confidence': 0.0,
                'structured_data': {},
                'error': str(e)
            }
    
    def _process_with_textract(self, image_data: bytes, document_type: str = None) -> Dict[str, Any]:
        """
        Process document with AWS Textract.
        
        Args:
            image_data: Image data as bytes
            document_type: Type of document
            
        Returns:
            Dict containing Textract results
        """
        try:
            if document_type == 'prescription':
                # Use specialized prescription processing
                prescription_data = textract_service.extract_prescription_data(image_data)
                return {
                    'text': prescription_data.get('raw_text', ''),
                    'confidence': prescription_data.get('textract_confidence', 0.0),
                    'structured_data': prescription_data
                }
            
            elif document_type == 'lab_report':
                # Use specialized lab report processing
                lab_data = textract_service.extract_lab_report_data(image_data)
                return {
                    'text': lab_data.get('text', ''),
                    'confidence': lab_data.get('confidence', 0.0),
                    'structured_data': lab_data
                }
            
            else:
                # Use general text extraction
                text, confidence, raw_response = textract_service.extract_text_from_image(image_data)
                
                # Extract structured data from text
                entities = extract_medical_entities(text)
                final_result = _calculate_confidence(entities)
                
                return {
                    'text': text,
                    'confidence': confidence,
                    'structured_data': final_result,
                    'raw_textract_response': raw_response
                }
                
        except Exception as e:
            logger.error(f"Textract processing failed: {e}")
            return {
                'text': '',
                'confidence': 0.0,
                'structured_data': {},
                'error': str(e)
            }
    
    def _should_use_textract(self, local_confidence: float, document_type: str = None) -> bool:
        """
        Determine if Textract should be used based on local results and document type.
        
        Args:
            local_confidence: Confidence from local OCR
            document_type: Type of document
            
        Returns:
            bool: True if Textract should be used
        """
        if not self.textract_enabled:
            return False
        
        # Always use Textract for prescriptions if enabled
        if document_type == 'prescription' and self.prescription_textract_enabled:
            return True
        
        # Use Textract for low confidence results
        if local_confidence < self.confidence_threshold:
            return True
        
        # Use Textract for complex documents that benefit from form/table extraction
        if document_type in ['lab_report', 'discharge_summary', 'referral', 'insurance']:
            return True
        
        # Cost optimization: don't use Textract for high-confidence simple documents
        if self.cost_optimization and local_confidence > 0.9 and document_type in ['progress_note', 'vital_signs']:
            return False
        
        return False
    
    def _combine_results(self, local_result: Dict, textract_result: Dict) -> Dict[str, Any]:
        """
        Combine local OCR and Textract results to get the best outcome.
        
        Args:
            local_result: Results from local OCR
            textract_result: Results from Textract
            
        Returns:
            Dict containing combined results
        """
        combined = {
            'text': '',
            'confidence': 0.0,
            'structured_data': {},
            'local_result': local_result,
            'textract_result': textract_result
        }
        
        # Choose text with higher confidence
        local_conf = local_result.get('confidence', 0.0)
        textract_conf = textract_result.get('confidence', 0.0)
        
        if textract_conf > local_conf:
            combined['text'] = textract_result.get('text', '')
            combined['confidence'] = textract_conf
            combined['primary_source'] = 'textract'
        else:
            combined['text'] = local_result.get('text', '')
            combined['confidence'] = local_conf
            combined['primary_source'] = 'local'
        
        # Combine structured data intelligently
        combined['structured_data'] = self._merge_structured_data(
            local_result.get('structured_data', {}),
            textract_result.get('structured_data', {})
        )
        
        return combined
    
    def _merge_structured_data(self, local_data: Dict, textract_data: Dict) -> Dict:
        """
        Merge structured data from local OCR and Textract.
        
        Args:
            local_data: Structured data from local OCR
            textract_data: Structured data from Textract
            
        Returns:
            Dict containing merged structured data
        """
        merged = {}
        
        # Merge patient info
        merged['patient_info'] = {**local_data.get('patient_info', {}), **textract_data.get('patient_info', {})}
        
        # Merge doctor info
        merged['doctor_info'] = {**local_data.get('doctor_info', {}), **textract_data.get('doctor_info', {})}
        
        # Merge medications (prefer Textract for better structure)
        local_meds = local_data.get('medicines', [])
        textract_meds = textract_data.get('medications', [])
        
        if textract_meds:
            merged['medicines'] = textract_meds
        else:
            merged['medicines'] = local_meds
        
        # Merge lab tests
        local_tests = local_data.get('lab_tests', [])
        textract_tests = textract_data.get('tests', [])
        
        if textract_tests:
            merged['lab_tests'] = textract_tests
        else:
            merged['lab_tests'] = local_tests
        
        # Use best diagnosis
        local_diag = local_data.get('diagnosis', {})
        textract_diag = textract_data.get('diagnosis', '')
        
        if isinstance(textract_diag, str) and textract_diag:
            merged['diagnosis'] = {'text': textract_diag, 'confidence': 0.8}
        elif isinstance(local_diag, dict) and local_diag.get('text'):
            merged['diagnosis'] = local_diag
        else:
            merged['diagnosis'] = {'text': '', 'confidence': 0.0}
        
        # Use best advice
        local_advice = local_data.get('advice', {})
        textract_advice = textract_data.get('advice', '')
        
        if isinstance(textract_advice, str) and textract_advice:
            merged['advice'] = {'text': textract_advice, 'confidence': 0.8}
        elif isinstance(local_advice, dict) and local_advice.get('text'):
            merged['advice'] = local_advice
        else:
            merged['advice'] = {'text': '', 'confidence': 0.0}
        
        # Calculate overall confidence
        confidences = []
        if merged.get('diagnosis', {}).get('confidence'):
            confidences.append(merged['diagnosis']['confidence'])
        if merged.get('medicines'):
            med_conf = sum(med.get('confidence', 0.5) for med in merged['medicines']) / len(merged['medicines'])
            confidences.append(med_conf)
        if merged.get('advice', {}).get('confidence'):
            confidences.append(merged['advice']['confidence'])
        
        merged['overall_confidence'] = sum(confidences) / len(confidences) if confidences else 0.0
        
        return merged
    
    def _estimate_textract_cost(self, image_data: bytes) -> float:
        """
        Estimate the cost of Textract processing.
        
        Args:
            image_data: Image data as bytes
            
        Returns:
            float: Estimated cost in USD
        """
        # AWS Textract pricing (as of 2024)
        # DetectDocumentText: $0.0015 per page
        # AnalyzeDocument: $0.05 per page for forms, $0.015 per page for tables
        
        base_cost = 0.0015  # Basic text detection
        analysis_cost = 0.065  # Forms + tables analysis
        
        # For now, assume single page
        return base_cost + analysis_cost
    
    def get_processing_stats(self) -> Dict[str, Any]:
        """
        Get processing statistics and configuration.
        
        Returns:
            Dict containing service statistics
        """
        return {
            'local_ocr_enabled': self.local_ocr_enabled,
            'textract_enabled': self.textract_enabled,
            'confidence_threshold': self.confidence_threshold,
            'cost_optimization': self.cost_optimization,
            'prescription_textract_enabled': self.prescription_textract_enabled,
            'textract_service_status': textract_service.is_enabled()
        }


# Import io module at the top
import io

# Singleton instance
enhanced_ocr_service = EnhancedOCRService()