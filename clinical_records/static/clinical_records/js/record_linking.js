/**
 * Record Linking Interface JavaScript
 * Handles drag-and-drop linking, search, and relationship management
 */

class RecordLinking {
    constructor() {
        this.config = {};
        this.currentRecord = null;
        this.linkableEntities = [];
        this.relationships = [];
        this.searchTimeout = null;
        this.editingRelationshipId = null;
        this.deletingRelationshipId = null;
    }

    /**
     * Initialize the record linking interface
     */
    init(config) {
        this.config = config;
        this.currentRecord = config.recordId;
        
        this.initializeEventListeners();
        this.initializeDragAndDrop();
        this.loadLinkableEntities();
        
        console.log('Record Linking initialized', config);
    }

    /**
     * Initialize event listeners
     */
    initializeEventListeners() {
        // Link form submission
        const linkForm = document.getElementById('linkForm');
        if (linkForm) {
            linkForm.addEventListener('submit', (e) => this.handleLinkFormSubmit(e));
        }

        // Entity search
        const entitySearch = document.getElementById('entitySearch');
        if (entitySearch) {
            entitySearch.addEventListener('input', (e) => this.handleEntitySearch(e));
            entitySearch.addEventListener('focus', () => this.showSearchResults());
            entitySearch.addEventListener('blur', () => {
                // Delay hiding to allow clicking on results
                setTimeout(() => this.hideSearchResults(), 200);
            });
        }

        // Entity filters
        const filterButtons = document.querySelectorAll('.filter-btn');
        filterButtons.forEach(btn => {
            btn.addEventListener('click', (e) => this.handleEntityFilter(e));
        });

        // Clear form button
        const clearBtn = document.querySelector('[onclick="clearForm()"]');
        if (clearBtn) {
            clearBtn.onclick = () => this.clearForm();
        }

        // Modal events
        this.initializeModalEvents();
    }

    /**
     * Initialize modal event listeners
     */
    initializeModalEvents() {
        // Bootstrap modal events
        const relationshipModal = document.getElementById('relationshipModal');
        if (relationshipModal) {
            relationshipModal.addEventListener('hidden.bs.modal', () => {
                this.editingRelationshipId = null;
            });
        }

        const confirmDeleteModal = document.getElementById('confirmDeleteModal');
        if (confirmDeleteModal) {
            confirmDeleteModal.addEventListener('hidden.bs.modal', () => {
                this.deletingRelationshipId = null;
            });
        }
    }

    /**
     * Initialize drag and drop functionality
     */
    initializeDragAndDrop() {
        if (!this.config.enableDragDrop) return;

        // Make entity items draggable
        const entityItems = document.querySelectorAll('.entity-item.draggable');
        entityItems.forEach(item => {
            item.draggable = true;
            item.addEventListener('dragstart', (e) => this.handleDragStart(e));
            item.addEventListener('dragend', (e) => this.handleDragEnd(e));
        });

        // Make link composer a drop zone
        const linkComposer = document.querySelector('.link-composer');
        if (linkComposer) {
            linkComposer.addEventListener('dragover', (e) => this.handleDragOver(e));
            linkComposer.addEventListener('drop', (e) => this.handleDrop(e));
            linkComposer.addEventListener('dragenter', (e) => this.handleDragEnter(e));
            linkComposer.addEventListener('dragleave', (e) => this.handleDragLeave(e));
        }
    }

    /**
     * Load linkable entities from API
     */
    async loadLinkableEntities(entityType = null) {
        try {
            const params = new URLSearchParams({
                exclude_record: this.currentRecord,
                limit: 50
            });
            
            if (entityType && entityType !== 'all') {
                params.append('type', entityType);
            }

            const response = await fetch(
                `${this.config.apiBaseUrl}patients/${this.config.patientId}/linkable-entities/?${params}`,
                {
                    headers: {
                        'Authorization': `Bearer ${this.getAuthToken()}`,
                        'Content-Type': 'application/json'
                    }
                }
            );

            if (response.ok) {
                const data = await response.json();
                this.linkableEntities = data.entities;
                this.renderEntitiesList(data.entities);
            } else {
                this.showError('Failed to load linkable entities');
            }
        } catch (error) {
            console.error('Error loading linkable entities:', error);
            this.showError('Failed to load linkable entities');
        }
    }

