# Sports Broadcast Audio Remix System

A Flask-based web application that separates commentator voices from crowd noise in sports broadcast audio. Users can remix the audio to their preference—muting commentary, amplifying crowd atmosphere, or finding a custom balance between the two.

## Features

- **Automatic Audio Analysis** — Analyzes uploaded videos to detect commentary, music, crowd noise, ambient sounds, and effects
- **AI-Powered Stem Separation** — Uses Demucs (Meta's state-of-the-art ML model) to separate vocals from background audio
- **Interactive Mixing** — Adjust commentary and crowd levels with intuitive sliders
- **Smart Recommendations** — Auto-suggests optimal mixing parameters based on detected audio components
- **Video Processing** — Remixes audio while preserving original video quality (lossless video copy, AAC audio encoding)
- **Fallback Handling** — Graceful degradation with safe defaults if analysis fails

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Backend Framework | Flask |
| Audio Processing | FFmpeg |
| Stem Separation | Demucs (htdemucs model) |
| Spectral Analysis | NumPy, FFT |
| File Handling | Werkzeug |
| Frontend | HTML/CSS/JavaScript |

## Installation

### Prerequisites

- Python 3.8+
- FFmpeg (for audio extraction and video processing)
- Demucs (for stem separation)

### Setup

1. **Clone/Navigate to project directory**
   ```bash
   cd testappspechproto
   ```

2. **Create virtual environment**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. **Install Python dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Install system dependencies**

   **macOS:**
   ```bash
   brew install ffmpeg
   pip install demucs
   ```

   **Ubuntu/Debian:**
   ```bash
   sudo apt-get install ffmpeg
   pip install demucs
   ```

   **Windows:**
   - Download FFmpeg from [ffmpeg.org](https://ffmpeg.org/download.html)
   - Add to PATH, then: `pip install demucs`

5. **Run the application**
   ```bash
   python app.py
   ```
   Navigate to `http://localhost:5000` in your browser.

## Project Structure

```
testappspechproto/
├── app.py                    # Main Flask application
├── requirements.txt          # Python dependencies
├── README.md                 # This file
├── templates/
│   └── index.html           # Web interface
├── static/
│   ├── app.js               # Frontend logic
│   └── styles.css           # Styling
├── uploads/                 # Temporary video uploads
├── processed/               # Final remixed videos
└── work/                    # Processing scratch space
```

## How It Works

### Phase 1: Upload & Analysis
1. User uploads a video (mp4, mov, mkv, avi, webm)
2. File is validated and stored with a unique UUID
3. System extracts first 25 seconds of audio and analyzes spectral features

### Phase 2: Component Detection
The analysis computes 6 audio features:
- **Bass Energy** — Low frequencies (20-250 Hz)
- **Mid Energy** — Mid frequencies (400-2500 Hz)
- **Treble Energy** — High frequencies (4000-12000 Hz)
- **Spectral Flatness** — Timbral diversity
- **Zero-Crossing Rate** — Pitch and noise indicator
- **Transientness** — Percussive/attack content

These features are matched against 5 audio component prototypes using distance-based classification:
- Commentary
- Music
- Stadium (crowd)
- Ambient Noise
- Effects

The system returns estimated percentages for each component and suggests initial slider settings.

### Phase 3: Processing
1. **Audio Extraction** — Extracts audio from video at 44100 Hz
2. **Stem Separation** — Uses Demucs to split into:
   - `vocals.wav` (commentary)
   - `no_vocals.wav` (background/crowd)
3. **Mixing** — Applies user-specified gain adjustments:
   - Commentary reduction (0-90%)
   - Stadium reduction (0-60%)
4. **Remuxing** — Attaches processed audio back to original video

### Phase 4: Download
User downloads the remixed video with their custom audio balance.

## API Endpoints

### GET `/`
Serves the web interface.

### POST `/upload`
Uploads a video and analyzes its audio.

**Request:**
```json
{
  "video": <file>
}
```

**Response:**
```json
{
  "video_id": "abc123def456",
  "video_url": "/media/uploads/abc123def456_sample.mp4",
  "analysis": {
    "components": {
      "commentary": 35,
      "music": 15,
      "stadium": 30,
      "ambient_noise": 15,
      "effects": 5
    },
    "mix_recommendations": {
      "commentary_reduction": 31,
      "stadium_reduction": 45,
      "note": "..."
    },
    "note": "Model inference complete. Components detected for stem-mix guidance."
  },
  "filename": "sample.mp4"
}
```

### POST `/process`
Processes the video with user adjustments.

**Request:**
```json
{
  "video_id": "abc123def456",
  "reductions": {
    "commentary": 50,
    "stadium": 25
  }
}
```

**Response:**
```json
{
  "output_url": "/media/processed/abc123def456_mixed.mp4"
}
```

### GET `/media/uploads/<filename>`
Serves uploaded video files.

### GET `/media/processed/<filename>`
Serves processed/remixed video files.

## Configuration

Edit `app.py` to customize:

| Setting | Default | Purpose |
|---------|---------|---------|
| `MAX_CONTENT_LENGTH` | 1 GB | Maximum upload file size |
| `ALLOWED_EXTENSIONS` | mp4, mov, mkv, avi, webm | Supported video formats |
| Sample rate (analysis) | 22050 Hz | Lower = faster analysis |
| Sample rate (processing) | 44100 Hz | Higher = better quality |
| Audio codec (output) | AAC 192kbps | Compression format |

## Demucs Model Details

The system uses the **htdemucs** model with **two-stems=vocals** mode:
- **Model:** htdemucs (state-of-the-art CNN for source separation)
- **Output:** Separates audio into vocals and background
- **Speed:** ~10-30 seconds per minute of audio (GPU-accelerated if available)
- **Accuracy:** ~8-10 dB improvement on typical benchmarks

## Error Handling

The system includes robust fallback mechanisms:

1. **Audio Analysis Fails** → Uses safe default percentages (25% commentary, etc.)
2. **Demucs Not Installed** → Tries multiple Python paths and venv locations
3. **FFmpeg Error** → Returns detailed error message to user
4. **Short Audio** → Triggers fallback if < 4096 samples detected

## Performance Notes

- **Upload time:** Depends on file size (1-5 minutes for typical sports clips)
- **Analysis time:** ~1-2 seconds for first 25 seconds of audio
- **Stem separation:** ~30-60 seconds for typical sports broadcast
- **Remixing:** ~10-20 seconds for final video processing

