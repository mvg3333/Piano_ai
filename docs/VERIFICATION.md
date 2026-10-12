# Verification report

Verified on Windows on 2026-10-11. These results describe this workspace, not a guarantee of transcription accuracy or third-party availability.

## Automated checks

### Simplify arrangement verification

- The arrangement regressions cover all four presets, independent hand settings, immutable sources and snapshots, melody below upper accompaniment, octave doubling, arpeggios, dense chords, weak ornamental runs, repeated accents, melody changing hands, protected notes, and explicit roles. Important sustained bass changes inside a single measure survive accompaniment reduction.
- Timing checks cover retained melody attacks/releases, pickups, imported tempo changes, MusicXML schema and measure-duration validation, source-linked fragments, MIDI event round-trips, and trailing silence. Physical-demand checks use overlapping key-down intervals and separately report melody exceptions.
- Persistence tests cover the additive version 3 schema, outdated arrangements, shared guidance, regeneration into new versions, selected exports, invalid settings/IDs, generation failures, source-change races, and deletion races. Bounded melody/harmony analysis is exercised on 10,000 notes.
- Frontend checks cover A/B switching while playing or paused, held notes, loop boundaries, speed/position continuity, external-to-synth comparison, and arrangement pedal events. The browser workflow covers generation, restored selection/settings, guidance/protection, explicit refresh, unchanged prior versions, score-note mappings, selected export links, and the mobile panel. Existing practice, offline, library, transcription, hand-correction, and YouTube tests remain included.
- Production build, all 96 backend tests, and 15 frontend unit tests pass. All nine browser tests pass, including the new arrangement workflow. Desktop and mobile screenshots were inspected; the score and keyboard now size to the available space above transport controls.

On the original Windowlight study, all 96 composed melody notes survive, including its accented octave-register change. Beginner reduces 64 accompaniment notes to 17; Easy retains additional source accents. These are controlled structural checks, not a human listening evaluation or a general accuracy claim. Competing melodic voices, uncertain harmony, ornament-versus-theme decisions, hand crossings, expressive overlap/pedaling, and retained wide jumps still need musical review. The UI reports these judgments and explains transformations; retained melody timing is unchanged and general rhythmic simplification remains deferred.

### Existing transcription checks

- Production TypeScript/Vite build passes.
- Backend: 79 tests cover expressive time/beat mapping, tempo changes, downbeat alignment, pickups/ties, immutable raw notes, MIDI chords/repeated notes/sustain round-trips, official MusicXML 4.0 XSD validation, persistence, input rejection, job retry/cancel APIs, and a real subprocess model-installation failure. Regressions also cover cleanup continuation merging, model-specific cleanup, event normalization, clip boundaries, pedal union, saved-audio snapshots, deletion races, re-transcription settings/offsets, and contextual hand assignment with manual overrides and consistent score/export staff placement.
- Frontend: 12 tests cover keyboard geometry, active-note boundaries, time-map inverses, loop overshoot, voice flushing/reconstruction, repeated pitches, hand muting, speed continuity, a buffered external clock without synthesized voices, and network versus HTTP error messages. Hand muting includes separate middle-C notes assigned to different hands in different phrases.
- Eight browser tests pass: demo playback/pause/seek/loop and responsive layout; MIDI import/correction saving/exports; offline cached demo playback; simulated YouTube rates, state, and player layout; transcription score/cleanup/restore/export; library cleanup/regeneration/deletion; saved-audio re-transcription; and contextual hands. Hand checks cover bass staff and green noteheads, the correction editor, manual right-hand overrides turning purple, and persistence across score regeneration.
- Browser tests use their own API on port 8001 and storage under `data/browser-tests`.
- Library actions were checked at 1280×900 and 390×844. Cancelling draft options leaves settings unchanged; applying cleanup, tempo, meter, grid, and downbeat changes preserves original notes and manual corrections and leaves another saved piece untouched. Delete requires confirmation, persists across reload, and returns the active view to Windowlight when deleting the open piece. Generated screenshots are `frontend/test-results/library-1280x900.png` and `library-390x844.png`.
- The API, Basic Pitch, and piano CRNN environments pass `uv pip check`. npm previously reported zero vulnerabilities for the installed frontend dependency set.
- Setup is provided through Python because this computer's PowerShell execution policy blocks `.ps1` scripts. No execution-policy setting was changed.
- `python scripts/setup.py --with-model` completed successfully, including model loading. The Python launcher started both processes on a spare port and printed the LAN address.

## Real CPU transcription

