/**
 * Admin Panel JavaScript
 * Handles upload functionality, manga management, and admin interactions
 */

class AdminManager {
    constructor() {
        this.uploadProgress = null;
        this.currentUpload = null;
        this.init();
    }

    init() {
        this.setupFileUploads();
        this.setupDragAndDrop();
        this.setupFormValidation();
        this.setupBulkActions();
        this.bindEvents();
        
        // Admin Manager initialized (debug log removed)
    }

    setupFileUploads() {
        // Cover image preview
        const coverInput = document.getElementById('cover_image');
        if (coverInput) {
            coverInput.addEventListener('change', (e) => {
                this.previewCoverImage(e.target);
            });
        }

        // Chapter file validation
        const chapterInputs = document.querySelectorAll('input[name="chapter_files"]');
        chapterInputs.forEach(input => {
            input.addEventListener('change', (e) => {
                this.validateChapterFile(e.target);
            });
        });
    }

    setupDragAndDrop() {
        const uploadZones = document.querySelectorAll('.upload-zone, .chapter-upload-item');
        
        uploadZones.forEach(zone => {
            ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
                zone.addEventListener(eventName, this.preventDefaults, false);
            });

            ['dragenter', 'dragover'].forEach(eventName => {
                zone.addEventListener(eventName, () => this.highlight(zone), false);
            });

            ['dragleave', 'drop'].forEach(eventName => {
                zone.addEventListener(eventName, () => this.unhighlight(zone), false);
            });

            zone.addEventListener('drop', (e) => this.handleDrop(e, zone), false);
        });
    }

    setupFormValidation() {
        const uploadForm = document.getElementById('upload-form');
        if (uploadForm) {
            uploadForm.addEventListener('submit', (e) => {
                if (!this.validateUploadForm()) {
                    e.preventDefault();
                }
            });
        }

        // Real-time validation
        const requiredInputs = document.querySelectorAll('input[required], select[required]');
        requiredInputs.forEach(input => {
            input.addEventListener('blur', () => {
                this.validateField(input);
            });

            input.addEventListener('input', () => {
                if (input.classList.contains('is-invalid')) {
                    this.validateField(input);
                }
            });
        });
    }

    setupBulkActions() {
        const selectAllCheckbox = document.getElementById('select-all');
        if (selectAllCheckbox) {
            selectAllCheckbox.addEventListener('change', (e) => {
                const checkboxes = document.querySelectorAll('.manga-checkbox');
                checkboxes.forEach(cb => {
                    cb.checked = e.target.checked;
                });
                this.updateBulkActionsVisibility();
            });
        }

        const mangaCheckboxes = document.querySelectorAll('.manga-checkbox');
        mangaCheckboxes.forEach(cb => {
            cb.addEventListener('change', () => {
                this.updateBulkActionsVisibility();
            });
        });

        // Bulk action buttons
        const bulkDeleteBtn = document.getElementById('bulk-delete');
        if (bulkDeleteBtn) {
            bulkDeleteBtn.addEventListener('click', () => {
                this.handleBulkDelete();
            });
        }
    }

    bindEvents() {
        // Dynamic chapter addition
        const addChapterBtn = document.querySelector('[onclick*="addChapterUpload"]');
        if (addChapterBtn) {
            addChapterBtn.onclick = null; // Remove inline handler
            addChapterBtn.addEventListener('click', () => {
                this.addChapterUpload();
            });
        }

        // Category management
        const categoryCheckboxes = document.querySelectorAll('input[name="categories"]');
        categoryCheckboxes.forEach(cb => {
            cb.addEventListener('change', () => {
                this.updateCategoryCount();
            });
        });

        // Auto-save draft functionality
        const formInputs = document.querySelectorAll('#upload-form input, #upload-form textarea, #upload-form select');
        formInputs.forEach(input => {
            input.addEventListener('change', () => {
                this.saveDraft();
            });
        });

        // Load saved draft on page load
        this.loadDraft();
    }

    previewCoverImage(input) {
        if (input.files && input.files[0]) {
            const file = input.files[0];
            
            // Validate file type
            if (!file.type.startsWith('image/')) {
                this.showNotification('Please select a valid image file', 'error');
                input.value = '';
                return;
            }

            // Validate file size (max 5MB)
            if (file.size > 5 * 1024 * 1024) {
                this.showNotification('Cover image must be less than 5MB', 'error');
                input.value = '';
                return;
            }

            const reader = new FileReader();
            reader.onload = (e) => {
                const preview = document.getElementById('cover-preview');
                const previewImg = document.getElementById('cover-preview-img');
                
                if (preview && previewImg) {
                    previewImg.src = e.target.result;
                    preview.style.display = 'block';
                    
                    // Add image info
                    const img = new Image();
                    img.onload = () => {
                        const info = document.getElementById('image-info') || document.createElement('small');
                        info.id = 'image-info';
                        info.className = 'text-muted d-block mt-2';
                        info.textContent = `${img.width}x${img.height}px, ${this.formatFileSize(file.size)}`;
                        
                        if (!document.getElementById('image-info')) {
                            preview.appendChild(info);
                        }
                    };
                    img.src = e.target.result;
                }
            };
            reader.readAsDataURL(file);
        }
    }

    validateChapterFile(input) {
        if (input.files && input.files[0]) {
            const file = input.files[0];
            const allowedTypes = ['.zip', '.cbz', '.rar', '.cbr'];
            const fileExtension = '.' + file.name.split('.').pop().toLowerCase();
            
            if (!allowedTypes.includes(fileExtension)) {
                this.showNotification('Please select a valid archive file (.zip, .cbz, .rar, .cbr)', 'error');
                input.value = '';
                return false;
            }

            // Validate file size (max 100MB)
            if (file.size > 100 * 1024 * 1024) {
                this.showNotification('Chapter file must be less than 100MB', 'error');
                input.value = '';
                return false;
            }

            // Show file info
            const container = input.closest('.chapter-upload-item');
            let info = container.querySelector('.file-info');
            
            if (!info) {
                info = document.createElement('small');
                info.className = 'file-info text-muted d-block mt-1';
                container.appendChild(info);
            }
            
            info.textContent = `${file.name} (${this.formatFileSize(file.size)})`;
            return true;
        }
        return false;
    }

    addChapterUpload() {
        const container = document.getElementById('chapter-uploads');
        const count = container.children.length + 1;
        
        const newUpload = document.createElement('div');
        newUpload.className = 'chapter-upload-item mb-3';
        
        // Create structure using safe DOM methods
        const outerDiv = document.createElement('div');
        outerDiv.className = 'd-flex align-items-start';
        
        const contentDiv = document.createElement('div');
        contentDiv.className = 'flex-grow-1 me-2';
        
        const label = document.createElement('label');
        label.className = 'form-label';
        label.textContent = `Chapter ${count}`;
        
        const input = document.createElement('input');
        input.type = 'file';
        input.className = 'form-control';
        input.name = 'chapter_files';
        input.accept = '.zip,.cbz,.rar,.cbr';
        
        const helpText = document.createElement('div');
        helpText.className = 'form-text';
        helpText.textContent = 'Upload chapter as ZIP/CBZ/RAR/CBR file containing images';
        
        const removeBtn = document.createElement('button');
        removeBtn.type = 'button';
        removeBtn.className = 'btn btn-outline-danger mt-4';
        removeBtn.onclick = function() {
            this.closest('.chapter-upload-item').remove();
            adminManager.updateChapterNumbers();
        };
        
        const icon = document.createElement('i');
        icon.className = 'fas fa-times';
        removeBtn.appendChild(icon);
        
        // Assemble the structure
        contentDiv.appendChild(label);
        contentDiv.appendChild(input);
        contentDiv.appendChild(helpText);
        outerDiv.appendChild(contentDiv);
        outerDiv.appendChild(removeBtn);
        newUpload.appendChild(outerDiv);
        
        container.appendChild(newUpload);
        
        // Add event listener for the new file input
        const newInput = newUpload.querySelector('input[type="file"]');
        newInput.addEventListener('change', (e) => {
            this.validateChapterFile(e.target);
        });

        this.showNotification('Chapter upload field added', 'success');
    }

    updateChapterNumbers() {
        const items = document.querySelectorAll('.chapter-upload-item');
        items.forEach((item, index) => {
            const label = item.querySelector('label');
            if (label) {
                label.textContent = `Chapter ${index + 1}`;
            }
        });
    }

    validateUploadForm() {
        let isValid = true;
        const errors = [];

        // Validate title
        const title = document.getElementById('title');
        if (!title || !title.value.trim()) {
            errors.push('Title is required');
            this.markFieldInvalid(title);
            isValid = false;
        }

        // Validate at least one category
        const selectedCategories = document.querySelectorAll('input[name="categories"]:checked');
        if (selectedCategories.length === 0) {
            errors.push('Please select at least one category');
            isValid = false;
        }

        // Validate chapter files
        const chapterFiles = document.querySelectorAll('input[name="chapter_files"]');
        let hasValidChapters = false;
        
        chapterFiles.forEach(input => {
            if (input.files && input.files[0]) {
                hasValidChapters = true;
            }
        });

        if (!hasValidChapters) {
            errors.push('Please upload at least one chapter');
            isValid = false;
        }

        if (errors.length > 0) {
            this.showNotification(errors.join('<br>'), 'error');
        }

        return isValid;
    }

    validateField(field) {
        const value = field.value.trim();
        let isValid = true;

        if (field.hasAttribute('required') && !value) {
            isValid = false;
        }

        if (field.type === 'email' && value && !this.isValidEmail(value)) {
            isValid = false;
        }

        if (field.hasAttribute('minlength') && value.length < parseInt(field.getAttribute('minlength'))) {
            isValid = false;
        }

        if (isValid) {
            field.classList.remove('is-invalid');
            field.classList.add('is-valid');
        } else {
            field.classList.remove('is-valid');
            field.classList.add('is-invalid');
        }

        return isValid;
    }

    markFieldInvalid(field) {
        if (field) {
            field.classList.add('is-invalid');
            field.focus();
        }
    }

    updateCategoryCount() {
        const selectedCount = document.querySelectorAll('input[name="categories"]:checked').length;
        let counter = document.getElementById('category-counter');
        
        if (!counter) {
            counter = document.createElement('small');
            counter.id = 'category-counter';
            counter.className = 'text-muted';
            
            const categoriesContainer = document.querySelector('input[name="categories"]').closest('.card-body');
            if (categoriesContainer) {
                categoriesContainer.appendChild(counter);
            }
        }
        
        counter.textContent = `${selectedCount} categories selected`;
    }

    saveDraft() {
        const formData = new FormData(document.getElementById('upload-form'));
        const draft = {};
        
        for (let [key, value] of formData.entries()) {
            if (key !== 'chapter_files' && key !== 'cover_image') {
                if (draft[key]) {
                    if (Array.isArray(draft[key])) {
                        draft[key].push(value);
                    } else {
                        draft[key] = [draft[key], value];
                    }
                } else {
                    draft[key] = value;
                }
            }
        }
        
        localStorage.setItem('mangaUploadDraft', JSON.stringify(draft));
    }

    loadDraft() {
        const draftData = localStorage.getItem('mangaUploadDraft');
        if (!draftData) return;
        
        try {
            const draft = JSON.parse(draftData);
            
            Object.keys(draft).forEach(key => {
                const field = document.querySelector(`[name="${key}"]`);
                if (field) {
                    if (field.type === 'checkbox') {
                        const values = Array.isArray(draft[key]) ? draft[key] : [draft[key]];
                        const checkboxes = document.querySelectorAll(`[name="${key}"]`);
                        
                        checkboxes.forEach(cb => {
                            cb.checked = values.includes(cb.value);
                        });
                    } else {
                        field.value = draft[key];
                    }
                }
            });
            
            this.showNotification('Draft loaded', 'info');
        } catch (error) {
            console.error('Error loading draft:', error);
        }
    }

    clearDraft() {
        localStorage.removeItem('mangaUploadDraft');
        this.showNotification('Draft cleared', 'info');
    }

    updateBulkActionsVisibility() {
        const checkedBoxes = document.querySelectorAll('.manga-checkbox:checked');
        const bulkActions = document.getElementById('bulk-actions');
        
        if (bulkActions) {
            if (checkedBoxes.length > 0) {
                bulkActions.style.display = 'block';
                document.getElementById('selected-count').textContent = checkedBoxes.length;
            } else {
                bulkActions.style.display = 'none';
            }
        }
    }

    handleBulkDelete() {
        const checkedBoxes = document.querySelectorAll('.manga-checkbox:checked');
        const mangaIds = Array.from(checkedBoxes).map(cb => cb.value);
        
        if (mangaIds.length === 0) return;
        
        const confirmed = confirm(`Are you sure you want to delete ${mangaIds.length} manga series? This action cannot be undone.`);
        
        if (confirmed) {
            // This would typically send a request to a bulk delete endpoint
            console.log('Bulk delete:', mangaIds);
            this.showNotification(`Deleted ${mangaIds.length} manga series`, 'success');
            
            // Remove rows from table
            checkedBoxes.forEach(cb => {
                const row = cb.closest('tr');
                if (row) {
                    row.remove();
                }
            });
            
            this.updateBulkActionsVisibility();
        }
    }

    // Drag and drop helpers
    preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }

    highlight(element) {
        element.classList.add('dragover');
    }

    unhighlight(element) {
        element.classList.remove('dragover');
    }

    handleDrop(e, zone) {
        const dt = e.dataTransfer;
        const files = dt.files;
        
        if (files.length > 0) {
            const input = zone.querySelector('input[type="file"]');
            if (input) {
                input.files = files;
                
                // Trigger change event
                const event = new Event('change', { bubbles: true });
                input.dispatchEvent(event);
            }
        }
    }

    // Utility functions
    formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    isValidEmail(email) {
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        return emailRegex.test(email);
    }

    showNotification(message, type = 'info') {
        // Create notification element
        const notification = document.createElement('div');
        notification.className = `alert alert-${type === 'error' ? 'danger' : type} alert-dismissible fade show position-fixed`;
        notification.style.cssText = `
            top: 20px;
            right: 20px;
            z-index: 9999;
            min-width: 300px;
            max-width: 500px;
        `;
        
        // Safe DOM manipulation - prevents XSS
        const messageDiv = document.createElement('div');
        messageDiv.textContent = message;
        notification.appendChild(messageDiv);
        
        const closeButton = document.createElement('button');
        closeButton.type = 'button';
        closeButton.className = 'btn-close';
        closeButton.setAttribute('data-bs-dismiss', 'alert');
        notification.appendChild(closeButton);

        document.body.appendChild(notification);

        // Auto-remove after 5 seconds
        setTimeout(() => {
            if (notification.parentNode) {
                notification.remove();
            }
        }, 5000);
    }
}

