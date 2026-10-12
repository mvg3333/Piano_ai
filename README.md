# Piano AI

A working local piano practice app: paste a YouTube performance link, upload audio/video, or import MIDI, then practice with synchronized sheet music, falling notes, keyboard, and sound. The original **Windowlight** demo is immediately playable without model setup.

## Run on this Windows computer

The project-local toolchains and dependencies have been installed in this workspace. In PowerShell:

```powershell
cd C:\projects\MyPythonProjects\Piano_ai
.\.venv\Scripts\python.exe -m scripts.run
```

Open **http://localhost:8000**. The launcher starts both the API and transcription worker; Ctrl+C stops both. If port 8000 is occupied, use `.\.venv\Scripts\python.exe -m scripts.run --port 8001`.

## Fresh Windows setup

Install a current Python from [python.org](https://www.python.org/downloads/windows/) if `python` is unavailable. The setup script installs isolated Python **3.11.17**, portable Node **24.21.0**, pinned dependencies, and optionally the transcription model. It does not replace your system Python 3.14.

```powershell
cd C:\projects\MyPythonProjects\Piano_ai
python scripts/setup.py --with-piano-model
.\.venv\Scripts\python.exe -m scripts.run
```

Omit the model flag for demo/MIDI practice only. `--with-piano-model` installs the piano-specific CRNN; `--with-model` installs Basic Pitch as an optional fallback. Both flags can be used together. Downloads require internet; the CPU environment occupies several hundred megabytes, including a 172 MB piano checkpoint. The Python setup works with restrictive PowerShell script policies and does not change execution policy. Optional PowerShell wrappers are also provided for environments that allow them.

To add the piano model to an existing installation without rebuilding the app:

```powershell
.\.venv\Scripts\python.exe -m scripts.setup_piano
.\.venv\Scripts\python.exe -m scripts.doctor
```

Restart the server afterward. Installing a model does not change previously saved transcriptions. In **My pieces → Cleanup & regenerate**, choose **Re-transcribe audio** to run inference on the saved audio and create a new copy. The original piece and its manual corrections remain intact. Ordinary cleanup and score regeneration work with the notes already detected.

Already have Node 24 and Python 3.11? Equivalent commands:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.lock
.\.venv\Scripts\python.exe -m scripts.setup_piano
npm.cmd --prefix frontend ci
.\.venv\Scripts\python.exe -m backend.demo
npm.cmd --prefix frontend run build
.\.venv\Scripts\python.exe -m scripts.run
```

### FFmpeg and model

FFmpeg **and ffprobe** must be on PATH for audio/video input. This workspace was verified using FFmpeg 4.2.11 supplied with GNU Octave. For a separate Windows installation, use a build linked from the [official FFmpeg download page](https://ffmpeg.org/download.html), then add its `bin` directory to your user PATH. Alternatively set full executable paths before running:

```powershell
$env:PIANO_FFMPEG = 'C:\tools\ffmpeg\bin\ffmpeg.exe'
$env:PIANO_FFPROBE = 'C:\tools\ffmpeg\bin\ffprobe.exe'
.\.venv\Scripts\python.exe -m scripts.doctor
```

The piano-specific [Kong/ByteDance CRNN](https://github.com/qiuqiangkong/piano_transcription_inference) runs on PyTorch CPU in `.venv-piano`. It predicts piano note attacks, releases, velocities, and sustain pedal events. Its checkpoint is downloaded from the authors' [Zenodo release](https://zenodo.org/records/4034264) into `.tools/models/piano-crnn.pth`, with SHA-256 verification and an atomic replacement. The pinned PyTorch wheel targets Windows x64 and Python 3.11. No shell downloader or API key is required.

The app prefers this model when installed; otherwise it uses Basic Pitch if available. Basic Pitch 0.4.0 uses TensorFlow 2.15.0 on CPU in `.venv-model`, with pretrained weights included in its package. The piano model is a larger computation and can take longer than Basic Pitch; processing time depends on the recording and computer. It is a better-matched model for solo piano, not a guarantee of perfect transcription. Keep the original audio available to check quiet notes, repeated attacks, and pedal-heavy passages. See [model attribution](THIRD_PARTY_NOTICES.md).

### Phone or tablet on the same Wi-Fi

Keep the Windows computer awake and run the Python launcher. It binds to `0.0.0.0` and prints candidate LAN URLs. Use `ipconfig` to find the Wi-Fi adapter's IPv4 address, then open **http://YOUR-PC-IP:8000** on the phone/tablet. `localhost` on a phone means the phone, not your PC.

If Windows Firewall prompts, allow the Python server on **Private networks**. Keep the firewall enabled. Both devices must be on the same non-isolated Wi-Fi network; guest Wi-Fi often prevents connections. Do not configure router port forwarding.

Ordinary practice/audio works over LAN HTTP after tapping Play. Service workers/PWA caching and screen wake generally require HTTPS or localhost. For those features on a phone, configure a trusted local HTTPS reverse proxy and a certificate trusted by that device. Never bypass certificate warnings. Fullscreen and installation vary by browser, especially iOS.

## Practice workflow

1. Play **Windowlight**, or choose **New piece**.
2. Import MIDI directly; or submit audio/video or a YouTube link, choose an interval, and transcribe.
3. Select Score, Falling notes, or Combined. Adjust the divider, notation size, and keyboard range in settings.
4. Use speed, A-B loop, count-in, metronome, hand selection, or transpose. Drag the timeline or tap a score measure to seek.
5. Choose **Piano**, **Original audio**, or **YouTube video** in the transport or settings. Original sources are mutually exclusive with synthesized audio. Transpose/hand muting apply to synthesized playback.
6. Tap a falling note or choose a note in settings to correct pitch, onset, duration, deletion, or hand. Regenerate after changing tempo, meter, grid, or downbeat. Raw transcription stays intact.
7. Imported/transcribed pieces and corrections save to **My pieces**. Export performance MIDI or draft MusicXML from settings.

Each saved entry in **My pieces** has **Cleanup & regenerate** and **Delete** actions. Cleanup & regenerate opens that piece's cleanup strength, tempo, meter, quantization, and downbeat settings; **Apply & regenerate** saves the changes to the same piece, preserving its original notes and manual corrections. Deleting requires confirmation and removes the piece, its revisions, and its local practice files. Deleting the piece currently open returns practice to Windowlight. The bundled demo is always available.

For audio transcriptions, **Practice settings → Reduce stray notes** offers Off, Balanced (default), and Strong. Balanced preserves the piano CRNN's detections; Strong can hide short, quiet notes that also have weak attack support. Basic Pitch uses separate filtering appropriate to its output. Cleanup applies consistently to notation, falling notes, synthesized playback, and exports. The original detections remain intact; Off restores them, and manual corrections take priority. Quiet legitimate notes can be hidden, so compare with the original recording and try Off when notes are missing. Cleanup cannot recover notes the model never detected. MIDI imports are not filtered.

Audio transcription hand labels use nearby notes, chord ranges, and phrase continuity. Middle C can belong to either hand: an accompaniment can rise above it, and a melody can dip below it. Regenerating an older audio piece also updates these hand estimates without running the audio model again. Manual note corrections take priority, and the raw detections remain intact. The score, falling notes, and synthesized hand selection use the same saved assignments.

YouTube embedding and downloading are separate. Acquisition uses pinned yt-dlp, its EJS package, Node, and FFmpeg. Availability can change with YouTube, location, restrictions, or extractor changes. The app does not bypass login, DRM, age restrictions, or access controls. If acquisition fails, Upload instead retains the video reference. A selected interval limits transcription; acquisition may download the whole permitted recording.

YouTube pieces use the video's title. A public metadata lookup fills in the name when you enter a link; the downloader also supplies it when acquiring audio. If metadata is temporarily unavailable, the name defaults to “YouTube performance.” To update older automatic video-code names, run `.\.venv\Scripts\python.exe -m scripts.refresh_youtube_titles`. This preserves custom titles, notes, and corrections.

## Development and verification

After setup, add bundled Node to the current terminal PATH:

```powershell
$env:PATH = "$PWD\.tools\node-v24.21.0-win-x64;" + $env:PATH
.\.venv\Scripts\python.exe -m pytest backend\tests -q
npm.cmd --prefix frontend test
npm.cmd --prefix frontend run build
```

Browser tests start an isolated test server on port 8001 and use `data/browser-tests`:

```powershell
.\frontend\node_modules\.bin\playwright.cmd install chromium
npm.cmd --prefix frontend run test:browser
```

For hot reload, keep the API/worker running and execute `npm.cmd --prefix frontend run dev`; Vite proxies `/api` to port 8000. PWA checks use the production build.

Optional real inference: `.\.venv\Scripts\python.exe -m scripts.benchmark`. This downloads an attributed CC BY-NC 3.0 piano example into ignored `data/benchmark`, for local noncommercial verification. It is not bundled. `scripts.verify_jobs` additionally tests interval processing, exports, media ranges, and running-job cancellation against the live app. `scripts.verify_youtube` tests the model project's public demonstration video.

See [architecture](docs/ARCHITECTURE.md), [verification results](docs/VERIFICATION.md), and [sample attribution](frontend/public/samples/ATTRIBUTION.txt). Data lives in `data/`; back up that directory with the app stopped. Environment overrides: `PIANO_DATA_DIR`, `PIANO_MODEL_PYTHON` (Basic Pitch), `PIANO_CRNN_PYTHON`, `PIANO_CRNN_CHECKPOINT`, `PIANO_NODE`, `PIANO_MAX_BYTES`, `PIANO_MAX_SECONDS`. Setup installs models at the project-local defaults; the CRNN overrides select existing alternative locations at runtime.

## Limitations

- Solo piano is the target. Accompaniment, reverb, and pedal can merge or miss notes. No accuracy percentage is claimed.
- The piano CRNN estimates sustain pedal; Basic Pitch does not detect pedal here. Imported MIDI pedal events are retained. Audio hand assignments use musical context and remain editable estimates; they do not identify the pianist's actual fingering. Imported MIDI and the composed demo retain their existing hands.
- Notation is a quantized draft, not a full editor. Meter is user-supplied (4/4 initially). Imported meter events remain raw but the draft uses one meter; imported tempo changes can be retained. Complex voices/rubato often need corrections.
- Uploaded-source playback is the selected, normalized mono interval. YouTube retains the original visible video; seek/loop precision depends on its player.
- Offline caching covers the shell, samples, and demo only. Saved pieces/transcription need the host. Backgrounding pauses playback deliberately.
- Browser emulation is not physical iPhone/iPad/Android testing. The app does not listen to or grade your playing.
