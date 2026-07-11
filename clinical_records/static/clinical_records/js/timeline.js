/**
 * Patient Timeline JavaScript
 * 
 * Handles the interactive functionality for the patient timeline view,
 * including loading data, filtering, searching, and displaying records.
 */

class PatientTimeline {
    constructor(options) {
        this.patientId = options.patientId;
        this.patientName = options.patientName;
        this.clinicName = options.clinicName;
        this.csrfToken = options.csrfToken;
        this.apiBaseUrl = options.apiBaseUrl;
        this.initialSummary = options.initialSummary || {};
        
        // State
        this.currentPage = 1;
        this.pageSize = 20;
        this.filters = {};
        this.searchQuery = '';
        this.searchType = 'all';
        this.isLoading = false;
        this.autoRefreshInterval = null;
        
        // Preferences
        this.preferences = {
            defaultPageSize: 20,
            defaultDateRange: 30,
            showDocumentPreviews: true,
            autoRefreshInterval: 0
        };
        
        // DOM elements
        this.elements = {};
        
        // Bind methods
        this.loadTimelineData = this.loadTimelineData.bind(this);
        this.handleSearch = this.handleSearch.bind(this);
        this.handleFilterChange = this.handleFilterChange.bind(this);
        this.handlePageChange = this.handlePageChange.bind(this);
        this.handleRecordClick = this.handleRecordClick.bind(this);
    }
    
    /**
     * Initialize the timeline
     */
    initialize() {
        this.cacheElements();
        this.bindEvents();
        this.loadPreferences();
        this.loadTimelineData();
        this.setupAutoRefresh();
    }
    
    /**
     * Cache DOM elements
     */
    cacheElements() {
        this.elements = {
            // Loading and error states
            loading: document.getElementById('timeline-loading'),
            error: document.getElementById('timeline-error'),
            empty: document.getElementById('timeline-empty'),
            
            // Content areas
            timelineItems: document.getElementById('timeline-items'),
            pagination: document.getElementById('timeline-pagination'),
            
            // Search elements
            searchInput: document.getElementById('search-input'),
            searchType: document.getElementById('search-type'),
            searchBtn: document.getElementById('search-btn'),
            
            // Filter elements
            toggleFilters: document.getElementById('toggle-filters'),
            filtersPanel: document.getElementById('filters-panel'),
            dateRangeStart: document.getElementById('date-range-start'),
            dateRangeEnd: document.getElementById('date-range-end'),
            recordTypeFilter: document.getElementById('record-type-filter'),
            documentFilter: document.getElementById('document-filter'),
            processingStatusFilter: document.getElementById('processing-status-filter'),
            applyFilters: document.getElementById('apply-filters'),
            clearFilters: document.getElementById('clear-filters'),
            activeFiltersCount: document.getElementById('active-filters-count'),
            
            // Action buttons
            refreshTimeline: document.getElementById('refresh-timeline'),
            exportTimeline: document.getElementById('export-timeline'),
            timelineSettings: document.getElementById('timeline-settings'),
            
            // Pagination elements
            paginationInfo: document.getElementById('pagination-info-text'),
            pageSizeSelect: document.getElementById('page-size-select'),
            
            // Modals
            recordDetailsModal: document.getElementById('record-details-modal'),
            recordDetailsContent: document.getElementById('record-details-content'),
            settingsModal: document.getElementById('settings-modal'),
            exportModal: document.getElementById('export-modal')
        };
    }
    
