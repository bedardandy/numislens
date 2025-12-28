# Numislens Deployment Guide

## Overview
Numislens is a Progressive Web Application (PWA) for AI-powered coin identification and grading. This guide provides instructions for deploying the application.

## Prerequisites
- Node.js (v14 or higher)
- npm or yarn package manager
- A web server capable of serving static files
- SSL certificate (required for PWA features and camera access)

## Installation

### 1. Clone the repository
```bash
git clone https://github.com/bedardandy/numislens.git
cd numislens
```

### 2. Install dependencies
```bash
npm install
```

### 3. Build the application
```bash
npm run build
```

## Development Server

To run the application locally for development:

```bash
npm run dev
```

The application will be available at `http://localhost:3000`

## Production Deployment

### Option 1: Static Hosting (Recommended)
Since Numislens is a PWA, it can be deployed as static files to any web server:

1. Build the production version:
```bash
npm run build
```

2. Upload the contents of the `public` directory to your web server

3. Ensure your server is configured with:
   - HTTPS (required for PWA features and camera access)
   - Proper MIME types for service worker files (.js)
   - Cache headers for static assets

### Option 2: Using a PaaS (Netlify, Vercel, etc.)
1. Connect your GitHub repository to your chosen platform
2. Set build command to: `npm run build`
3. Set publish directory to: `public`

## Configuration

### API Integration
To connect to the llama.cpp server with vision capabilities:

1. Start your llama.cpp server with vision support:
   ```bash
   ./server -m your-vision-model.gguf --port 8080 --chat-template llama3 -c 4096
   ```

2. Update the API endpoint in `public/js/aiService.js` if using a different port:
   ```javascript
   this.apiEndpoint = 'http://localhost:8080/v1/chat/completions';
   ```

3. The application uses the default llama.cpp API key ('sk-llama') which can be changed in the configuration.

4. Ensure your model supports image inputs (like LLaVA, Phi-3 Vision, etc.)

### PWA Settings
Customize PWA settings in `public/manifest.json`:
- App name and short name
- Theme colors
- Icons (replace placeholder icons in `public/icons/`)

## Environment Variables
Create a `.env` file in the root directory:

```env
# API Configuration
REACT_APP_API_BASE_URL=https://your-ai-api-endpoint.com
REACT_APP_API_KEY=your-api-key-here

# Application Settings
REACT_APP_ENVIRONMENT=production
```

## SSL Certificate
A valid SSL certificate is required for:
- PWA installation
- Camera access via HTTPS
- Service worker registration

## Troubleshooting

### PWA Not Installing
- Ensure HTTPS is enabled
- Verify manifest.json is properly configured
- Check service worker is registered

### Camera Access Issues
- Ensure the site is served over HTTPS
- Check browser permissions for camera access
- Verify the `capture="environment"` attribute is set

### AI Service Errors
- Verify API endpoint configuration
- Check API key validity
- Ensure proper CORS settings

## Performance Optimization

### Image Optimization
- Images are automatically resized to optimal dimensions
- Maximum upload size is 5MB per image
- Consider implementing lazy loading for results

### Caching Strategy
- Service worker caches essential assets
- Implement cache versioning for updates
- Consider caching API responses for offline use

## Security Considerations

- All API communication should be over HTTPS
- Validate and sanitize uploaded images
- Implement rate limiting for API calls
- Store API keys securely, never in client code

## Updating the Application

1. Pull the latest code
2. Install any new dependencies
3. Rebuild the application
4. Replace static files on your server
5. Update service worker cache version to force updates

## Support

For issues with deployment, please check:
- Console logs in browser developer tools
- Network tab for API request issues
- Server logs for configuration problems

## License

This project is licensed under the GPL-3.0 License - see the LICENSE file for details.