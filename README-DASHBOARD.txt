TAMIL CINEMATIC REELS — READ-ONLY DASHBOARD

Files:
- index.html
- styles.css
- app.js

Setup:
1. Host these three files on GitHub Pages or another static host.
2. In app.js, set APPS_SCRIPT_URL to the deployed Apps Script web-app URL.
3. Deploy Apps Script as a web app with access appropriate for your intended viewers.
4. Open the hosted dashboard and use Refresh.

Security:
- Never put Gemini API keys, GitHub tokens or other secrets in app.js.
- The dashboard uses JSONP and is read-only. It must not perform approval, dispatch or publishing actions.
- Workflow links are accepted only when they are HTTPS URLs on github.com.

Status limitation:
The frontend accepts optional githubStatus and githubRunUrl values, but this ZIP does not include the Apps Script Code.gs. Until the Apps Script backend is extended to look up GitHub workflow runs and return run-specific fields, the dashboard can only show the statuses and links already stored in the sheet. A general Actions URL is not a run-specific tracking link.

The daily render cap is controlled by Apps Script. The dashboard deliberately does not hardcode a daily limit.