// Statistics Dashboard
class StatsDashboard {
    constructor() {
        this.charts = {};
        this.init();
    }

    init() {
        this.setupRefreshButton();
        this.loadStats();
        
        // Auto-refresh every 5 minutes
        setInterval(() => {
            this.loadStats();
        }, 5 * 60 * 1000);
    }

    setupRefreshButton() {
        const refreshBtn = document.getElementById('refresh-stats');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => {
                this.loadStats();
            });
        }
    }

    async loadStats() {
        try {
            // This would typically fetch from an API endpoint
            const stats = await this.fetchStats();
            this.updateStatCards(stats);
            this.updateCharts(stats);
        } catch (error) {
            console.error('Error loading stats:', error);
        }
    }

    async fetchStats() {
        // Simulated stats - in real implementation, this would fetch from server
        return {
            totalManga: parseInt(document.querySelector('.card.bg-primary h2')?.textContent || '0'),
            totalChapters: parseInt(document.querySelector('.card.bg-success h2')?.textContent || '0'),
            totalUsers: parseInt(document.querySelector('.card.bg-info h2')?.textContent || '0'),
            weeklyViews: 12500,
            monthlyViews: 48000,
            popularGenres: [
                { name: 'Action', count: 45 },
                { name: 'Romance', count: 38 },
                { name: 'Fantasy', count: 32 },
                { name: 'Comedy', count: 28 },
                { name: 'Drama', count: 25 }
            ]
        };
    }

    updateStatCards(stats) {
        const cards = [
            { selector: '.card.bg-primary h2', value: stats.totalManga },
            { selector: '.card.bg-success h2', value: stats.totalChapters },
            { selector: '.card.bg-info h2', value: stats.totalUsers }
        ];

        cards.forEach(card => {
            const element = document.querySelector(card.selector);
            if (element) {
                this.animateNumber(element, parseInt(element.textContent), card.value);
            }
        });
    }

    updateCharts(stats) {
        // This would update any charts on the dashboard
        console.log('Updating charts with stats:', stats);
    }

    animateNumber(element, start, end, duration = 1000) {
        const startTime = performance.now();
        
        const animate = (currentTime) => {
            const elapsed = currentTime - startTime;
            const progress = Math.min(elapsed / duration, 1);
            
            const current = Math.floor(start + (end - start) * progress);
            element.textContent = current.toLocaleString();
            
            if (progress < 1) {
                requestAnimationFrame(animate);
            }
        };
        
        requestAnimationFrame(animate);
    }
}

