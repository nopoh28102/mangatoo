/**
 * Main JavaScript file for Manga Platform
 * Handles theme switching, language toggle, and general interactions
 */

// Dynamic URL utilities
const MangaURL = {
    /**
     * Generate API URL dynamically
     */
    api: function(endpoint) {
        const baseUrl = window.MANGA_PLATFORM ? window.MANGA_PLATFORM.baseUrl : '';
        return `${baseUrl}/api/${endpoint.replace(/^\//, '')}`;
    },
    
    /**
     * Generate absolute URL for any path
     */
    url: function(path) {
        const baseUrl = window.MANGA_PLATFORM ? window.MANGA_PLATFORM.baseUrl : '';
        return `${baseUrl}/${path.replace(/^\//, '')}`;
    },
    
    /**
     * Get current base URL
     */
    base: function() {
        return window.MANGA_PLATFORM ? window.MANGA_PLATFORM.baseUrl : '';
    }
};

// Theme Management
class ThemeManager {
    constructor() {
        this.currentTheme = localStorage.getItem('theme') || 'light';
        this.init();
    }

    init() {
        this.applyTheme(this.currentTheme);
        this.bindEvents();
    }

    bindEvents() {
        const themeToggle = document.getElementById('theme-toggle');
        if (themeToggle) {
            themeToggle.addEventListener('click', () => this.toggleTheme());
        }
    }

    toggleTheme() {
        this.currentTheme = this.currentTheme === 'light' ? 'dark' : 'light';
        this.applyTheme(this.currentTheme);
        localStorage.setItem('theme', this.currentTheme);
    }

    applyTheme(theme) {
        document.documentElement.setAttribute('data-bs-theme', theme);
        
        const themeToggle = document.getElementById('theme-toggle');
        if (themeToggle) {
            const icon = themeToggle.querySelector('i');
            if (theme === 'dark') {
                icon.className = 'fas fa-sun';
                themeToggle.title = 'Switch to Light Mode';
            } else {
                icon.className = 'fas fa-moon';
                themeToggle.title = 'Switch to Dark Mode';
            }
        }
        
        // Update mobile status bar color
        this.updateStatusBarColor(theme);
    }
    
    updateStatusBarColor(theme) {
        // Keep status bar black always
        let themeColorMeta = document.querySelector('meta[name="theme-color"]');
        if (themeColorMeta) {
            themeColorMeta.content = '#000000';
        }
        
        // Keep apple status bar black translucent
        let appleStatusBar = document.querySelector('meta[name="apple-mobile-web-app-status-bar-style"]');
        if (appleStatusBar) {
            appleStatusBar.content = 'black-translucent';
        }
    }
}

// Language Management
class LanguageManager {
    constructor() {
        this.currentLang = localStorage.getItem('language') || 'en';
        this.init();
    }

    init() {
        // Only apply language if not already applied to prevent flicker
        if (!document.documentElement.classList.contains('lang-' + this.currentLang)) {
            this.applyLanguage(this.currentLang);
        }
        this.bindEvents();
    }

    bindEvents() {
        const langToggle = document.getElementById('lang-toggle');
        const mobileLangToggle = document.getElementById('mobile-lang-toggle');
        
        if (langToggle) {
            langToggle.addEventListener('click', () => this.toggleLanguage());
        }
        if (mobileLangToggle) {
            mobileLangToggle.addEventListener('click', () => this.toggleLanguage());
        }
    }

    toggleLanguage() {
        this.currentLang = this.currentLang === 'en' ? 'ar' : 'en';
        this.applyLanguage(this.currentLang);
        localStorage.setItem('language', this.currentLang);
    }

