// Configuration for Numislens AI Integration
const config = {
    // API settings
    api: {
        baseUrl: 'https://api.example.com/qwenVL3-30B3A', // Replace with actual API endpoint
        timeout: 30000, // 30 seconds
        maxRetries: 3
    },
    
    // Image processing settings
    image: {
        maxSize: 5 * 1024 * 1024, // 5MB
        allowedTypes: ['image/jpeg', 'image/png', 'image/webp'],
        maxWidth: 1920,
        maxHeight: 1080
    },
    
    // Coin identification settings
    identification: {
        confidenceThreshold: 0.7, // 70% minimum confidence
        maxResults: 5 // Return up to 5 possible matches
    }
};

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = config;
} else {
    // For browser environment
    window.NumislensConfig = config;
}