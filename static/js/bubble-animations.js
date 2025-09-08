/**
 * Golden Halos and Sparkle Animation Enhancement
 * Adds beautiful golden halos and floating sparkles to the hero section
 */

class SparkleAnimations {
    constructor() {
        this.init();
    }

    init() {
        this.enhanceSparkles();
        this.enhanceGoldenHalos();
        this.addInteractiveEffects();
        this.optimizePerformance();
    }

    enhanceSparkles() {
        const sparkles = document.querySelectorAll('.sparkle');
        sparkles.forEach((sparkle, index) => {
            // Add random movement variations
            const randomDelay = Math.random() * 3;
            const randomDuration = 6 + Math.random() * 4;
            
            sparkle.style.animationDelay = `${randomDelay}s`;
            sparkle.style.animationDuration = `${randomDuration}s`;
        });
    }

    enhanceGoldenHalos() {
        const goldenHalos = document.querySelectorAll('.golden-halo');
        goldenHalos.forEach((halo, index) => {
            // Add random variations to golden halos
            const randomDelay = Math.random() * 2;
            const randomDuration = 7 + Math.random() * 3;
            
            halo.style.animationDelay = `${randomDelay}s`;
            halo.style.animationDuration = `${randomDuration}s`;
        });
    }

    addInteractiveEffects() {
        const heroSection = document.querySelector('.hero-section');
        
        if (heroSection) {
            // Add mouse movement effect for sparkles
            heroSection.addEventListener('mousemove', (e) => {
                const sparkles = document.querySelectorAll('.sparkle');
                
                const rect = heroSection.getBoundingClientRect();
                const mouseX = e.clientX - rect.left;
                const mouseY = e.clientY - rect.top;
                
                sparkles.forEach((sparkle, index) => {
                    const sparkleRect = sparkle.getBoundingClientRect();
                    const sparkleX = sparkleRect.left + sparkleRect.width / 2 - rect.left;
                    const sparkleY = sparkleRect.top + sparkleRect.height / 2 - rect.top;
                    
                    const distance = Math.sqrt(
                        Math.pow(mouseX - sparkleX, 2) + Math.pow(mouseY - sparkleY, 2)
                    );
                    
                    if (distance < 80) {
                        const force = (80 - distance) / 80;
                        sparkle.style.transform = `scale(${1 + force * 0.5})`;
                        sparkle.style.filter = `brightness(${1 + force * 0.5})`;
                    } else {
                        sparkle.style.transform = '';
                        sparkle.style.filter = '';
                    }
                });
            });
            
            // Reset on mouse leave
            heroSection.addEventListener('mouseleave', () => {
                const sparkles = document.querySelectorAll('.sparkle');
                sparkles.forEach(sparkle => {
                    sparkle.style.transform = '';
                    sparkle.style.filter = '';
                });
            });
        }
    }

    optimizePerformance() {
        // Pause animations when not visible
        const observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                const sparkles = entry.target.querySelectorAll('.sparkle');
                const goldenHalos = entry.target.querySelectorAll('.golden-halo');
                
                if (entry.isIntersecting) {
                    sparkles.forEach(element => {
                        element.style.animationPlayState = 'running';
                    });
                    goldenHalos.forEach(element => {
                        element.style.animationPlayState = 'running';
                    });
                } else {
                    sparkles.forEach(element => {
                        element.style.animationPlayState = 'paused';
                    });
                    goldenHalos.forEach(element => {
                        element.style.animationPlayState = 'paused';
                    });
                }
            });
        }, {
            threshold: 0.1
        });
        
        const heroSection = document.querySelector('.hero-section');
        if (heroSection) {
            observer.observe(heroSection);
        }
    }
    
    // Method to add extra sparkle effect on user interaction
    addSparkleEffect(x, y) {
        const sparklesContainer = document.querySelector('.sparkles-container');
        if (!sparklesContainer) return;
        
        const sparkleEmojis = ['✨', '⭐', '💫'];
        const randomEmoji = sparkleEmojis[Math.floor(Math.random() * sparkleEmojis.length)];
        
        const sparkle = document.createElement('div');
        sparkle.className = 'sparkle';
        sparkle.textContent = randomEmoji;
        sparkle.style.left = x + 'px';
        sparkle.style.top = y + 'px';
        sparkle.style.animationDuration = '2s';
        sparkle.style.transform = 'scale(0)';
        sparkle.style.position = 'absolute';
        
        sparklesContainer.appendChild(sparkle);
        
        // Animate in
        setTimeout(() => {
            sparkle.style.transform = 'scale(1.2)';
            sparkle.style.transition = 'transform 0.3s ease';
        }, 10);
        
        // Remove after animation
        setTimeout(() => {
            if (sparkle.parentNode) {
                sparkle.parentNode.removeChild(sparkle);
            }
        }, 2000);
    }
}

// Initialize animations when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    const sparkleAnimations = new SparkleAnimations();
    
    // Add sparkle effect on hero button clicks
    const heroButtons = document.querySelectorAll('.btn-hero-primary, .btn-hero-outline');
    heroButtons.forEach(button => {
        button.addEventListener('click', (e) => {
            const rect = button.getBoundingClientRect();
            const x = rect.left + rect.width / 2;
            const y = rect.top + rect.height / 2;
            sparkleAnimations.addSparkleEffect(x - 10, y - 10);
        });
    });
});

// Performance monitoring
if (window.console && console.log) {
    // Sparkle animations initialized successfully (debug log removed)
}