    applyLanguage(lang) {
        // Prevent white page during language change
        document.body.style.opacity = '1';
        document.body.style.visibility = 'visible';
        
        // Remove old language classes
        document.documentElement.className = document.documentElement.className.replace(/\blang-[a-z]{2}\b/g, '');
        document.documentElement.classList.add('lang-' + lang);
        
        document.documentElement.lang = lang;
        document.documentElement.dir = lang === 'ar' ? 'rtl' : 'ltr';
        
        // Add/remove language classes
        document.body.className = document.body.className.replace(/\b(rtl-mode|ltr-mode)\b/g, '');
        document.body.classList.add(lang === 'ar' ? 'rtl-mode' : 'ltr-mode');
        
        // Store current language in body data attribute for CSS targeting
        document.body.setAttribute('data-lang', lang);
        
        // Handle language elements with proper display management - prevent white page
        const allLangElements = document.querySelectorAll('[data-lang]');
        
        // First, show all elements for current language
        allLangElements.forEach(element => {
            const elementLang = element.getAttribute('data-lang');
            
            if (elementLang === lang) {
                // Show elements for current language immediately
                element.style.display = '';
                element.style.visibility = 'visible';
                element.removeAttribute('hidden');
                element.style.opacity = '1';
            }
        });
        
        // Then hide elements for other languages with a small delay to prevent flicker
        setTimeout(() => {
            allLangElements.forEach(element => {
                const elementLang = element.getAttribute('data-lang');
                
                if (elementLang !== lang) {
                    element.style.display = 'none';
                    element.style.visibility = 'hidden';
                    element.setAttribute('hidden', '');
                    element.style.opacity = '0';
                }
            });
        }, 10);
        
        // Update placeholders dynamically
        this.updatePlaceholders(lang);
        
        // Update titles and other attributes
        this.updateTitles(lang);
        
        // Update select options with proper translations
        this.updateSelectOptions(lang);
        
        // Update text content for special elements
        this.updateTextContent(lang);
        
        // Update accessibility attributes
        this.updateAriaLabels(lang);

        // Update toggle buttons
        this.updateToggleButtons(lang);

        // Update CSS style for immediate language application
        const existingStyle = document.getElementById('initial-lang-style');
        if (existingStyle) {
            existingStyle.textContent = `
                [data-lang]:not([data-lang="${lang}"]) {
                    display: none !important;
                    visibility: hidden !important;
                    opacity: 0 !important;
                }
                [data-lang="${lang}"] {
                    display: initial !important;
                    visibility: visible !important;
                    opacity: 1 !important;
                }
                
                /* Ensure body content is visible during language switch */
                body {
                    min-height: 100vh;
                    background-color: var(--bs-body-bg, #fff);
                    opacity: 1 !important;
                    visibility: visible !important;
                }
                
                /* Prevent layout shift during language change */
                .container, .container-fluid {
                    opacity: 1 !important;
                    visibility: visible !important;
                }
            `;
        }

        // Trigger custom event for other components to listen to
        window.dispatchEvent(new CustomEvent('languageChanged', { 
            detail: { language: lang } 
        }));
    }

    updatePlaceholders(lang) {
        const inputsWithPlaceholders = document.querySelectorAll('[placeholder-en], [placeholder-ar]');
        inputsWithPlaceholders.forEach(input => {
            const enPlaceholder = input.getAttribute('placeholder-en');
            const arPlaceholder = input.getAttribute('placeholder-ar');
            
            if (lang === 'ar' && arPlaceholder) {
                input.placeholder = arPlaceholder;
            } else if (lang === 'en' && enPlaceholder) {
                input.placeholder = enPlaceholder;
            }
        });
    }

    updateTitles(lang) {
        const elementsWithTitles = document.querySelectorAll('[title-en], [title-ar]');
        elementsWithTitles.forEach(element => {
            const enTitle = element.getAttribute('title-en');
            const arTitle = element.getAttribute('title-ar');
            
            if (lang === 'ar' && arTitle) {
                element.title = arTitle;
            } else if (lang === 'en' && enTitle) {
                element.title = enTitle;
            }
        });
    }

    updateSelectOptions(lang) {
        const selectElements = document.querySelectorAll('select');
        selectElements.forEach(select => {
            const options = select.querySelectorAll('option');
            options.forEach(option => {
                const langElements = option.querySelectorAll('[data-lang]');
                langElements.forEach(el => {
                    const elementLang = el.getAttribute('data-lang');
                    if (elementLang === lang) {
                        option.textContent = el.textContent;
                    }
                });
            });
        });
    }

    updateTextContent(lang) {
        const elementsWithText = document.querySelectorAll('[text-en], [text-ar]');
        elementsWithText.forEach(element => {
            const enText = element.getAttribute('text-en');
            const arText = element.getAttribute('text-ar');
            
            if (lang === 'ar' && arText) {
                element.textContent = arText;
            } else if (lang === 'en' && enText) {
                element.textContent = enText;
            }
        });
    }

