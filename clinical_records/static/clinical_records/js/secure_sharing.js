/**
 * Secure Sharing JavaScript
 * Handles the secure sharing interface functionality
 */

class SecureSharingManager {
    constructor() {
        this.recordData = window.recordData || null;
        this.sharingConfig = window.sharingConfig || {};
        this.init();
    }

    init() {
        this.bindEvents();
        this.initializeForm();
        this.formatDates();
    }

    bindEvents() {
        // Form submission
        const form = document.getElementById('create-share-form');
        if (form) {
            form.addEventListener('submit', (e) => this.handleFormSubmit(e));
        }

        // Access level change
        const accessLevelSelect = document.getElementById('access_level');
        if (accessLevelSelect) {
            accessLevelSelect.addEventListener('change', (e) => this.handleAccessLevelChange(e));
        }

        // Email notification checkbox
        const sendNotificationCheckbox = document.getElementById('send_notification');
        const recipientEmailInput = document.getElementById('recipient_email');
        if (sendNotificationCheckbox && recipientEmailInput) {
            sendNotificationCheckbox.addEventListener('change', (e) => {
                if (e.target.checked) {
                    recipientEmailInput.setAttribute('required', 'required');
                } else {
                    recipientEmailInput.removeAttribute('required');
                }
            });
        }

        // Form validation
        this.setupFormValidation();
    }

    initializeForm() {
        // Set default values
        const expiryDaysInput = document.getElementById('expiry_days');
        if (expiryDaysInput && this.sharingConfig.default_expiry_days) {
            expiryDaysInput.value = this.sharingConfig.default_expiry_days;
        }

        // Update access level descriptions
        this.updateAccessLevelDescription();
    }

    setupFormValidation() {
        const form = document.getElementById('create-share-form');
        if (!form) return;

        // Real-time validation
        const inputs = form.querySelectorAll('input, select, textarea');
        inputs.forEach(input => {
            input.addEventListener('blur', () => this.validateField(input));
            input.addEventListener('input', () => this.clearFieldError(input));
        });
    }

    validateField(field) {
        const value = field.value.trim();
        let isValid = true;
        let errorMessage = '';

        switch (field.name) {
            case 'expiry_days':
                const days = parseInt(value);
                if (days < 1 || days > this.sharingConfig.max_expiry_days) {
                    isValid = false;
                    errorMessage = `Expiry days must be between 1 and ${this.sharingConfig.max_expiry_days}`;
                }
                break;

            case 'max_access_count':
                const count = parseInt(value);
                if (count < 1 || count > 100) {
                    isValid = false;
                    errorMessage = 'Access count must be between 1 and 100';
                }
                break;

            case 'recipient_email':
                if (value && !this.isValidEmail(value)) {
                    isValid = false;
                    errorMessage = 'Please enter a valid email address';
                }
                break;

            case 'allowed_ips':
                if (value && !this.validateIPAddresses(value)) {
                    isValid = false;
                    errorMessage = 'Please enter valid IP addresses or CIDR blocks';
                }
                break;
        }

        this.showFieldValidation(field, isValid, errorMessage);
        return isValid;
    }

    showFieldValidation(field, isValid, errorMessage) {
        const formGroup = field.closest('.form-group');
        if (!formGroup) return;

        // Remove existing validation classes and messages
        formGroup.classList.remove('has-error', 'has-success');
        const existingError = formGroup.querySelector('.field-error');
        if (existingError) {
            existingError.remove();
        }

        if (!isValid && errorMessage) {
            formGroup.classList.add('has-error');
            field.classList.add('is-invalid');
            
            const errorDiv = document.createElement('div');
            errorDiv.className = 'field-error text-danger mt-1';
            errorDiv.style.fontSize = '0.85rem';
            errorDiv.textContent = errorMessage;
            formGroup.appendChild(errorDiv);
        } else if (field.value.trim()) {
            formGroup.classList.add('has-success');
            field.classList.remove('is-invalid');
            field.classList.add('is-valid');
        }
    }

    clearFieldError(field) {
        const formGroup = field.closest('.form-group');
        if (formGroup) {
            formGroup.classList.remove('has-error');
            field.classList.remove('is-invalid');
            const errorDiv = formGroup.querySelector('.field-error');
            if (errorDiv) {
                errorDiv.remove();
            }
        }
    }

    handleAccessLevelChange(event) {
        this.updateAccessLevelDescription();
    }

