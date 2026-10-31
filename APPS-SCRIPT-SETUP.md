# Apps Script backend setup — Tamil Cinematic Reels

This file is the companion setup guide for `Code.gs`. It adds approval protection and GitHub run/artifact callbacks. It does **not** dispatch a render during installation and does **not** publish to Instagram.

## 1. Pause rendering, back up and replace Code.gs

1. Open the existing Apps Script project.
2. In the Apps Script **Triggers** page, temporarily delete only the hourly `dispatchApprovedDrafts` trigger. Keep the two `createReelDraft` triggers. This prevents an existing hourly trigger from acting on pending approved rows while the backend is being replaced.
3. Copy the current `Code.gs` into a local backup file.
4. Replace the contents of `Code.gs` with the `Code.gs` included in this ZIP.
5. Save the project.
6. Do not run `createReelDraft`, `testOneDraft`, `sendSelectedDraftToRenderer`, `dispatchApprovedDrafts`, or `setupDailyRenderer` during installation. Do not recreate the hourly dispatch trigger until you explicitly want automatic render dispatch again.

## 2. Script Properties

In **Project Settings → Script properties**, preserve existing values and verify these properties:

| Property | Value |
|---|---|
| `SPREADSHEET_ID` | Existing Google Sheets ID |
| `GEMINI_API_KEY` | Existing Gemini API key |
| `GITHUB_TOKEN` | GitHub token with repository Actions workflow-dispatch permission |
| `GITHUB_OWNER` | GitHub repository owner, e.g. `VinothNatesan0221` |
| `GITHUB_REPO` | Repository name, e.g. `tamil-cinematic-reels` |
| `GITHUB_CALLBACK_SECRET` | A newly generated random secret (at least 32 random bytes) |
| `APPROVAL_ADMIN_EMAIL` | Exact Google account email of the spreadsheet owner who will approve and dispatch stories |

Generate a secret locally with `openssl rand -hex 32`. Do not paste it into source code, chat, or the dashboard.

## 3. Prepare the sheet and protect approvals

Run these functions manually from the Apps Script editor, as the Google Sheets owner:

1. `preparePhase2Columns` — adds missing tracking headers without deleting existing data.
2. `setupApprovalProtection` — protects the complete `Status` column so only the account running this setup can edit it.

Other spreadsheet editors can review stories, but they cannot type `APPROVED` or use the approval menu to change the protected status. The owner must perform approvals/rejections. This is intentional: allowing every editor to edit the protected cell would defeat the direct-edit bypass protection.

The protection applies to the `Status` and `Draft ID` columns. The configured `APPROVAL_ADMIN_EMAIL` must match the Google account executing the approval actions and creating any optional hourly trigger. Do not remove the named protections `TCR_MANAGED_APPROVAL_STATUS` or `TCR_MANAGED_DRAFT_ID`. The approval menu also writes a hash-based approval record into Script Properties. The dispatcher requires that record to match the exact Raw JSON, so typing `APPROVED` directly—even as the owner—does not by itself authorize rendering. Existing APPROVED rows need to be selected and confirmed once with **Confirm legacy approved story**.

## 4. Deploy/update the Apps Script web app

The GitHub workflow must call the Apps Script web app. In **Deploy → Manage deployments**, edit the existing web app deployment and deploy a new version (or create a web app deployment if none exists):

- Execute as: **Me** (the spreadsheet owner)
- Who has access: **Anyone**

Copy the deployed `/exec` URL. The GET dashboard endpoint remains read-only and returns no Raw JSON or credentials. The POST callback is write-capable but checks `GITHUB_CALLBACK_SECRET` before changing any row. Anyone-accessible deployment is required for GitHub-hosted runners to call it; keep the secret private.

## 5. GitHub repository Actions secrets

In GitHub → repository → Settings → Secrets and variables → Actions → New repository secret, add:

| Secret | Value |
|---|---|
| `APPS_SCRIPT_WEB_APP_URL` | Deployed Apps Script `/exec` URL |
| `APPS_SCRIPT_CALLBACK_SECRET` | Exactly the same random value as Script Property `GITHUB_CALLBACK_SECRET` |

Never add the callback secret to `app.js`, `index.html`, README files, workflow literals, or `Code.gs`.

## 6. Replace the GitHub workflow and dashboard files

Copy the ZIP contents into the repository, preserving paths. In particular, commit:

- `Code.gs` is pasted into Apps Script, not committed as a live integration by GitHub.
- `.github/workflows/render-reel.yml`
- `app.js` and `index.html`
- The other repaired files listed in `REPAIR-NOTES.md`

The render workflow accepts a `dispatch_id`, reports `RUNNING` after it starts, then reports `SUCCESS`, `FAILED`, or `CANCELLED` after the render job finishes. On success it sends the run ID, run URL and render artifact ID/URL to Apps Script.

A GitHub HTTP 204 means only that the dispatch was accepted. The workflow callback supplies the actual run ID later. If callback secrets are absent or the web app is unreachable, the video render can still run because callback steps are configured not to fail the render job; however, the sheet will not receive reliable run status until callback delivery is restored.

## 7. Triggers — enable only after reviewing configuration

- `setupAgent` installs the two daily draft-generation triggers (10:00 and 19:00 Asia/Kolkata).
- `setupDailyRenderer` protects the Status column and installs the hourly approved-draft dispatcher.

The previous project may already have an hourly `dispatchApprovedDrafts` trigger. It survives a Code.gs replacement, so pause/delete that trigger before installation as described in Step 1. Run `setupDailyRenderer` only when you are ready for approved drafts to be automatically submitted to GitHub, with a maximum of two dispatch attempts per Asia/Kolkata calendar day. To keep render dispatch manual, do **not** install this hourly trigger; use the sheet menu's **Send selected draft to renderer** action instead.

The daily cap counts attempts, including uncertain network results, conservatively to prevent duplicate paid renders. A definite `DISPATCH ERROR` can be cleared with **Reset a failed dispatch** after reviewing the GitHub Actions page. Never reset `DISPATCH UNKNOWN` until you have verified whether GitHub accepted the run.

## 8. Safe verification without rendering

After deployment and secret setup:

1. Open the web app `/exec` URL and verify the health response.
2. Open `/exec?action=dashboard` and verify the JSON dashboard response.
3. Confirm the `Status` column shows a protected-range indicator in Google Sheets.
4. Confirm the GitHub workflow file contains the two callback steps and the optional `dispatch_id` input.
5. Do not use a real approved story as a test. No render dispatch is required to verify this installation configuration.

A full callback test requires a GitHub workflow run. Do that later with a dedicated test story only after explicitly deciding to run a test render.

## Manual Instagram publishing

The package workflow only creates review files (MP4, cover, caption and SRT). Download and inspect the package yourself, then publish manually through Instagram. No Instagram publishing API or automatic post action is included.
