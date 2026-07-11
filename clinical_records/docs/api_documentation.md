# Clinical Records API Documentation

## Overview

The Clinical Records API provides comprehensive CRUD operations for managing clinical records with proper tenant isolation, search capabilities, and advanced filtering.

## Base URL

```
/clinical-records/api/
```

## Authentication

All endpoints require authentication. Include the JWT token in the Authorization header:

```
Authorization: Bearer <your-jwt-token>
```

## Endpoints

### Clinical Records

#### List Clinical Records
```
GET /clinical-records/api/records/
```

**Query Parameters:**
- `page`: Page number for pagination (default: 1)
- `page_size`: Number of records per page (default: 20, max: 100)
- `record_type`: Filter by record type (lab_report, prescription, etc.)
- `status`: Filter by status (active, archived, etc.)
- `priority`: Filter by priority (low, normal, high, urgent)
- `patient_id`: Filter by patient ID
- `date_from`: Filter records from this date (ISO format)
- `date_to`: Filter records to this date (ISO format)
- `tags`: Filter by tags (can specify multiple)
- `has_documents`: Filter by document presence (true/false)
- `include_documents`: Include document details (true/false)
- `search`: Search across title, description, patient name, tags
- `ordering`: Order results by field (record_date, created_at, title, priority)

**Example Response:**
```json
{
  "count": 150,
  "next": "http://example.com/api/records/?page=2",
  "previous": null,
  "results": [
    {
      "id": "123e4567-e89b-12d3-a456-426614174000",
      "patient": {
        "id": "456e7890-e89b-12d3-a456-426614174001",
        "first_name": "John",
        "last_name": "Doe",
        "full_name": "John Doe",
        "date_of_birth": "1990-01-01"
      },
      "clinic_name": "Test Clinic",
      "created_by": {
        "id": "789e0123-e89b-12d3-a456-426614174002",
        "username": "doctor@clinic.com",
        "full_name": "Dr. Smith"
      },
      "record_type": "lab_report",
      "title": "Blood Test Results",
      "description": "Complete blood count analysis",
      "status": "active",
      "priority": "normal",
      "record_date": "2024-01-15T10:00:00Z",
      "is_active": true,
      "is_confidential": false,
      "requires_consent": true,
      "tags": ["blood-test", "routine"],
      "metadata": {},
      "created_at": "2024-01-15T10:00:00Z",
      "updated_at": "2024-01-15T10:00:00Z",
      "document_count": 2,
      "has_documents": true,
      "latest_document": {
        "id": "abc12345-e89b-12d3-a456-426614174003",
        "original_filename": "blood_test.pdf",
        "document_type": "pdf",
        "processing_status": "completed",
        "created_at": "2024-01-15T10:05:00Z"
      }
    }
  ]
}
```

#### Create Clinical Record
```
POST /clinical-records/api/records/
```

**Request Body:**
```json
{
  "patient": "456e7890-e89b-12d3-a456-426614174001",
  "record_type": "lab_report",
  "title": "Blood Test Results",
  "description": "Complete blood count analysis",
  "priority": "normal",
  "record_date": "2024-01-15T10:00:00Z",
  "tags": ["blood-test", "routine"],
  "metadata": {
    "lab_name": "Central Lab",
    "test_code": "CBC001"
  }
}
```

#### Get Clinical Record
```
GET /clinical-records/api/records/{id}/
```

#### Update Clinical Record
```
PUT /clinical-records/api/records/{id}/
PATCH /clinical-records/api/records/{id}/
```

#### Delete Clinical Record
```
DELETE /clinical-records/api/records/{id}/
```
*Note: This performs a soft delete, setting status to 'deleted'*

### Custom Actions

#### Archive Record
```
POST /clinical-records/api/records/{id}/archive/
```

#### Restore Record
```
POST /clinical-records/api/records/{id}/restore/
```

#### Add Tag
```
POST /clinical-records/api/records/{id}/add_tag/
```

**Request Body:**
```json
{
  "tag": "urgent"
}
```

