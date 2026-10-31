# Repair notes — 2026-11-01

This is a source-level repair of the ZIP archive. It does not dispatch a GitHub workflow, call the image-generation endpoint, generate TTS, modify Google Sheets, or publish to Instagram.

## Exact replacements / additions

### Replaced

- `.github/workflows/render-reel.yml`
  - Validates all five scenes and required fields before rendering.
  - Verifies the actual output under `work/` (the previous workflow checked the repository root while the renderer wrote into `work/`).
  - Uploads the video, matching story, ambience stem and SFX stem together.
  - Performs basic resolution and duration checks before upload.

- `.github/workflows/build-instagram-package.yml`
  - Keeps automatic package creation after a successful render.
  - Downloads the artifact from the exact source workflow run.
  - Correctly stages the nested `work/` artifact paths.
  - Uses `requirements.txt` for pip cache key and installation.
  - Validates all four package files and the final video streams.
  - Does not publish to Instagram.

- `.github/workflows/assemble-final-reel.yml`
  - Fixes the prior story-overwrite defect: it uses the story bundled with the selected render artifact and never copies the repository sample story over it.
  - Uses the same assembly and validation process as the automatic package workflow.

- `render_reel.py`
  - Removes the hard-coded Kavin character identity.
  - Supports an optional story-level `character_description` and relies on scene prompts when it is absent.
  - Uses the five scene duration weights to create a 30-second timeline.
  - Leaves English subtitles for final assembly so they are burned only once.
  - Keeps the Tamil hook in the visual render.
  - Creates separate ambience and procedural clock/shutter/flash SFX stems based on the `sound_design` description.

- `assemble_final_reel.py`
  - Uses only the exact `story.json` and render assets downloaded from the same source run.
  - Generates scene-by-scene Tamil narration using the selected Edge TTS voice, with a gTTS fallback.
  - Caps automatic speech speed-up at 1.25× and fails clearly if narration needs shortening.
  - Aligns narration and English subtitles to the same scene-duration weights used by the renderer.
  - Burns English subtitles once and mixes narration, ambience and available SFX.
  - Creates and validates the four-file review package.

- `app.js`, `index.html`, `styles.css`
  - Makes the API connection indicator reflect connected, disconnected and connecting states.
  - Validates workflow links as HTTPS GitHub URLs before rendering them.
  - Accepts optional `githubStatus` and `githubRunUrl` fields from Apps Script.
  - Removes the hardcoded daily render limit from the dashboard display.

- `README.md`, `INSTALL.txt`, `README-INSTALL.txt`, `README-DASHBOARD.txt`
  - Rewritten to describe the current workflows and the manual publishing policy.

### Added

- `Code.gs` — complete Apps Script replacement with header-based column lookup, owner-only Status and Draft ID protection, a Script Properties approval ledger bound to the exact Raw JSON hash, shared dispatch logic, unique dispatch IDs, authenticated GitHub callbacks, run/artifact tracking and dashboard fields.
- `APPS-SCRIPT-SETUP.md` — exact Script Properties, GitHub Secrets, deployment and safe installation steps.
- `requirements.txt` — explicit Edge TTS and gTTS dependencies.
- `REPAIR-NOTES.md` — this change summary.

### Preserved without functional changes

- `.github/workflows/generate-tamil-voice.yml`
- `generate_tamil_voice.py`
- `styles.css` visual design apart from connection-state indicators

## Important remaining integration item: Apps Script is not in this ZIP

The ZIP now includes a complete companion `Code.gs` and `APPS-SCRIPT-SETUP.md`. The Apps Script source is a prepared replacement, but it has not been pasted into the user's live Apps Script project or deployed. The owner must configure the Script Properties, deploy the web app, add the two GitHub Actions secrets, and run the sheet preparation/protection functions as described in `APPS-SCRIPT-SETUP.md`.

The render workflow now sends authenticated start/completion callbacks using a unique dispatch ID. Apps Script stores the exact run ID, run URL, conclusion and artifact link, and the dashboard consumes those fields. This tracking remains inactive until the Apps Script replacement is deployed and both callback secrets are configured.

The `Status` column protection is configured by `setupApprovalProtection()` and intentionally limits direct status edits and approval-menu actions to the account that runs setup (normally the spreadsheet owner). It has not yet been applied to the live sheet.

## Validation performed

- Python syntax compilation passed for all three Python scripts.
- JavaScript syntax check passed for `app.js`.
- All four GitHub Actions YAML files parsed successfully.
- A local FFmpeg smoke test successfully encoded a synthetic vertical test video with the narration + ambience + SFX mix and subtitle filter.
- No real image generation, TTS request, GitHub workflow dispatch, Apps Script write, or Instagram publish was performed.
- `Code.gs` JavaScript syntax passed a Node parser check; this is not a live Apps Script execution test.
- Workflow YAML parsing and sample story schema checks passed locally.

## Known limitations retained / not claimed as solved

- Independent image generation cannot guarantee identical faces across all five scenes. The optional story-level character description and consistent scene prompts improve the chance but are not a reference-image identity lock.
- The sound effects are procedurally synthesized approximations, not realistic recorded foley.
- gTTS fallback cannot honor the male/female voice selection.
- Instagram publishing is intentionally manual.
- GitHub run tracking and protected approval cells require the separate Apps Script source, which is absent from this ZIP.
