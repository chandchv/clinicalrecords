/**
 * Document Upload Interface JavaScript
 * 
 * Handles drag-and-drop uploads, progress tracking, camera capture,
 * and upload queue management.
 */

class DocumentUploader {
    constructor() {
        this.config = this.loadConfig();
        this.uploadQueue = new Map();
        this.activeUploads = 0;
        this.stats = {
            total: 0,
            successful: 0,
            failed: 0,
            processing: 0
        };
        
        this.init();
    }
    
    loadConfig() {
        const configElement = document.getElementById('upload-config');
        if (configElement) {
            return JSON.parse(configElement.textContent);
        }
        return {};
    }
    
    init() {
        this.setupDropZone();
        this.setupFileInput();
        this.setupCameraCapture();
        this.setupQueueControls();
        this.setupEventListeners();
        this.loadExistingUploads();
    }
    
    setupDropZone() {
        const dropZone = document.getElementById('drop-zone');
        if (!dropZone) return;
        
        // Prevent default drag behaviors
        ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
            dropZone.addEventListener(eventName, this.preventDefaults, false);
            document.body.addEventListener(eventName, this.preventDefaults, false);
        });
        
        // Highlight drop zone when item is dragged over it
        ['dragenter', 'dragover'].forEach(eventName => {
            dropZone.addEventListener(eventName, () => {
                dropZone.classList.add('drag-over');
            }, false);
        });
        
        ['dragleave', 'drop'].forEach(eventName => {
            dropZone.addEventListener(eventName, () => {
                dropZone.classList.remove('drag-over');
            }, false);
        });
        
        // Handle dropped files
        dropZone.addEventListener('drop', (e) => {
            const files = e.dataTransfer.files;
            this.handleFiles(files);
        }, false);
        
        // Handle click to browse
        dropZone.addEventListener('click', () => {
            document.getElementById('file-input').click();
        });
    }
    
    setupFileInput() {
        const fileInput = document.getElementById('file-input');
        const browseButton = document.getElementById('browse-files');
        
        if (fileInput) {
            fileInput.addEventListener('change', (e) => {
                this.handleFiles(e.target.files);
                e.target.value = ''; // Reset input
            });
        }
        
        if (browseButton) {
            browseButton.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                fileInput.click();
            });
        }
    }
    
    setupCameraCapture() {
        const cameraButton = document.getElementById('camera-capture');
        const cameraModal = document.getElementById('camera-modal');
        const closeCamera = document.getElementById('close-camera');
        const capturePhoto = document.getElementById('capture-photo');
        const retakePhoto = document.getElementById('retake-photo');
        const uploadPhoto = document.getElementById('upload-photo');
        
        if (!cameraButton || !cameraModal) return;
        
        let stream = null;
        let capturedImageData = null;
        
        cameraButton.addEventListener('click', async () => {
            try {
                stream = await navigator.mediaDevices.getUserMedia({
                    video: { facingMode: 'environment' } // Prefer back camera
                });
                
                const video = document.getElementById('camera-video');
                video.srcObject = stream;
                cameraModal.style.display = 'flex';
                
            } catch (error) {
                this.showError('Camera access denied or not available');
            }
        });
        
        closeCamera.addEventListener('click', () => {
            this.stopCamera(stream);
            cameraModal.style.display = 'none';
        });
        
        capturePhoto.addEventListener('click', () => {
            const video = document.getElementById('camera-video');
            const canvas = document.getElementById('camera-canvas');
            const context = canvas.getContext('2d');
            
            canvas.width = video.videoWidth;
            canvas.height = video.videoHeight;
            context.drawImage(video, 0, 0);
            
            capturedImageData = canvas.toDataURL('image/jpeg', 0.8);
            
            // Show preview
            const previewImage = document.getElementById('preview-image');
            previewImage.src = capturedImageData;
            
            document.querySelector('.camera-container').style.display = 'none';
            document.querySelector('.camera-controls').style.display = 'none';
            document.getElementById('captured-preview').style.display = 'block';
        });
        
        retakePhoto.addEventListener('click', () => {
            document.querySelector('.camera-container').style.display = 'block';
            document.querySelector('.camera-controls').style.display = 'flex';
            document.getElementById('captured-preview').style.display = 'none';
            capturedImageData = null;
        });
        
        uploadPhoto.addEventListener('click', () => {
            if (capturedImageData) {
                this.uploadCameraCapture(capturedImageData);
                this.stopCamera(stream);
                cameraModal.style.display = 'none';
            }
        });
    }
    
    setupQueueControls() {
        const clearCompleted = document.getElementById('clear-completed');
        const cancelAll = document.getElementById('cancel-all');
        
        if (clearCompleted) {
            clearCompleted.addEventListener('click', () => {
                this.clearCompletedUploads();
            });
        }
        
        if (cancelAll) {
            cancelAll.addEventListener('click', () => {
                this.cancelAllUploads();
            });
        }
    }
    
    setupEventListeners() {
        // Close modals when clicking outside
        document.addEventListener('click', (e) => {
            if (e.target.classList.contains('modal')) {
                e.target.style.display = 'none';
            }
        });
        
        // Close error modal
        const closeError = document.getElementById('close-error');
        const closeErrorBtn = document.getElementById('close-error-btn');
        
        if (closeError) {
            closeError.addEventListener('click', () => {
                document.getElementById('error-modal').style.display = 'none';
            });
        }
        
        if (closeErrorBtn) {
            closeErrorBtn.addEventListener('click', () => {
                document.getElementById('error-modal').style.display = 'none';
            });
        }
    }
    
    preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }
    
    async handleFiles(files) {
        if (!files || files.length === 0) return;
        
        if (!this.config.recordId) {
            this.showError('No clinical record selected for upload');
            return;
        }
        
        const fileArray = Array.from(files);
        
        // Validate files
        for (const file of fileArray) {
            const validation = await this.validateFile(file);
            if (!validation.valid) {
                this.showError(`${file.name}: ${validation.message}`);
                return;
            }
        }
        
        // Add files to queue
        for (const file of fileArray) {
            this.addToQueue(file);
        }
        
        // Start processing queue
        this.processQueue();
    }
    
    async validateFile(file) {
        // Client-side validation
        if (file.size > this.config.maxFileSize) {
            return {
                valid: false,
                message: `File size (${this.formatFileSize(file.size)}) exceeds maximum allowed size (${this.formatFileSize(this.config.maxFileSize)})`
            };
        }
        
        const extension = '.' + file.name.split('.').pop().toLowerCase();
        if (!this.config.allowedExtensions.includes(extension)) {
            return {
                valid: false,
                message: `File type '${extension}' is not allowed`
            };
        }
        
        // Server-side validation
        try {
            const formData = new FormData();
            formData.append('filename', file.name);
            formData.append('size', file.size);
            
            const response = await fetch('/api/clinical-records/upload/validate/', {
                method: 'POST',
                headers: {
                    'X-CSRFToken': this.config.csrfToken
                },
                body: formData
            });
            
            const result = await response.json();
            return result;
            
        } catch (error) {
            console.warn('Server validation failed, using client-side only');
            return { valid: true, message: 'Validation passed' };
        }
    }
    
    addToQueue(file) {
        const uploadId = this.generateUploadId();
        const uploadItem = {
            id: uploadId,
            file: file,
            status: 'pending',
            progress: 0,
            error: null,
            documentId: null,
            startTime: null,
            endTime: null
        };
        
        this.uploadQueue.set(uploadId, uploadItem);
        this.renderQueueItem(uploadItem);
        this.updateStats();
        this.showQueue();
    }
    
    renderQueueItem(uploadItem) {
        const template = document.getElementById('upload-item-template');
        const queueList = document.getElementById('queue-list');
        
        if (!template || !queueList) return;
        
        const clone = template.content.cloneNode(true);
        const itemElement = clone.querySelector('.upload-item');
        
        itemElement.setAttribute('data-upload-id', uploadItem.id);
        
        // Set file details
        clone.querySelector('.file-name').textContent = uploadItem.file.name;
        clone.querySelector('.file-size').textContent = this.formatFileSize(uploadItem.file.size);
        clone.querySelector('.file-status').textContent = uploadItem.status;
        clone.querySelector('.file-status').className = `file-status ${uploadItem.status}`;
        
        // Set file icon
        const fileIcon = clone.querySelector('.file-icon i');
        fileIcon.className = `icon-file ${this.getFileTypeClass(uploadItem.file.name)}`;
        
        // Setup action buttons
        const cancelBtn = clone.querySelector('.btn-cancel');
        const retryBtn = clone.querySelector('.btn-retry');
        const removeBtn = clone.querySelector('.btn-remove');
        
        cancelBtn.addEventListener('click', () => {
            this.cancelUpload(uploadItem.id);
        });
        
        retryBtn.addEventListener('click', () => {
            this.retryUpload(uploadItem.id);
        });
        
        removeBtn.addEventListener('click', () => {
            this.removeFromQueue(uploadItem.id);
        });
        
        queueList.appendChild(clone);
    }
    
    async processQueue() {
        if (this.activeUploads >= this.config.maxConcurrentUploads) {
            return;
        }
        
        const pendingUploads = Array.from(this.uploadQueue.values())
            .filter(item => item.status === 'pending')
            .slice(0, this.config.maxConcurrentUploads - this.activeUploads);
        
        for (const uploadItem of pendingUploads) {
            this.uploadFile(uploadItem);
        }
    }
    
    async uploadFile(uploadItem) {
        this.activeUploads++;
        uploadItem.status = 'uploading';
        uploadItem.startTime = Date.now();
        
        this.updateQueueItem(uploadItem);
        
        try {
            const formData = new FormData();
            formData.append('file', uploadItem.file);
            formData.append('record_id', this.config.recordId);
            formData.append('metadata', JSON.stringify({
                upload_source: 'web_interface',
                upload_timestamp: new Date().toISOString()
            }));
            
            const xhr = new XMLHttpRequest();
            
            // Track upload progress
            xhr.upload.addEventListener('progress', (e) => {
                if (e.lengthComputable) {
                    const progress = Math.round((e.loaded / e.total) * 100);
                    uploadItem.progress = progress;
                    this.updateQueueItem(uploadItem);
                }
            });
            
            // Handle completion
            xhr.addEventListener('load', () => {
                this.activeUploads--;
                uploadItem.endTime = Date.now();
                
                if (xhr.status === 201) {
                    const response = JSON.parse(xhr.responseText);
                    uploadItem.status = 'completed';
                    uploadItem.documentId = response.document_id;
                    this.stats.successful++;
                    
                    if (response.processing_queued) {
                        uploadItem.status = 'processing';
                        this.stats.processing++;
                        this.monitorProcessing(uploadItem);
                    }
                } else {
                    const error = JSON.parse(xhr.responseText);
                    uploadItem.status = 'failed';
                    uploadItem.error = error.error || 'Upload failed';
                    this.stats.failed++;
                }
                
                this.updateQueueItem(uploadItem);
                this.updateStats();
                this.processQueue(); // Process next in queue
            });
            
            // Handle errors
            xhr.addEventListener('error', () => {
                this.activeUploads--;
                uploadItem.status = 'failed';
                uploadItem.error = 'Network error';
                uploadItem.endTime = Date.now();
                this.stats.failed++;
                
                this.updateQueueItem(uploadItem);
                this.updateStats();
                this.processQueue();
            });
            
            xhr.open('POST', '/api/clinical-records/upload/');
            xhr.setRequestHeader('X-CSRFToken', this.config.csrfToken);
            xhr.send(formData);
            
        } catch (error) {
            this.activeUploads--;
            uploadItem.status = 'failed';
            uploadItem.error = error.message;
            uploadItem.endTime = Date.now();
            this.stats.failed++;
            
            this.updateQueueItem(uploadItem);
            this.updateStats();
            this.processQueue();
        }
    }    