    updateAriaLabels(lang) {
        const elementsWithAriaLabel = document.querySelectorAll('[aria-label-en], [aria-label-ar]');
        elementsWithAriaLabel.forEach(element => {
            const enAriaLabel = element.getAttribute('aria-label-en');
            const arAriaLabel = element.getAttribute('aria-label-ar');
            
            if (lang === 'ar' && arAriaLabel) {
                element.setAttribute('aria-label', arAriaLabel);
            } else if (lang === 'en' && enAriaLabel) {
                element.setAttribute('aria-label', enAriaLabel);
            }
        });
    }

    updateToggleButtons(lang) {
        const langToggle = document.getElementById('lang-toggle');
        const mobileLangToggle = document.getElementById('mobile-lang-toggle');
        
        [langToggle, mobileLangToggle].forEach(toggle => {
            if (toggle) {
                const flagIcon = toggle.querySelector('.flag-icon');
                const textSpan = toggle.querySelector('.lang-text');
                
                if (lang === 'ar') {
                    toggle.innerHTML = '<i class="fas fa-language"></i>';
                    toggle.title = 'تغيير إلى الإنجليزية';
                } else {
                    toggle.innerHTML = '<i class="fas fa-language"></i>';
                    toggle.title = 'Switch to Arabic';
                }
            }
        });
        
        if (langToggle) {
            langToggle.title = lang === 'en' ? 'التبديل إلى العربية' : 'Switch to English';
        }
        if (mobileLangToggle) {
            mobileLangToggle.title = lang === 'en' ? 'التبديل إلى العربية' : 'Switch to English';
        }

        // Update form labels
        const labelsWithLang = document.querySelectorAll('[label-en], [label-ar]');
        labelsWithLang.forEach(label => {
            const enLabel = label.getAttribute('label-en');
            const arLabel = label.getAttribute('label-ar');
            
            if (lang === 'ar' && arLabel) {
                label.textContent = arLabel;
            } else if (lang === 'en' && enLabel) {
                label.textContent = enLabel;
            }
        });

        // Update page title if available
        const titleElements = document.querySelectorAll('title[title-en], title[title-ar]');
        titleElements.forEach(titleEl => {
            const enTitle = titleEl.getAttribute('title-en');
            const arTitle = titleEl.getAttribute('title-ar');
            
            if (lang === 'ar' && arTitle) {
                document.title = arTitle;
            } else if (lang === 'en' && enTitle) {
                document.title = enTitle;
            }
        });

        // Trigger custom event for other components to listen to
        window.dispatchEvent(new CustomEvent('languageChanged', { 
            detail: { language: lang } 
        }));
    }
}

// Manga Card Interactions
class MangaCardManager {
    constructor() {
        this.init();
    }

    init() {
        this.bindEvents();
        this.setupLazyLoading();
    }

    bindEvents() {
        // Bookmark functionality
        document.addEventListener('click', (e) => {
            if (e.target.closest('.bookmark-btn')) {
                e.preventDefault();
                this.handleBookmark(e.target.closest('.bookmark-btn'));
            }
        });

        // Rating functionality
        document.addEventListener('click', (e) => {
            if (e.target.classList.contains('rating-star')) {
                this.handleRating(e.target);
            }
        });
    }

    setupLazyLoading() {
        if ('IntersectionObserver' in window) {
            const imageObserver = new IntersectionObserver((entries, observer) => {
                entries.forEach(entry => {
                    if (entry.isIntersecting) {
                        const img = entry.target;
                        img.src = img.dataset.src;
                        img.classList.remove('lazy');
                        observer.unobserve(img);
                    }
                });
            });

            document.querySelectorAll('img[data-src]').forEach(img => {
                imageObserver.observe(img);
            });
        }
    }