#### Remove Tag
```
POST /clinical-records/api/records/{id}/remove_tag/
```

**Request Body:**
```json
{
  "tag": "urgent"
}
```

#### Get Record Documents
```
GET /clinical-records/api/records/{id}/documents/
```

**Query Parameters:**
- `document_type`: Filter by document type
- `processing_status`: Filter by processing status

#### Get Record Timeline
```
GET /clinical-records/api/records/{id}/timeline/
```

Returns a chronological timeline of all activities related to the record.

#### Get Statistics
```
GET /clinical-records/api/records/statistics/
```

Returns statistics about clinical records for the current clinic.

**Example Response:**
```json
{
  "total_records": 1250,
  "active_records": 1100,
  "archived_records": 150,
  "by_type": {
    "lab_report": {
      "count": 450,
      "display_name": "Lab Report"
    },
    "prescription": {
      "count": 380,
      "display_name": "Prescription"
    }
  },
  "by_priority": {
    "urgent": {
      "count": 25,
      "display_name": "Urgent"
    },
    "high": {
      "count": 120,
      "display_name": "High"
    }
  },
  "recent_activity": {
    "last_7_days": 45,
    "last_30_days": 180
  }
}
```

#### Advanced Search
```
GET /clinical-records/api/records/search/?q=blood+test&include_documents=true
```

**Query Parameters:**
- `q`: Search query (required)
- `include_documents`: Search in document OCR text (true/false)

## Error Responses

### 400 Bad Request
```json
{
  "error": "Invalid request data",
  "details": {
    "field_name": ["This field is required."]
  }
}
```

### 401 Unauthorized
```json
{
  "detail": "Authentication credentials were not provided."
}
```

### 403 Forbidden
```json
{
  "detail": "You do not have permission to perform this action."
}
```

### 404 Not Found
```json
{
  "detail": "Not found."
}
```

## Tenant Isolation

All API endpoints automatically filter data based on the user's current tenant (clinic). Users can only access records that belong to their clinic, ensuring complete data isolation between different clinics.

## Rate Limiting

API endpoints are subject to rate limiting to ensure fair usage and system stability. The default limits are:
- 1000 requests per hour for authenticated users
- 100 requests per hour for unauthenticated requests

## Pagination

List endpoints use cursor-based pagination with the following structure:
- `count`: Total number of records
- `next`: URL for the next page (null if last page)
- `previous`: URL for the previous page (null if first page)
- `results`: Array of records for the current page

## Filtering and Search

The API supports advanced filtering and search capabilities:

### Filtering
Use query parameters to filter results by specific fields. Multiple filters can be combined.

### Search
The search functionality looks across multiple fields including title, description, patient names, and tags. When `include_documents=true` is specified, it also searches within document OCR text.

### Ordering
Results can be ordered by various fields using the `ordering` parameter. Prefix with `-` for descending order.

Examples:
- `ordering=record_date` (ascending by record date)
- `ordering=-created_at` (descending by creation date)
- `ordering=priority,-record_date` (by priority, then by record date descending)
## Do
cument Upload Endpoints

### Upload Single Document
```
POST /clinical-records/api/documents/upload/
```

**Content-Type:** `multipart/form-data`

**Form Fields:**
- `file`: The document file to upload (required)
- `clinical_record`: UUID of the clinical record (required)

**Example Request:**
```bash
curl -X POST \
  -H "Authorization: Bearer <your-jwt-token>" \
  -F "file=@/path/to/document.pdf" \
  -F "clinical_record=123e4567-e89b-12d3-a456-426614174000" \
  http://example.com/clinical-records/api/documents/upload/
```

**Example Response:**
```json
{
  "id": "789e0123-e89b-12d3-a456-426614174003",
  "clinical_record": {
    "id": "123e4567-e89b-12d3-a456-426614174000",
    "title": "Blood Test Results"
  },
  "uploaded_by": {
    "id": "456e7890-e89b-12d3-a456-426614174001",
    "full_name": "Dr. Smith"
  },
  "original_filename": "document.pdf",
  "file_size": 1048576,
  "content_type": "application/pdf",
  "document_type": "pdf",
  "processing_status": "pending",
  "file_hash": "a1b2c3d4e5f6...",
  "created_at": "2024-01-15T10:00:00Z",
  "updated_at": "2024-01-15T10:00:00Z"
}
```

