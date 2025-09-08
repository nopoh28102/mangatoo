/**
 * Manga Reader JavaScript
 * Handles reading interface, navigation, zoom, and user interactions
 */

class MangaReader {
    constructor(config) {
        this.config = {
            mangaId: config.mangaId,
            chapterId: config.chapterId,
            totalPages: config.totalPages,
            nextChapterUrl: config.nextChapterUrl,
            prevChapterUrl: config.prevChapterUrl,
            // Webtoon settings from backend
            enableWebtoonMode: config.enableWebtoonMode || true,
            webtoonAutoHeight: config.webtoonAutoHeight || true,
            webtoonGapSize: config.webtoonGapSize || 5,
            webtoonMaxWidth: config.webtoonMaxWidth || 100,
            ...config
        };
        
        this.currentPage = 1;
        this.isFullscreen = false;
        this.readingMode = localStorage.getItem('readingMode') || 'vertical';
        this.isWebtoonMode = localStorage.getItem('isWebtoonMode') === 'true' || false;
        this.zoomLevel = 1;
        this.isAutoMode = false;
        this.autoModeInterval = null;
        
        this.init();
    }

    init() {
        this.setupElements();
        this.bindEvents();
        this.setupKeyboardNavigation();
        this.setupTouchGestures();
        this.setupProgressTracking();
        this.loadReadingPreferences();
        this.applyReadingMode();
        
        // Manga Reader initialized (debug log removed)
    }

    setupElements() {
        this.pagesContainer = document.getElementById('pages-container');
        this.pageCounter = document.getElementById('current-page');
        this.totalPagesElement = document.getElementById('total-pages');
        this.readerControls = document.querySelector('.reader-controls');
        
        // Update page counter
        if (this.pageCounter) {
            this.pageCounter.textContent = this.currentPage;
        }
        if (this.totalPagesElement) {
            this.totalPagesElement.textContent = this.config.totalPages;
        }
    }

    bindEvents() {
        // Navigation buttons
        document.getElementById('prev-page')?.addEventListener('click', () => this.previousPage());
        document.getElementById('next-page')?.addEventListener('click', () => this.nextPage());
        
        // Zoom controls
        document.getElementById('zoom-in')?.addEventListener('click', () => this.zoomIn());
        document.getElementById('zoom-out')?.addEventListener('click', () => this.zoomOut());
        document.getElementById('zoom-reset')?.addEventListener('click', () => this.resetZoom());
        
        // Fullscreen toggle
        document.getElementById('fullscreen-btn')?.addEventListener('click', () => this.toggleFullscreen());
        
        // Reading mode toggle
        document.getElementById('reading-mode-btn')?.addEventListener('click', () => this.toggleReadingMode());
        
        // Page image clicks
        document.addEventListener('click', (e) => {
            if (e.target.classList.contains('page-image')) {
                this.handlePageClick(e);
            }
        });
        
        // Scroll tracking for vertical mode
        if (this.readingMode === 'vertical') {
            window.addEventListener('scroll', () => this.handleScroll());
        }
        
        // Fullscreen change events
        document.addEventListener('fullscreenchange', () => this.handleFullscreenChange());
        document.addEventListener('webkitfullscreenchange', () => this.handleFullscreenChange());
    }