    async handleBookmark(button) {
        const mangaId = button.dataset.mangaId;
        
        try {
            const response = await fetch(MangaURL.url(`bookmark/${mangaId}`), {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                }
            });

            const data = await response.json();
            
            if (data.status === 'success') {
                const icon = button.querySelector('i');
                const text = button.querySelector('.btn-text');
                
                if (data.action === 'added') {
                    icon.className = 'fas fa-bookmark';
                    button.classList.remove('btn-outline-warning');
                    button.classList.add('btn-warning');
                    if (text) text.textContent = 'Bookmarked';
                    this.showNotification('Added to bookmarks', 'success');
                } else {
                    icon.className = 'far fa-bookmark';
                    button.classList.remove('btn-warning');
                    button.classList.add('btn-outline-warning');
                    if (text) text.textContent = 'Bookmark';
                    this.showNotification('Removed from bookmarks', 'info');
                }
            }
        } catch (error) {
            console.error('Bookmark error:', error);
            this.showNotification('Error updating bookmark', 'error');
        }
    }

    async handleRating(star) {
        const container = star.closest('.rating-stars');
        const mangaId = container.dataset.mangaId;
        const rating = parseInt(star.dataset.rating);

        try {
            const response = await fetch(MangaURL.url(`rate/${mangaId}`), {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ rating: rating })
            });

            const data = await response.json();
            
            if (data.status === 'success') {
                // Update star display
                const stars = container.querySelectorAll('.rating-star');
                stars.forEach((s, index) => {
                    if (index < rating) {
                        s.classList.add('active');
                    } else {
                        s.classList.remove('active');
                    }
                });

                container.dataset.currentRating = rating;
                this.showNotification(`Rated ${rating} stars`, 'success');
            }
        } catch (error) {
            console.error('Rating error:', error);
            this.showNotification('Error submitting rating', 'error');
        }
    }

    showNotification(message, type = 'info') {
        const notification = document.createElement('div');
        notification.className = `alert alert-${type === 'error' ? 'danger' : type} alert-dismissible fade show position-fixed`;
        notification.style.top = '20px';
        notification.style.right = '20px';
        notification.style.zIndex = '9999';
        notification.style.minWidth = '300px';
        
        // Safe DOM manipulation - prevents XSS
        notification.textContent = message;
        
        const closeButton = document.createElement('button');
        closeButton.type = 'button';
        closeButton.className = 'btn-close';
        closeButton.setAttribute('data-bs-dismiss', 'alert');
        notification.appendChild(closeButton);

        document.body.appendChild(notification);

        // Auto-remove after 3 seconds
        setTimeout(() => {
            if (notification.parentNode) {
                notification.remove();
            }
        }, 3000);
    }
}

// Search Enhancement
class SearchManager {
    constructor() {
        this.searchInput = document.querySelector('input[name="search"]');
        this.init();
    }

    init() {
        if (this.searchInput) {
            this.bindEvents();
            this.setupAutoComplete();
        }
    }

    bindEvents() {
        let searchTimeout;
        
        this.searchInput.addEventListener('input', (e) => {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(() => {
                this.handleSearch(e.target.value);
            }, 300);
        });

        // Clear search
        const clearBtn = document.createElement('button');
        clearBtn.type = 'button';
        clearBtn.className = 'btn btn-outline-secondary position-absolute end-0 top-50 translate-middle-y me-2';
        clearBtn.innerHTML = '<i class="fas fa-times"></i>';
        clearBtn.style.display = 'none';
        clearBtn.style.zIndex = '10';

        const searchContainer = this.searchInput.parentElement;
        if (searchContainer.classList.contains('d-flex')) {
            searchContainer.style.position = 'relative';
            searchContainer.appendChild(clearBtn);

            clearBtn.addEventListener('click', () => {
                this.searchInput.value = '';
                this.searchInput.focus();
                clearBtn.style.display = 'none';
            });

            this.searchInput.addEventListener('input', (e) => {
                clearBtn.style.display = e.target.value ? 'block' : 'none';
            });
        }
    }

    setupAutoComplete() {
        // This would implement autocomplete functionality
        // For now, we'll just add visual feedback
        this.searchInput.addEventListener('focus', () => {
            this.searchInput.parentElement.classList.add('shadow-sm');
        });

        this.searchInput.addEventListener('blur', () => {
            this.searchInput.parentElement.classList.remove('shadow-sm');
        });
    }

    handleSearch(query) {
        if (query.length >= 2) {
            // Implement search suggestions or instant search
            console.log('Searching for:', query);
        }
    }
}

// Keyboard Navigation
class KeyboardNavigationManager {
    constructor() {
        this.init();
    }

