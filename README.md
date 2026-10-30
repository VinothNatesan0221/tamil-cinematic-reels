PHASE 2 — FREE CINEMATIC REEL RENDERER (Android-only setup)

WHAT THIS DOES
- Uses 5 still images supplied as public HTTPS direct links.
- Renders a 30-second vertical 1080x1920 MP4 with slow Ken Burns motion and English subtitles.
- Runs FFmpeg on GitHub Actions; no computer or always-on server is needed.
- Stores the MP4 as a GitHub Actions artifact for 7 days.
- Does NOT generate images, create Tamil voice audio, add music, or publish to Instagram.

FREE-TIER CAVEATS
- Create a PUBLIC GitHub repository to use standard GitHub-hosted runners without consuming private-repo minutes. Public repo contents are public; never upload secrets or private photos.
- GitHub Free has limited artifact storage (currently 500 MB); delete old runs/artifacts as needed.
- Image-generation APIs are not assumed free. Create 5 fictional scene images using a free app/account feature, then host them at public direct HTTPS image URLs. Anyone with the links may access them.
- Tamil narration is not generated in this first zero-cost version. It renders English subtitles. Add voice/music in a later stage if a genuinely free, permitted route is available.

GITHUB SETUP (phone browser)
1. Sign in at https://github.com and create a NEW PUBLIC repository, e.g. tamil-cinematic-reels.
2. Upload render_reel.py to the repository root.
3. Create folder .github/workflows and upload render-reel.yml there.
4. Ensure the default branch is named main.
5. Open Settings > Developer settings > Personal access tokens > Fine-grained tokens > Generate new token.
6. Select only this repository; grant Actions: Read and write, and Metadata: Read-only. Generate and copy the token once.
7. In Apps Script > Project Settings > Script properties, add:
   GITHUB_TOKEN = the token
   GITHUB_OWNER = your GitHub username
   GITHUB_REPO = tamil-cinematic-reels (your repo name)
8. In your existing Google Sheet, reload it. Use Reels Agent > Prepare Phase 2 columns.
9. For a draft row, put five publicly accessible direct HTTPS image URLs into the five Scene image URL columns.
10. Select any cell in that same row; use Reels Agent > Send selected draft to renderer.
11. Open the GitHub workflow link written in the row. Open the latest run, wait for green success, then download the cinematic-reel artifact.
12. Review the MP4 on Android. Publish manually to Instagram only after approval.

IMAGE URL NOTE
The URL must return image bytes directly, not an HTML preview page. A public raw.githubusercontent.com image URL is suitable. Public Google Drive sharing links can be tricky; use a direct download URL and test it in an incognito browser first. Do not use personal photos or confidential assets in a public repo.

TROUBLESHOOTING
- 404 workflow: workflow file must be at .github/workflows/render-reel.yml on branch main.
- 401/403 dispatch: check token expiration and Actions: Read and write permission; verify owner and repo spelling.
- Download too small: image link is not a direct public image URL.
- Render error: open the failed GitHub Actions run and inspect logs.
- Artifact missing: ensure render step completed and upload-artifact step succeeded.

APPS SCRIPT
Paste AppsScript_addon.gs at the BOTTOM of the existing Code.gs. Save, reload the Sheet, and use the Reels Agent menu. Existing Gemini draft triggers remain unchanged.
