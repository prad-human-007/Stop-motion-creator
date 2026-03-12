# Stop Motion Creator

Create a stop-motion MP4 video from a folder of images.

## Python version
- Minimum: Python 3.10
- Recommended: Python 3.11

## Setup (Conda - recommended for your machine)
```bash
conda create -n stop-motion python=3.11 -y
conda activate stop-motion
pip install -r requirements.txt
```

## Setup (venv alternative)
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Configure
Update settings in `config.json`.

Current input folder path is:
`/Users/prad/Projects/Stop-Motion/Photos`

Important video settings:
- `fps`: playback speed
- `codec`: OpenCV writer codec (default `mp4v`)
- `postprocess_h264`: when `true`, script re-encodes final output to H.264 using ffmpeg for better player compatibility
- `ffmpeg_binary`: ffmpeg command path (default `ffmpeg`)
- `h264_crf`: quality setting for H.264 (lower = higher quality, default `18`)
- `h264_preset`: encoding speed/efficiency tradeoff (default `medium`)

## Run
```bash
python stop_motion.py --config config.json
```

Output video is written to the `output/` folder by default.

## Note about green screen preview on macOS
If Finder/Quick Look shows a green video at some FPS values (for example 8 FPS), that is usually a decode compatibility issue with `mp4v` preview, not bad input images.

This project now supports automatic H.264 post-processing (`postprocess_h264: true`) to avoid that issue.
