/**
 * Document Viewer JavaScript
 * 
 * Handles document viewing, metadata display, OCR overlay,
 * annotations, search, and viewer controls.
 */

class DocumentViewer {
    constructor() {
        this.config = this.loadConfig();
        this.currentZoom = 100;
        this.currentRotation = 0;
        this.searchResults = [];
        this.currentSearchIndex = 0;
        this.annotations = [];
        this.ocrOverlayVisible = false;
        
        this.init();
    }
    
    loadConfig() {
        const configElement = document.getElementById('viewer-config');
        if (configElement) {
            return JSON.parse(configElement.textContent);
        }
        return {};
    }
    
    init() {
        this.setupEventListeners();
        this.loadDocument();
        this.loadOCRText();
        this.setupKeyboardShortcuts();
        this.initializeViewer();
    }
    
    setupEventListeners() {
        // Zoom controls
        const zoomIn = document.getElementById('zoom-in');
        const zoomOut = document.getElementById('zoom-out');
        const zoomSelect = document.getElementById('zoom-select');
        
        if (zoomIn) zoomIn.addEventListener('click', () => this.zoomIn());
        if (zoomOut) zoomOut.addEventListener('click', () => this.zoomOut());
        if (zoomSelect) zoomSelect.addEventListener('change', (e) => this.setZoom(e.target.value));
        
        // Rotation controls
        const rotateLeft = document.getElementById('rotate-left');
        const rotateRight = document.getElementById('rotate-right');
        
        if (rotateLeft) rotateLeft.addEventListener('click', () => this.rotateLeft());
        if (rotateRight) rotateRight.addEventListener('click', () => this.rotateRight());
        
        // View controls
        const searchToggle = document.getElementById('search-toggle');
        const sidebarToggle = document.getElementById('sidebar-toggle');
        const fullscreenToggle = document.getElementById('fullscreen-toggle');
        
        if (searchToggle) searchToggle.addEventListener('click', () => this.toggleSearch());
        if (sidebarToggle) sidebarToggle.addEventListener('click', () => this.toggleSidebar());
        if (fullscreenToggle) fullscreenToggle.addEventListener('click', () => this.toggleFullscreen());
        
        // Action controls
        const downloadBtn = document.getElementById('download-btn');
        const printBtn = document.getElementById('print-btn');
        
        if (downloadBtn) downloadBtn.addEventListener('click', () => this.downloadDocument());
        if (printBtn) printBtn.addEventListener('click', () => this.printDocument());
        
        // Search controls
        const searchInput = document.getElementById('search-input');
        const searchPrev = document.getElementById('search-prev');
        const searchNext = document.getElementById('search-next');
        const searchClose = document.getElementById('search-close');
        
        if (searchInput) {
            searchInput.addEventListener('input', (e) => this.performSearch(e.target.value));
            searchInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') {
                    e.shiftKey ? this.searchPrevious() : this.searchNext();
                } else if (e.key === 'Escape') {
                    this.closeSearch();
                }
            });
        }
        
        if (searchPrev) searchPrev.addEventListener('click', () => this.searchPrevious());
        if (searchNext) searchNext.addEventListener('click', () => this.searchNext());
        if (searchClose) searchClose.addEventListener('click', () => this.closeSearch());
        
        // Sidebar controls
        const sidebarClose = document.getElementById('sidebar-close');
        if (sidebarClose) sidebarClose.addEventListener('click', () => this.closeSidebar());
        
        // OCR controls
        const toggleOcrOverlay = document.getElementById('toggle-ocr-overlay');
        const copyOcrText = document.getElementById('copy-ocr-text');
        
        if (toggleOcrOverlay) toggleOcrOverlay.addEventListener('click', () => this.toggleOCROverlay());
        if (copyOcrText) copyOcrText.addEventListener('click', () => this.copyOCRText());
        
        // Error handling
        const retryLoad = document.getElementById('retry-load');
        if (retryLoad) retryLoad.addEventListener('click', () => this.loadDocument());
        
        // Modal controls
        this.setupModalControls();
        
        // Window resize
        window.addEventListener('resize', () => this.handleResize());
        
        // Fullscreen change
        document.addEventListener('fullscreenchange', () => this.handleFullscreenChange());
    }
    
    setupModalControls() {
        // Error modal
        const closeError = document.getElementById('close-error');
        const closeErrorBtn = document.getElementById('close-error-btn');
        
        if (closeError) closeError.addEventListener('click', () => this.closeErrorModal());
        if (closeErrorBtn) closeErrorBtn.addEventListener('click', () => this.closeErrorModal());
        
        // Annotation modal
        const closeAnnotation = document.getElementById('close-annotation');
        const cancelAnnotation = document.getElementById('cancel-annotation');
        const saveAnnotation = document.getElementById('save-annotation');
        
        if (closeAnnotation) closeAnnotation.addEventListener('click', () => this.closeAnnotationModal());
        if (cancelAnnotation) cancelAnnotation.addEventListener('click', () => this.closeAnnotationModal());
        if (saveAnnotation) saveAnnotation.addEventListener('click', () => this.saveAnnotation());
        
        // Close modals when clicking outside
        document.addEventListener('click', (e) => {
            if (e.target.classList.contains('modal')) {
                e.target.style.display = 'none';
            }
        });
    }
    
    setupKeyboardShortcuts() {
        document.addEventListener('keydown', (e) => {
            if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') {
                return; // Don't handle shortcuts when typing in inputs
            }
            
            if (e.ctrlKey || e.metaKey) {
                switch (e.key) {
                    case '=':
                    case '+':
                        e.preventDefault();
                        this.zoomIn();
                        break;
                    case '-':
                        e.preventDefault();
                        this.zoomOut();
                        break;
                    case '0':
                        e.preventDefault();
                        this.setZoom('fit_width');
                        break;
                    case '1':
                        e.preventDefault();
                        this.setZoom('fit_page');
                        break;
                    case 'l':
                        e.preventDefault();
                        this.rotateLeft();
                        break;
                    case 'r':
                        e.preventDefault();
                        this.rotateRight();
                        break;
                    case 's':
                        e.preventDefault();
                        this.toggleSidebar();
                        break;
                    case 'f':
                        e.preventDefault();
                        this.toggleSearch();
                        break;
                }
            } else if (e.key === 'F11') {
                e.preventDefault();
                this.toggleFullscreen();
            } else if (e.key === 'Escape') {
                if (document.fullscreenElement) {
                    this.exitFullscreen();
                } else if (this.isSearchVisible()) {
                    this.closeSearch();
                }
            }
        });
    }
    
    initializeViewer() {
        // Set initial zoom
        const zoomSelect = document.getElementById('zoom-select');
        if (zoomSelect && this.config.viewer_config) {
            const defaultZoom = this.config.viewer_config.default_zoom || 'fit_width';
            zoomSelect.value = defaultZoom;
            this.setZoom(defaultZoom);
        }
        
        // Initialize sidebar state
        if (this.config.viewer_config && !this.config.viewer_config.sidebar_enabled) {
            this.closeSidebar();
        }
    }
    
    async loadDocument() {
        const loadingIndicator = document.getElementById('loading-indicator');
        const errorDisplay = document.getElementById('error-display');
        const viewerContent = document.getElementById('document-viewer-content');
        
        if (loadingIndicator) loadingIndicator.style.display = 'flex';
        if (errorDisplay) errorDisplay.style.display = 'none';
        if (viewerContent) viewerContent.innerHTML = '';
        
        try {
            if (!this.config.document_id) {
                throw new Error('No document ID provided');
            }
            
            // Load document based on format
            const format = this.config.viewer_config?.format || 'pdf';
            
            switch (format) {
                case 'pdf':
                    await this.loadPDFDocument();
                    break;
                case 'image':
                    await this.loadImageDocument();
                    break;
                case 'dicom':
                    await this.loadDICOMDocument();
                    break;
                case 'text':
                    await this.loadTextDocument();
                    break;
                default:
                    await this.loadPDFDocument(); // Fallback
            }
            
            if (loadingIndicator) loadingIndicator.style.display = 'none';
            
        } catch (error) {
            console.error('Error loading document:', error);
            this.showError(error.message);
            
            if (loadingIndicator) loadingIndicator.style.display = 'none';
            if (errorDisplay) {
                errorDisplay.style.display = 'flex';
                const errorMessage = document.getElementById('error-message');
                if (errorMessage) {
                    errorMessage.textContent = error.message;
                }
            }
        }
    }
    
    async loadPDFDocument() {
        if (!window.pdfjsLib) {
            throw new Error('PDF.js library not loaded');
        }
        
        const downloadUrl = this.config.download_url;
        if (!downloadUrl) {
            throw new Error('No download URL available');
        }
        
        // Configure PDF.js worker
        if (this.config.viewer_config?.pdf_js_config?.worker_src) {
            window.pdfjsLib.GlobalWorkerOptions.workerSrc = this.config.viewer_config.pdf_js_config.worker_src;
        }
        
        const loadingTask = window.pdfjsLib.getDocument(downloadUrl);
        const pdf = await loadingTask.promise;
        
        const viewerContent = document.getElementById('document-viewer-content');
        const pdfViewer = document.createElement('div');
        pdfViewer.className = 'pdf-viewer';
        
        // Render first page (could be enhanced to render all pages)
        const page = await pdf.getPage(1);
        const scale = this.calculateScale(page);
        const viewport = page.getViewport({ scale });
        
        const canvas = document.createElement('canvas');
        canvas.className = 'pdf-page';
        const context = canvas.getContext('2d');
        canvas.height = viewport.height;
        canvas.width = viewport.width;
        
        const renderContext = {
            canvasContext: context,
            viewport: viewport
        };
        
        await page.render(renderContext).promise;
        
        pdfViewer.appendChild(canvas);
        viewerContent.appendChild(pdfViewer);
        
        // Store references for zoom/rotation
        this.pdfDocument = pdf;
        this.pdfPage = page;
        this.pdfCanvas = canvas;
    }
    
    async loadImageDocument() {
        const downloadUrl = this.config.download_url;
        if (!downloadUrl) {
            throw new Error('No download URL available');
        }
        
        const viewerContent = document.getElementById('document-viewer-content');
        const imageViewer = document.createElement('div');
        imageViewer.className = 'image-viewer';
        
        const img = document.createElement('img');
        img.src = downloadUrl;
        img.alt = this.config.filename;
        
        img.onload = () => {
            this.applyImageTransforms(img);
        };
        
        img.onerror = () => {
            throw new Error('Failed to load image');
        };
        
        imageViewer.appendChild(img);
        viewerContent.appendChild(imageViewer);
        
        // Store reference for transforms
        this.imageElement = img;
    }
    
    async loadDICOMDocument() {
        if (!window.cornerstone) {
            throw new Error('Cornerstone DICOM library not loaded');
        }
        
        const downloadUrl = this.config.download_url;
        if (!downloadUrl) {
            throw new Error('No download URL available');
        }
        
        const viewerContent = document.getElementById('document-viewer-content');
        const dicomViewer = document.createElement('div');
        dicomViewer.className = 'dicom-viewer';
        
        const canvas = document.createElement('canvas');
        canvas.className = 'dicom-canvas';
        canvas.width = 512;
        canvas.height = 512;
        
        dicomViewer.appendChild(canvas);
        viewerContent.appendChild(dicomViewer);
        
        // Initialize Cornerstone
        window.cornerstone.enable(canvas);
        
        // Load DICOM image
        const imageId = `wadouri:${downloadUrl}`;
        const image = await window.cornerstone.loadImage(imageId);
        
        // Display image
        window.cornerstone.displayImage(canvas, image);
        
        // Store reference
        this.dicomCanvas = canvas;
        this.dicomImage = image;
    }
    
    async loadTextDocument() {
        const downloadUrl = this.config.download_url;
        if (!downloadUrl) {
            throw new Error('No download URL available');
        }
        
        const response = await fetch(downloadUrl);
        if (!response.ok) {
            throw new Error('Failed to load text document');
        }
        
        const text = await response.text();
        
        const viewerContent = document.getElementById('document-viewer-content');
        const textViewer = document.createElement('div');
        textViewer.className = 'text-viewer';
        textViewer.textContent = text;
        
        viewerContent.appendChild(textViewer);
        
        // Store reference
        this.textElement = textViewer;
    }
    
    async loadOCRText() {
        if (!this.config.ocr_data) return;
        
        const ocrTextDisplay = document.getElementById('ocr-text-display');
        if (ocrTextDisplay && this.config.ocr_data.text) {
            ocrTextDisplay.textContent = this.config.ocr_data.text;
        }
    }
    
    calculateScale(page) {
        const container = document.getElementById('document-container');
        if (!container) return 1.0;
        
        const containerWidth = container.clientWidth - 40; // Account for padding
        const containerHeight = container.clientHeight - 40;
        
        const viewport = page.getViewport({ scale: 1.0 });
        const scaleX = containerWidth / viewport.width;
        const scaleY = containerHeight / viewport.height;
        
        // Use fit_width as default
        return Math.min(scaleX, 2.0); // Cap at 200%
    }
    
    zoomIn() {
        const currentZoom = this.getCurrentZoom();
        const newZoom = Math.min(currentZoom + 25, 500);
        this.setZoom(newZoom);
    }
    
    zoomOut() {
        const currentZoom = this.getCurrentZoom();
        const newZoom = Math.max(currentZoom - 25, 10);
        this.setZoom(newZoom);
    }
    
    setZoom(zoom) {
        const zoomSelect = document.getElementById('zoom-select');
        
        if (typeof zoom === 'string') {
            if (zoom === 'fit_width' || zoom === 'fit_page') {
                this.applyFitZoom(zoom);
                if (zoomSelect) zoomSelect.value = zoom;
                return;
            }
            zoom = parseInt(zoom);
        }
        
        this.currentZoom = zoom;
        this.applyZoom(zoom / 100);
        
        if (zoomSelect) {
            // Update select or add custom value
            const option = Array.from(zoomSelect.options).find(opt => opt.value === zoom.toString());
            if (option) {
                zoomSelect.value = zoom.toString();
            } else {
                zoomSelect.value = 'custom';
            }
        }
    }
    
    getCurrentZoom() {
        return this.currentZoom;
    }
    
    applyFitZoom(fitType) {
        const container = document.getElementById('document-container');
        if (!container) return;
        
        // Implementation depends on document type
        if (this.pdfCanvas) {
            this.applyPDFFitZoom(fitType);
        } else if (this.imageElement) {
            this.applyImageFitZoom(fitType);
        }
    }
    
    applyPDFFitZoom(fitType) {
        if (!this.pdfPage || !this.pdfCanvas) return;
        
        const container = document.getElementById('document-container');
        const containerWidth = container.clientWidth - 40;
        const containerHeight = container.clientHeight - 40;
        
        const viewport = this.pdfPage.getViewport({ scale: 1.0 });
        
        let scale;
        if (fitType === 'fit_width') {
            scale = containerWidth / viewport.width;
        } else { // fit_page
            const scaleX = containerWidth / viewport.width;
            const scaleY = containerHeight / viewport.height;
            scale = Math.min(scaleX, scaleY);
        }
        
        this.applyZoom(scale);
        this.currentZoom = Math.round(scale * 100);
    }
    
    applyImageFitZoom(fitType) {
        if (!this.imageElement) return;
        
        const container = document.getElementById('document-container');
        const containerWidth = container.clientWidth - 40;
        const containerHeight = container.clientHeight - 40;
        
        const naturalWidth = this.imageElement.naturalWidth;
        const naturalHeight = this.imageElement.naturalHeight;
        
        let scale;
        if (fitType === 'fit_width') {
            scale = containerWidth / naturalWidth;
        } else { // fit_page
            const scaleX = containerWidth / naturalWidth;
            const scaleY = containerHeight / naturalHeight;
            scale = Math.min(scaleX, scaleY);
        }
        
        this.applyZoom(scale);
        this.currentZoom = Math.round(scale * 100);
    }
    
    applyZoom(scale) {
        if (this.pdfCanvas) {
            this.applyPDFZoom(scale);
        } else if (this.imageElement) {
            this.applyImageZoom(scale);
        } else if (this.textElement) {
            this.applyTextZoom(scale);
        }
    }
    
    async applyPDFZoom(scale) {
        if (!this.pdfPage || !this.pdfCanvas) return;
        
        const viewport = this.pdfPage.getViewport({ 
            scale: scale,
            rotation: this.currentRotation 
        });
        
        this.pdfCanvas.height = viewport.height;
        this.pdfCanvas.width = viewport.width;
        
        const context = this.pdfCanvas.getContext('2d');
        const renderContext = {
            canvasContext: context,
            viewport: viewport
        };
        
        await this.pdfPage.render(renderContext).promise;
    }
    
    applyImageZoom(scale) {
        if (!this.imageElement) return;
        
        const width = this.imageElement.naturalWidth * scale;
        const height = this.imageElement.naturalHeight * scale;
        
        this.imageElement.style.width = `${width}px`;
        this.imageElement.style.height = `${height}px`;
        this.imageElement.style.transform = `rotate(${this.currentRotation}deg)`;
    }
    
    applyTextZoom(scale) {
        if (!this.textElement) return;
        
        const baseFontSize = 14; // Base font size in pixels
        const newFontSize = baseFontSize * scale;
        this.textElement.style.fontSize = `${newFontSize}px`;
    }
    
    rotateLeft() {
        this.currentRotation = (this.currentRotation - 90) % 360;
        this.applyRotation();
    }
    
    rotateRight() {
        this.currentRotation = (this.currentRotation + 90) % 360;
        this.applyRotation();
    }
    
    applyRotation() {
        if (this.pdfCanvas) {
            // Re-render PDF with new rotation
            this.applyZoom(this.currentZoom / 100);
        } else if (this.imageElement) {
            this.imageElement.style.transform = `rotate(${this.currentRotation}deg)`;
        }
    }
    
    applyImageTransforms(img) {
        const scale = this.currentZoom / 100;
        const width = img.naturalWidth * scale;
        const height = img.naturalHeight * scale;
        
        img.style.width = `${width}px`;
        img.style.height = `${height}px`;
        img.style.transform = `rotate(${this.currentRotation}deg)`;
    }    togg
