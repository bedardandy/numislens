// Numislens - AI Coin Identifier Application
class NumislensApp {
    constructor() {
        this.frontImage = null;
        this.edgeImage = null;
        this.deferredPrompt = null; // For PWA installation prompt
        this.initializeElements();
        this.bindEvents();
        this.checkOfflineStatus();
        this.setupInstallPrompt();
    }

    initializeElements() {
        // Upload elements
        this.frontInput = document.getElementById('front-input');
        this.edgeInput = document.getElementById('edge-input');
        this.frontPreview = document.getElementById('front-preview');
        this.edgePreview = document.getElementById('edge-preview');
        
        // Buttons
        this.frontCameraBtn = document.getElementById('front-camera-btn');
        this.frontFileBtn = document.getElementById('front-file-btn');
        this.edgeCameraBtn = document.getElementById('edge-camera-btn');
        this.edgeFileBtn = document.getElementById('edge-file-btn');
        this.analyzeBtn = document.getElementById('analyze-btn');
        this.newAnalysisBtn = document.getElementById('new-analysis-btn');
        
        // Results section
        this.resultsSection = document.getElementById('results-section');
        this.coinName = document.getElementById('coin-name');
        this.coinGrade = document.getElementById('coin-grade');
        this.coinValue = document.getElementById('coin-value');
        this.coinDetails = document.getElementById('coin-details');
    }

    bindEvents() {
        // Front image events
        this.frontCameraBtn.addEventListener('click', () => this.openCamera('front'));
        this.frontFileBtn.addEventListener('click', () => this.openFileSelector('front'));
        this.frontInput.addEventListener('change', (e) => this.handleImageUpload(e, 'front'));

        // Edge image events
        this.edgeCameraBtn.addEventListener('click', () => this.openCamera('edge'));
        this.edgeFileBtn.addEventListener('click', () => this.openFileSelector('edge'));
        this.edgeInput.addEventListener('change', (e) => this.handleImageUpload(e, 'edge'));

        // Analysis events
        this.analyzeBtn.addEventListener('click', () => this.analyzeCoin());
        this.newAnalysisBtn.addEventListener('click', () => this.resetApp());
    }

    openCamera(type) {
        // For mobile devices, the file input with capture="environment" will open the camera
        // Check if we're on a mobile device
        const isMobile = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);