async monitorProcessing(uploadItem) {
        if (!uploadItem.documentId) return;
        
        const checkProgress = async () => {
            try {
                const response = await fetch(`/api/clinical-records/upload/progress/${uploadItem.documentId}/`);
                const progress = await response.json();
                
                if (progress.processing_status === 'completed') {
                    uploadItem.status = 'completed';
                    this.stats.processing--;
                    this.stats.successful++;
                    this.updateQueueItem(uploadItem);
                    this.updateStats();
                } else if (progress.processing_status === 'failed') {
                    uploadItem.status = 'failed';
                    uploadItem.error = progress.error || 'Processing failed';
                    this.stats.processing--;
                    this.stats.failed++;
                    this.updateQueueItem(uploadItem);
                    this.updateStats();
                } else {
                    // Still processing, check again in 5 seconds
                    setTimeout(checkProgress, 5000);
                }
            } catch (error) {
                console.error('Error checking processing progress:', error);
                // Retry in 10 seconds
                setTimeout(checkProgress, 10000);
            }
        };
        
        // Start monitoring after 2 seconds
        setTimeout(checkProgress, 2000);
    }
    
    updateQueueItem(uploadItem) {
        const itemElement = document.querySelector(`[data-upload-id="${uploadItem.id}"]`);
        if (!itemElement) return;
        
        // Update status
        const statusElement = itemElement.querySelector('.file-status');
        statusElement.textContent = uploadItem.status;
        statusElement.className = `file-status ${uploadItem.status}`;
        
        // Update progress
        const progressFill = itemElement.querySelector('.progress-fill');
        const progressText = itemElement.querySelector('.progress-text');
        
        if (uploadItem.status === 'uploading') {
            progressFill.style.width = `${uploadItem.progress}%`;
            progressText.textContent = `${uploadItem.progress}%`;
        } else if (uploadItem.status === 'completed') {
            progressFill.style.width = '100%';
            progressFill.classList.add('completed');
            progressText.textContent = '100%';
        } else if (uploadItem.status === 'failed') {
            progressFill.classList.add('failed');
            progressText.textContent = 'Failed';
        } else if (uploadItem.status === 'processing') {
            progressFill.style.width = '100%';
            progressText.textContent = 'Processing...';
        }
        
        // Update action buttons
        const cancelBtn = itemElement.querySelector('.btn-cancel');
        const retryBtn = itemElement.querySelector('.btn-retry');
        const removeBtn = itemElement.querySelector('.btn-remove');
        
        if (uploadItem.status === 'uploading' || uploadItem.status === 'pending') {
            cancelBtn.style.display = 'block';
            retryBtn.style.display = 'none';
            removeBtn.style.display = 'none';
        } else if (uploadItem.status === 'failed') {
            cancelBtn.style.display = 'none';
            retryBtn.style.display = 'block';
            removeBtn.style.display = 'block';
        } else {
            cancelBtn.style.display = 'none';
            retryBtn.style.display = 'none';
            removeBtn.style.display = 'block';
        }
        
        // Show error if present
        if (uploadItem.error) {
            statusElement.title = uploadItem.error;
        }
    }
    
    async uploadCameraCapture(imageData) {
        if (!this.config.recordId) {
            this.showError('No clinical record selected for upload');
            return;
        }
        
        try {
            const response = await fetch('/api/clinical-records/upload/camera/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.config.csrfToken
                },
                body: JSON.stringify({
                    record_id: this.config.recordId,
                    image_data: imageData,
                    capture_metadata: JSON.stringify({
                        capture_source: 'web_camera',
                        capture_timestamp: new Date().toISOString(),
                        user_agent: navigator.userAgent
                    })
                })
            });
            
            const result = await response.json();
            
            if (response.ok) {
                // Add to queue for monitoring
                const uploadItem = {
                    id: this.generateUploadId(),
                    file: { name: 'Camera Capture.jpg', size: 0 },
                    status: result.processing_queued ? 'processing' : 'completed',
                    progress: 100,
                    error: null,
                    documentId: result.document_id,
                    startTime: Date.now(),
                    endTime: Date.now()
                };
                
                this.uploadQueue.set(uploadItem.id, uploadItem);
                this.renderQueueItem(uploadItem);
                
                if (result.processing_queued) {
                    this.stats.processing++;
                    this.monitorProcessing(uploadItem);
                } else {
                    this.stats.successful++;
                }
                
                this.stats.total++;
                this.updateStats();
                this.showQueue();
                
            } else {
                this.showError(result.error || 'Camera capture upload failed');
            }
            
        } catch (error) {
            this.showError('Failed to upload camera capture');
        }
    }
    
    cancelUpload(uploadId) {
        const uploadItem = this.uploadQueue.get(uploadId);
        if (!uploadItem) return;
        
        if (uploadItem.status === 'uploading') {
            // Cancel ongoing upload (would need to store xhr reference)
            uploadItem.status = 'cancelled';
            this.activeUploads--;
        } else if (uploadItem.documentId) {
            // Cancel server-side processing
            this.cancelServerUpload(uploadItem.documentId);
        }
        
        this.removeFromQueue(uploadId);
        this.processQueue();
    }
    
    async cancelServerUpload(documentId) {
        try {
            await fetch(`/api/clinical-records/upload/cancel/${documentId}/`, {
                method: 'DELETE',
                headers: {
                    'X-CSRFToken': this.config.csrfToken
                }
            });
        } catch (error) {
            console.error('Failed to cancel server upload:', error);
        }
    }
    
    retryUpload(uploadId) {
        const uploadItem = this.uploadQueue.get(uploadId);
        if (!uploadItem) return;
        
        uploadItem.status = 'pending';
        uploadItem.progress = 0;
        uploadItem.error = null;
        uploadItem.documentId = null;
        
        this.updateQueueItem(uploadItem);
        this.processQueue();
    }
    
    removeFromQueue(uploadId) {
        const uploadItem = this.uploadQueue.get(uploadId);
        if (!uploadItem) return;
        
        // Update stats
        if (uploadItem.status === 'completed') {
            this.stats.successful--;
        } else if (uploadItem.status === 'failed') {
            this.stats.failed--;
        } else if (uploadItem.status === 'processing') {
            this.stats.processing--;
        }
        this.stats.total--;
        
        // Remove from DOM
        const itemElement = document.querySelector(`[data-upload-id="${uploadId}"]`);
        if (itemElement) {
            itemElement.remove();
        }
        
        // Remove from queue
        this.uploadQueue.delete(uploadId);
        
        this.updateStats();
        
        // Hide queue if empty
        if (this.uploadQueue.size === 0) {
            this.hideQueue();
        }
    }
    
    clearCompletedUploads() {
        const completedIds = Array.from(this.uploadQueue.entries())
            .filter(([id, item]) => item.status === 'completed')
            .map(([id, item]) => id);
        
        completedIds.forEach(id => this.removeFromQueue(id));
    }
    
    cancelAllUploads() {
        const uploadIds = Array.from(this.uploadQueue.keys());
        uploadIds.forEach(id => this.cancelUpload(id));
    }
    
    loadExistingUploads() {
        // Load recent uploads from server
        if (!this.config.recordId) return;
        
        fetch(`/api/clinical-records/upload/queue-status/?record_id=${this.config.recordId}`)
            .then(response => response.json())
            .then(data => {
                if (data.recent_uploads > 0) {
                    this.showStats();
                    // Could load and display recent uploads here
                }
            })
            .catch(error => {
                console.error('Failed to load existing uploads:', error);
            });
    }
    
    updateStats() {
        const totalElement = document.getElementById('total-uploads');
        const successfulElement = document.getElementById('successful-uploads');
        const failedElement = document.getElementById('failed-uploads');
        const processingElement = document.getElementById('processing-uploads');
        
        if (totalElement) totalElement.textContent = this.stats.total;
        if (successfulElement) successfulElement.textContent = this.stats.successful;
        if (failedElement) failedElement.textContent = this.stats.failed;
        if (processingElement) processingElement.textContent = this.stats.processing;
        
        if (this.stats.total > 0) {
            this.showStats();
        }
    }
    
    showQueue() {
        const queueElement = document.getElementById('upload-queue');
        if (queueElement) {
            queueElement.style.display = 'block';
            queueElement.classList.add('fade-in');
        }
    }
    
    hideQueue() {
        const queueElement = document.getElementById('upload-queue');
        if (queueElement) {
            queueElement.style.display = 'none';
        }
    }
    
    showStats() {
        const statsElement = document.getElementById('upload-stats');
        if (statsElement) {
            statsElement.style.display = 'block';
            statsElement.classList.add('fade-in');
        }
    }
    
    showError(message, details = null) {
        const errorModal = document.getElementById('error-modal');
        const errorMessage = document.getElementById('error-message');
        const errorDetails = document.getElementById('error-details');
        
        if (errorModal && errorMessage) {
            errorMessage.textContent = message;
            
            if (details && errorDetails) {
                errorDetails.textContent = details;
                errorDetails.style.display = 'block';
            } else if (errorDetails) {
                errorDetails.style.display = 'none';
            }
            
            errorModal.style.display = 'flex';
        } else {
            // Fallback to alert
            alert(message);
        }
    }
    
    stopCamera(stream) {
        if (stream) {
            stream.getTracks().forEach(track => track.stop());
        }
        
        // Reset camera UI
        document.querySelector('.camera-container').style.display = 'block';
        document.querySelector('.camera-controls').style.display = 'flex';
        document.getElementById('captured-preview').style.display = 'none';
    }
    
    generateUploadId() {
        return 'upload_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
    }
    
    formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }
    
    getFileTypeClass(filename) {
        const extension = filename.split('.').pop().toLowerCase();
        
        if (['pdf'].includes(extension)) return 'pdf';
        if (['jpg', 'jpeg', 'png', 'gif', 'bmp', 'tiff', 'tif'].includes(extension)) return 'image';
        if (['dcm', 'dicom'].includes(extension)) return 'dicom';
        if (['doc', 'docx', 'txt', 'rtf'].includes(extension)) return 'document';
        
        return 'default';
    }
}

// Initialize uploader when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    if (document.getElementById('upload-area')) {
        window.documentUploader = new DocumentUploader();
    }
});

// Handle mobile device detection
if (/Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent)) {
    document.body.classList.add('mobile-device');
    
    // Show camera button on mobile
    const cameraSection = document.querySelector('.mobile-camera-section');
    if (cameraSection) {
        cameraSection.style.display = 'block';
    }
}

// Handle page visibility changes to pause/resume monitoring
document.addEventListener('visibilitychange', () => {
    if (window.documentUploader) {
        if (document.hidden) {
            // Page is hidden, could pause monitoring
        } else {
            // Page is visible, resume monitoring
        }
    }
});

// Handle beforeunload to warn about ongoing uploads
window.addEventListener('beforeunload', (e) => {
    if (window.documentUploader && window.documentUploader.activeUploads > 0) {
        e.preventDefault();
        e.returnValue = 'You have uploads in progress. Are you sure you want to leave?';
        return e.returnValue;
    }
});