### Bulk Upload Documents
```
POST /clinical-records/api/documents/bulk_upload/
```

**Content-Type:** `multipart/form-data`

**Form Fields:**
- `clinical_record`: UUID of the clinical record (required)
- Multiple file fields with any names (e.g., `file1`, `file2`, etc.)

**Example Response:**
```json
{
  "uploaded_documents": [
    {
      "id": "789e0123-e89b-12d3-a456-426614174003",
      "original_filename": "document1.pdf",
      "processing_status": "pending"
    },
    {
      "id": "890e1234-e89b-12d3-a456-426614174004",
      "original_filename": "document2.jpg",
      "processing_status": "pending"
    }
  ],
  "upload_count": 2,
  "error_count": 0,
  "errors": []
}
```

### List Documents
```
GET /clinical-records/api/documents/
```

**Query Parameters:**
- `clinical_record_id`: Filter by clinical record
- `document_type`: Filter by document type (pdf, image, dicom, etc.)
- `processing_status`: Filter by processing status
- `search`: Search in filename and OCR text
- `ordering`: Order results by field

### Get Document Details
```
GET /clinical-records/api/documents/{id}/
```

### Download Document
```
GET /clinical-records/api/documents/{id}/download/
```

**Example Response:**
```json
{
  "download_url": "http://example.com/media/documents/clinic_123/document.pdf",
  "filename": "document.pdf",
  "content_type": "application/pdf",
  "file_size": 1048576
}
```

### Reprocess Document
```
POST /clinical-records/api/documents/{id}/reprocess/
```

Triggers reprocessing of a document (retry OCR/analysis).

### Get Processing Status
```
GET /clinical-records/api/documents/processing_status/
```

Returns processing statistics for all documents in the clinic.

**Example Response:**
```json
{
  "total_documents": 1250,
  "by_status": {
    "pending": {
      "count": 45,
      "display_name": "Pending Processing"
    },
    "processing": {
      "count": 12,
      "display_name": "Processing"
    },
    "completed": {
      "count": 1180,
      "display_name": "Processing Completed"
    },
    "failed": {
      "count": 13,
      "display_name": "Processing Failed"
    }
  },
  "by_type": {
    "pdf": {
      "count": 650,
      "display_name": "PDF Document"
    },
    "image": {
      "count": 480,
      "display_name": "Image File"
    },
    "dicom": {
      "count": 120,
      "display_name": "DICOM Medical Image"
    }
  },
  "processing_queue": {
    "pending": 45,
    "processing": 12,
    "failed": 13
  }
}
```

## File Upload Validation

### Supported File Types
- **PDF Documents**: `application/pdf`
- **Images**: `image/jpeg`, `image/png`, `image/tiff`, `image/bmp`
- **DICOM Files**: `application/dicom`
- **Text Files**: `text/plain`, `text/csv`
- **Office Documents**: Word, Excel files

### File Size Limits
- **Images**: 50MB maximum
- **PDF Documents**: 100MB maximum
- **DICOM Files**: 500MB maximum
- **Text Files**: 10MB maximum
- **Office Documents**: 50MB maximum
- **Other Types**: 25MB maximum

### Validation Rules
1. File must not be empty
2. File type must be supported
3. File size must be within limits
4. Filename must be provided and reasonable length
5. Dangerous file extensions (.exe, .bat, etc.) are blocked
6. File integrity is verified with SHA-256 hash

### Error Responses

#### File Validation Failed
```json
{
  "error": "File validation failed",
  "details": [
    "File size (52428800 bytes) exceeds maximum allowed size (50000000 bytes)",
    "Unsupported file type: application/x-executable"
  ]
}
```

