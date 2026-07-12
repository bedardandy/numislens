// Central configuration for Numislens PWA (single source of endpoint/model/key/timeout)
const NumislensConfig = {
    apiEndpoint: 'http://localhost:8080/v1/chat/completions',
    modelName: 'qwenVL3-30B3A',
    apiKey: 'sk-llama',
    timeout: 30000
};

if (typeof module !== 'undefined' && module.exports) {
    module.exports = NumislensConfig;
} else {
    window.NumislensConfig = NumislensConfig;
}