    updateAccessLevelDescription() {
        const accessLevel = document.getElementById('access_level')?.value;
        const descriptions = {
            'VIEW': 'Recipients can view the record and documents online but cannot download them.',
            'DOWNLOAD': 'Recipients can view and download documents from the shared record.',
            'FULL': 'Recipients have full access to all record data including structured information.'
        };

        // Update description if there's a description element
        const descElement = document.querySelector('.access-level-description');
        if (descElement && descriptions[accessLevel]) {
            descElement.textContent = descriptions[accessLevel];
        }
    }

    async handleFormSubmit(event) {
        event.preventDefault();
        
        const form = event.target;
        const formData = new FormData(form);
        
        // Validate form
        if (!this.validateForm(form)) {
            this.showAlert('Please correct the errors in the form.', 'error');
            return;
        }

        // Prepare share options
        const shareOptions = this.prepareShareOptions(formData);
        
        try {
            this.showLoading(true);
            
            const response = await this.createShareToken(shareOptions);
            
            if (response.success) {
                this.showShareCreatedModal(response);
                this.resetForm();
                // Optionally reload the page to show the new share in the table
                setTimeout(() => {
                    window.location.reload();
                }, 2000);
            } else {
                throw new Error(response.error || 'Failed to create share');
            }
            
        } catch (error) {
            console.error('Error creating share:', error);
            this.showAlert(error.message || 'Failed to create share token', 'error');
        } finally {
            this.showLoading(false);
        }
    }

    validateForm(form) {
        const inputs = form.querySelectorAll('input[required], select[required], textarea[required]');
        let isValid = true;

        inputs.forEach(input => {
            if (!this.validateField(input)) {
                isValid = false;
            }
        });

        // Check patient consent
        const consentCheckbox = document.getElementById('patient_consent_confirmed');
        if (consentCheckbox && !consentCheckbox.checked) {
            this.showAlert('Patient consent confirmation is required.', 'error');
            isValid = false;
        }

        return isValid;
    }

    prepareShareOptions(formData) {
        const options = {
            access_level: formData.get('access_level'),
            expiry_days: parseInt(formData.get('expiry_days')),
            max_access_count: parseInt(formData.get('max_access_count')),
            purpose: formData.get('purpose') || '',
            require_authentication: formData.get('require_authentication') === 'on',
            patient_consent_confirmed: formData.get('patient_consent_confirmed') === 'on',
            send_notification: formData.get('send_notification') === 'on',
            recipient_info: {
                name: formData.get('recipient_name') || '',
                email: formData.get('recipient_email') || '',
                organization: formData.get('recipient_organization') || ''
            }
        };

        // Parse allowed IPs
        const allowedIPs = formData.get('allowed_ips');
        if (allowedIPs) {
            options.allowed_ips = allowedIPs.split('\n')
                .map(ip => ip.trim())
                .filter(ip => ip.length > 0);
        }

        return options;
    }