        if (isMobile) {
            // On mobile, directly open camera
            if (type === 'front') {
                this.frontInput.click();
            } else {
                this.edgeInput.click();
            }
        } else {
            // On desktop, show a message or fallback to file upload
            if (confirm('Camera access is optimized for mobile devices. Would you like to upload an image instead?')) {
                this.openFileSelector(type);
            }
        }
    }

    openFileSelector(type) {
        if (type === 'front') {
            this.frontInput.click();
        } else {
            this.edgeInput.click();
        }
    }

    handleImageUpload(event, type) {
        const file = event.target.files[0];
        if (!file) return;

        // Validate image type
        if (!file.type.match('image.*')) {
            alert('Please select an image file (JPEG, PNG, etc.)');
            return;
        }

        // Validate image size (max 5MB)
        if (file.size > 5 * 1024 * 1024) {
            alert('Image size should be less than 5MB for optimal processing');
            return;
        }

        const reader = new FileReader();
        reader.onload = (e) => {
            if (type === 'front') {
                this.frontPreview.src = e.target.result;
                this.frontPreview.style.display = 'block';
                this.frontImage = file;
            } else {
                this.edgePreview.src = e.target.result;
                this.edgePreview.style.display = 'block';
                this.edgeImage = file;
            }

            // Enable analyze button when both images are uploaded
            if (this.frontImage && this.edgeImage) {
                this.analyzeBtn.disabled = false;
            }
        };
        reader.readAsDataURL(file);
    }

    async analyzeCoin() {
        if (!this.frontImage && !this.edgeImage) {
            alert('Please upload both front and edge images of the coin');
            return;
        }

        // Show loading state
        this.analyzeBtn.disabled = true;
        this.analyzeBtn.textContent = 'Analyzing...';

        try {
            // Preprocess images before sending to AI
            const processedImages = await this.preprocessImages();

            // Call the AI analysis
            const result = await this.getCoinAnalysis();

            // Display results
            this.displayResults(result);

            // Show results section
            this.resultsSection.style.display = 'block';

            // Scroll to results
            this.resultsSection.scrollIntoView({ behavior: 'smooth' });
        } catch (error) {
            console.error('Analysis error:', error);
            alert('Error analyzing coin. Please try again.');
        } finally {
            this.analyzeBtn.disabled = false;
            this.analyzeBtn.textContent = 'Analyze Coin';
        }
    }

    async preprocessImages() {
        // Import image processor for preprocessing
        // In a real implementation, we would import the actual image processor
        // For now, we'll simulate the preprocessing

        // In a real implementation, we would do something like:
        /*
        const imageProcessor = new CoinImageProcessor();
        const processedFront = await imageProcessor.processFrontImage(this.frontImage);
        const processedEdge = await imageProcessor.processEdgeImage(this.edgeImage);
        return imageProcessor.combineViews(processedFront, processedEdge);
        */

        // For this demo, return the original images with some metadata
        return {
            front: this.frontImage,
            edge: this.edgeImage,
            metadata: {
                timestamp: new Date().toISOString(),
                originalSizes: {
                    front: this.frontImage ? this.frontImage.size : 0,
                    edge: this.edgeImage ? this.edgeImage.size : 0
                }
            }
        };
    }

    async getCoinAnalysis() {
        // Import and use the AI service
        // In a real implementation, we would import the actual AI service
        // For now, we'll instantiate the CoinAIService class

        // Create an instance of the AI service
        const aiService = new CoinAIService();

        try {
            // Call the AI service to identify the coin
            const result = await aiService.identifyCoin(this.frontImage, this.edgeImage);

            // Extract the coin data from the result
            const coinData = result.coin;

            // Format the result to match what the UI expects
            return {
                name: coinData.name || 'Unknown Coin',
                grade: coinData.grade || 'Unknown Grade',
                value: coinData.estimatedValue || 'Value Not Available',
                details: coinData.conditionDetails || 'No details available'
            };
        } catch (error) {
            console.error('AI analysis error:', error);

            // If AI service fails, return a default response
            return {
                name: 'Unable to identify coin',
                grade: 'Unknown',
                value: 'Value Not Available',
                details: 'Could not analyze the coin. Please try again with clearer images.'
            };
        }
    }

    displayResults(result) {
        this.coinName.textContent = result.name;
        this.coinGrade.textContent = result.grade;
        this.coinValue.textContent = result.value;
        this.coinDetails.textContent = result.details;
    }

    resetApp() {
        // Reset images
        this.frontImage = null;
        this.edgeImage = null;

        // Reset previews
        this.frontPreview.style.display = 'none';
        this.edgePreview.style.display = 'none';

        // Reset inputs
        this.frontInput.value = '';
        this.edgeInput.value = '';

        // Disable analyze button
        this.analyzeBtn.disabled = true;
        this.analyzeBtn.textContent = 'Analyze Coin';

        // Hide results section
        this.resultsSection.style.display = 'none';
    }

    // Check if the app is running offline
    checkOfflineStatus() {
        // Update UI based on online/offline status
        const updateOnlineStatus = () => {
            const statusElement = document.createElement('div');
            statusElement.id = 'online-status';
            statusElement.style.position = 'fixed';
            statusElement.style.top = '10px';
            statusElement.style.right = '10px';
            statusElement.style.padding = '5px 10px';
            statusElement.style.borderRadius = '4px';
            statusElement.style.fontSize = '14px';
            statusElement.style.zIndex = '1000';

            if (navigator.onLine) {
                statusElement.textContent = 'Online';
                statusElement.style.backgroundColor = 'rgba(76, 175, 80, 0.9)';
                statusElement.style.color = 'white';
            } else {
                statusElement.textContent = 'Offline';
                statusElement.style.backgroundColor = 'rgba(244, 67, 54, 0.9)';
                statusElement.style.color = 'white';
            }

            // Remove any existing status element
            const existingStatus = document.getElementById('online-status');
            if (existingStatus) {
                existingStatus.remove();
            }

            document.body.appendChild(statusElement);
        };

        // Initial check
        updateOnlineStatus();

        // Listen for online/offline events
        window.addEventListener('online', updateOnlineStatus);
        window.addEventListener('offline', updateOnlineStatus);
    }

    // Set up the install prompt for PWA
    setupInstallPrompt() {
        // Listen for the beforeinstallprompt event
        window.addEventListener('beforeinstallprompt', (e) => {
            // Prevent the mini-infobar from appearing on mobile
            e.preventDefault();
            // Stash the event so it can be triggered later
            this.deferredPrompt = e;

            // Show install button if available
            const installBtn = document.createElement('button');
            installBtn.id = 'install-pwa-btn';
            installBtn.textContent = 'Install App';
            installBtn.style.position = 'fixed';
            installBtn.style.bottom = '20px';
            installBtn.style.right = '20px';
            installBtn.style.padding = '10px 15px';
            installBtn.style.backgroundColor = '#2196f3';
            installBtn.style.color = 'white';
            installBtn.style.border = 'none';
            installBtn.style.borderRadius = '5px';
            installBtn.style.cursor = 'pointer';
            installBtn.style.zIndex = '1000';
            installBtn.style.display = 'none'; // Initially hidden

            installBtn.addEventListener('click', () => {
                // Show the install prompt
                this.deferredPrompt.prompt();
                // Wait for the user to respond to the prompt
                this.deferredPrompt.userChoice.then((choiceResult) => {
                    if (choiceResult.outcome === 'accepted') {
                        console.log('User accepted the install prompt');
                    } else {
                        console.log('User dismissed the install prompt');
                    }
                    this.deferredPrompt = null;
                    installBtn.style.display = 'none';
                });
            });

            document.body.appendChild(installBtn);

            // Show the install button
            const existingInstallBtn = document.getElementById('install-pwa-btn');
            if (existingInstallBtn) {
                existingInstallBtn.style.display = 'block';
            }
        });

        // Listen for when the PWA is successfully installed
        window.addEventListener('appinstalled', () => {
            console.log('PWA was installed');
            // Hide the install button after installation
            const installBtn = document.getElementById('install-pwa-btn');
            if (installBtn) {
                installBtn.style.display = 'none';
            }
            this.deferredPrompt = null;
        });
    }
}

// Initialize the app when the page loads
document.addEventListener('DOMContentLoaded', () => {
    new NumislensApp();
});