    init() {
        document.addEventListener('keydown', (e) => {
            // Only handle shortcuts when not typing in inputs
            if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') {
                return;
            }

            switch (e.key) {
                case 'Escape':
                    this.handleEscape();
                    break;
                case 'f':
                case 'F':
                    if (e.ctrlKey || e.metaKey) {
                        e.preventDefault();
                        this.focusSearch();
                    }
                    break;
                case 't':
                case 'T':
                    if (e.ctrlKey || e.metaKey) {
                        e.preventDefault();
                        this.toggleTheme();
                    }
                    break;
                case 'h':
                case 'H':
                    if (e.ctrlKey || e.metaKey) {
                        e.preventDefault();
                        this.goHome();
                    }
                    break;
            }
        });
    }

    handleEscape() {
        // Close any open modals or overlays
        const activeModal = document.querySelector('.modal.show');
        if (activeModal) {
            const modal = bootstrap.Modal.getInstance(activeModal);
            if (modal) {
                modal.hide();
            }
        }
    }

    focusSearch() {
        const searchInput = document.querySelector('input[name="search"]');
        if (searchInput) {
            searchInput.focus();
            searchInput.select();
        }
    }

    toggleTheme() {
        const themeToggle = document.getElementById('theme-toggle');
        if (themeToggle) {
            themeToggle.click();
        }
    }

    goHome() {
        window.location.href = '/';
    }
}

// Performance Monitoring
class PerformanceManager {
    constructor() {
        this.init();
    }

    init() {
        this.monitorPageLoad();
        this.setupPerformanceObserver();
    }

    monitorPageLoad() {
        window.addEventListener('load', () => {
            const loadTime = performance.now();
            // Only log in development mode
            if (window.location.hostname === 'localhost' || window.location.hostname.includes('127.0.0.1')) {
                console.log(`Page loaded in ${loadTime.toFixed(2)}ms`);
            }
            
            // Report to analytics or monitoring service
            this.reportPerformance('page_load', loadTime);
        });
    }

    setupPerformanceObserver() {
        if ('PerformanceObserver' in window) {
            const observer = new PerformanceObserver((list) => {
                list.getEntries().forEach((entry) => {
                    if (entry.entryType === 'largest-contentful-paint') {
                        // Only log in development mode
                        if (window.location.hostname === 'localhost' || window.location.hostname.includes('127.0.0.1')) {
                            console.log('LCP:', entry.startTime);
                        }
                        this.reportPerformance('lcp', entry.startTime);
                    }
                });
            });

            observer.observe({ entryTypes: ['largest-contentful-paint'] });
        }
    }

    reportPerformance(metric, value) {
        // This would send data to your analytics service
        // Only log in development mode
        if (window.location.hostname === 'localhost' || window.location.hostname.includes('127.0.0.1')) {
            console.log(`Performance metric - ${metric}: ${value}`);
        }
    }
}

// Error Handling
class ErrorManager {
    constructor() {
        this.init();
    }

    init() {
        window.addEventListener('error', (event) => {
            this.handleError(event.error, event.filename, event.lineno);
        });

        window.addEventListener('unhandledrejection', (event) => {
            this.handlePromiseRejection(event.reason);
        });
    }

    handleError(error, filename, lineno) {
        console.error('JavaScript Error:', error, filename, lineno);
        // Report to error tracking service
    }

    handlePromiseRejection(reason) {
        console.error('Unhandled Promise Rejection:', reason);
        // Report to error tracking service
    }
}

// Mobile Search Toggle Function
function initMobileSearch() {
    const mobileSearchToggle = document.getElementById('mobile-search-toggle');
    const mobileSearchBar = document.getElementById('mobileSearchBar');
    const mobileSearchClose = document.getElementById('mobile-search-close');
    const mobileSearchInput = document.getElementById('mobileHeaderSearch');

    // Only log in development mode
    if (window.location.hostname === 'localhost' || window.location.hostname.includes('127.0.0.1')) {
        console.log('Initializing mobile search...', {
            toggle: !!mobileSearchToggle,
            bar: !!mobileSearchBar,
            close: !!mobileSearchClose,
            input: !!mobileSearchInput
        });
    }

    if (mobileSearchToggle && mobileSearchBar) {
        // Show mobile search
        mobileSearchToggle.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            // Debug log removed for cleaner console
            
            // Toggle visibility
            if (mobileSearchBar.classList.contains('show')) {
                mobileSearchBar.classList.remove('show');
            } else {
                mobileSearchBar.classList.add('show');
                // Focus on input after animation
                setTimeout(() => {
                    if (mobileSearchInput) {
                        mobileSearchInput.focus();
                    }
                }, 150);
            }
        });

        // Hide mobile search
        if (mobileSearchClose) {
            mobileSearchClose.addEventListener('click', function(e) {
                e.preventDefault();
                e.stopPropagation();
                // Debug log removed for cleaner console
                mobileSearchBar.classList.remove('show');
            });
        }

        // Hide when clicking outside (with proper event handling)
        document.addEventListener('click', function(e) {
            // Only process if the search bar is actually visible
            if (!mobileSearchBar.classList.contains('show')) {
                return;
            }
            
            // Check if click is outside both search bar and toggle button
            if (!mobileSearchBar.contains(e.target) && 
                !mobileSearchToggle.contains(e.target)) {
                // Debug log removed for cleaner console
                mobileSearchBar.classList.remove('show');
                // Don't prevent default or stop propagation for outside clicks
            }
        }, true); // Use capture phase to handle before other handlers

        // Handle Enter key in mobile search
        if (mobileSearchInput) {
            mobileSearchInput.addEventListener('keypress', function(e) {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    quickSearch('mobile');
                }
            });
        }
    } else {
        console.error('Mobile search elements not found');
    }
}