// Quick Edit Modal
class QuickEditModal {
    constructor() {
        this.modal = null;
        this.currentMangaId = null;
        this.init();
    }

    init() {
        this.modal = document.getElementById('editModal');
        if (this.modal) {
            this.bindEvents();
        }
    }

    bindEvents() {
        const saveBtn = this.modal.querySelector('.btn-primary');
        if (saveBtn) {
            saveBtn.addEventListener('click', () => {
                this.saveChanges();
            });
        }
    }

    open(mangaId, mangaData = null) {
        this.currentMangaId = mangaId;
        
        if (mangaData) {
            this.populateForm(mangaData);
        } else {
            this.loadMangaData(mangaId);
        }
        
        const modalInstance = new bootstrap.Modal(this.modal);
        modalInstance.show();
    }

    async loadMangaData(mangaId) {
        try {
            // This would fetch manga data from server
            const baseUrl = window.MANGA_PLATFORM ? window.MANGA_PLATFORM.baseUrl : '';
            const response = await fetch(`${baseUrl}/api/manga/${mangaId}`);
            const data = await response.json();
            this.populateForm(data);
        } catch (error) {
            console.error('Error loading manga data:', error);
        }
    }

    populateForm(data) {
        const fields = ['title', 'author', 'status', 'type', 'language', 'description'];
        
        fields.forEach(field => {
            const input = this.modal.querySelector(`#edit-${field}`);
            if (input && data[field]) {
                input.value = data[field];
            }
        });
    }

