// AI Integration Module for Numislens
// This module handles communication with a local llama.cpp server via OpenAI-compatible API

class CoinAIService {
    constructor() {
        // Configuration for local llama.cpp server
        this.apiEndpoint = 'http://localhost:8080/v1/chat/completions'; // Default llama.cpp endpoint
        this.modelName = 'qwenVL3-30B3A'; // Model name for the API
        this.apiKey = 'sk-llama'; // Default key for local llama.cpp
        this.timeout = 30000; // 30 seconds timeout
    }

    async identifyCoin(frontImage, edgeImage) {
        try {
            // Convert images to base64 for API request
            const frontBase64 = await this.imageToBase64(frontImage);
            const edgeBase64 = await this.imageToBase64(edgeImage);

            // Prepare the request for the OpenAI-compatible API
            const requestBody = {
                model: this.modelName,
                messages: [
                    {
                        role: "system",
                        content: "You are an expert numismatist. Analyze the provided coin images and identify the coin type, year, country, denomination, composition, condition grade, and estimated value. Respond in JSON format with the following structure: {name, year, mintmark, denomination, country, composition, diameter, weight, grade, estimatedValue, confidence, conditionDetails, wear, luster, strike, surface}"
                    },
                    {
                        role: "user",
                        content: [
                            {
                                type: "text",
                                text: "Analyze this coin. The first image shows the front and the second shows the edge. Provide detailed identification, grading, and value estimation."
                            },
                            {
                                type: "image_url",
                                image_url: {
                                    url: `data:image/jpeg;base64,${frontBase64}`
                                }
                            },
                            {
                                type: "image_url",
                                image_url: {
                                    url: `data:image/jpeg;base64,${edgeBase64}`
                                }
                            }
                        ]
                    }
                ],
                temperature: 0.1,
                max_tokens: 1000,
                response_format: { type: "json_object" }
            };

            // Create a timeout promise
            const timeoutPromise = new Promise((_, reject) => {
                setTimeout(() => reject(new Error('Request timeout')), this.timeout);
            });

            // Make the API call to the local llama.cpp server with timeout
            const fetchPromise = fetch(this.apiEndpoint, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${this.apiKey}`
                },
                body: JSON.stringify(requestBody)
            });

            // Race the fetch request against the timeout
            const response = await Promise.race([fetchPromise, timeoutPromise]);

            if (!response.ok) {
                throw new Error(`AI service error: ${response.status} ${response.statusText}`);
            }

            const data = await response.json();

            // Parse the response from the AI model
            if (data.choices && data.choices.length > 0) {
                const content = data.choices[0].message.content;
                try {
                    // Parse the JSON response from the AI
                    const parsedResponse = JSON.parse(content);
                    return {
                        success: true,
                        coin: parsedResponse
                    };
                } catch (parseError) {
                    console.error('Error parsing AI response:', parseError);
                    return { success: false, error: 'Could not parse AI response as JSON' };
                }
            } else {
                throw new Error('No response from AI model');
            }

        } catch (error) {
            console.error('AI identification error:', error);
            return { success: false, error: error.message || 'AI identification failed' };
        }
    }

    // Convert image file to base64
    async imageToBase64(imageFile) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => {
                // Remove the data URL prefix (e.g., "data:image/jpeg;base64,")
                const base64String = reader.result.split(',')[1];
                resolve(base64String);
            };
            reader.onerror = reject;
            reader.readAsDataURL(imageFile);
        });
    }

    // Method to validate if the service is configured properly
    isConfigured() {
        // Check if the API endpoint is accessible
        return this.apiEndpoint && this.apiEndpoint.startsWith('http');
    }

    // Method to update the API configuration
    updateConfig(config) {
        if (config.apiEndpoint) this.apiEndpoint = config.apiEndpoint;
        if (config.modelName) this.modelName = config.modelName;
        if (config.apiKey) this.apiKey = config.apiKey;
        if (config.timeout) this.timeout = config.timeout;
    }
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = CoinAIService;
} else {
    // For browser environment
    window.CoinAIService = CoinAIService;
}