    /**
     * Render entities list
     */
    renderEntitiesList(entities) {
        const entitiesList = document.getElementById('entitiesList');
        if (!entitiesList) return;

        if (entities.length === 0) {
            entitiesList.innerHTML = `
                <div class="empty-state">
                    <i class="fas fa-search"></i>
                    <p>No items found</p>
                    <small>Try adjusting your filters</small>
                </div>
            `;
            return;
        }

        entitiesList.innerHTML = entities.map(entity => `
            <div class="entity-item draggable" 
                 data-entity-id="${entity.id}" 
                 data-entity-type="${entity.type}"
                 data-entity-title="${entity.title}"
                 draggable="true">
                <div class="entity-icon" style="color: ${entity.color}">
                    <i class="${entity.icon}"></i>
                </div>
                <div class="entity-info">
                    <div class="entity-title">${entity.title}</div>
                    <div class="entity-subtitle">${entity.subtitle}</div>
                    <div class="entity-meta">
                        <span class="entity-date">${this.formatDate(entity.date)}</span>
                        ${entity.status ? `<span class="entity-status status-${entity.status}">${entity.status}</span>` : ''}
                    </div>
                </div>
                <div class="entity-actions">
                    <button class="btn-icon" onclick="RecordLinking.instance.quickLink('${entity.id}', '${entity.type}')" title="Quick Link">
                        <i class="fas fa-link"></i>
                    </button>
                </div>
            </div>
        `).join('');

        // Re-initialize drag and drop for new items
        this.initializeDragAndDrop();
    }