    async saveChanges() {
        const formData = new FormData();
        const fields = ['title', 'author', 'status', 'type', 'language', 'description'];
        
        fields.forEach(field => {
            const input = this.modal.querySelector(`#edit-${field}`);
            if (input) {
                formData.append(field, input.value);
            }
        });
        
        try {
            const response = await fetch(`/api/manga/${this.currentMangaId}`, {
                method: 'PUT',
                body: formData
            });
            
            if (response.ok) {
                adminManager.showNotification('Manga updated successfully', 'success');
                
                // Close modal
                const modalInstance = bootstrap.Modal.getInstance(this.modal);
                modalInstance.hide();
                
                // Refresh page or update row
                setTimeout(() => {
                    window.location.reload();
                }, 1000);
            } else {
                throw new Error('Failed to update manga');
            }
        } catch (error) {
            console.error('Error saving changes:', error);
            adminManager.showNotification('Error updating manga', 'error');
        }
    }
}

// Initialize admin components
document.addEventListener('DOMContentLoaded', function() {
    // Initialize main admin manager
    window.adminManager = new AdminManager();
    
    // Initialize dashboard if on dashboard page
    if (document.querySelector('.card.bg-primary')) {
        window.statsDashboard = new StatsDashboard();
    }
    
    // Initialize quick edit modal
    window.quickEditModal = new QuickEditModal();
    
    // Global functions for inline event handlers
    window.editManga = function(mangaId) {
        window.quickEditModal.open(mangaId);
    };
    
    window.addChapter = function(mangaId) {
        // Redirect to chapter upload or show modal
        window.location.href = `/admin/add-chapter/${mangaId}`;
    };
    
    window.confirmDelete = function(mangaId, mangaTitle) {
        document.getElementById('delete-manga-title').textContent = mangaTitle;
        document.getElementById('delete-form').action = `/admin/delete_manga/${mangaId}`;
        new bootstrap.Modal(document.getElementById('deleteModal')).show();
    };
    
    // Admin JavaScript initialized successfully (debug log removed)
});