#### Missing Required Fields
```json
{
  "error": "clinical_record field is required"
}
```

#### Clinical Record Not Found
```json
{
  "error": "Clinical record not found"
}
```

## Background Processing

When documents are uploaded, they are automatically queued for background processing which includes:

1. **File Type Detection**: Detailed analysis of file format and metadata
2. **OCR Processing**: Text extraction from images and PDFs
3. **Structured Data Extraction**: Parsing of lab reports, prescriptions, etc.
4. **DICOM Processing**: Medical image metadata extraction and preview generation
5. **Quality Assessment**: Confidence scoring and validation
6. **Manual Review Queue**: Low-confidence results are flagged for human review

Processing status can be monitored through the API endpoints and will be updated in real-time as documents are processed.

## Security Considerations

- All file uploads are validated for type and content
- Files are stored with secure naming to prevent conflicts
- Access is restricted by tenant isolation
- All upload and download activities are logged for audit purposes
- File integrity is verified using cryptographic hashes
- Dangerous file types are blocked for security
## 
Document Retrieval and Download Endpoints

### Download Document
- **GET** `/api/clinical_records/documents/{id}/download/`
- Download the original document file with proper access control
- **Response**: File download with appropriate headers and audit logging
- **Headers**: 
  - `Content-Disposition`: attachment with original filename
  - `Content-Type`: Original file MIME type
  - `X-Document-ID`: Document UUID

**Example:**
```bash
curl -H "Authorization: Bearer <token>" \
     -o document.pdf \
     /api/clinical_records/documents/123e4567-e89b-12d3-a456-426614174000/download/
```

### Preview Document
- **GET** `/api/clinical_records/documents/{id}/preview/`
- Get a preview image of the document (for images, PDFs, DICOM files)
- **Response**: JPEG preview image served inline
- **Headers**:
  - `Content-Type`: image/jpeg
  - `Content-Disposition`: inline with preview filename
  - `Cache-Control`: private, max-age=3600

**Example:**
```bash
curl -H "Authorization: Bearer <token>" \
     /api/clinical_records/documents/123e4567-e89b-12d3-a456-426614174000/preview/
```

### Thumbnail Document
- **GET** `/api/clinical_records/documents/{id}/thumbnail/`
- Get a small thumbnail image of the document
- **Response**: JPEG thumbnail image served inline
- **Headers**:
  - `Content-Type`: image/jpeg
  - `Content-Disposition`: inline with thumbnail filename
  - `Cache-Control`: private, max-age=3600

### Batch Download Documents
- **POST** `/api/clinical_records/documents/batch_download/`
- Download multiple documents as a ZIP archive
- **Request Body**:
```json
{
  "document_ids": [
    "123e4567-e89b-12d3-a456-426614174000",
    "987fcdeb-51a2-43d1-9f12-345678901234"
  ],
  "include_metadata": false
}
```
- **Response**: ZIP file download with all accessible documents
- **Limits**: Maximum 50 documents per batch, 500MB total size
- **Headers**:
  - `Content-Type`: application/zip
  - `X-Document-Count`: Number of documents included
  - `X-Total-Size`: Total size in bytes

**Example:**
```bash
curl -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{"document_ids": ["123e4567-e89b-12d3-a456-426614174000"]}' \
     -o documents.zip \
     /api/clinical_records/documents/batch_download/
```

### Get Document Metadata
- **GET** `/api/clinical_records/documents/{id}/metadata/`
- Get comprehensive metadata without downloading the file
- **Query Parameters**:
  - `include_ocr=true`: Include OCR text in response
  - `include_structured_data=true`: Include parsed structured data
  - `include_dicom=true`: Include DICOM metadata

