# Tamil Cinematic Reels — Read-only Dashboard

This folder contains the first GitHub Pages dashboard frontend:

- `index.html` — page structure
- `app.js` — read-only Apps Script JSONP connection and table rendering
- `styles.css` — responsive dark dashboard styling

## Deploy to GitHub Pages

1. Extract these files into the root of your `tamil-cinematic-reels` repository.
2. Ensure `index.html`, `app.js`, and `styles.css` are at the repository root (same level as `render_reel.py`).
3. Commit and push to the `main` branch.
4. In GitHub, open **Settings → Pages**.
5. Under Build and deployment, select **Deploy from a branch**.
6. Select branch `main`, folder `/ (root)`, then Save.
7. Wait for GitHub Pages to publish, then open the Pages URL.

## Apps Script connection

`app.js` is configured with the Apps Script `/exec` URL previously shared in this project. If you redeploy the Apps Script as a different deployment, update `APPS_SCRIPT_URL` at the top of `app.js`.

The backend must have the `doGet(e)` JSONP support and `action=dashboard` route already added. The dashboard requests:

`?action=dashboard&callback=tcrDashboardCallback`

The API must be deployed with access that allows the dashboard visitor to read it. The endpoint returns draft titles, hooks and workflow links. Anyone who can access a public dashboard may be able to view this data.

## Security and scope

This is intentionally **read-only**. It does not approve/reject stories, dispatch GitHub Actions, publish to Instagram, or store credentials. Do not put Gemini API keys, GitHub tokens, or other secrets in frontend files.

Approval/rejection and render buttons must only be added after a server-side authenticated Apps Script action is designed and tested. Hiding a button in JavaScript is not security.

## Troubleshooting

- **Connection failed:** check `APPS_SCRIPT_URL`, the deployment's `/exec` URL, and web app access settings.
- **Basic health JSON appears:** verify the deployed `doGet(e)` contains the `action=dashboard` route and deploy a new version.
- **No drafts:** inspect the Google Sheet headers; expected names include `Created at`, `Status`, `Title`, `Hook`, `Render status`, and `GitHub workflow`.
- **Browser console reports a callback error:** confirm your deployed `doGet(e)` supports the `callback` parameter and JSONP response.