    async createShareToken(shareOptions) {
        const recordId = this.recordData?.id;
        if (!recordId) {
            throw new Error('No record selected for sharing');
        }

        const response = await fetch(`/api/clinical-records/records/${recordId}/share/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.getCSRFToken()
            },
            body: JSON.stringify(shareOptions)
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || `HTTP ${response.status}`);
        }

        return await response.json();
    }

    showShareCreatedModal(shareData) {
        const modal = document.getElementById('shareCreatedModal');
        if (!modal) return;

        // Populate modal with share data
        document.getElementById('shareUrlInput').value = shareData.share_url;
        document.getElementById('shareExpiresAt').textContent = this.formatDate(shareData.expires_at);
        document.getElementById('shareAccessLevel').textContent = shareData.access_level;
        document.getElementById('shareMaxAccess').textContent = shareData.max_access_count;

        // Show modal
        $(modal).modal('show');
    }

    resetForm() {
        const form = document.getElementById('create-share-form');
        if (form) {
            form.reset();
            
            // Clear validation states
            const formGroups = form.querySelectorAll('.form-group');
            formGroups.forEach(group => {
                group.classList.remove('has-error', 'has-success');
                const errorDiv = group.querySelector('.field-error');
                if (errorDiv) {
                    errorDiv.remove();
                }
            });

            const inputs = form.querySelectorAll('input, select, textarea');
            inputs.forEach(input => {
                input.classList.remove('is-invalid', 'is-valid');
            });

            // Reset to default values
            this.initializeForm();
        }
    }

    showLoading(show) {
        const overlay = document.getElementById('loadingOverlay');
        if (overlay) {
            overlay.style.display = show ? 'flex' : 'none';
        }
    }

    showAlert(message, type = 'info') {
        // Create alert element
        const alertDiv = document.createElement('div');
        alertDiv.className = `alert alert-${type === 'error' ? 'danger' : type} alert-dismissible fade show`;
        alertDiv.innerHTML = `
            ${message}
            <button type="button" class="close" data-dismiss="alert">
                <span>&times;</span>
            </button>
        `;

        // Insert at top of container
        const container = document.querySelector('.secure-sharing-container');
        if (container) {
            container.insertBefore(alertDiv, container.firstChild);
            
            // Auto-dismiss after 5 seconds
            setTimeout(() => {
                if (alertDiv.parentNode) {
                    alertDiv.remove();
                }
            }, 5000);
        }
    }

    formatDates() {
        const dateElements = document.querySelectorAll('.date-display');
        dateElements.forEach(element => {
            const dateStr = element.getAttribute('data-date');
            if (dateStr) {
                const date = new Date(dateStr);
                element.textContent = this.formatDate(date);
            }
        });
    }

    formatDate(date) {
        if (typeof date === 'string') {
            date = new Date(date);
        }
        
        return date.toLocaleDateString('en-US', {
            year: 'numeric',
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        });
    }

    isValidEmail(email) {
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        return emailRegex.test(email);
    }

    validateIPAddresses(ipString) {
        const ips = ipString.split('\n').map(ip => ip.trim()).filter(ip => ip.length > 0);
        
        for (const ip of ips) {
            if (!this.isValidIP(ip) && !this.isValidCIDR(ip)) {
                return false;
            }
        }
        
        return true;
    }

    isValidIP(ip) {
        const ipRegex = /^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$/;
        return ipRegex.test(ip);
    }

    isValidCIDR(cidr) {
        const cidrRegex = /^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\/(?:[0-9]|[1-2][0-9]|3[0-2])$/;
        return cidrRegex.test(cidr);
    }

    getCSRFToken() {
        const token = document.querySelector('[name=csrfmiddlewaretoken]')?.value;
        if (!token) {
            // Try to get from cookie
            const cookies = document.cookie.split(';');
            for (let cookie of cookies) {
                const [name, value] = cookie.trim().split('=');
                if (name === 'csrftoken') {
                    return value;
                }
            }
        }
        return token;
    }
}

// Global functions for template usage
window.copyToClipboard = function(inputId) {
    const input = document.getElementById(inputId);
    if (input) {
        input.select();
        input.setSelectionRange(0, 99999); // For mobile devices
        
        try {
            document.execCommand('copy');
            
            // Show feedback
            const button = event.target.closest('button');
            if (button) {
                const originalText = button.innerHTML;
                button.innerHTML = '<i class="fas fa-check"></i> Copied!';
                button.classList.add('btn-success');
                
                setTimeout(() => {
                    button.innerHTML = originalText;
                    button.classList.remove('btn-success');
                }, 2000);
            }
        } catch (err) {
            console.error('Failed to copy text: ', err);
        }
    }
};

window.copyShareLink = function(token) {
    const shareUrl = `${window.location.origin}/clinical-records/shared/${token}/`;
    
    // Create temporary input
    const tempInput = document.createElement('input');
    tempInput.value = shareUrl;
    document.body.appendChild(tempInput);
    tempInput.select();
    
    try {
        document.execCommand('copy');
        
        // Show feedback
        const button = event.target.closest('button');
        if (button) {
            const originalHTML = button.innerHTML;
            button.innerHTML = '<i class="fas fa-check"></i>';
            button.classList.add('btn-success');
            
            setTimeout(() => {
                button.innerHTML = originalHTML;
                button.classList.remove('btn-success');
            }, 2000);
        }
    } catch (err) {
        console.error('Failed to copy link: ', err);
    } finally {
        document.body.removeChild(tempInput);
    }
};

window.revokeShare = async function(shareId) {
    if (!confirm('Are you sure you want to revoke this share? This action cannot be undone.')) {
        return;
    }

    try {
        const response = await fetch(`/api/clinical-records/shares/${shareId}/revoke/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]')?.value
            },
            body: JSON.stringify({
                reason: 'Manually revoked by user'
            })
        });

        if (response.ok) {
            // Reload page to update the table
            window.location.reload();
        } else {
            const errorData = await response.json();
            alert('Failed to revoke share: ' + (errorData.error || 'Unknown error'));
        }
    } catch (error) {
        console.error('Error revoking share:', error);
        alert('Failed to revoke share: ' + error.message);
    }
};

window.resetForm = function() {
    if (window.secureSharingManager) {
        window.secureSharingManager.resetForm();
    }
};

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    window.secureSharingManager = new SecureSharingManager();
});