// Category Management Functions
function toggleCategoryStatus(categoryId) {
    if (confirm('Are you sure you want to toggle this category status?')) {
        const form = document.createElement('form');
        form.method = 'POST';
        form.action = `/admin/categories/toggle/${categoryId}`;
        document.body.appendChild(form);
        form.submit();
    }
}

function duplicateCategory(categoryId) {
    if (confirm('Are you sure you want to duplicate this category?')) {
        const form = document.createElement('form');
        form.method = 'POST';
        form.action = `/admin/categories/duplicate/${categoryId}`;
        document.body.appendChild(form);
        form.submit();
    }
}

function deleteCategory(categoryId) {
    if (confirm('Are you sure you want to delete this category? This action cannot be undone.')) {
        const form = document.createElement('form');
        form.method = 'POST';
        form.action = `/admin/categories/delete/${categoryId}`;
        document.body.appendChild(form);
        form.submit();
    }
}

function editCategory(categoryId) {
    window.location.href = `/admin/categories/edit/${categoryId}`;
}

// User Management Functions
function toggleUserStatus(userId) {
    if (confirm('Are you sure you want to toggle this user status?')) {
        const form = document.createElement('form');
        form.method = 'POST';
        form.action = `/admin/users/toggle-active/${userId}`;
        document.body.appendChild(form);
        form.submit();
    }
}

