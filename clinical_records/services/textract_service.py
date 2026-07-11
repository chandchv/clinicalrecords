"""
AWS Textract integration service for enhanced OCR processing.
Provides fallback to AWS Textract for complex documents and prescription OCR.
"""

import os
import json
import logging
import boto3
from typing import Dict, List, Optional, Tuple, Any
from decimal import Decimal
from django.conf import settings
from botocore.exceptions import ClientError, NoCredentialsError

logger = logging.getLogger(__name__)


class TextractService:
    """
    AWS Textract service for enhanced OCR processing with form and table extraction.
    """
    
    def __init__(self):
        """Initialize Textract client with AWS credentials."""
        self.textract_client = None
        self.s3_client = None
        self.enabled = getattr(settings, 'TEXTRACT_ENABLED', False)
        
        if self.enabled:
            try:
                # Initialize AWS clients
                self.textract_client = boto3.client(
                    'textract',
                    region_name=getattr(settings, 'AWS_REGION', 'us-east-1'),
                    aws_access_key_id=getattr(settings, 'AWS_ACCESS_KEY_ID', None),
                    aws_secret_access_key=getattr(settings, 'AWS_SECRET_ACCESS_KEY', None)
                )
                
                self.s3_client = boto3.client(
                    's3',
                    region_name=getattr(settings, 'AWS_REGION', 'us-east-1'),
                    aws_access_key_id=getattr(settings, 'AWS_ACCESS_KEY_ID', None),
                    aws_secret_access_key=getattr(settings, 'AWS_SECRET_ACCESS_KEY', None)
                )
                
                # Test connection
                self._test_connection()
                logger.info("AWS Textract service initialized successfully")
                
            except (NoCredentialsError, ClientError) as e:
                logger.error(f"Failed to initialize AWS Textract: {e}")
                self.enabled = False
                self.textract_client = None
                self.s3_client = None
    
    def _test_connection(self):
        """Test AWS Textract connection."""
        try:
            # Simple test call to verify credentials
            self.textract_client.get_document_text_detection(JobId='test-job-id')
        except ClientError as e:
            if e.response['Error']['Code'] != 'InvalidJobIdException':
                raise e
            # InvalidJobIdException is expected for test call
    
    def is_enabled(self) -> bool:
        """Check if Textract service is enabled and configured."""
        return self.enabled and self.textract_client is not None
    
    def should_use_textract(self, confidence: float, document_type: str = None) -> bool:
        """
        Determine if Textract should be used based on confidence and document type.
        
        Args:
            confidence: OCR confidence from local processing
            document_type: Type of document (prescription, lab_report, etc.)
            
        Returns:
            bool: True if Textract should be used
        """
        if not self.is_enabled():
            return False
        
        # Use Textract for low confidence results
        if confidence < getattr(settings, 'TEXTRACT_CONFIDENCE_THRESHOLD', 0.7):
            return True
        
        # Always use Textract for prescriptions if enabled
        if document_type == 'prescription' and getattr(settings, 'TEXTRACT_PRESCRIPTION_ENABLED', True):
            return True
        
        # Use Textract for complex documents (forms, tables)
        if document_type in ['lab_report', 'discharge_summary', 'referral']:
            return True
        
        return False
    
    def extract_text_from_image(self, image_bytes: bytes) -> Tuple[str, float, Dict]:
        """
        Extract text from image using AWS Textract.
        
        Args:
            image_bytes: Image data as bytes
            
        Returns:
            Tuple of (extracted_text, confidence, raw_response)
        """
        if not self.is_enabled():
            raise ValueError("Textract service is not enabled or configured")
        
        try:
            # Call Textract detect_document_text
            response = self.textract_client.detect_document_text(
                Document={'Bytes': image_bytes}
            )
            
            # Extract text and calculate confidence
            text, confidence = self._extract_text_from_response(response)
            
            logger.info(f"Textract extracted {len(text)} characters with confidence {confidence:.2f}")
            
            return text, confidence, response
            
        except ClientError as e:
            logger.error(f"Textract text extraction failed: {e}")
            raise
    
    def analyze_document(self, image_bytes: bytes, feature_types: List[str] = None) -> Dict:
        """
        Analyze document with forms and tables using AWS Textract.
        
        Args:
            image_bytes: Image data as bytes
            feature_types: List of features to extract (TABLES, FORMS)
            
        Returns:
            Dict containing extracted data
        """
        if not self.is_enabled():
            raise ValueError("Textract service is not enabled or configured")
        
        if feature_types is None:
            feature_types = ['TABLES', 'FORMS']
        
        try:
            # Call Textract analyze_document
            response = self.textract_client.analyze_document(
                Document={'Bytes': image_bytes},
                FeatureTypes=feature_types
            )
            
            # Process the response
            result = self._process_analyze_response(response)
            
            logger.info(f"Textract analyzed document with {len(result.get('forms', []))} forms and {len(result.get('tables', []))} tables")
            
            return result
            
        except ClientError as e:
            logger.error(f"Textract document analysis failed: {e}")
            raise
    
    def extract_prescription_data(self, image_bytes: bytes) -> Dict:
        """
        Extract structured prescription data using Textract with medical-specific processing.
        
        Args:
            image_bytes: Image data as bytes
            
        Returns:
            Dict containing structured prescription data
        """
        try:
            # First, get basic text extraction
            text, confidence, _ = self.extract_text_from_image(image_bytes)
            
            # Then analyze for forms and tables
            analysis = self.analyze_document(image_bytes, ['FORMS', 'TABLES'])
            
            # Process prescription-specific data
            prescription_data = self._extract_prescription_entities(text, analysis)
            prescription_data['textract_confidence'] = confidence
            prescription_data['raw_text'] = text
            
            return prescription_data
            
        except Exception as e:
            logger.error(f"Prescription extraction failed: {e}")
            raise
    
    def extract_lab_report_data(self, image_bytes: bytes) -> Dict:
        """
        Extract structured lab report data using Textract.
        
        Args:
            image_bytes: Image data as bytes
            
        Returns:
            Dict containing structured lab report data
        """
        try:
            # Analyze document for tables and forms
            analysis = self.analyze_document(image_bytes, ['TABLES', 'FORMS'])
            
            # Process lab-specific data
            lab_data = self._extract_lab_entities(analysis)
            
            return lab_data
            
        except Exception as e:
            logger.error(f"Lab report extraction failed: {e}")
            raise
    
    def _extract_text_from_response(self, response: Dict) -> Tuple[str, float]:
        """
        Extract text and calculate confidence from Textract response.
        
        Args:
            response: Textract API response
            
        Returns:
            Tuple of (text, average_confidence)
        """
        text_blocks = []
        confidences = []
        
        for block in response.get('Blocks', []):
            if block['BlockType'] == 'LINE':
                text_blocks.append(block.get('Text', ''))
                confidences.append(float(block.get('Confidence', 0)))
        
        text = '\n'.join(text_blocks)
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
        
        return text, avg_confidence / 100.0  # Convert to 0-1 scale
    
    def _process_analyze_response(self, response: Dict) -> Dict:
        """
        Process Textract analyze_document response to extract forms and tables.
        
        Args:
            response: Textract analyze_document response
            
        Returns:
            Dict containing processed forms and tables
        """
        result = {
            'forms': [],
            'tables': [],
            'text': '',
            'confidence': 0.0
        }
        
        blocks = response.get('Blocks', [])
        
        # Extract text and confidence
        text_blocks = []
        confidences = []
        
        for block in blocks:
            if block['BlockType'] == 'LINE':
                text_blocks.append(block.get('Text', ''))
                confidences.append(float(block.get('Confidence', 0)))
        
        result['text'] = '\n'.join(text_blocks)
        result['confidence'] = (sum(confidences) / len(confidences) / 100.0) if confidences else 0.0
        
        # Extract forms (key-value pairs)
        result['forms'] = self._extract_forms(blocks)
        
        # Extract tables
        result['tables'] = self._extract_tables(blocks)
        
        return result
    
    def _extract_forms(self, blocks: List[Dict]) -> List[Dict]:
        """Extract form key-value pairs from Textract blocks."""
        forms = []
        
        # Create block map for easy lookup
        block_map = {block['Id']: block for block in blocks}
        
        for block in blocks:
            if block['BlockType'] == 'KEY_VALUE_SET':
                if block.get('EntityTypes') and 'KEY' in block['EntityTypes']:
                    # This is a key block
                    key_text = self._get_text_from_block(block, block_map)
                    
                    # Find associated value
                    value_text = ''
                    if 'Relationships' in block:
                        for relationship in block['Relationships']:
                            if relationship['Type'] == 'VALUE':
                                for value_id in relationship['Ids']:
                                    value_block = block_map.get(value_id)
                                    if value_block:
                                        value_text = self._get_text_from_block(value_block, block_map)
                                        break
                    
                    if key_text:
                        forms.append({
                            'key': key_text.strip(),
                            'value': value_text.strip(),
                            'confidence': float(block.get('Confidence', 0)) / 100.0
                        })
        
        return forms
    
    def _extract_tables(self, blocks: List[Dict]) -> List[Dict]:
        """Extract tables from Textract blocks."""
        tables = []
        
        # Create block map for easy lookup
        block_map = {block['Id']: block for block in blocks}
        
        for block in blocks:
            if block['BlockType'] == 'TABLE':
                table_data = {
                    'rows': [],
                    'confidence': float(block.get('Confidence', 0)) / 100.0
                }
                
                # Get table cells
                if 'Relationships' in block:
                    for relationship in block['Relationships']:
                        if relationship['Type'] == 'CHILD':
                            cells = {}
                            for cell_id in relationship['Ids']:
                                cell_block = block_map.get(cell_id)
                                if cell_block and cell_block['BlockType'] == 'CELL':
                                    row_index = cell_block.get('RowIndex', 0)
                                    col_index = cell_block.get('ColumnIndex', 0)
                                    cell_text = self._get_text_from_block(cell_block, block_map)
                                    
                                    if row_index not in cells:
                                        cells[row_index] = {}
                                    cells[row_index][col_index] = cell_text.strip()
                            
                            # Convert to ordered rows
                            for row_idx in sorted(cells.keys()):
                                row = []
                                for col_idx in sorted(cells[row_idx].keys()):
                                    row.append(cells[row_idx][col_idx])
                                table_data['rows'].append(row)
                
                tables.append(table_data)
        
        return tables
    
    def _get_text_from_block(self, block: Dict, block_map: Dict) -> str:
        """Get text content from a block and its children."""
        text_parts = []
        
        if 'Relationships' in block:
            for relationship in block['Relationships']:
                if relationship['Type'] == 'CHILD':
                    for child_id in relationship['Ids']:
                        child_block = block_map.get(child_id)
                        if child_block and child_block['BlockType'] == 'WORD':
                            text_parts.append(child_block.get('Text', ''))
        
        return ' '.join(text_parts)
    
    def _extract_prescription_entities(self, text: str, analysis: Dict) -> Dict:
        """
        Extract prescription entities from Textract analysis.
        
        Args:
            text: Raw extracted text
            analysis: Textract analysis result
            
        Returns:
            Dict containing structured prescription data
        """
        import re
        
        prescription_data = {
            'patient_info': {},
            'doctor_info': {},
            'medications': [],
            'diagnosis': '',
            'advice': '',
            'date': None,
            'confidence': analysis.get('confidence', 0.0)
        }
        
        # Extract from forms (key-value pairs)
        forms = analysis.get('forms', [])
        for form in forms:
            key = form['key'].lower()
            value = form['value']
            
            # Patient information
            if any(keyword in key for keyword in ['patient', 'name', 'pt']):
                prescription_data['patient_info']['name'] = value
            elif any(keyword in key for keyword in ['age', 'years']):
                prescription_data['patient_info']['age'] = value
            elif any(keyword in key for keyword in ['gender', 'sex']):
                prescription_data['patient_info']['gender'] = value
            elif any(keyword in key for keyword in ['date', 'dt']):
                prescription_data['date'] = value
            
            # Doctor information
            elif any(keyword in key for keyword in ['doctor', 'dr', 'physician']):
                prescription_data['doctor_info']['name'] = value
            elif any(keyword in key for keyword in ['registration', 'reg', 'license']):
                prescription_data['doctor_info']['registration'] = value
        
        # Extract medications from tables
        tables = analysis.get('tables', [])
        for table in tables:
            medications = self._extract_medications_from_table(table)
            prescription_data['medications'].extend(medications)
        
        # Extract from raw text if no structured data found
        if not prescription_data['medications']:
            prescription_data['medications'] = self._extract_medications_from_text(text)
        
        # Extract diagnosis and advice from text
        lines = text.split('\n')
        for line in lines:
            line_lower = line.lower().strip()
            if any(keyword in line_lower for keyword in ['diagnosis', 'dx', 'impression']):
                prescription_data['diagnosis'] = line.split(':', 1)[-1].strip()
            elif any(keyword in line_lower for keyword in ['advice', 'instructions', 'note']):
                prescription_data['advice'] = line.split(':', 1)[-1].strip()
        
        return prescription_data
    
    def _extract_medications_from_table(self, table: Dict) -> List[Dict]:
        """Extract medications from a table structure."""
        medications = []
        rows = table.get('rows', [])
        
        if not rows:
            return medications
        
        # Assume first row might be headers
        headers = [cell.lower() for cell in rows[0]] if rows else []
        
        for row in rows[1:]:  # Skip header row
            if len(row) >= 2:  # At least name and dosage
                medication = {
                    'name': row[0].strip(),
                    'dosage': row[1].strip() if len(row) > 1 else '',
                    'frequency': row[2].strip() if len(row) > 2 else '',
                    'duration': row[3].strip() if len(row) > 3 else '',
                    'instructions': row[4].strip() if len(row) > 4 else '',
                    'confidence': table.get('confidence', 0.0)
                }
                
                # Skip empty or header-like rows
                if medication['name'] and not any(header in medication['name'].lower() 
                                                for header in ['medicine', 'drug', 'medication', 'name']):
                    medications.append(medication)
        
        return medications
    
    def _extract_medications_from_text(self, text: str) -> List[Dict]:
        """Extract medications from raw text using regex patterns."""
        import re
        
        medications = []
        lines = text.split('\n')
        
        # Enhanced patterns for medication extraction
        patterns = [
            r'(?:Tab\.?|Cap\.?|Syp\.?|Inj\.?)\s*([A-Za-z0-9\s\-\+]+?)\s*(\d+\.?\d*\s*(?:mg|ml|mcg|g|IU))\s*([0-9\-xX]+|OD|BD|TDS|QID|HS)?\s*(\d+\s*(?:days?|weeks?|months?))?',
            r'(\d+\.)\s*([A-Za-z0-9\s\-\+]+?)\s*(\d+\.?\d*\s*(?:mg|ml|mcg|g|IU))\s*([0-9\-xX]+|OD|BD|TDS|QID|HS)?\s*(\d+\s*(?:days?|weeks?|months?))?',
            r'([A-Za-z0-9\s\-\+]{3,})\s+(\d+\.?\d*\s*(?:mg|ml|mcg|g|IU))\s*([0-9\-xX]+|OD|BD|TDS|QID|HS)?\s*(\d+\s*(?:days?|weeks?|months?))?'
        ]
        
        for line in lines:
            for pattern in patterns:
                matches = re.findall(pattern, line, re.IGNORECASE)
                for match in matches:
                    if len(match) >= 2:
                        medication = {
                            'name': match[1].strip() if pattern.startswith(r'(\d+\.)') else match[0].strip(),
                            'dosage': match[2].strip() if pattern.startswith(r'(\d+\.)') else match[1].strip(),
                            'frequency': match[3].strip() if len(match) > 3 and pattern.startswith(r'(\d+\.)') else (match[2].strip() if len(match) > 2 else ''),
                            'duration': match[4].strip() if len(match) > 4 and pattern.startswith(r'(\d+\.)') else (match[3].strip() if len(match) > 3 else ''),
                            'instructions': '',
                            'confidence': 0.8  # Default confidence for text extraction
                        }
                        
                        if medication['name'] and len(medication['name']) > 2:
                            medications.append(medication)
        
        return medications
    
    def _extract_lab_entities(self, analysis: Dict) -> Dict:
        """
        Extract lab report entities from Textract analysis.
        
        Args:
            analysis: Textract analysis result
            
        Returns:
            Dict containing structured lab report data
        """
        lab_data = {
            'patient_info': {},
            'lab_info': {},
            'tests': [],
            'date': None,
            'confidence': analysis.get('confidence', 0.0)
        }
        
        # Extract from forms
        forms = analysis.get('forms', [])
        for form in forms:
            key = form['key'].lower()
            value = form['value']
            
            # Patient information
            if any(keyword in key for keyword in ['patient', 'name']):
                lab_data['patient_info']['name'] = value
            elif any(keyword in key for keyword in ['age', 'years']):
                lab_data['patient_info']['age'] = value
            elif any(keyword in key for keyword in ['gender', 'sex']):
                lab_data['patient_info']['gender'] = value
            elif any(keyword in key for keyword in ['date', 'collected', 'reported']):
                lab_data['date'] = value
            
            # Lab information
            elif any(keyword in key for keyword in ['lab', 'laboratory']):
                lab_data['lab_info']['name'] = value
        
        # Extract test results from tables
        tables = analysis.get('tables', [])
        for table in tables:
            tests = self._extract_tests_from_table(table)
            lab_data['tests'].extend(tests)
        
        return lab_data
    
    def _extract_tests_from_table(self, table: Dict) -> List[Dict]:
        """Extract lab test results from a table structure."""
        tests = []
        rows = table.get('rows', [])
        
        if not rows:
            return tests
        
        # Look for test result patterns in table
        for row in rows:
            if len(row) >= 3:  # At least test name, value, reference range
                test_name = row[0].strip()
                test_value = row[1].strip()
                reference_range = row[2].strip() if len(row) > 2 else ''
                unit = row[3].strip() if len(row) > 3 else ''
                
                # Skip header rows
                if test_name and not any(header in test_name.lower() 
                                       for header in ['test', 'parameter', 'investigation']):
                    # Try to parse numeric value
                    try:
                        numeric_value = float(test_value.replace('<', '').replace('>', ''))
                        is_numeric = True
                    except (ValueError, AttributeError):
                        numeric_value = None
                        is_numeric = False
                    
                    test = {
                        'name': test_name,
                        'value': test_value,
                        'numeric_value': numeric_value,
                        'unit': unit,
                        'reference_range': reference_range,
                        'is_numeric': is_numeric,
                        'confidence': table.get('confidence', 0.0)
                    }
                    
                    # Determine if result is abnormal
                    if reference_range and is_numeric:
                        test['is_abnormal'] = self._is_value_abnormal(numeric_value, reference_range)
                    else:
                        test['is_abnormal'] = None
                    
                    tests.append(test)
        
        return tests
    
    def _is_value_abnormal(self, value: float, reference_range: str) -> bool:
        """Determine if a test value is abnormal based on reference range."""
        import re
        
        # Parse reference range (e.g., "10-20", "< 5", "> 100")
        range_patterns = [
            r'(\d+\.?\d*)\s*-\s*(\d+\.?\d*)',  # Range: 10-20
            r'<\s*(\d+\.?\d*)',                # Less than: < 5
            r'>\s*(\d+\.?\d*)',                # Greater than: > 100
            r'(\d+\.?\d*)\s*to\s*(\d+\.?\d*)', # Range: 10 to 20
        ]
        
        for pattern in range_patterns:
            match = re.search(pattern, reference_range)
            if match:
                if '-' in pattern or 'to' in pattern:
                    # Range
                    min_val = float(match.group(1))
                    max_val = float(match.group(2))
                    return not (min_val <= value <= max_val)
                elif '<' in pattern:
                    # Less than
                    max_val = float(match.group(1))
                    return value >= max_val
                elif '>' in pattern:
                    # Greater than
                    min_val = float(match.group(1))
                    return value <= min_val
        
        return False  # Cannot determine, assume normal


# Singleton instance
textract_service = TextractService()