**Example Response:**
```json
{
  "document_info": {
    "id": "123e4567-e89b-12d3-a456-426614174000",
    "filename": "lab_report_2024.pdf",
    "file_size": 245760,
    "content_type": "application/pdf",
    "document_type": "PDF Document",
    "file_hash": "sha256:abc123...",
    "created_at": "2024-01-15T10:30:00Z",
    "updated_at": "2024-01-15T10:35:00Z"
  },
  "clinical_record": {
    "id": "456e7890-e89b-12d3-a456-426614174000",
    "title": "Blood Test Results",
    "record_type": "Laboratory Report",
    "patient_name": "John Doe"
  },
  "processing_info": {
    "status": "Completed",
    "ocr_confidence": 0.95,
    "has_ocr_text": true,
    "has_structured_data": true,
    "has_dicom_metadata": false
  },
  "file_availability": {
    "original_file": true,
    "preview": true,
    "thumbnail": false,
    "file_size": 245760,
    "last_modified": "2024-01-15T10:30:00Z"
  }
}
```

### Generate Secure URL
- **GET** `/api/clinical_records/documents/{id}/secure_url/`
- Generate a secure URL for direct file access (supports future S3 integration)
- **Query Parameters**:
  - `action`: Type of access (download, preview, thumbnail) - default: download
  - `expires_in`: URL expiration in seconds (max 86400) - default: 3600

**Example Response:**
```json
{
  "secure_url": "https://example.com/secure/documents/abc123?token=xyz789&expires=1642248000",
  "action": "download",
  "expires_in": 3600,
  "expires_at": "2024-01-15T11:30:00Z"
}
```

## Access Control and Security

### Permission Requirements
- **View/Preview/Thumbnail**: Requires `clinical_records.view_documents` permission
- **Download**: Requires `clinical_records.download_documents` permission
- **Confidential Documents**: Requires `clinical_records.view_confidential_documents` permission

### Tenant Isolation
All document access is automatically filtered by the user's current clinic tenant. Users cannot access documents from other clinics.

### Audit Logging
All document access operations are logged with the following information:
- User who accessed the document
- Action performed (download, preview, thumbnail, etc.)
- Document ID and filename
- Timestamp and IP address
- Clinical record and patient information

### File Security
- All file paths are validated to prevent directory traversal attacks
- File types are validated against allowed MIME types
- File sizes are limited based on document type
- Secure filename generation for ZIP archives
- Optional file encryption at rest (configurable)

## Error Responses

### Common Error Codes
- `400 Bad Request`: Invalid request parameters
- `401 Unauthorized`: Missing or invalid authentication
- `403 Forbidden`: Insufficient permissions or access denied
- `404 Not Found`: Document or file not found
- `413 Payload Too Large`: File size exceeds limits
- `429 Too Many Requests`: Rate limit exceeded
- `500 Internal Server Error`: Server processing error

### Error Response Format
```json
{
  "error": "Error description",
  "details": {
    "field": "Additional error details"
  }
}
```

## Rate Limiting

Document download endpoints are rate-limited to prevent abuse:
- **Individual Downloads**: 100 requests per hour per user
- **Batch Downloads**: 10 requests per hour per user
- **Preview/Thumbnail**: 500 requests per hour per user

## Storage Backend Abstraction

The API supports both local file storage and cloud storage (S3) with automatic detection:

### Local Storage
- Files served directly by Django with proper access control
- Preview and thumbnail files stored alongside originals
- Secure file path validation and access logging

### S3 Storage (Future)
- Presigned URLs for secure direct access
- Automatic fallback for preview/thumbnail generation
- CloudFront CDN integration for improved performance
- Server-side encryption and access logging

The storage backend is transparent to API consumers - all endpoints work the same regardless of the underlying storage system.
##
 Secure Sharing API Endpoints

### Create Document Share Token
- **POST** `/api/clinical_records/sharing/create-document-share/`
- Create a secure share token for a specific document
- **Request Body**:
```json
{
  "document_id": "123e4567-e89b-12d3-a456-426614174000",
  "expires_in_hours": 24,
  "max_accesses": 10,
  "allowed_ips": ["192.168.1.1", "10.0.0.1"],
  "patient_consent": true,
  "purpose": "Referral to specialist",
  "recipient_info": {
    "name": "Dr. Smith",
    "organization": "City Hospital",
    "email": "dr.smith@cityhospital.com"
  }
}
```
- **Response**: Share token details with secure URL
- **Limits**: Max 168 hours (7 days) expiry, max 100 accesses

