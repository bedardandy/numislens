# Numislens - AI Coin Identifier

This repository contains the complete Numislens application - a Progressive Web Application that uses AI to identify and grade antique and rare coins using images of the front and edge.

## Project Status

The project is fully developed and ready for deployment. All source code, documentation, and build scripts are included.

## GitHub Setup Instructions

To complete the GitHub setup and push the code to the remote repository, follow these steps:

### Option 1: Using Personal Access Token (Recommended)

1. Create a Personal Access Token on GitHub:
   - Go to GitHub Settings > Developer settings > Personal access tokens > Tokens (classic)
   - Click "Generate new token"
   - Select the "repo" scope
   - Copy the generated token

2. Update the remote URL with your token:
   ```bash
   git remote set-url origin https://<your_token>@github.com/bedardandy/numislens.git
   ```

3. Push the code:
   ```bash
   git push -u origin master
   ```

### Option 2: Using SSH (Alternative)

1. Generate an SSH key pair:
   ```bash
   ssh-keygen -t rsa -b 4096 -C "andy@example.com"
   ```

2. Add the SSH key to your GitHub account:
   - Copy the public key: `cat ~/.ssh/id_rsa.pub`
   - Go to GitHub Settings > SSH and GPG keys
   - Click "New SSH key" and paste your public key

3. Change the remote URL to use SSH:
   ```bash
   git remote set-url origin git@github.com:bedardandy/numislens.git
   ```

4. Push the code:
   ```bash
   git push -u origin master
   ```

## Project Structure

- `public/` - Contains the PWA frontend files (HTML, CSS, JS)
- `src/utils/` - Contains utility modules (AI service, grading system, etc.)
- `src/config.js` - Configuration settings
- `build.sh` - Build script for packaging the application
- `DEPLOYMENT.md` - Deployment instructions
- `README.md` - Project documentation

## Features

- AI-powered coin identification using OpenAI-compatible API (configured for llama.cpp)
- Coin grading system based on standard numismatic scales
- Value estimation algorithm
- PWA functionality with offline support
- Camera integration for mobile devices
- Image processing for coin analysis

## API Configuration

The application is configured to work with a local llama.cpp server. To set up the AI backend:

1. Start your llama.cpp server with vision capabilities:
   ```bash
   ./server -m your-vision-model.gguf --port 8080 --chat-template llama3 -c 4096
   ```

2. The frontend is configured to connect to `http://localhost:8080` by default

## Deployment

To deploy the application:
1. Run `./build.sh` to create the build package
2. Serve the `build` directory using a web server with HTTPS support
3. Ensure the llama.cpp server is accessible from the deployment environment

For more detailed instructions, see the `DEPLOYMENT.md` file.