    setupKeyboardNavigation() {
        document.addEventListener('keydown', (e) => {
            // Don't interfere with form inputs
            if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') {
                return;
            }

            switch (e.key) {
                case 'ArrowLeft':
                case 'a':
                case 'A':
                    e.preventDefault();
                    this.previousPage();
                    break;
                
                case 'ArrowRight':
                case 'd':
                case 'D':
                case ' ': // Spacebar
                    e.preventDefault();
                    this.nextPage();
                    break;
                
                case 'ArrowUp':
                case 'w':
                case 'W':
                    if (this.readingMode === 'vertical') {
                        e.preventDefault();
                        this.scrollUp();
                    }
                    break;
                
                case 'ArrowDown':
                case 's':
                case 'S':
                    if (this.readingMode === 'vertical') {
                        e.preventDefault();
                        this.scrollDown();
                    }
                    break;
                
                case 'Home':
                    e.preventDefault();
                    this.goToPage(1);
                    break;
                
                case 'End':
                    e.preventDefault();
                    this.goToPage(this.config.totalPages);
                    break;
                
                case 'f':
                case 'F':
                    e.preventDefault();
                    this.toggleFullscreen();
                    break;
                
                case 'm':
                case 'M':
                    e.preventDefault();
                    this.toggleReadingMode();
                    break;
                
                case '+':
                case '=':
                    e.preventDefault();
                    this.zoomIn();
                    break;
                
                case '-':
                    e.preventDefault();
                    this.zoomOut();
                    break;
                
                case '0':
                    e.preventDefault();
                    this.resetZoom();
                    break;
                
                case 'Escape':
                    if (this.isFullscreen) {
                        this.toggleFullscreen();
                    }
                    break;
            }
        });
    }

    setupTouchGestures() {
        let startX = 0;
        let startY = 0;
        let endX = 0;
        let endY = 0;
        let initialZoom = 1;
        let initialDistance = 0;

        this.pagesContainer.addEventListener('touchstart', (e) => {
            if (e.touches.length === 1) {
                startX = e.touches[0].clientX;
                startY = e.touches[0].clientY;
            } else if (e.touches.length === 2) {
                // Pinch zoom start
                initialDistance = this.getDistance(e.touches[0], e.touches[1]);
                initialZoom = this.zoomLevel;
            }
        });

        this.pagesContainer.addEventListener('touchmove', (e) => {
            if (e.touches.length === 2) {
                e.preventDefault();
                const currentDistance = this.getDistance(e.touches[0], e.touches[1]);
                const scale = currentDistance / initialDistance;
                this.setZoom(initialZoom * scale);
            }
        });

        this.pagesContainer.addEventListener('touchend', (e) => {
            if (e.changedTouches.length === 1) {
                endX = e.changedTouches[0].clientX;
                endY = e.changedTouches[0].clientY;
                
                const deltaX = endX - startX;
                const deltaY = endY - startY;
                const threshold = 50;
                
                if (Math.abs(deltaX) > Math.abs(deltaY)) {
                    if (deltaX > threshold) {
                        this.previousPage();
                    } else if (deltaX < -threshold) {
                        this.nextPage();
                    }
                } else if (this.readingMode === 'vertical') {
                    if (deltaY > threshold) {
                        this.scrollUp();
                    } else if (deltaY < -threshold) {
                        this.scrollDown();
                    }
                }
            }
        });
    }

    setupProgressTracking() {
        // Update progress every 5 seconds
        this.progressInterval = setInterval(() => {
            this.updateReadingProgress();
        }, 5000);

        // Update on page change
        window.addEventListener('beforeunload', () => {
            this.updateReadingProgress();
        });
    }

    loadReadingPreferences() {
        const preferences = JSON.parse(localStorage.getItem('readerPreferences') || '{}');
        
        this.readingMode = preferences.readingMode || 'vertical';
        this.isWebtoonMode = preferences.isWebtoonMode || false;
        this.zoomLevel = preferences.zoomLevel || 1;
        
        // Apply zoom
        if (this.zoomLevel !== 1) {
            this.setZoom(this.zoomLevel);
        }
    }

    saveReadingPreferences() {
        const preferences = {
            readingMode: this.readingMode,
            isWebtoonMode: this.isWebtoonMode,
            zoomLevel: this.zoomLevel
        };
        
        localStorage.setItem('readerPreferences', JSON.stringify(preferences));
        localStorage.setItem('isWebtoonMode', this.isWebtoonMode.toString());
    }

    applyReadingMode() {
        const container = this.pagesContainer;
        const pages = container.querySelectorAll('.page-wrapper');
        
        // Apply webtoon mode if enabled
        if (this.isWebtoonMode && this.config.enableWebtoonMode) {
            container.className = `pages-container webtoon-reading`;
            this.applyWebtoonMode(pages);
        } else {
            container.className = `pages-container ${this.readingMode}-reading`;
            
            if (this.readingMode === 'vertical') {
                pages.forEach((page, index) => {
                    page.style.display = 'block';
                    page.style.marginBottom = '10px';
                    const img = page.querySelector('.page-image');
                    if (img) {
                        img.style.display = 'block';
                        img.style.maxWidth = '100%';
                        img.style.height = 'auto';
                    }
                });
            } else if (this.readingMode === 'horizontal') {
                pages.forEach((page, index) => {
                    page.style.display = index === this.currentPage - 1 ? 'block' : 'none';
                    const img = page.querySelector('.page-image');
                    if (img) {
                        img.style.display = 'block';
                    }
                });
            }
        }
        
        // Update reading mode button
        const readingModeBtn = document.getElementById('reading-mode-btn');
        if (readingModeBtn) {
            const icon = readingModeBtn.querySelector('i');
            if (this.isWebtoonMode) {
                icon.className = 'fas fa-scroll';
                readingModeBtn.title = 'Switch to Page Mode';
            } else if (this.readingMode === 'vertical') {
                icon.className = 'fas fa-columns';
                readingModeBtn.title = 'Switch to Horizontal Mode';
            } else {
                icon.className = 'fas fa-align-justify';
                readingModeBtn.title = 'Switch to Vertical Mode';
            }
        }
    }

    applyWebtoonMode(pages) {
        const gapSize = this.config.webtoonGapSize || 5;
        const maxWidth = this.config.webtoonMaxWidth || 100;
        
        pages.forEach((page, index) => {
            page.style.display = 'block';
            page.style.marginBottom = `${gapSize}px`;
            page.style.textAlign = 'center';
            
            const img = page.querySelector('.page-image');
            if (img) {
                img.style.display = 'block';
                img.style.maxWidth = `${maxWidth}%`;
                img.style.width = 'auto';
                img.style.margin = '0 auto';
                
                if (this.config.webtoonAutoHeight) {
                    img.style.height = 'auto';
                } else {
                    img.style.maxHeight = '100vh';
                }
            }
        });
        
        // Smooth scroll for webtoon mode
        document.documentElement.style.scrollBehavior = 'smooth';
    }

    toggleReadingMode() {
        if (this.config.enableWebtoonMode) {
            // Three modes: horizontal -> vertical -> webtoon -> horizontal
            if (this.readingMode === 'horizontal' && !this.isWebtoonMode) {
                this.readingMode = 'vertical';
                this.isWebtoonMode = false;
            } else if (this.readingMode === 'vertical' && !this.isWebtoonMode) {
                this.readingMode = 'vertical';
                this.isWebtoonMode = true;
            } else {
                this.readingMode = 'horizontal';
                this.isWebtoonMode = false;
            }
        } else {
            // Two modes: horizontal -> vertical -> horizontal
            this.readingMode = this.readingMode === 'vertical' ? 'horizontal' : 'vertical';
            this.isWebtoonMode = false;
        }
        
        this.applyReadingMode();
        this.saveReadingPreferences();
        
        let modeName = this.readingMode;
        if (this.isWebtoonMode) {
            modeName = 'webtoon';
        }
        
        if (window.MangaPlatform) {
            window.MangaPlatform.showNotification(
                `Switched to ${modeName} reading mode`, 
                'info'
            );
        }
    }

    handlePageClick(e) {
        const rect = e.target.getBoundingClientRect();
        const clickX = e.clientX - rect.left;
        const clickPercent = clickX / rect.width;
        
        if (clickPercent < 0.3) {
            this.previousPage();
        } else if (clickPercent > 0.7) {
            this.nextPage();
        } else {
            // Middle click - toggle controls
            this.toggleControls();
        }
    }

    handleScroll() {
        if (this.readingMode !== 'vertical') return;
        
        const pages = document.querySelectorAll('.page-wrapper');
        let currentPageFromScroll = 1;
        
        pages.forEach((page, index) => {
            const rect = page.getBoundingClientRect();
            if (rect.top <= window.innerHeight / 2 && rect.bottom >= window.innerHeight / 2) {
                currentPageFromScroll = index + 1;
            }
        });
        
        if (currentPageFromScroll !== this.currentPage) {
            this.currentPage = currentPageFromScroll;
            this.updatePageCounter();
        }
    }

    previousPage() {
        if (this.readingMode === 'vertical') {
            this.scrollUp();
        } else {
            if (this.currentPage > 1) {
                this.goToPage(this.currentPage - 1);
            } else if (this.config.prevChapterUrl) {
                window.location.href = this.config.prevChapterUrl;
            }
        }
    }

    nextPage() {
        if (this.readingMode === 'vertical') {
            this.scrollDown();
        } else {
            if (this.currentPage < this.config.totalPages) {
                this.goToPage(this.currentPage + 1);
            } else if (this.config.nextChapterUrl) {
                if (confirm('Go to next chapter?')) {
                    window.location.href = this.config.nextChapterUrl;
                }
            }
        }
    }

    goToPage(pageNumber) {
        if (pageNumber < 1 || pageNumber > this.config.totalPages) return;
        
        this.currentPage = pageNumber;
        
        if (this.readingMode === 'horizontal') {
            const pages = document.querySelectorAll('.page-wrapper');
            pages.forEach((page, index) => {
                page.style.display = index === pageNumber - 1 ? 'block' : 'none';
            });
        } else {
            const targetPage = document.querySelector(`[data-page="${pageNumber}"]`);
            if (targetPage) {
                targetPage.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
        }
        
        this.updatePageCounter();
        this.updateReadingProgress();
    }

    scrollUp() {
        window.scrollBy(0, -window.innerHeight * 0.8);
    }

    scrollDown() {
        window.scrollBy(0, window.innerHeight * 0.8);
    }

    zoomIn() {
        this.setZoom(Math.min(this.zoomLevel * 1.2, 3));
    }

    zoomOut() {
        this.setZoom(Math.max(this.zoomLevel / 1.2, 0.5));
    }

    resetZoom() {
        this.setZoom(1);
    }

    setZoom(level) {
        this.zoomLevel = level;
        
        const images = document.querySelectorAll('.page-image');
        images.forEach(img => {
            img.style.transform = `scale(${level})`;
            img.style.transformOrigin = 'center';
        });
        
        this.saveReadingPreferences();
        
        if (window.MangaPlatform) {
            window.MangaPlatform.showNotification(
                `Zoom: ${Math.round(level * 100)}%`, 
                'info'
            );
        }
    }

    toggleFullscreen() {
        if (!this.isFullscreen) {
            const element = document.documentElement;
            if (element.requestFullscreen) {
                element.requestFullscreen();
            } else if (element.webkitRequestFullscreen) {
                element.webkitRequestFullscreen();
            } else if (element.msRequestFullscreen) {
                element.msRequestFullscreen();
            }
        } else {
            if (document.exitFullscreen) {
                document.exitFullscreen();
            } else if (document.webkitExitFullscreen) {
                document.webkitExitFullscreen();
            } else if (document.msExitFullscreen) {
                document.msExitFullscreen();
            }
        }
    }

    handleFullscreenChange() {
        this.isFullscreen = !!(document.fullscreenElement || document.webkitFullscreenElement || document.msFullscreenElement);
        
        const fullscreenBtn = document.getElementById('fullscreen-btn');
        if (fullscreenBtn) {
            const icon = fullscreenBtn.querySelector('i');
            if (this.isFullscreen) {
                icon.className = 'fas fa-compress';
                fullscreenBtn.title = 'Exit Fullscreen';
            } else {
                icon.className = 'fas fa-expand';
                fullscreenBtn.title = 'Enter Fullscreen';
            }
        }
    }

    toggleControls() {
        const controls = document.querySelectorAll('.reader-controls, .page-counter, .fullscreen-toggle, .reading-mode-toggle, .chapter-nav');
        
        controls.forEach(control => {
            if (control.style.opacity === '0') {
                control.style.opacity = '1';
                control.style.pointerEvents = 'auto';
            } else {
                control.style.opacity = '0';
                control.style.pointerEvents = 'none';
            }
        });
    }

    updatePageCounter() {
        if (this.pageCounter) {
            this.pageCounter.textContent = this.currentPage;
        }
    }

    async updateReadingProgress() {
        if (!this.config.mangaId || !this.config.chapterId) return;
        
        try {
            const baseUrl = window.MANGA_PLATFORM ? window.MANGA_PLATFORM.baseUrl : '';
            const response = await fetch(`${baseUrl}/api/update_progress`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    manga_id: this.config.mangaId,
                    chapter_id: this.config.chapterId,
                    page_number: this.currentPage
                })
            });
            
            if (!response.ok && response.status !== 401) {
                // Only log errors that aren't authentication issues
                console.warn(`Reading progress update failed: ${response.status}`);
            }
        } catch (error) {
            // Only log network errors, not server errors
            if (error.name === 'NetworkError' || error.name === 'TypeError') {
                console.warn('Network issue updating reading progress');
            }
        }
    }

    getDistance(touch1, touch2) {
        const dx = touch1.clientX - touch2.clientX;
        const dy = touch1.clientY - touch2.clientY;
        return Math.sqrt(dx * dx + dy * dy);
    }

    destroy() {
        if (this.progressInterval) {
            clearInterval(this.progressInterval);
        }
        
        if (this.autoModeInterval) {
            clearInterval(this.autoModeInterval);
        }
    }
}