// Desktop Search Toggle Function
function initDesktopSearch() {
    const desktopSearchToggle = document.getElementById('desktop-search-toggle');
    const desktopSearchBar = document.getElementById('desktopSearchBar');
    const desktopSearchClose = document.getElementById('desktop-search-close');
    const desktopSearchInput = document.getElementById('desktopHeaderSearch');

    // Only log in development mode
    if (window.location.hostname === 'localhost' || window.location.hostname.includes('127.0.0.1')) {
        console.log('Initializing desktop search...', {
            toggle: !!desktopSearchToggle,
            bar: !!desktopSearchBar,
            close: !!desktopSearchClose,
            input: !!desktopSearchInput
        });
    }

    if (desktopSearchToggle && desktopSearchBar) {
        // Show desktop search
        desktopSearchToggle.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            // Debug log removed for cleaner console
            
            // Toggle visibility
            if (desktopSearchBar.classList.contains('show')) {
                desktopSearchBar.classList.remove('show');
            } else {
                desktopSearchBar.classList.add('show');
                // Focus on input after animation
                setTimeout(() => {
                    if (desktopSearchInput) {
                        desktopSearchInput.focus();
                    }
                }, 150);
            }
        });

        // Hide desktop search
        if (desktopSearchClose) {
            desktopSearchClose.addEventListener('click', function(e) {
                e.preventDefault();
                e.stopPropagation();
                // Debug log removed for cleaner console
                desktopSearchBar.classList.remove('show');
            });
        }

        // Hide when clicking outside (with proper event handling)
        document.addEventListener('click', function(e) {
            // Only process if the search bar is actually visible
            if (!desktopSearchBar.classList.contains('show')) {
                return;
            }
            
            // Check if click is outside both search bar and toggle button
            if (!desktopSearchBar.contains(e.target) && 
                !desktopSearchToggle.contains(e.target)) {
                // Debug log removed for cleaner console
                desktopSearchBar.classList.remove('show');
                // Don't prevent default or stop propagation for outside clicks
            }
        }, true); // Use capture phase to handle before other handlers

        // Handle Enter key in desktop search
        if (desktopSearchInput) {
            desktopSearchInput.addEventListener('keypress', function(e) {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    quickSearch('desktop');
                }
            });
        }

        // Handle Escape key to close
        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape' && desktopSearchBar.classList.contains('show')) {
                desktopSearchBar.classList.remove('show');
            }
        });
    } else {
        console.error('Desktop search elements not found');
    }
}

// Quick Search Function
function quickSearch(source = 'desktop') {
    let searchInput;
    
    if (source === 'mobile') {
        searchInput = document.getElementById('mobileHeaderSearch');
    } else if (source === 'desktop') {
        searchInput = document.getElementById('desktopHeaderSearch');
    } else {
        // Fallback to any search input
        searchInput = document.querySelector('input[name="search"]');
    }
    
    if (searchInput && searchInput.value.trim()) {
        const searchQuery = encodeURIComponent(searchInput.value.trim());
        window.location.href = `/search?search=${searchQuery}`;
    }
}