    /**
     * Bind event listeners
     */
    bindEvents() {
        // Search events
        this.elements.searchBtn.addEventListener('click', this.handleSearch);
        this.elements.searchInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                this.handleSearch();
            }
        });
        
        // Filter events
        this.elements.toggleFilters.addEventListener('click', this.toggleFiltersPanel.bind(this));
        this.elements.applyFilters.addEventListener('click', this.handleFilterChange);
        this.elements.clearFilters.addEventListener('click', this.clearAllFilters.bind(this));
        this.elements.clearFiltersEmpty = document.getElementById('clear-filters-empty');
        if (this.elements.clearFiltersEmpty) {
            this.elements.clearFiltersEmpty.addEventListener('click', this.clearAllFilters.bind(this));
        }
        
        // Action button events
        this.elements.refreshTimeline.addEventListener('click', () => {
            this.loadTimelineData(true);
        });
        this.elements.exportTimeline.addEventListener('click', this.showExportModal.bind(this));
        this.elements.timelineSettings.addEventListener('click', this.showSettingsModal.bind(this));
        
        // Pagination events
        this.elements.pageSizeSelect.addEventListener('change', (e) => {
            this.pageSize = parseInt(e.target.value);
            this.currentPage = 1;
            this.loadTimelineData();
        });
        
        // Modal events
        const saveSettingsBtn = document.getElementById('save-settings');
        if (saveSettingsBtn) {
            saveSettingsBtn.addEventListener('click', this.saveSettings.bind(this));
        }
        
        const startExportBtn = document.getElementById('start-export');
        if (startExportBtn) {
            startExportBtn.addEventListener('click', this.startExport.bind(this));
        }
        
        // Retry button
        const retryBtn = document.getElementById('retry-load');
        if (retryBtn) {
            retryBtn.addEventListener('click', () => {
                this.loadTimelineData(true);
            });
        }
    }
    
    /**
     * Load timeline data from API
     */
    async loadTimelineData(forceRefresh = false) {
        if (this.isLoading && !forceRefresh) return;
        
        this.isLoading = true;
        this.showLoading();
        
        try {
            const params = new URLSearchParams({
                page: this.currentPage,
                page_size: this.pageSize
            });
            
            // Add filters
            Object.entries(this.filters).forEach(([key, value]) => {
                if (value !== null && value !== undefined && value !== '') {
                    if (Array.isArray(value)) {
                        params.append(key, value.join(','));
                    } else {
                        params.append(key, value);
                    }
                }
            });
            
            const response = await fetch(`${this.apiBaseUrl}${this.patientId}/data/?${params}`, {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.csrfToken
                }
            });
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            const data = await response.json();
            this.renderTimelineData(data);
            
        } catch (error) {
            console.error('Error loading timeline data:', error);
            this.showError('Failed to load timeline data. Please try again.');
        } finally {
            this.isLoading = false;
        }
    }
    
    /**
     * Render timeline data
     */
    renderTimelineData(data) {
        this.hideAllStates();
        
        if (!data.timeline_items || data.timeline_items.length === 0) {
            this.showEmpty();
            return;
        }
        
        // Render timeline items
        this.renderTimelineItems(data.timeline_items);
        
        // Render pagination
        this.renderPagination(data.pagination);
        
        // Show content
        this.elements.timelineItems.style.display = 'block';
        this.elements.pagination.style.display = 'block';
    }
    
    /**
     * Render timeline items
     */
    renderTimelineItems(items) {
        const container = this.elements.timelineItems;
        container.innerHTML = '';
        
        items.forEach((item, index) => {
            const itemElement = this.createTimelineItem(item);
            itemElement.classList.add('fade-in');
            itemElement.style.animationDelay = `${index * 0.1}s`;
            container.appendChild(itemElement);
        });
    }
    
    /**
     * Create timeline item element
     */
    createTimelineItem(item) {
        const itemDiv = document.createElement('div');
        itemDiv.className = 'timeline-item';
        itemDiv.dataset.recordId = item.id;
        
        // Add status classes
        if (item.documents_count > 0) {
            itemDiv.classList.add('has-documents');
        }
        if (item.has_unprocessed_documents) {
            itemDiv.classList.add('has-unprocessed');
        }
        
        const contentDiv = document.createElement('div');
        contentDiv.className = 'timeline-item-content';
        contentDiv.addEventListener('click', () => this.handleRecordClick(item.id));
        
        // Header
        const headerDiv = document.createElement('div');
        headerDiv.className = 'timeline-item-header';
        
        const titleH3 = document.createElement('h3');
        titleH3.className = 'timeline-item-title';
        titleH3.textContent = item.title;
        
        const metaDiv = document.createElement('div');
        metaDiv.className = 'timeline-item-meta';
        
        const badge = document.createElement('span');
        badge.className = `record-type-badge ${item.record_type.replace('_', '-')}`;
        badge.textContent = item.record_type.replace('_', ' ').toUpperCase();
        
        const dateSpan = document.createElement('span');
        dateSpan.textContent = this.formatDate(item.created_at);
        
        metaDiv.appendChild(badge);
        metaDiv.appendChild(dateSpan);
        
        headerDiv.appendChild(titleH3);
        headerDiv.appendChild(metaDiv);
        
        // Description
        const descDiv = document.createElement('div');
        descDiv.className = 'timeline-item-description';
        descDiv.textContent = item.description || 'No description available';
        
        contentDiv.appendChild(headerDiv);
        contentDiv.appendChild(descDiv);
        
        // Documents
        if (item.documents && item.documents.length > 0) {
            const docsDiv = document.createElement('div');
            docsDiv.className = 'timeline-item-documents';
            
            item.documents.forEach(doc => {
                const docChip = this.createDocumentChip(doc);
                docsDiv.appendChild(docChip);
            });
            
            contentDiv.appendChild(docsDiv);
        }
        
        itemDiv.appendChild(contentDiv);
        return itemDiv;
    }
    
    /**
     * Create document chip element
     */
    createDocumentChip(doc) {
        const chip = document.createElement('div');
        chip.className = 'document-chip';
        
        // Add status class
        if (doc.processing_status === 'processing') {
            chip.classList.add('processing');
        } else if (doc.processing_status === 'failed') {
            chip.classList.add('failed');
        } else if (doc.content_type.includes('pdf')) {
            chip.classList.add('pdf');
        } else if (doc.content_type.includes('image')) {
            chip.classList.add('image');
        }
        
        const icon = document.createElement('i');
        if (doc.content_type.includes('pdf')) {
            icon.className = 'fas fa-file-pdf';
        } else if (doc.content_type.includes('image')) {
            icon.className = 'fas fa-file-image';
        } else {
            icon.className = 'fas fa-file';
        }
        
        const text = document.createElement('span');
        text.textContent = doc.filename;
        
        chip.appendChild(icon);
        chip.appendChild(text);
        
        return chip;
    }
    
    /**
     * Render pagination
     */
    renderPagination(pagination) {
        const container = this.elements.pagination.querySelector('.pagination');
        container.innerHTML = '';
        
        // Previous button
        const prevLi = document.createElement('li');
        prevLi.className = `page-item ${!pagination.has_previous ? 'disabled' : ''}`;
        const prevA = document.createElement('a');
        prevA.className = 'page-link';
        prevA.href = '#';
        prevA.textContent = 'Previous';
        if (pagination.has_previous) {
            prevA.addEventListener('click', (e) => {
                e.preventDefault();
                this.handlePageChange(pagination.current_page - 1);
            });
        }
        prevLi.appendChild(prevA);
        container.appendChild(prevLi);
        
        // Page numbers
        const startPage = Math.max(1, pagination.current_page - 2);
        const endPage = Math.min(pagination.total_pages, pagination.current_page + 2);
        
        for (let i = startPage; i <= endPage; i++) {
            const pageLi = document.createElement('li');
            pageLi.className = `page-item ${i === pagination.current_page ? 'active' : ''}`;
            const pageA = document.createElement('a');
            pageA.className = 'page-link';
            pageA.href = '#';
            pageA.textContent = i;
            pageA.addEventListener('click', (e) => {
                e.preventDefault();
                this.handlePageChange(i);
            });
            pageLi.appendChild(pageA);
            container.appendChild(pageLi);
        }
        
        // Next button
        const nextLi = document.createElement('li');
        nextLi.className = `page-item ${!pagination.has_next ? 'disabled' : ''}`;
        const nextA = document.createElement('a');
        nextA.className = 'page-link';
        nextA.href = '#';
        nextA.textContent = 'Next';
        if (pagination.has_next) {
            nextA.addEventListener('click', (e) => {
                e.preventDefault();
                this.handlePageChange(pagination.current_page + 1);
            });
        }
        nextLi.appendChild(nextA);
        container.appendChild(nextLi);
        
        // Update pagination info
        const start = (pagination.current_page - 1) * pagination.page_size + 1;
        const end = Math.min(pagination.current_page * pagination.page_size, pagination.total_records);
        this.elements.paginationInfo.textContent = 
            `Showing ${start}-${end} of ${pagination.total_records} records`;
    }
    
    /**
     * Handle search
     */
    async handleSearch() {
        const query = this.elements.searchInput.value.trim();
        const type = this.elements.searchType.value;
        
        if (!query) {
            // Clear search and reload normal timeline
            this.searchQuery = '';
            this.searchType = 'all';
            this.currentPage = 1;
            this.loadTimelineData();
            return;
        }
        
        this.searchQuery = query;
        this.searchType = type;
        
        try {
            this.showLoading();
            
            const params = new URLSearchParams({
                q: query,
                type: type
            });
            
            const response = await fetch(`${this.apiBaseUrl}${this.patientId}/search/?${params}`, {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.csrfToken
                }
            });
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            const data = await response.json();
            this.renderSearchResults(data);
            
        } catch (error) {
            console.error('Error searching timeline:', error);
            this.showError('Search failed. Please try again.');
        }
    }
    
    /**
     * Render search results
     */
    renderSearchResults(data) {
        this.hideAllStates();
        
        if (!data.results || data.results.length === 0) {
            this.showEmpty();
            return;
        }
        
        // Render search results
        this.renderTimelineItems(data.results);
        
        // Hide pagination for search results
        this.elements.pagination.style.display = 'none';
        this.elements.timelineItems.style.display = 'block';
        
        // Show search info
        const searchInfo = document.createElement('div');
        searchInfo.className = 'alert alert-info';
        searchInfo.innerHTML = `
            <i class="fas fa-search"></i>
            Found ${data.results_count} results for "${data.search_query}"
            <button class="btn btn-sm btn-outline-info ms-2" onclick="this.parentElement.nextElementSibling.querySelector('#search-input').value=''; this.parentElement.nextElementSibling.querySelector('#search-btn').click(); this.remove();">
                Clear Search
            </button>
        `;
        
        this.elements.timelineItems.insertBefore(searchInfo, this.elements.timelineItems.firstChild);
    }
    
    /**
     * Handle filter changes
     */
    handleFilterChange() {
        this.filters = {};
        
        // Date range
        if (this.elements.dateRangeStart.value) {
            this.filters.start_date = this.elements.dateRangeStart.value;
        }
        if (this.elements.dateRangeEnd.value) {
            this.filters.end_date = this.elements.dateRangeEnd.value;
        }
        
        // Record types
        const selectedTypes = Array.from(this.elements.recordTypeFilter.selectedOptions)
            .map(option => option.value);
        if (selectedTypes.length > 0) {
            this.filters.record_types = selectedTypes;
        }
        
        // Document filter
        if (this.elements.documentFilter.value === 'has_documents') {
            this.filters.has_documents = true;
        }
        
        // Processing status
        if (this.elements.processingStatusFilter.value) {
            this.filters.processing_status = this.elements.processingStatusFilter.value;
        }
        
        // Update active filters count
        this.updateActiveFiltersCount();
        
        // Reset to first page and load data
        this.currentPage = 1;
        this.loadTimelineData();
        
        // Hide filters panel
        this.elements.filtersPanel.style.display = 'none';
    }
    
    /**
     * Clear all filters
     */
    clearAllFilters() {
        this.filters = {};
        this.elements.dateRangeStart.value = '';
        this.elements.dateRangeEnd.value = '';
        this.elements.recordTypeFilter.selectedIndex = -1;
        this.elements.documentFilter.value = '';
        this.elements.processingStatusFilter.value = '';
        
        this.updateActiveFiltersCount();
        this.currentPage = 1;
        this.loadTimelineData();
        
        this.elements.filtersPanel.style.display = 'none';
    }
    
    /**
     * Update active filters count
     */
    updateActiveFiltersCount() {
        const count = Object.keys(this.filters).length;
        if (count > 0) {
            this.elements.activeFiltersCount.textContent = count;
            this.elements.activeFiltersCount.style.display = 'flex';
        } else {
            this.elements.activeFiltersCount.style.display = 'none';
        }
    }
    
    /**
     * Toggle filters panel
     */
    toggleFiltersPanel() {
        const panel = this.elements.filtersPanel;
        panel.style.display = panel.style.display === 'none' ? 'block' : 'none';
    }
    
    /**
     * Handle page change
     */
    handlePageChange(page) {
        this.currentPage = page;
        this.loadTimelineData();
        
        // Scroll to top of timeline
        this.elements.timelineItems.scrollIntoView({ behavior: 'smooth' });
    }
    
    /**
     * Handle record click
     */
    async handleRecordClick(recordId) {
        try {
            const response = await fetch(`${this.apiBaseUrl}record/${recordId}/`, {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.csrfToken
                }
            });
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            const data = await response.json();
            this.showRecordDetails(data);
            
        } catch (error) {
            console.error('Error loading record details:', error);
            this.showAlert('Failed to load record details', 'error');
        }
    }
    
    /**
     * Show record details modal
     */
    showRecordDetails(record) {
        const modal = new bootstrap.Modal(this.elements.recordDetailsModal);
        const content = this.elements.recordDetailsContent;
        
        // Set modal title
        document.getElementById('record-details-title').textContent = record.title;
        
        // Build content
        content.innerHTML = `
            <div class="record-detail-section">
                <h6>Basic Information</h6>
                <div class="record-detail-grid">
                    <div class="record-detail-item">
                        <div class="record-detail-label">Record Type</div>
                        <div class="record-detail-value">${record.record_type.replace('_', ' ').toUpperCase()}</div>
                    </div>
                    <div class="record-detail-item">
                        <div class="record-detail-label">Created Date</div>
                        <div class="record-detail-value">${this.formatDate(record.created_at)}</div>
                    </div>
                    <div class="record-detail-item">
                        <div class="record-detail-label">Last Updated</div>
                        <div class="record-detail-value">${this.formatDate(record.updated_at)}</div>
                    </div>
                </div>
            </div>
            
            <div class="record-detail-section">
                <h6>Description</h6>
                <p>${record.description || 'No description available'}</p>
            </div>
            
            ${record.documents.length > 0 ? `
                <div class="record-detail-section">
                    <h6>Documents (${record.documents.length})</h6>
                    <div class="document-list">
                        ${record.documents.map(doc => `
                            <div class="document-item">
                                <div class="document-icon ${this.getDocumentIconClass(doc.content_type)}">
                                    <i class="${this.getDocumentIcon(doc.content_type)}"></i>
                                </div>
                                <div class="document-info">
                                    <div class="document-name">${doc.filename}</div>
                                    <div class="document-meta">
                                        ${this.formatFileSize(doc.file_size)} • 
                                        ${doc.processing_status} • 
                                        ${this.formatDate(doc.created_at)}
                                    </div>
                                </div>
                            </div>
                        `).join('')}
                    </div>
                </div>
            ` : ''}
            
            ${record.relationships.length > 0 ? `
                <div class="record-detail-section">
                    <h6>Related Records</h6>
                    <div class="relationships-list">
                        ${record.relationships.map(rel => `
                            <div class="relationship-item">
                                <strong>${rel.relationship_type}:</strong> 
                                ${rel.target_type} (${rel.target_id})
                            </div>
                        `).join('')}
                    </div>
                </div>
            ` : ''}
        `;
        
        modal.show();
    }
    
    /**
     * Show/hide states
     */
    showLoading() {
        this.hideAllStates();
        this.elements.loading.style.display = 'flex';
    }
    
    showError(message) {
        this.hideAllStates();
        document.getElementById('error-message').textContent = message;
        this.elements.error.style.display = 'block';
    }
    
    showEmpty() {
        this.hideAllStates();
        this.elements.empty.style.display = 'block';
    }
    
    hideAllStates() {
        this.elements.loading.style.display = 'none';
        this.elements.error.style.display = 'none';
        this.elements.empty.style.display = 'none';
        this.elements.timelineItems.style.display = 'none';
        this.elements.pagination.style.display = 'none';
    }
    
    /**
     * Utility methods
     */
    formatDate(dateString) {
        const date = new Date(dateString);
        return date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
    }
    
    formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }
    
    getDocumentIcon(contentType) {
        if (contentType.includes('pdf')) return 'fas fa-file-pdf';
        if (contentType.includes('image')) return 'fas fa-file-image';
        if (contentType.includes('text')) return 'fas fa-file-alt';
        return 'fas fa-file';
    }
    
    getDocumentIconClass(contentType) {
        if (contentType.includes('pdf')) return 'pdf';
        if (contentType.includes('image')) return 'image';
        return 'text';
    }
    
    /**
     * Settings and preferences
     */
    loadPreferences() {
        // Load from localStorage or session
        const saved = localStorage.getItem('timeline-preferences');
        if (saved) {
            this.preferences = { ...this.preferences, ...JSON.parse(saved) };
        }
        
        // Apply preferences
        this.pageSize = this.preferences.defaultPageSize;
        this.elements.pageSizeSelect.value = this.pageSize;
    }
    
    savePreferences() {
        localStorage.setItem('timeline-preferences', JSON.stringify(this.preferences));
    }
    
    showSettingsModal() {
        const modal = new bootstrap.Modal(this.elements.settingsModal);
        
        // Populate current settings
        document.getElementById('default-page-size').value = this.preferences.defaultPageSize;
        document.getElementById('default-date-range').value = this.preferences.defaultDateRange;
        document.getElementById('show-document-previews').checked = this.preferences.showDocumentPreviews;
        document.getElementById('auto-refresh').value = this.preferences.autoRefreshInterval;
        
        modal.show();
    }
    
    saveSettings() {
        // Get values from form
        this.preferences.defaultPageSize = parseInt(document.getElementById('default-page-size').value);
        this.preferences.defaultDateRange = parseInt(document.getElementById('default-date-range').value);
        this.preferences.showDocumentPreviews = document.getElementById('show-document-previews').checked;
        this.preferences.autoRefreshInterval = parseInt(document.getElementById('auto-refresh').value);
        
        // Save to storage
        this.savePreferences();
        
        // Apply changes
        this.pageSize = this.preferences.defaultPageSize;
        this.elements.pageSizeSelect.value = this.pageSize;
        this.setupAutoRefresh();
        
        // Close modal
        bootstrap.Modal.getInstance(this.elements.settingsModal).hide();
        
        this.showAlert('Settings saved successfully', 'success');
    }
    
    setupAutoRefresh() {
        // Clear existing interval
        if (this.autoRefreshInterval) {
            clearInterval(this.autoRefreshInterval);
            this.autoRefreshInterval = null;
        }
        
        // Set up new interval if enabled
        if (this.preferences.autoRefreshInterval > 0) {
            this.autoRefreshInterval = setInterval(() => {
                this.loadTimelineData();
            }, this.preferences.autoRefreshInterval * 1000);
        }
    }
    
    /**
     * Export functionality
     */
    showExportModal() {
        const modal = new bootstrap.Modal(this.elements.exportModal);
        modal.show();
    }
    
    startExport() {
        const format = document.getElementById('export-format').value;
        const includeDocuments = document.getElementById('include-documents').checked;
        const includeMetadata = document.getElementById('include-metadata').checked;
        
        const params = new URLSearchParams({
            format: format,
            include_documents: includeDocuments,
            include_metadata: includeMetadata
        });
        
        // Create download link
        const url = `${this.apiBaseUrl}${this.patientId}/export/?${params}`;
        const link = document.createElement('a');
        link.href = url;
        link.download = `timeline_${this.patientId}.${format}`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        
        // Close modal
        bootstrap.Modal.getInstance(this.elements.exportModal).hide();
        
        this.showAlert('Export started', 'success');
    }
    
    /**
     * Show alert message
     */
    showAlert(message, type = 'info') {
        const alertDiv = document.createElement('div');
        alertDiv.className = `alert alert-${type} alert-dismissible fade show`;
        alertDiv.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;
        
        // Insert at top of timeline container
        this.elements.timelineItems.insertBefore(alertDiv, this.elements.timelineItems.firstChild);
        
        // Auto-dismiss after 5 seconds
        setTimeout(() => {
            if (alertDiv.parentNode) {
                alertDiv.remove();
            }
        }, 5000);
    }
}

// Export for use in other scripts
window.PatientTimeline = PatientTimeline;