Recording: **Pistachio Ice Cream Ragtime** by The Piano Lady / Lena Orsa, from [librosa's example collection](https://librosa.org/doc/0.10.2/recordings.html), [original source](https://freesound.org/people/lena_orsa/sounds/442789/). CC BY-NC 3.0. Used only as a local noncommercial verification fixture, excluded from application source/assets.

- Selected interval: 5-15 seconds (10 seconds of real solo piano).
- Engine: Basic Pitch 0.4.0, TensorFlow 2.15.0 CPU, Python 3.11.17.
- Host: Intel64 Family 6 Model 170 Stepping 4; Windows build 26200.
- Measured adapter wall time: **23.363 seconds**, including model-process startup.
- Model-reported inference call: **9.326 seconds** in that run.
- Output: **71 note events**, MIDI pitches **39-92**.
- No aligned ground truth or human scoring was used. Note accuracy, missed-note rate, and timing accuracy were **not measured**. No claim is made that every predicted note is correct. Pedal information is absent, and velocity is model-derived amplitude rather than calibrated key velocity.

The first run exposed a NumPy-integer JSON serialization error after inference. That was fixed with explicit integer conversion, and the successful run above was measured afterward. Other compatibility warnings from the older TensorFlow/Basic Pitch dependencies remain warnings, not suppressed failures.

## Complete upload/worker pipeline

A five-second interval (2-7 seconds) of the locally cached test clip went through upload, FFmpeg decoding, real model inference, score generation, persistence, and export. It produced **39 notes** and retained `clipStart=2` and `duration=5`. Stored source media returned HTTP **206** for a range request. MIDI and MusicXML downloads succeeded. A second job was cancelled while loading the model; the worker terminated its process tree and persisted `cancelled`.

Machine-readable reports are in ignored `data/benchmark/report.json` and `data/benchmark/integration.json`. These are measurements, not benchmark promises for other hardware or recordings.

## YouTube

The public video `5U-WL0QvKCg`, linked from the piano-transcription project's demo, was tested without credentials, cookies, or restriction workarounds. yt-dlp resolved a 75-second WebM audio source. The app acquired it and transcribed the selected **5-10 second** interval, producing **49 notes** and a saved score in **28.047 seconds** of measured job wall time. `clipStart=5` was preserved. Report: `data/benchmark/youtube.json`.

This verifies acquisition on this connection at that time. It does not establish that all videos are available. IFrame playback-rate/state/visible-player behavior is covered with a simulated player; live YouTube playback and its actual buffering/seek precision have not been physically verified.

### Reported recording: pMU3_1VbRn0

Reused the user's already acquired **176.541-second** recording; no new YouTube download was needed. Reproduced the mixed `None`/string tie-sort exception on its **1,104 raw notes**. Fixed that ordering and the duplicate note IDs generated when music21 splits irregular durations into tied segments.

- Re-ran Basic Pitch on the full cached audio and inspected its real onset activations. Balanced cleanup retains **805** events and hides **299** (287 weak-attack candidates, 12 short/weak candidates); Strong retains **676**. Off restores all 1,104. These counts do not measure note accuracy; no aligned ground truth is available.
- The updated full upload/transcription/score/save/export pipeline completed in **24.708 seconds** in isolated storage, with **112 measures** and valid MusicXML against the official schema. Both export routes succeeded.
- Chromium loaded the entire recording, rendered its score, sought to 61 seconds, applied cleanup through the real API, exported, and restored all raw notes through Off. No browser page errors. Screenshot: `frontend/test-results/transcription-cleaned.png` (generated/ignored).
- The existing library piece was repaired with Balanced selected. Its raw JSON checksum and manual edits were preserved. Its previous piece payload and a repair report are under ignored `data/benchmark/stray-notes/`; the full pipeline report is under `data/benchmark/cleanup-pipeline/report.json`.
- To repeat the browser check with the locally prepared recording, set `PIANO_TEST_PIECE` to the absolute path of `data/benchmark/stray-notes/prepared-piece.json` before running `npm.cmd --prefix frontend run test:browser -- transcription.spec.ts`. Without that variable, the test uses a synthetic fixture derived from the bundled demo.

## Piano-specific accuracy upgrade

The default installed engine is now the high-resolution piano CRNN, isolated in `.venv-piano` (PyTorch 2.8.0 CPU, `piano-transcription-inference` 0.0.6). Its official checkpoint passed SHA-256 verification and loaded with PyTorch's safe `weights_only` default. Basic Pitch remains the fallback when the specialist is absent. No user library data is used for training.

### Controlled comparison

`scripts/evaluate_transcription.py` renders a fixed 35-second, 86-note passage using the bundled piano samples. Cases include melody, chords, quiet inner voices, fast repetitions, and wide registers. Matching requires exact MIDI pitch and onset within 50 ms, with maximum one-to-one matching and no fitted time shift. Eight evaluator self-checks pass; an additional 250 randomized matching cases agreed with optimal assignment. Labels were fixed before running either model.

| Balanced cleanup | Correct pitch/onset matches | Missed | Extra detections | Onset F1 | Pitch/onset/release F1 |
|---|---:|---:|---:|---:|---:|
| Basic Pitch, including the sustain cleanup fix | 78 | 8 | 20 | 0.8478 | 0.3587 |
| Piano CRNN, standard decoder | 84 | 2 | 27 | 0.8528 | 0.7919 |

Mean matched onset error decreased from 9.69 ms to 4.64 ms. Quiet-inner-voice matches increased from 19/24 to 22/24. Release matching allows the larger of 50 ms or 20% of reference duration. The CRNN run took 117.07 seconds including its first audio load and model initialization; CPU speed varies with host load.

This synthetic result supports fewer misses and better timing, **not a general 97.7% transcription-accuracy claim**. Extra detections increased, including octave harmonics in the sample-based fixture. A proposed tiny-note filter would improve this particular fixture, but it was not added to Balanced solely to improve the benchmark. No aligned ground truth is available for the YouTube recording.

### Reported interval, 23–25 seconds

The old cleanup truncates contiguous Basic Pitch detections of F3 (23.118–23.862), A3 (23.524–24.280), and C4 (23.897–24.327). The continuation fix joins weak split segments back into their preceding held notes, without adding attacks. A read-only spectral check found continuing energy at those pitches after the old retained segments ended. That is supporting evidence, not annotated ground truth.

On the complete Song of Storms recording, this cleanup fix restores 159 continuation segments (74.41 note-seconds of overlapping held durations) while keeping 805 attacks. Manual corrections and the immutable raw detections are preserved. The full CRNN comparison produced **1,033 notes and 193 estimated pedal spans** in **366.93 seconds**. Counts alone do not establish correctness.

The resulting **112-measure** score validates against the official MusicXML schema. A new library piece, ending in **(new transcription)**, was saved. The source piece was then separately regenerated through its revision API to apply the confirmed continuation fix; its raw checksum, manual edits, and settings were verified unchanged, and its prior payload was backed up. Chromium opened the new score at 24 seconds, with no page errors. MIDI and MusicXML exports returned 200, and the saved recording returned 206 for a range request. Reports and the screenshot are in ignored `data/benchmark/accuracy/`.

Comparison at the user's timestamp remains mixed: the specialist adds an F6 near 23.736 seconds and retains the F6 near 24.092 that old cleanup hid. It also substitutes F2 near 23.098 for Basic Pitch's F3 near 23.118, while local spectral energy favors F3. Other octave disagreements remain uncertain. This is why the new inference is saved separately and is not advertised as a uniformly correct replacement. No song-specific pitch corrections or hand-authored notes were inserted.

The runner crops model predictions to actual audio frames before decoding, then adds twelve silent frames to flush the upstream decoder's final pedal. Real-decoder boundary verification preserves the held note/pedal, discards padded-audio attacks, and caps events at the real clip end. Pure regressions cover fractional-frame durations and immutable prediction inputs.

## Contextual hand assignment

The user-reported middle C starts at **18.899 seconds** in the piano CRNN piece. The former `pitch < 60` rule put it on the right, despite the E3–A3–C4 accompaniment and shared release around 20.56 seconds. Hand inference now uses nearby registers, grouped attacks, voice continuity, hand reach, and rest boundaries. It is an editable estimate of musical roles, not a measurement of actual hands/fingering.

Nine focused algorithm tests cover left arpeggios crossing C4, right melodies descending below it, high left/low right parts, chords/repeated attacks, rest resets, explicit manual crossings, immutable inputs, empty/unsorted notes, and resistance to very brief stray detections. Five backend integration cases verify score staff/color, regeneration, manual corrections, MIDI/demo preservation, and exports. A 100,000-note inference check completed in 2.97 seconds on this host; the 1,033-note recording took approximately 0.04 seconds.

Both saved Song of Storms versions were regenerated through the revision API. The CRNN version changed 58 hand labels and the Basic Pitch version changed 74, including the reported C4. These counts are changes, not measured accuracy. Note counts, pitches, timing, velocities, raw JSON checksums, settings, and manual edits were verified unchanged. Prior piece payloads and validation reports are in ignored `data/benchmark/hands/`.

Both regenerated MusicXML scores validate against the official schema. A live Chromium check at 19.2 seconds verified C4 in green on the left staff and Left in its editor, with no page errors. The screenshot is `data/benchmark/hands/left-middle-c-19s.png`. The local app was restarted with the update; no audio-model rerun was needed.

## Responsive and offline checks

Chromium browser emulation was inspected at **1440x1000, 390x844, 844x390, 768x1024, and 1024x768**. Checks include no page-wide horizontal overflow, a visible persistent Play control, cursor relocation after resize, and the keyboard staying above the transport. Portrait and landscape screenshots are generated in `frontend/test-results`.

The cached demo renders and plays with network access disabled. API/media routes are excluded from the service-worker cache. A normal HTTP LAN origin does not gain secure-context features simply by having a manifest.

**Not verified:** physical iPhone/iPad/Android audio behavior, browser installation UI, real-device wake lock/fullscreen, Bluetooth audio latency, GPU acceleration, note accuracy on the user's recordings, or long-hour performance load. These limits remain explicit in the README and app.