// Initialize all managers when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    // Initialize search functionality
    initMobileSearch();
    initDesktopSearch();
    
    // Initialize core managers
    window.themeManager = new ThemeManager();
    window.languageManager = new LanguageManager();
    window.mangaCardManager = new MangaCardManager();
    window.searchManager = new SearchManager();
    window.keyboardNavigationManager = new KeyboardNavigationManager();
    window.performanceManager = new PerformanceManager();
    window.errorManager = new ErrorManager();

    // Initialize Bootstrap tooltips
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });

    // Initialize Bootstrap popovers
    const popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'));
    popoverTriggerList.map(function (popoverTriggerEl) {
        return new bootstrap.Popover(popoverTriggerEl);
    });

    // Add smooth scrolling to anchor links
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function (e) {
            e.preventDefault();
            const href = this.getAttribute('href');
            // Validate that href is a valid CSS selector
            if (href && href !== '#' && /^#[a-zA-Z][a-zA-Z0-9\-_]*$/.test(href)) {
                try {
                    const target = document.querySelector(href);
                    if (target) {
                        target.scrollIntoView({
                            behavior: 'smooth',
                            block: 'start'
                        });
                    }
                } catch (e) {
                    console.warn('Invalid selector for smooth scrolling:', href);
                }
            }
        });
    });

    // Add loading states to forms
    document.querySelectorAll('form').forEach(form => {
        form.addEventListener('submit', function() {
            const submitBtn = form.querySelector('button[type="submit"]');
            if (submitBtn && !submitBtn.disabled) {
                submitBtn.classList.add('disabled');
                const originalText = submitBtn.textContent;
                submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>Loading...';
                
                // Restore button after 5 seconds (fallback)
                setTimeout(() => {
                    submitBtn.classList.remove('disabled');
                    submitBtn.textContent = originalText;
                }, 5000);
            }
        });
    });

    // Only log initialization success in development mode
    if (window.location.hostname === 'localhost' || window.location.hostname.includes('127.0.0.1')) {
        console.log('Manga Platform JavaScript initialized successfully');
    }
});



// Utility functions
window.MangaPlatform = {
    // Show notification
    showNotification: function(message, type = 'info', duration = 3000) {
        if (window.mangaCardManager) {
            window.mangaCardManager.showNotification(message, type);
        }
    },

    // Format number with commas
    formatNumber: function(num) {
        return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
    },

    // Truncate text
    truncateText: function(text, length = 100) {
        if (text.length <= length) return text;
        return text.substring(0, length) + '...';
    },

    // Get relative time
    getRelativeTime: function(date) {
        const now = new Date();
        const diff = now - new Date(date);
        const seconds = Math.floor(diff / 1000);
        const minutes = Math.floor(seconds / 60);
        const hours = Math.floor(minutes / 60);
        const days = Math.floor(hours / 24);

        if (days > 0) return `${days} day${days > 1 ? 's' : ''} ago`;
        if (hours > 0) return `${hours} hour${hours > 1 ? 's' : ''} ago`;
        if (minutes > 0) return `${minutes} minute${minutes > 1 ? 's' : ''} ago`;
        return 'Just now';
    },

    // Copy to clipboard
    copyToClipboard: function(text) {
        if (navigator.clipboard) {
            navigator.clipboard.writeText(text).then(() => {
                this.showNotification('Copied to clipboard', 'success');
            });
        } else {
            // Fallback for older browsers
            const textArea = document.createElement('textarea');
            textArea.value = text;
            document.body.appendChild(textArea);
            textArea.select();
            document.execCommand('copy');
            document.body.removeChild(textArea);
            this.showNotification('Copied to clipboard', 'success');
        }
    }
};

// FOUC Prevention - Add loaded class to manga slider after DOM and CSS load
document.addEventListener('DOMContentLoaded', function() {
    // Add loaded class with small delay to ensure CSS is applied
    setTimeout(function() {
        const mangaSlider = document.getElementById('mangaSlider');
        if (mangaSlider) {
            mangaSlider.classList.add('loaded');
            // Debug log removed for cleaner console
        }
    }, 100);
});

// Alternative approach - ensure content is hidden until styles load
window.addEventListener('load', function() {
    // Ensure all sliders show content properly after everything loads
    const sliders = document.querySelectorAll('.manga-slider');
    sliders.forEach(function(slider) {
        if (!slider.classList.contains('loaded')) {
            slider.classList.add('loaded');
        }
    });
});