**Example Response:**
```json
{
  "id": "456e7890-e89b-12d3-a456-426614174000",
  "token": "secure-token-string",
  "scope": "document",
  "expires_at": "2024-01-16T10:30:00Z",
  "max_access_count": 10,
  "current_access_count": 0,
  "patient_consent_obtained": true,
  "purpose": "Referral to specialist",
  "share_url": "https://example.com/clinical-records/share/secure-token-string/"
}
```

### Create Record Share Token
- **POST** `/api/clinical_records/sharing/create-record-share/`
- Create a secure share token for a clinical record
- **Request Body**:
```json
{
  "record_id": "123e4567-e89b-12d3-a456-426614174000",
  "expires_in_hours": 48,
  "max_accesses": 5,
  "patient_consent": true,
  "purpose": "Second opinion consultation"
}
```

### Create Patient Bundle Share Token
- **POST** `/api/clinical_records/sharing/create-patient-bundle-share/`
- Create a secure share token for a patient's complete clinical data
- **Request Body**:
```json
{
  "patient_id": "123e4567-e89b-12d3-a456-426614174000",
  "expires_in_hours": 72,
  "max_accesses": 3,
  "patient_consent": true,
  "purpose": "Transfer of care",
  "recipient_info": {
    "name": "Dr. Wilson",
    "organization": "Regional Hospital"
  }
}
```

### List Share Tokens
- **GET** `/api/clinical_records/sharing/list/`
- List all share tokens for the current clinic
- **Query Parameters**:
  - `scope`: Filter by scope (document, record, patient_bundle)
  - `is_active`: Filter by active status (true/false)
  - `patient_id`: Filter by patient ID
- **Response**: Paginated list of share tokens

### Revoke Share Token
- **POST** `/api/clinical_records/sharing/revoke/{token_id}/`
- Revoke an active share token
- **Request Body**:
```json
{
  "reason": "No longer needed"
}
```
- **Response**: Updated token details showing revoked status

### Extend Share Token
- **POST** `/api/clinical_records/sharing/extend/{token_id}/`
- Extend the expiry time of a share token
- **Request Body**:
```json
{
  "additional_hours": 24
}
```
- **Limits**: Max 168 hours (7 days) extension
- **Response**: Updated token with new expiry time

### Access Shared Content (Public)
- **GET** `/api/clinical_records/sharing/access/{token}/`
- Access shared content using a share token (no authentication required)
- **Query Parameters**:
  - `format`: Response format (json, fhir, file)
- **Response**: Shared content based on token scope and format

**Example Usage:**
```bash
# Access document as JSON
curl https://example.com/api/clinical_records/sharing/access/secure-token/?format=json

# Access record as FHIR
curl https://example.com/api/clinical_records/sharing/access/secure-token/?format=fhir

# Download document file
curl -o document.pdf https://example.com/api/clinical_records/sharing/access/secure-token/?format=file
```

**Response Formats:**

**JSON Format (Document):**
```json
{
  "share_info": {
    "scope": "document",
    "purpose": "Referral to specialist",
    "expires_at": "2024-01-16T10:30:00Z",
    "access_count": 1
  },
  "document": {
    "id": "123e4567-e89b-12d3-a456-426614174000",
    "original_filename": "blood_test.pdf",
    "file_size": 245760,
    "content_type": "application/pdf",
    "created_at": "2024-01-15T10:30:00Z"
  }
}
```

**JSON Format (Patient Bundle):**
```json
{
  "share_info": {
    "scope": "patient_bundle",
    "purpose": "Transfer of care",
    "expires_at": "2024-01-18T10:30:00Z",
    "access_count": 1
  },
  "patient": {
    "name": "John Doe",
    "date_of_birth": "1990-01-01",
    "gender": "M",
    "record_count": 5
  },
  "clinical_records": [
    {
      "id": "456e7890-e89b-12d3-a456-426614174000",
      "title": "Blood Test Results",
      "record_type": "Laboratory Report",
      "record_date": "2024-01-15",
      "document_count": 2
    }
  ]
}
```