// Auto-reading mode
class AutoReader {
    constructor(reader) {
        this.reader = reader;
        this.isActive = false;
        this.interval = null;
        this.speed = parseInt(localStorage.getItem('autoReadSpeed') || '3000');
    }

    start() {
        if (this.isActive) return;
        
        this.isActive = true;
        this.interval = setInterval(() => {
            this.reader.nextPage();
        }, this.speed);
        
        if (window.MangaPlatform) {
            window.MangaPlatform.showNotification('Auto-reading started', 'info');
        }
    }

    stop() {
        if (!this.isActive) return;
        
        this.isActive = false;
        if (this.interval) {
            clearInterval(this.interval);
            this.interval = null;
        }
        
        if (window.MangaPlatform) {
            window.MangaPlatform.showNotification('Auto-reading stopped', 'info');
        }
    }

    toggle() {
        if (this.isActive) {
            this.stop();
        } else {
            this.start();
        }
    }

    setSpeed(speed) {
        this.speed = speed;
        localStorage.setItem('autoReadSpeed', speed.toString());
        
        if (this.isActive) {
            this.stop();
            this.start();
        }
    }
}

// Initialize reader
function initReader(config) {
    window.mangaReader = new MangaReader(config);
    window.autoReader = new AutoReader(window.mangaReader);
    
    // Add auto-reader controls
    const readerControls = document.querySelector('.reader-controls .d-flex');
    if (readerControls) {
        const autoButton = document.createElement('button');
        autoButton.className = 'btn btn-outline-light btn-sm';
        autoButton.innerHTML = '<i class="fas fa-play"></i>';
        autoButton.title = 'Toggle Auto-reading';
        autoButton.addEventListener('click', () => {
            window.autoReader.toggle();
            const icon = autoButton.querySelector('i');
            if (window.autoReader.isActive) {
                icon.className = 'fas fa-pause';
                autoButton.title = 'Stop Auto-reading';
            } else {
                icon.className = 'fas fa-play';
                autoButton.title = 'Start Auto-reading';
            }
        });
        
        readerControls.appendChild(autoButton);
    }
    
    // Manga Reader fully initialized (debug log removed)
}

// Export for global access
window.initReader = initReader;
window.MangaReader = MangaReader;
window.AutoReader = AutoReader;
