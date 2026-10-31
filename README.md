# Tamil Cinematic Reels

A human-reviewed pipeline for generating a vertical cinematic Reel and preparing a manual Instagram publishing package.

## Pipeline

1. Google Sheets / Apps Script creates a five-scene story. A human must approve it before dispatch.
2. **Generate cinematic Reel** (`render-reel.yml`) receives the approved story JSON, validates all five scenes, generates five still images, renders a 1080×1920 visual reel, and creates separate ambience and sound-effect audio stems. It stores the exact `story.json` with the render artifact.
3. **Build Instagram Publishing Package** (`build-instagram-package.yml`) starts only after a successful render. It downloads the artifact from that exact render run, uses the matching `story.json`, generates Tamil narration, burns English subtitles once, mixes narration with ambience and sound effects, and creates the cover and caption.
4. A person downloads and reviews the package. Instagram publishing remains manual; no workflow in this repository posts to Instagram.

## Output package

The `instagram-publishing-package` artifact contains:

- `final_reel.mp4` — 1080×1920 video with Tamil narration, English subtitles, ambience and supported sound cues.
- `reel_cover.jpg` — vertical cover frame.
- `instagram_caption.txt` — Tamil and English caption plus hashtags.
- `english_subtitles.srt` — separate English subtitle file.

Artifacts are retained for seven days by the workflows. Download and archive any approved final package before expiry.

## Required repository files

- `.github/workflows/render-reel.yml`
- `.github/workflows/build-instagram-package.yml`
- `.github/workflows/assemble-final-reel.yml` (manual retry path)
- `.github/workflows/generate-tamil-voice.yml` (standalone narration diagnostic)
- `render_reel.py`
- `assemble_final_reel.py`
- `generate_tamil_voice.py`
- `requirements.txt`

## GitHub Actions setup

1. Push the repository to GitHub with the default branch set to `main` (or update the dispatch ref in your Apps Script configuration if you use another branch).
2. In **Settings → Actions → General**, allow the repository's workflows to run.
3. Ensure Actions artifacts are enabled.
4. The render workflow uses the configured OVH AI Stable Diffusion XL endpoint in `render_reel.py`. Check that the endpoint is reachable and that your usage is permitted before production use.
5. No Instagram token or publishing secret is required because publishing is deliberately manual.

## Story JSON contract

The render workflow requires exactly five scenes. Each scene must include:

- `visual_prompt`
- `tamil_narration`
- `english_subtitle`
- `speaker_gender` (`male` or `female`)
- `duration_seconds` (positive number; defaults to 6 if omitted)

Optional story-level fields include `character_description`, `hook`, `sound_design`, `caption_tamil`, `caption_english`, and `hashtags`.

For character consistency, provide a clear `character_description` and repeat important identifying clothing/appearance details in each `visual_prompt`. The image service generates each scene independently; visual identity consistency is encouraged by prompts, not guaranteed by a shared reference-image system.

The renderer scales the five `duration_seconds` weights to a 30-second total. The final assembler uses those same weights to align narration and subtitle timing with the rendered scene cuts.

## Narration and audio

- Primary voice provider: Microsoft Edge TTS.
- Fallback: Google gTTS. The fallback is Tamil-language but does not preserve the male/female voice selection.
- Automatic narration speed-up is limited to 1.25×. If a scene's narration is too long, the assembly job stops and asks for shorter text instead of aggressively speeding it up or cutting speech.
- The ambience stem is synthesized locally. Clock, shutter and flash cues are synthesized when the `sound_design` text includes the corresponding terms.
- Sound effects are generated procedurally; they are not recordings of real clocks or cameras.

## Manual retry

If the automatic package workflow fails after a successful render:

1. Open the successful **Generate cinematic Reel** run in GitHub Actions and copy its run ID.
2. Open **Build Instagram Publishing Package** → **Run workflow**.
3. Enter that source run ID and run the workflow manually.
4. Download `instagram-publishing-package` only after the workflow succeeds.

Alternatively, **Assemble Final Tamil Reel (manual retry)** uses the same source artifact and produces the same four-file review package.

## Dashboard status

`index.html`, `styles.css`, and `app.js` implement a read-only Apps Script JSONP dashboard. It displays the fields returned by the Apps Script endpoint. The dashboard frontend can display a run-specific URL/status if the endpoint supplies `githubRunUrl` and `githubStatus`; the Apps Script `Code.gs` is not included in this ZIP, so GitHub run-ID polling and artifact-status synchronization must be integrated in that separate script before those fields will appear. Do not treat the current general Actions link as a specific run link.

## Local validation (no production render)

Run syntax checks only:

```bash
python -m py_compile render_reel.py assemble_final_reel.py generate_tamil_voice.py
node --check app.js
```

These checks do not call the image API, generate TTS, dispatch GitHub workflows, or publish content.


## Google Sheets backend and run tracking

The matching Apps Script source is included as `Code.gs`. Follow `APPS-SCRIPT-SETUP.md` before enabling GitHub callback tracking or the hourly dispatcher. Do not commit API keys or callback secrets. Instagram publishing remains manual.