leSearch() {
        const searchBar = document.getElementById('search-bar');
        if (!searchBar) return;
        
        if (searchBar.style.display === 'none') {
            searchBar.style.display = 'block';
            const searchInput = document.getElementById('search-input');
            if (searchInput) {
                searchInput.focus();
            }
        } else {
            this.closeSearch();
        }
    }
    
    closeSearch() {
        const searchBar = document.getElementById('search-bar');
        if (searchBar) {
            searchBar.style.display = 'none';
        }
        
        // Clear search highlights
        this.clearSearchHighlights();
        this.searchResults = [];
        this.currentSearchIndex = 0;
        this.updateSearchResults();
    }
    
    isSearchVisible() {
        const searchBar = document.getElementById('search-bar');
        return searchBar && searchBar.style.display !== 'none';
    }
    
    async performSearch(query) {
        if (!query.trim()) {
            this.clearSearchHighlights();
            this.searchResults = [];
            this.updateSearchResults();
            return;
        }
        
        try {
            const response = await fetch(
                `/api/clinical-records/documents/${this.config.document_id}/search/?q=${encodeURIComponent(query)}`
            );
            
            if (response.ok) {
                const data = await response.json();
                this.searchResults = data.results || [];
                this.currentSearchIndex = 0;
                this.highlightSearchResults();
                this.updateSearchResults();
                
                if (this.searchResults.length > 0) {
                    this.scrollToSearchResult(0);
                }
            }
        } catch (error) {
            console.error('Search failed:', error);
        }
    }
    
    searchNext() {
        if (this.searchResults.length === 0) return;
        
        this.currentSearchIndex = (this.currentSearchIndex + 1) % this.searchResults.length;
        this.scrollToSearchResult(this.currentSearchIndex);
        this.updateSearchResults();
    }
    
    searchPrevious() {
        if (this.searchResults.length === 0) return;
        
        this.currentSearchIndex = this.currentSearchIndex === 0 
            ? this.searchResults.length - 1 
            : this.currentSearchIndex - 1;
        this.scrollToSearchResult(this.currentSearchIndex);
        this.updateSearchResults();
    }
    
    updateSearchResults() {
        const searchResultsElement = document.getElementById('search-results');
        if (searchResultsElement) {
            if (this.searchResults.length === 0) {
                searchResultsElement.textContent = '0 of 0';
            } else {
                searchResultsElement.textContent = `${this.currentSearchIndex + 1} of ${this.searchResults.length}`;
            }
        }
    }
    
    highlightSearchResults() {
        // Implementation would depend on document type
        // For OCR overlay, this would highlight text regions
        // For PDF, this would use PDF.js text layer
        // For images, this would overlay highlight boxes
    }
    
    clearSearchHighlights() {
        // Remove existing search highlights
        const highlights = document.querySelectorAll('.search-highlight');
        highlights.forEach(highlight => highlight.remove());
    }
    
    scrollToSearchResult(index) {
        if (index < 0 || index >= this.searchResults.length) return;
        
        // Implementation would scroll to the specific search result
        // This would depend on the document type and highlight implementation
    }
    
    toggleSidebar() {
        const sidebar = document.getElementById('metadata-sidebar');
        if (!sidebar) return;
        
        if (window.innerWidth <= 768) {
            // Mobile: slide in/out
            sidebar.classList.toggle('open');
        } else {
            // Desktop: show/hide
            sidebar.style.display = sidebar.style.display === 'none' ? 'flex' : 'none';
        }
    }
    
    closeSidebar() {
        const sidebar = document.getElementById('metadata-sidebar');
        if (!sidebar) return;
        
        if (window.innerWidth <= 768) {
            sidebar.classList.remove('open');
        } else {
            sidebar.style.display = 'none';
        }
    }
    
    toggleFullscreen() {
        if (document.fullscreenElement) {
            this.exitFullscreen();
        } else {
            this.enterFullscreen();
        }
    }
    
    enterFullscreen() {
        const container = document.querySelector('.document-viewer-container');
        if (container && container.requestFullscreen) {
            container.requestFullscreen();
        }
    }
    
    exitFullscreen() {
        if (document.exitFullscreen) {
            document.exitFullscreen();
        }
    }
    
    handleFullscreenChange() {
        const container = document.querySelector('.document-viewer-container');
        if (document.fullscreenElement) {
            container.classList.add('fullscreen');
        } else {
            container.classList.remove('fullscreen');
        }
    }
    
    toggleOCROverlay() {
        this.ocrOverlayVisible = !this.ocrOverlayVisible;
        
        if (this.ocrOverlayVisible) {
            this.showOCROverlay();
        } else {
            this.hideOCROverlay();
        }
    }
    
    showOCROverlay() {
        // Implementation would overlay OCR text regions on the document
        // This would require OCR word/region coordinates
        console.log('OCR overlay shown');
    }
    
    hideOCROverlay() {
        // Remove OCR overlay
        const overlays = document.querySelectorAll('.ocr-overlay');
        overlays.forEach(overlay => overlay.remove());
    }
    
    copyOCRText() {
        if (!this.config.ocr_data?.text) return;
        
        navigator.clipboard.writeText(this.config.ocr_data.text).then(() => {
            // Show success feedback
            this.showToast('OCR text copied to clipboard');
        }).catch(error => {
            console.error('Failed to copy text:', error);
            this.showToast('Failed to copy text', 'error');
        });
    }
    
    downloadDocument() {
        if (this.config.download_url) {
            const link = document.createElement('a');
            link.href = this.config.download_url;
            link.download = this.config.filename;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
        }
    }
    
    printDocument() {
        window.print();
    }
    
    handleResize() {
        // Recalculate zoom for fit modes
        const zoomSelect = document.getElementById('zoom-select');
        if (zoomSelect && (zoomSelect.value === 'fit_width' || zoomSelect.value === 'fit_page')) {
            this.applyFitZoom(zoomSelect.value);
        }
    }
    
    showError(message) {
        const errorModal = document.getElementById('error-modal');
        const errorMessage = document.getElementById('modal-error-message');
        
        if (errorModal && errorMessage) {
            errorMessage.textContent = message;
            errorModal.style.display = 'flex';
        } else {
            alert(message);
        }
    }
    
    closeErrorModal() {
        const errorModal = document.getElementById('error-modal');
        if (errorModal) {
            errorModal.style.display = 'none';
        }
    }
    
    openAnnotationModal(position) {
        const annotationModal = document.getElementById('annotation-modal');
        if (annotationModal) {
            annotationModal.style.display = 'flex';
            
            // Store annotation position
            this.pendingAnnotation = {
                position: position,
                timestamp: new Date().toISOString()
            };
        }
    }
    
    closeAnnotationModal() {
        const annotationModal = document.getElementById('annotation-modal');
        if (annotationModal) {
            annotationModal.style.display = 'none';
        }
        
        // Clear form
        const form = document.querySelector('.annotation-form');
        if (form) {
            form.reset();
        }
        
        this.pendingAnnotation = null;
    }
    
    async saveAnnotation() {
        if (!this.pendingAnnotation) return;
        
        const type = document.getElementById('annotation-type')?.value;
        const content = document.getElementById('annotation-content')?.value;
        const color = document.getElementById('annotation-color')?.value;
        
        if (!content.trim()) {
            this.showToast('Please enter annotation content', 'error');
            return;
        }
        
        const annotationData = {
            type: type,
            content: content.trim(),
            color: color,
            position: this.pendingAnnotation.position,
            timestamp: this.pendingAnnotation.timestamp
        };
        
        try {
            const response = await fetch(
                `/api/clinical-records/documents/${this.config.document_id}/annotations/`,
                {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': this.getCsrfToken()
                    },
                    body: JSON.stringify(annotationData)
                }
            );
            
            if (response.ok) {
                const result = await response.json();
                this.showToast('Annotation saved successfully');
                this.closeAnnotationModal();
                
                // Add annotation to display
                this.addAnnotationToDisplay(annotationData);
            } else {
                const error = await response.json();
                this.showToast(error.message || 'Failed to save annotation', 'error');
            }
        } catch (error) {
            console.error('Error saving annotation:', error);
            this.showToast('Failed to save annotation', 'error');
        }
    }
    
    addAnnotationToDisplay(annotationData) {
        // Implementation would add visual annotation to the document
        // This would depend on the document type and annotation type
        console.log('Annotation added:', annotationData);
    }
    
    showToast(message, type = 'success') {
        // Simple toast notification
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.textContent = message;
        
        toast.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            padding: 12px 20px;
            background: ${type === 'error' ? '#dc3545' : '#28a745'};
            color: white;
            border-radius: 4px;
            z-index: 2000;
            animation: slideInRight 0.3s ease;
        `;
        
        document.body.appendChild(toast);
        
        setTimeout(() => {
            toast.style.animation = 'slideOutRight 0.3s ease';
            setTimeout(() => {
                document.body.removeChild(toast);
            }, 300);
        }, 3000);
    }
    
    getCsrfToken() {
        const token = document.querySelector('[name=csrfmiddlewaretoken]');
        return token ? token.value : '';
    }
}

// Initialize document viewer when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    if (document.getElementById('document-viewer-content')) {
        window.documentViewer = new DocumentViewer();
    }
});

// Add CSS animations
const style = document.createElement('style');
style.textContent = `
    @keyframes slideInRight {
        from {
            transform: translateX(100%);
            opacity: 0;
        }
        to {
            transform: translateX(0);
            opacity: 1;
        }
    }
    
    @keyframes slideOutRight {
        from {
            transform: translateX(0);
            opacity: 1;
        }
        to {
            transform: translateX(100%);
            opacity: 0;
        }
    }
`;
document.head.appendChild(style);