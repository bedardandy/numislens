#!/bin/bash

# Build script for Numislens PWA
# This script prepares the application for deployment

echo "Building Numislens application..."

# Create build directory if it doesn't exist
mkdir -p build

# Copy public directory contents to build
cp -r public/* build/

# Create a zip file for easy deployment
cd build
zip -r ../numislens-pwa.zip .
cd ..

echo "Build completed! The application is ready for deployment."
echo "Deployment files are in the 'build' directory."
echo "Alternatively, you can use the 'numislens-pwa.zip' file for deployment."

echo ""
echo "To run the application with llama.cpp:"
echo "1. Start your llama.cpp server with vision capabilities:"
echo "   ./server -m your-model.gguf --port 8080 --chat-template llama3"
echo "2. Ensure the model supports image input (like LLaVA or similar)"
echo "3. Set the API endpoint in aiService.js to match your server configuration"
echo "4. Serve the build directory using a web server with HTTPS"