function editUser(userId) {
    console.log('Edit user:', userId);
}

function sendMessage(userId) {
    const message = prompt('Enter message to send:');
    if (message && message.trim()) {
        const form = document.createElement('form');
        form.method = 'POST';
        form.action = `/admin/users/send-message/${userId}`;
        
        const input = document.createElement('input');
        input.type = 'hidden';
        input.name = 'message';
        input.value = message;
        form.appendChild(input);
        
        document.body.appendChild(form);
        form.submit();
    }
}

function resetPassword(userId) {
    if (confirm('Are you sure you want to reset this user\'s password? A new temporary password will be generated.')) {
        const form = document.createElement('form');
        form.method = 'POST';
        form.action = `/admin/users/reset-password/${userId}`;
        document.body.appendChild(form);
        form.submit();
    }
}

function exportCategory(categoryId) {
    alert('Export functionality would be implemented here');
}

function bulkReorder() {
    alert('Bulk reorder functionality would be implemented here');
}

// Global functions accessible from templates
window.toggleCategoryStatus = toggleCategoryStatus;
window.duplicateCategory = duplicateCategory;
window.deleteCategory = deleteCategory;
window.editCategory = editCategory;
window.toggleUserStatus = toggleUserStatus;
window.editUser = editUser;
window.sendMessage = sendMessage;
window.resetPassword = resetPassword;
window.exportCategory = exportCategory;
window.bulkReorder = bulkReorder;

// Export for testing
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { AdminManager, StatsDashboard, QuickEditModal };
}
