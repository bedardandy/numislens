# Numislens - AI Coin Identifier

Numislens is a Progressive Web Application (PWA) that uses AI to identify and grade antique and rare coins. Simply take pictures of the front and edge of your coin to get identification, condition grade, and value estimation.

## Repository layout

- **`core/`** — the collection ledger: a dependency-free Python package (`numislens_core`) over a single SQLite database, plus its data (SQL migrations, the compositions seed, and set manifests in `core/sets/`). This is the source of truth for the whole platform. Run its tests with `cd core && python3 -m pytest`.
- **`daemon/`** — FastAPI REST + OpenAPI surface, bearer auth, label PDFs.
- **`ops/`** — operational files: user-level systemd units for the daily melt update, plus Litestream and dump-based backup config. See `ops/README.md` and `ops/BACKUP.md`. Nothing here is installed or enabled automatically.
- **`public/`** — the existing vanilla-JS PWA. It is slated for a thin rebuild against the core API in a later phase; treat it as legacy for now.

### Core CLI quickstart

The `core/` package installs a `numislens` console script (`pip install -e core`). The database resolves from `--db`, then `$NUMISLENS_DB`, then `~/.local/share/numislens/numislens.db`.

```bash
numislens init                                          # create/migrate the database
numislens add --series "Peace Dollar" --year 1921 \
  --mint P --composition 4 --value-basis melt           # returns an accession, e.g. NL-000001
numislens melt update                                   # fetch dual-source spot, recompute melt values
numislens melt status                                   # latest spots + portfolio melt + daily change
```

Melt fetching is keyless and fail-loud: it never fabricates a price and exits non-zero on source disagreement (>2%), staleness (>48h), or network errors. Read commands (`show`, `find`, `set gaps`, `set status`, `melt status`) accept `--json`.

## Features

- **AI-Powered Identification**: Uses advanced AI to identify coin types
- **Condition Grading**: Evaluates coin condition using standard numismatic scales
- **Value Estimation**: Provides ballpark value estimates without external pricing APIs
- **PWA Support**: Works offline, installable on mobile and desktop
- **Camera Integration**: Direct camera access for easy image capture
- **Image Processing**: Optimizes images for better AI analysis

## How It Works

1. **Capture Images**: Take photos of the front and edge of your coin
2. **AI Analysis**: Our AI model identifies the coin type and evaluates condition
3. **Get Results**: Receive identification, grade, and value estimate
4. **Save/Share**: Save results or share with others

## Technology Stack

- **Frontend**: Vanilla JavaScript, HTML5, CSS3
- **Architecture**: Progressive Web App (PWA)
- **AI Integration**: OpenAI-compatible API (configured for llama.cpp)
- **Image Processing**: Client-side preprocessing
- **Offline Support**: Service Worker caching

## Installation

### Prerequisites
- Node.js (v14 or higher)
- npm or yarn package manager

### Setup
```bash
# Clone the repository
git clone https://github.com/bedardandy/numislens.git
cd numislens

# Install dependencies
npm install

# Start development server
npm run dev
```

The application will be available at `http://localhost:3000`

## Usage

1. Open the application in a modern browser (Chrome, Firefox, Safari, Edge)
2. Allow camera access when prompted
3. Take photos of the front and edge of your coin
4. Click "Analyze Coin" to get results
5. Review identification, grade, and value estimate

## API Integration

The application is designed to work with an OpenAI-compatible API, specifically configured for llama.cpp with vision capabilities. To configure:

1. Start your llama.cpp server with vision support:
   ```bash
   ./server -m your-vision-model.gguf --port 8080 --chat-template llama3 -c 4096
   ```

2. Update the API endpoint in `public/js/config.js` if using a different port:
   ```javascript
   apiEndpoint: 'http://localhost:8080/v1/chat/completions',
   ```

3. The application uses the default llama.cpp API key ('sk-llama'), set in `public/js/config.js`, which can be changed there.

4. Ensure your model supports image inputs (like LLaVA, Phi-3 Vision, etc.)

## PWA Features

- **Installable**: Add to home screen on mobile or desktop
- **Offline Support**: Core functionality works without internet
- **Responsive**: Works on mobile, tablet, and desktop
- **Fast Loading**: Service worker caches assets for quick access

## Components

- `public/index.html` - Main application structure
- `public/js/config.js` - Central configuration (endpoint, model, key, timeout)
- `public/js/app.js` - Core application logic
- `public/js/aiService.js` - AI integration layer
- `public/js/gradingSystem.js` - Coin grading algorithms
- `public/js/valueEstimation.js` - Value calculation algorithms
- `public/js/imageProcessor.js` - Image processing functions
- `public/styles/main.css` - Styling
- `public/sw.js` - Service worker for PWA features

## Testing

Run the test suite to validate functionality:

```bash
npm test
```

## Deployment

See `DEPLOYMENT.md` for detailed deployment instructions.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

This project is licensed under the GPL-3.0 License - see the LICENSE file for details.

## Acknowledgments

- AI model integration using qwenVL3-30B3A
- Numismatic grading standards based on industry practices
- PWA technologies for enhanced user experience

## Support

For support, please open an issue in the GitHub repository.