### Validate Share Token (Public)
- **GET** `/api/clinical_records/sharing/validate/{token}/`
- Validate a share token without accessing content (no authentication required)
- **Response**: Token validation status and metadata

**Example Response:**
```json
{
  "valid": true,
  "expires_at": "2024-01-16T10:30:00Z",
  "access_remaining": 9,
  "scope": "document",
  "content_summary": {
    "type": "document",
    "title": "blood_test.pdf",
    "patient": "John Doe",
    "record_type": "Laboratory Report"
  }
}
```

## Security Features

### Access Control
- **Token-Based Authentication**: Secure URL-safe tokens for external access
- **Time-Limited Access**: Configurable expiration times (max 7 days)
- **Access Count Limits**: Configurable maximum access attempts
- **IP Address Restrictions**: Optional IP whitelist for additional security
- **Patient Consent Tracking**: Required consent verification with audit trail

### Audit and Compliance
- **Comprehensive Logging**: All share operations logged with full audit trail
- **Access Tracking**: Every access attempt logged with IP, timestamp, and user agent
- **Revocation Logging**: Token revocations logged with reason and timestamp
- **Consent Documentation**: Patient consent status and method tracked

### Data Protection
- **Tenant Isolation**: Share tokens respect multi-tenant boundaries
- **Secure Token Generation**: Cryptographically secure token generation
- **Automatic Expiry**: Tokens automatically expire after configured time
- **Immediate Revocation**: Tokens can be instantly revoked and invalidated

## Error Responses

### Share Token Creation Errors
```json
{
  "error": "Maximum expiry time is 168 hours (7 days)"
}
```

### Access Errors
```json
{
  "error": "Share token has expired"
}
```

```json
{
  "error": "Maximum access count reached"
}
```

```json
{
  "error": "Access denied from IP address: 192.168.1.200"
}
```

### Validation Errors
```json
{
  "valid": false,
  "error": "Token not found"
}
```

## Use Cases

### 1. Referral to Specialist
```bash
# Create share token for specific lab results
POST /api/clinical_records/sharing/create-document-share/
{
  "document_id": "lab-results-uuid",
  "expires_in_hours": 48,
  "max_accesses": 3,
  "patient_consent": true,
  "purpose": "Referral to cardiologist",
  "recipient_info": {
    "name": "Dr. Heart Specialist",
    "organization": "Cardiology Center"
  }
}

# Share the returned URL with the specialist
# Specialist accesses: GET /sharing/access/{token}/?format=json
```

### 2. Patient Data Transfer
```bash
# Create comprehensive patient bundle share
POST /api/clinical_records/sharing/create-patient-bundle-share/
{
  "patient_id": "patient-uuid",
  "expires_in_hours": 72,
  "max_accesses": 5,
  "patient_consent": true,
  "purpose": "Transfer to new primary care provider"
}

# New provider accesses complete medical history
# GET /sharing/access/{token}/?format=fhir
```

### 3. Second Opinion Consultation
```bash
# Share specific clinical record
POST /api/clinical_records/sharing/create-record-share/
{
  "record_id": "clinical-record-uuid",
  "expires_in_hours": 24,
  "max_accesses": 2,
  "allowed_ips": ["specialist-clinic-ip"],
  "patient_consent": true,
  "purpose": "Second opinion on treatment plan"
}
```

### 4. Emergency Access
```bash
# Create emergency access token
POST /api/clinical_records/sharing/create-patient-bundle-share/
{
  "patient_id": "patient-uuid",
  "expires_in_hours": 6,
  "max_accesses": 10,
  "patient_consent": true,
  "purpose": "Emergency department access"
}

# Emergency staff can access immediately
# GET /sharing/access/{token}/?format=json
```

The secure sharing system provides healthcare providers with a compliant, auditable way to share patient data externally while maintaining strict access controls and comprehensive audit trails.