    /**
     * Handle link form submission
     */
    async handleLinkFormSubmit(e) {
        e.preventDefault();
        
        const formData = new FormData(e.target);
        const data = {
            source_record_id: this.currentRecord,
            target_entity_id: formData.get('target_entity_id') || document.getElementById('targetEntityId').value,
            target_entity_type: formData.get('target_entity_type') || document.getElementById('targetEntityType').value,
            relationship_type: formData.get('relationship_type'),
            notes: formData.get('notes')
        };

        // Validate required fields
        if (!data.target_entity_id || !data.target_entity_type || !data.relationship_type) {
            this.showError('Please fill in all required fields');
            return;
        }

        try {
            this.setLoading(true);
            
            const response = await fetch(`${this.config.apiBaseUrl}relationships/create/`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${this.getAuthToken()}`,
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken()
                },
                body: JSON.stringify(data)
            });

            const result = await response.json();

            if (response.ok && result.success) {
                this.showSuccess('Relationship created successfully');
                this.clearForm();
                this.refreshRelationships();
            } else {
                this.showError(result.error || 'Failed to create relationship');
            }
        } catch (error) {
            console.error('Error creating relationship:', error);
            this.showError('Failed to create relationship');
        } finally {
            this.setLoading(false);
        }
    }

    /**
     * Handle entity search
     */
    handleEntitySearch(e) {
        const query = e.target.value.trim();
        
        // Clear previous timeout
        if (this.searchTimeout) {
            clearTimeout(this.searchTimeout);
        }

        // Debounce search
        this.searchTimeout = setTimeout(() => {
            this.performEntitySearch(query);
        }, 300);
    }

    /**
     * Perform entity search
     */
    performEntitySearch(query) {
        if (!query) {
            this.hideSearchResults();
            return;
        }

        // Filter entities based on query
        const filteredEntities = this.linkableEntities.filter(entity => 
            entity.title.toLowerCase().includes(query.toLowerCase()) ||
            entity.subtitle.toLowerCase().includes(query.toLowerCase())
        );

        this.showSearchResults(filteredEntities.slice(0, 10)); // Limit to 10 results
    }

    /**
     * Show search results
     */
    showSearchResults(entities = null) {
        const searchResults = document.getElementById('searchResults');
        if (!searchResults) return;

        if (!entities) {
            entities = this.linkableEntities.slice(0, 10);
        }

        if (entities.length === 0) {
            searchResults.innerHTML = '<div class="search-result-item">No results found</div>';
        } else {
            searchResults.innerHTML = entities.map(entity => `
                <div class="search-result-item" onclick="RecordLinking.instance.selectEntity('${entity.id}', '${entity.type}', '${entity.title}')">
                    <div class="entity-icon" style="color: ${entity.color}">
                        <i class="${entity.icon}"></i>
                    </div>
                    <div class="entity-info">
                        <div class="entity-title">${entity.title}</div>
                        <div class="entity-subtitle">${entity.subtitle}</div>
                    </div>
                </div>
            `).join('');
        }

        searchResults.style.display = 'block';
    }

    /**
     * Hide search results
     */
    hideSearchResults() {
        const searchResults = document.getElementById('searchResults');
        if (searchResults) {
            searchResults.style.display = 'none';
        }
    }

    /**
     * Select entity from search results
     */
    selectEntity(entityId, entityType, entityTitle) {
        document.getElementById('targetEntityId').value = entityId;
        document.getElementById('targetEntityType').value = entityType;
        document.getElementById('entitySearch').value = entityTitle;
        this.hideSearchResults();
    }

    /**
     * Handle entity filter
     */
    handleEntityFilter(e) {
        const filterButtons = document.querySelectorAll('.filter-btn');
        filterButtons.forEach(btn => btn.classList.remove('active'));
        
        e.target.classList.add('active');
        
        const entityType = e.target.dataset.type;
        this.loadLinkableEntities(entityType);
    }

    /**
     * Quick link functionality
     */
    async quickLink(entityId, entityType) {
        // Pre-fill the form with default relationship type
        document.getElementById('targetEntityId').value = entityId;
        document.getElementById('targetEntityType').value = entityType;
        
        // Find entity details
        const entity = this.linkableEntities.find(e => e.id === entityId);
        if (entity) {
            document.getElementById('entitySearch').value = entity.title;
        }

        // Set default relationship type
        const relationshipType = document.getElementById('relationshipType');
        if (relationshipType.value === '') {
            relationshipType.value = 'RELATED_TO';
        }

        // Scroll to form
        document.querySelector('.link-composer').scrollIntoView({ behavior: 'smooth' });
        
        // Focus on relationship type if not set
        if (relationshipType.value === 'RELATED_TO') {
            relationshipType.focus();
        }
    }

    /**
     * Apply suggestion
     */
    applySuggestion(button) {
        const suggestionItem = button.closest('.suggestion-item');
        const suggestionData = JSON.parse(suggestionItem.dataset.suggestion);
        
        // Fill form with suggestion data
        document.getElementById('targetEntityId').value = suggestionData.target_entity.id;
        document.getElementById('targetEntityType').value = suggestionData.target_entity.type;
        document.getElementById('entitySearch').value = suggestionData.target_entity.title;
        document.getElementById('relationshipType').value = suggestionData.suggested_relationship_type;
        
        // Scroll to form
        document.querySelector('.link-composer').scrollIntoView({ behavior: 'smooth' });
    }

    /**
     * Clear form
     */
    clearForm() {
        document.getElementById('linkForm').reset();
        document.getElementById('targetEntityId').value = '';
        document.getElementById('targetEntityType').value = '';
        this.hideSearchResults();
    }

    /**
     * Drag and drop handlers
     */
    handleDragStart(e) {
        const entityData = {
            id: e.target.dataset.entityId,
            type: e.target.dataset.entityType,
            title: e.target.dataset.entityTitle
        };
        
        e.dataTransfer.setData('application/json', JSON.stringify(entityData));
        e.target.style.opacity = '0.5';
    }

    handleDragEnd(e) {
        e.target.style.opacity = '1';
    }

    handleDragOver(e) {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'link';
    }

    handleDragEnter(e) {
        e.preventDefault();
        e.target.closest('.link-composer').classList.add('drag-over');
    }

    handleDragLeave(e) {
        if (!e.target.closest('.link-composer').contains(e.relatedTarget)) {
            e.target.closest('.link-composer').classList.remove('drag-over');
        }
    }

    handleDrop(e) {
        e.preventDefault();
        e.target.closest('.link-composer').classList.remove('drag-over');
        
        try {
            const entityData = JSON.parse(e.dataTransfer.getData('application/json'));
            this.selectEntity(entityData.id, entityData.type, entityData.title);
            
            // Set default relationship type if not set
            const relationshipType = document.getElementById('relationshipType');
            if (relationshipType.value === '') {
                relationshipType.value = 'RELATED_TO';
            }
        } catch (error) {
            console.error('Error handling drop:', error);
        }
    }

    /**
     * Edit relationship
     */
    editRelationship(relationshipId) {
        this.editingRelationshipId = relationshipId;
        
        // Find relationship data
        const relationship = this.relationships.find(r => r.id === relationshipId);
        if (relationship) {
            document.getElementById('editRelationshipType').value = relationship.type;
            document.getElementById('editNotes').value = relationship.notes || '';
        }
        
        // Show modal
        const modal = new bootstrap.Modal(document.getElementById('relationshipModal'));
        modal.show();
    }

    /**
     * Save relationship edit
     */
    async saveRelationshipEdit() {
        if (!this.editingRelationshipId) return;
        
        const formData = new FormData(document.getElementById('editRelationshipForm'));
        const data = {
            relationship_type: formData.get('relationship_type'),
            notes: formData.get('notes')
        };
        
        try {
            this.setLoading(true);
            
            const response = await fetch(`${this.config.apiBaseUrl}relationships/${this.editingRelationshipId}/`, {
                method: 'PATCH',
                headers: {
                    'Authorization': `Bearer ${this.getAuthToken()}`,
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken()
                },
                body: JSON.stringify(data)
            });
            
            if (response.ok) {
                this.showSuccess('Relationship updated successfully');
                this.refreshRelationships();
                
                // Hide modal
                const modal = bootstrap.Modal.getInstance(document.getElementById('relationshipModal'));
                modal.hide();
            } else {
                this.showError('Failed to update relationship');
            }
        } catch (error) {
            console.error('Error updating relationship:', error);
            this.showError('Failed to update relationship');
        } finally {
            this.setLoading(false);
        }
    }

    /**
     * Delete relationship
     */
    deleteRelationship(relationshipId) {
        this.deletingRelationshipId = relationshipId;
        
        // Show confirmation modal
        const modal = new bootstrap.Modal(document.getElementById('confirmDeleteModal'));
        modal.show();
    }

    /**
     * Confirm delete relationship
     */
    async confirmDeleteRelationship() {
        if (!this.deletingRelationshipId) return;
        
        try {
            this.setLoading(true);
            
            const response = await fetch(`${this.config.apiBaseUrl}relationships/${this.deletingRelationshipId}/`, {
                method: 'DELETE',
                headers: {
                    'Authorization': `Bearer ${this.getAuthToken()}`,
                    'X-CSRFToken': this.getCSRFToken()
                }
            });
            
            if (response.ok) {
                this.showSuccess('Relationship deleted successfully');
                this.refreshRelationships();
                
                // Hide modal
                const modal = bootstrap.Modal.getInstance(document.getElementById('confirmDeleteModal'));
                modal.hide();
            } else {
                this.showError('Failed to delete relationship');
            }
        } catch (error) {
            console.error('Error deleting relationship:', error);
            this.showError('Failed to delete relationship');
        } finally {
            this.setLoading(false);
        }
    }

    /**
     * Refresh relationships list
     */
    async refreshRelationships() {
        try {
            const response = await fetch(`${this.config.apiBaseUrl}records/${this.currentRecord}/relationships/`, {
                headers: {
                    'Authorization': `Bearer ${this.getAuthToken()}`,
                    'Content-Type': 'application/json'
                }
            });
            
            if (response.ok) {
                const data = await response.json();
                this.relationships = data.relationships;
                // Reload page to update relationships display
                window.location.reload();
            }
        } catch (error) {
            console.error('Error refreshing relationships:', error);
        }
    }

    /**
     * Utility functions
     */
    formatDate(dateString) {
        const date = new Date(dateString);
        return date.toLocaleDateString('en-US', { 
            year: 'numeric', 
            month: 'short', 
            day: 'numeric' 
        });
    }

    getAuthToken() {
        // Get auth token from localStorage or cookie
        return localStorage.getItem('authToken') || '';
    }

    getCSRFToken() {
        // Get CSRF token from cookie or meta tag
        const token = document.querySelector('[name=csrfmiddlewaretoken]');
        return token ? token.value : '';
    }

    setLoading(loading) {
        const form = document.getElementById('linkForm');
        if (form) {
            if (loading) {
                form.classList.add('loading');
            } else {
                form.classList.remove('loading');
            }
        }
    }

    showSuccess(message) {
        this.showNotification(message, 'success');
    }

    showError(message) {
        this.showNotification(message, 'error');
    }

    showNotification(message, type) {
        // Create notification element
        const notification = document.createElement('div');
        notification.className = `alert alert-${type === 'success' ? 'success' : 'danger'} alert-dismissible fade show`;
        notification.style.position = 'fixed';
        notification.style.top = '20px';
        notification.style.right = '20px';
        notification.style.zIndex = '9999';
        notification.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;
        
        document.body.appendChild(notification);
        
        // Auto-remove after 5 seconds
        setTimeout(() => {
            if (notification.parentNode) {
                notification.parentNode.removeChild(notification);
            }
        }, 5000);
    }

    /**
     * Show relationship map
     */
    showRelationshipMap() {
        window.open(`/clinical-records/patients/${this.config.patientId}/relationship-map/`, '_blank');
    }

    /**
     * Show bulk linking interface
     */
    showBulkLinking() {
        window.open(`/clinical-records/patients/${this.config.patientId}/bulk-linking/`, '_blank');
    }
}

// Create global instance
RecordLinking.instance = new RecordLinking();

// Global functions for onclick handlers
window.editRelationship = (id) => RecordLinking.instance.editRelationship(id);
window.deleteRelationship = (id) => RecordLinking.instance.deleteRelationship(id);
window.saveRelationshipEdit = () => RecordLinking.instance.saveRelationshipEdit();
window.confirmDeleteRelationship = () => RecordLinking.instance.confirmDeleteRelationship();
window.applySuggestion = (button) => RecordLinking.instance.applySuggestion(button);
window.clearForm = () => RecordLinking.instance.clearForm();
window.showRelationshipMap = () => RecordLinking.instance.showRelationshipMap();
window.showBulkLinking = () => RecordLinking.instance.showBulkLinking();