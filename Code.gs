/**
 * Tamil Cinematic Reels — Google Apps Script backend
 *
 * Features:
 * - Gemini draft generation (5 scenes)
 * - Owner-controlled approval status protection
 * - Shared manual/hourly GitHub dispatch validation and daily limit
 * - Unique dispatch IDs and authenticated GitHub Actions callbacks
 * - GitHub run, conclusion and artifact tracking for the read-only dashboard
 * - Manual Instagram publishing only; this script never publishes to Instagram
 *
 * Required Script Properties:
 * SPREADSHEET_ID, GEMINI_API_KEY, GITHUB_TOKEN, GITHUB_OWNER, GITHUB_REPO,
 * GITHUB_CALLBACK_SECRET, APPROVAL_ADMIN_EMAIL
 */

const TZ = 'Asia/Kolkata';
const MODEL = 'gemini-3.8-flash';
const DAILY_RENDER_LIMIT = 2;
const APPROVAL_PROTECTION_DESCRIPTION = 'TCR_MANAGED_APPROVAL_STATUS';
const DRAFT_ID_PROTECTION_DESCRIPTION = 'TCR_MANAGED_DRAFT_ID';
const APPROVAL_RECORD_PREFIX = 'TCR_APPROVED_DRAFT_';

const BASE_HEADERS = [
  'Created at', 'Status', 'Title', 'Hook', 'Scene prompts JSON',
  'Tamil narration JSON', 'English subtitles JSON', 'Tamil caption',
  'English caption', 'Hashtags', 'Cover text', 'Sound notes', 'Raw JSON'
];

const TRACKING_HEADERS = [
  'Scene 1 image URL', 'Scene 2 image URL', 'Scene 3 image URL',
  'Scene 4 image URL', 'Scene 5 image URL', 'Render status',
  'GitHub workflow', 'Dispatch date', 'Dispatch ID', 'GitHub run ID',
  'Run status', 'Artifact ID', 'Artifact URL', 'Render started at',
  'Render completed at', 'Run conclusion', 'Draft ID'
];

function setupAgent() {
  const props = PropertiesService.getScriptProperties();
  ['SPREADSHEET_ID', 'GEMINI_API_KEY'].forEach(name => {
    if (!props.getProperty(name)) {
      throw new Error('Add ' + name + ' in Project Settings > Script properties.');
    }
  });

  const sheet = getDraftSheet_();
  ensureBaseHeaders_(sheet);
  ensureHeaderColumn_(sheet, 'Draft ID');
  ensureDraftIds_(sheet);

  ScriptApp.getProjectTriggers().forEach(trigger => {
    if (trigger.getHandlerFunction() === 'createReelDraft') {
      ScriptApp.deleteTrigger(trigger);
    }
  });
  ScriptApp.newTrigger('createReelDraft').timeBased().everyDays(1).atHour(10).inTimezone(TZ).create();
  ScriptApp.newTrigger('createReelDraft').timeBased().everyDays(1).atHour(19).inTimezone(TZ).create();

  Logger.log('Draft agent installed. Apps Script scheduling runs within Google scheduling windows.');
}

function createReelDraft() {
  const props = PropertiesService.getScriptProperties();
  const key = props.getProperty('GEMINI_API_KEY');
  if (!key) throw new Error('Missing GEMINI_API_KEY script property.');

  const sheet = getDraftSheet_();
  ensureBaseHeaders_(sheet);
  ensureHeaderColumn_(sheet, 'Draft ID');
  const now = new Date();
  const seed = Utilities.formatDate(now, TZ, 'yyyy-MM-dd-HH:mm') + '-' + Utilities.getUuid().slice(0, 8);

  const prompt = `
You are a creative director for an original cinematic AI storytelling Instagram account.
Create one 25–35 second vertical Reel concept in natural spoken Tamil with English subtitles.
Make it an original mystery, suspense, emotional twist, supernatural fiction, or sci-fi story.
Use a strong 2-second hook, exactly five scenes, a satisfying twist and a loop-friendly ending.
For visual prompts specify 9:16, cinematic lighting, camera motion, atmosphere, and consistent character appearance.
Do not ask for copyrighted characters, existing movie scenes, logos, or text embedded in generated footage.

Return ONLY valid JSON with this schema:
{
  "title": "short title",
  "hook": "opening on-screen hook",
  "character_description": "optional consistent protagonist description",
  "scenes": [
    {
      "duration_seconds": 6,
      "speaker_gender": "male",
      "visual_prompt": "detailed prompt",
      "tamil_narration": "Tamil narration",
      "english_subtitle": "English translation"
    }
  ],
  "caption_tamil": "Tamil caption",
  "caption_english": "English caption",
  "hashtags": ["CinematicAI", "TamilReels"],
  "cover_text": "short cover title",
  "sound_design": "original or properly licensed sound suggestions"
}

VOICE SELECTION RULES:
1. Every scene MUST include speaker_gender.
2. Use only "male" or "female".
3. Select the gender of the person whose voice is speaking the narration or dialogue.
4. If a male character is speaking, use "male".
5. If a female character is speaking, use "female".
6. If the same narrator speaks throughout the story, keep the same gender in every scene.
7. Do not guess from the person visible in visual_prompt.
8. Never leave speaker_gender empty.

Exactly five scene objects. Make the story coherent and keep Tamil natural. This is fictional entertainment.
Unique seed for this run: ${seed}
`;

  const response = UrlFetchApp.fetch('https://generativelanguage.googleapis.com/v1beta/interactions', {
    method: 'post',
    contentType: 'application/json',
    headers: {'x-goog-api-key': key},
    payload: JSON.stringify({
      model: MODEL,
      input: prompt,
      generation_config: {temperature: 0.9},
      store: false
    }),
    muteHttpExceptions: true
  });

  const code = response.getResponseCode();
  const body = response.getContentText();
  if (code < 200 || code >= 300) {
    appendDraftError_(sheet, 'ERROR: Gemini HTTP ' + code, body);
    throw new Error('Gemini API failed with HTTP ' + code + '. Check API key, model availability and quota.');
  }

  const apiData = JSON.parse(body);
  let rawText = apiData.output_text || '';
  if (!rawText && Array.isArray(apiData.steps)) {
    rawText = apiData.steps
      .filter(step => step.type === 'model_output')
      .flatMap(step => step.content || [])
      .filter(item => item.type === 'text')
      .map(item => item.text || '')
      .join('\n');
  }
  if (!rawText && Array.isArray(apiData.outputs)) rawText = apiData.outputs.map(item => item.text || '').join('');
  if (!rawText && Array.isArray(apiData.output)) rawText = apiData.output.map(item => item.text || '').join('');
  if (!rawText) {
    appendDraftError_(sheet, 'ERROR: no text output', body);
    throw new Error('Gemini returned no readable text. Inspect the Raw JSON column.');
  }

  let draft;
  try {
    draft = JSON.parse(rawText);
    validateDraft_(draft, true);
  } catch (error) {
    appendDraftError_(sheet, 'ERROR: draft validation failed', rawText);
    throw new Error('Draft validation failed: ' + error.message);
  }

  const visual = draft.scenes.map((scene, i) => (i + 1) + '. ' + scene.visual_prompt).join('\n');
  const tamil = draft.scenes.map((scene, i) => (i + 1) + '. ' + scene.tamil_narration).join('\n');
  const english = draft.scenes.map((scene, i) => (i + 1) + '. ' + scene.english_subtitle).join('\n');
  const hashtags = Array.isArray(draft.hashtags)
    ? draft.hashtags.map(tag => String(tag).startsWith('#') ? tag : '#' + tag).join(' ')
    : '';

  sheet.appendRow([
    new Date(), 'DRAFT — REVIEW REQUIRED', draft.title, draft.hook,
    visual, tamil, english, draft.caption_tamil, draft.caption_english,
    hashtags, draft.cover_text || '', draft.sound_design || '', JSON.stringify(draft)
  ]);
  sheet.getRange(sheet.getLastRow(), getColumnMap_(sheet)['Draft ID']).setValue(Utilities.getUuid());
}

function validateDraft_(draft, requireCaptions) {
  if (!draft || !draft.title || !draft.hook || !Array.isArray(draft.scenes) || draft.scenes.length !== 5) {
    throw new Error('Story must include title, hook and exactly five scenes.');
  }
  if (requireCaptions && (!draft.caption_tamil || !draft.caption_english)) {
    throw new Error('Tamil and English captions are required.');
  }
  draft.scenes.forEach((scene, index) => {
    const gender = String(scene.speaker_gender || '').trim().toLowerCase();
    if (!scene.visual_prompt || !scene.tamil_narration || !scene.english_subtitle) {
      throw new Error('Scene ' + (index + 1) + ' needs visual_prompt, tamil_narration and english_subtitle.');
    }
    if (gender !== 'male' && gender !== 'female') {
      throw new Error('Scene ' + (index + 1) + ' speaker_gender must be male or female.');
    }
    const duration = Number(scene.duration_seconds == null ? 6 : scene.duration_seconds);
    if (!isFinite(duration) || duration <= 0) {
      throw new Error('Scene ' + (index + 1) + ' duration_seconds must be positive.');
    }
    scene.speaker_gender = gender;
    scene.duration_seconds = duration;
  });
  return draft;
}

function appendDraftError_(sheet, status, details) {
  const headers = getHeaders_(sheet);
  const row = new Array(headers.length).fill('');
  const createdIndex = headers.indexOf('Created at');
  const statusIndex = headers.indexOf('Status');
  const rawIndex = headers.indexOf('Raw JSON');
  if (createdIndex >= 0) row[createdIndex] = new Date();
  if (statusIndex >= 0) row[statusIndex] = status;
  if (rawIndex >= 0) row[rawIndex] = String(details || '').slice(0, 4000);
  sheet.appendRow(row);
}

function getDraftSheet_() {
  const id = PropertiesService.getScriptProperties().getProperty('SPREADSHEET_ID');
  if (!id) throw new Error('Missing SPREADSHEET_ID script property.');
  const ss = SpreadsheetApp.openById(id);
  let sheet = ss.getSheetByName('Reel Drafts');
  if (!sheet) sheet = ss.insertSheet('Reel Drafts');
  return sheet;
}

function ensureBaseHeaders_(sheet) {
  if (sheet.getLastRow() === 0) {
    sheet.getRange(1, 1, 1, BASE_HEADERS.length).setValues([BASE_HEADERS]);
    sheet.setFrozenRows(1);
    return;
  }
  BASE_HEADERS.forEach(header => ensureHeaderColumn_(sheet, header));
}

function getHeaders_(sheet) {
  const width = Math.max(sheet.getLastColumn(), 1);
  return sheet.getRange(1, 1, 1, width).getValues()[0].map(value => String(value).trim());
}

function getColumnMap_(sheet) {
  const headers = getHeaders_(sheet);
  const map = {};
  headers.forEach((header, index) => { if (header) map[header] = index + 1; });
  return map;
}

function ensureHeaderColumn_(sheet, name) {
  const headers = getHeaders_(sheet);
  if (headers.indexOf(name) !== -1) return headers.indexOf(name) + 1;
  const column = Math.max(sheet.getLastColumn(), 0) + 1;
  sheet.getRange(1, column).setValue(name);
  return column;
}

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('Reels Agent')
    .addItem('Approve selected story', 'approveSelectedDraft')
    .addItem('Reject selected story', 'rejectSelectedDraft')
    .addItem('Confirm legacy approved story', 'registerExistingApprovedDraft')
    .addSeparator()
    .addItem('Protect approval status (owner only)', 'setupApprovalProtection')
    .addItem('Prepare Phase 2 and tracking columns', 'preparePhase2Columns')
    .addItem('Send selected draft to renderer', 'sendSelectedDraftToRenderer')
    .addItem('Reset a failed dispatch', 'resetFailedDispatch')
    .addSeparator()
    .addItem('Audit today’s render limit', 'auditRenderDispatchLimit')
    .addToUi();
}

function preparePhase2Columns() {
  const sheet = getDraftSheet_();
  ensureBaseHeaders_(sheet);
  TRACKING_HEADERS.forEach(header => ensureHeaderColumn_(sheet, header));
  ensureDraftIds_(sheet);
  SpreadsheetApp.getUi().alert('Render and tracking columns are ready. Run Protect approval status before using approval controls.');
}

/**
 * Protects the complete Status column so only the account executing this setup
 * (normally the spreadsheet owner) can edit it directly or approve via menu.
 * Run this once as the spreadsheet owner. Other editors can review stories but
 * must ask the owner to approve/reject them.
 */
function protectOwnerOnlyColumn_(sheet, columnNumber, description, ownerEmail) {
  const range = sheet.getRange(1, columnNumber, sheet.getMaxRows(), 1);
  const protections = sheet.getProtections(SpreadsheetApp.ProtectionType.RANGE);
  let protection = protections.find(item => item.getDescription() === description);
  if (!protection) protection = range.protect();
  protection.setDescription(description);
  protection.setWarningOnly(false);
  try { protection.setDomainEdit(false); } catch (error) { /* Personal Google accounts may not have a Workspace domain setting. */ }
  const editors = protection.getEditors();
  const removableEditors = editors.filter(editor => editor.getEmail() !== ownerEmail);
  if (removableEditors.length) protection.removeEditors(removableEditors);
  protection.addEditor(ownerEmail);
  return protection;
}

function applyApprovalProtection_() {
  const sheet = getDraftSheet_();
  ensureBaseHeaders_(sheet);
  ensureHeaderColumn_(sheet, 'Draft ID');
  ensureDraftIds_(sheet);
  const columns = getColumnMap_(sheet);
  if (!columns.Status || !columns['Draft ID']) throw new Error('Status or Draft ID header is missing.');

  const owner = Session.getEffectiveUser();
  const ownerEmail = owner && owner.getEmail();
  const configuredAdmin = PropertiesService.getScriptProperties().getProperty('APPROVAL_ADMIN_EMAIL');
  if (!ownerEmail || !configuredAdmin || ownerEmail.toLowerCase() !== configuredAdmin.toLowerCase()) {
    throw new Error('Only the configured APPROVAL_ADMIN_EMAIL account can set or use the approval controls. Add the spreadsheet owner email to Script Properties.');
  }

  protectOwnerOnlyColumn_(sheet, columns.Status, APPROVAL_PROTECTION_DESCRIPTION, ownerEmail);
  protectOwnerOnlyColumn_(sheet, columns['Draft ID'], DRAFT_ID_PROTECTION_DESCRIPTION, ownerEmail);
  return ownerEmail;
}

function setupApprovalProtection() {
  const ownerEmail = applyApprovalProtection_();
  SpreadsheetApp.getUi().alert('Approval Status column protected. Only ' + ownerEmail + ' can edit it or use the approval menu.');
}

function assertApprovalProtection_(sheet, columns) {
  const owner = Session.getEffectiveUser();
  const ownerEmail = owner && owner.getEmail();
  const configuredAdmin = PropertiesService.getScriptProperties().getProperty('APPROVAL_ADMIN_EMAIL');
  if (!ownerEmail || !configuredAdmin || ownerEmail.toLowerCase() !== configuredAdmin.toLowerCase() || !columns.Status || !columns['Draft ID']) {
    throw new Error('Only the configured approval administrator can approve or dispatch stories. Check APPROVAL_ADMIN_EMAIL.');
  }
  const protections = sheet.getProtections(SpreadsheetApp.ProtectionType.RANGE);
  [
    {description: APPROVAL_PROTECTION_DESCRIPTION, column: columns.Status},
    {description: DRAFT_ID_PROTECTION_DESCRIPTION, column: columns['Draft ID']}
  ].forEach(item => {
    const protection = protections.find(p => p.getDescription() === item.description);
    if (!protection || protection.isWarningOnly()) {
      throw new Error('Rendering blocked: run setupApprovalProtection as the spreadsheet owner first.');
    }
    const authorized = protection.getEditors().some(editor => editor.getEmail() === ownerEmail);
    if (!authorized) throw new Error('Rendering blocked: current account is not the authorized approval owner.');
  });
}

function approvalRecordKey_(draftId) {
  return APPROVAL_RECORD_PREFIX + String(draftId);
}

function approvalHash_(rawJson) {
  const digest = Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, String(rawJson), Utilities.Charset.UTF_8);
  return Utilities.base64Encode(digest);
}

function writeApprovalRecord_(draftId, rawJson) {
  const record = {hash: approvalHash_(rawJson), approvedAt: new Date().toISOString()};
  PropertiesService.getScriptProperties().setProperty(approvalRecordKey_(draftId), JSON.stringify(record));
}

function hasApprovalRecord_(draftId, rawJson) {
  if (!draftId || !rawJson) return false;
  const stored = PropertiesService.getScriptProperties().getProperty(approvalRecordKey_(draftId));
  if (!stored) return false;
  try { return JSON.parse(stored).hash === approvalHash_(rawJson); }
  catch (error) { return false; }
}

function ensureDraftIds_(sheet) {
  const idColumn = ensureHeaderColumn_(sheet, 'Draft ID');
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return;
  const values = sheet.getRange(2, idColumn, lastRow - 1, 1).getDisplayValues();
  values.forEach((item, index) => {
    if (!String(item[0]).trim()) sheet.getRange(index + 2, idColumn).setValue(Utilities.getUuid());
  });
}

function approveSelectedDraft() { updateSelectedDraftDecision_('APPROVED'); }
function rejectSelectedDraft() { updateSelectedDraftDecision_('REJECTED'); }

function updateSelectedDraftDecision_(decision) {
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(20000)) throw new Error('Another operation is running. Try again shortly.');
  try {
    const sheet = getDraftSheet_();
    const range = SpreadsheetApp.getActiveRange();
    if (!range || range.getSheet().getSheetId() !== sheet.getSheetId()) {
      throw new Error('Select a cell in the Reel Drafts story row first.');
    }
    const row = range.getRow();
    if (row < 2) throw new Error('Select a story row, not the header.');

    const columns = getColumnMap_(sheet);
    requireColumns_(columns, ['Status', 'Draft ID']);
    assertApprovalProtection_(sheet, columns);
    ['Status', 'Raw JSON', 'Render status', 'Title', 'Draft ID'].forEach(name => {
      if (!columns[name]) throw new Error('Missing column: ' + name);
    });
    const current = String(sheet.getRange(row, columns.Status).getValue()).trim().toUpperCase();
    const renderStatus = String(sheet.getRange(row, columns['Render status']).getValue()).trim();
    if (current !== 'DRAFT — REVIEW REQUIRED') {
      throw new Error('Only DRAFT — REVIEW REQUIRED stories can be changed.');
    }
    if (renderStatus) throw new Error('This story already has a render status and cannot be changed.');

    let approvalRaw = '';
    const draftId = String(sheet.getRange(row, columns['Draft ID']).getValue()).trim();
    if (!draftId) throw new Error('Draft ID is missing. Run Prepare Phase 2 and tracking columns.');
    if (decision === 'APPROVED') {
      approvalRaw = String(sheet.getRange(row, columns['Raw JSON']).getValue()).trim();
      if (!approvalRaw) throw new Error('Cannot approve: Raw JSON is empty.');
      validateDraft_(JSON.parse(approvalRaw), true);
    }

    const ui = SpreadsheetApp.getUi();
    const title = sheet.getRange(row, columns.Title).getDisplayValue();
    const choice = ui.alert(decision === 'APPROVED' ? 'Approve this story?' : 'Reject this story?',
      'Story: ' + title + '\n\nConfirm this decision?', ui.ButtonSet.YES_NO);
    if (choice !== ui.Button.YES) return;

    sheet.getRange(row, columns.Status).setValue(decision);
    if (decision === 'APPROVED') writeApprovalRecord_(draftId, approvalRaw);
    else PropertiesService.getScriptProperties().deleteProperty(approvalRecordKey_(draftId));
    ui.alert(decision === 'APPROVED' ? 'Story approved and approval record secured.' : 'Story rejected.');
  } finally {
    lock.releaseLock();
  }
}

function registerExistingApprovedDraft() {
  const sheet = getDraftSheet_();
  const range = SpreadsheetApp.getActiveRange();
  if (!range || range.getSheet().getSheetId() !== sheet.getSheetId() || range.getRow() < 2) {
    throw new Error('Select an existing approved story row first.');
  }
  const row = range.getRow();
  const columns = getColumnMap_(sheet);
  requireColumns_(columns, ['Status', 'Raw JSON', 'Render status', 'Draft ID']);
  assertApprovalProtection_(sheet, columns);
  const status = String(sheet.getRange(row, columns.Status).getValue()).trim().toUpperCase();
  const renderStatus = String(sheet.getRange(row, columns['Render status']).getValue()).trim();
  if (status !== 'APPROVED' || renderStatus) throw new Error('This action is only for an APPROVED story that has not started rendering.');
  const draftId = String(sheet.getRange(row, columns['Draft ID']).getValue()).trim();
  const raw = String(sheet.getRange(row, columns['Raw JSON']).getValue()).trim();
  if (!draftId || !raw) throw new Error('Draft ID or Raw JSON is missing.');
  validateDraft_(JSON.parse(raw), true);
  const ui = SpreadsheetApp.getUi();
  const choice = ui.alert('Confirm this legacy approval?',
    'This creates a protected approval record for the selected existing story. Check the story before continuing.', ui.ButtonSet.YES_NO);
  if (choice !== ui.Button.YES) return;
  writeApprovalRecord_(draftId, raw);
  ui.alert('Legacy approval record created. This story can now pass the render approval gate.');
}

function sendSelectedDraftToRenderer() {
  const sheet = getDraftSheet_();
  const range = SpreadsheetApp.getActiveRange();
  if (!range || range.getSheet().getSheetId() !== sheet.getSheetId()) {
    throw new Error('Select a cell in the Reel Drafts story row first.');
  }
  const row = range.getRow();
  if (row < 2) throw new Error('Select a story row first.');
  const result = withDispatchLock_(function() { return dispatchDraftRow_(sheet, row); });
  SpreadsheetApp.getUi().alert(result.message);
}

function setupDailyRenderer() {
  const sheet = getDraftSheet_();
  ensureBaseHeaders_(sheet);
  TRACKING_HEADERS.forEach(header => ensureHeaderColumn_(sheet, header));
  applyApprovalProtection_();

  ScriptApp.getProjectTriggers().forEach(trigger => {
    if (trigger.getHandlerFunction() === 'dispatchApprovedDrafts') ScriptApp.deleteTrigger(trigger);
  });
  ScriptApp.newTrigger('dispatchApprovedDrafts').timeBased().everyHours(1).create();
  Logger.log('Hourly approved-draft dispatcher installed. Daily cap: ' + DAILY_RENDER_LIMIT + '.');
}

function withDispatchLock_(callback) {
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(20000)) throw new Error('Another render dispatch is in progress. Try again shortly.');
  try { return callback(); } finally { lock.releaseLock(); }
}

function dispatchApprovedDrafts() {
  return withDispatchLock_(function() {
    const sheet = getDraftSheet_();
    const columns = getColumnMap_(sheet);
    requireColumns_(columns, ['Status', 'Raw JSON', 'Render status', 'Dispatch date', 'Dispatch ID']);
    const lastRow = sheet.getLastRow();
    if (lastRow < 2) return;

    let sentToday = countDispatchesToday_(sheet, columns);
    if (sentToday >= DAILY_RENDER_LIMIT) {
      Logger.log('Daily render limit reached.');
      return;
    }

    for (let row = 2; row <= lastRow && sentToday < DAILY_RENDER_LIMIT; row++) {
      const approval = String(sheet.getRange(row, columns.Status).getValue()).trim().toUpperCase();
      const renderStatus = String(sheet.getRange(row, columns['Render status']).getValue()).trim();
      if (approval !== 'APPROVED' || renderStatus !== '') continue;
      const rowRaw = String(sheet.getRange(row, columns['Raw JSON']).getValue()).trim();
      const rowDraftId = columns['Draft ID'] ? String(sheet.getRange(row, columns['Draft ID']).getValue()).trim() : '';
      if (!hasApprovalRecord_(rowDraftId, rowRaw)) {
        Logger.log('Row ' + row + ' has APPROVED text but no valid approval record; skipped.');
        continue;
      }
      try {
        const result = dispatchDraftRow_(sheet, row);
        if (result.accepted || result.uncertain) sentToday++;
        Logger.log('Row ' + row + ': ' + result.message);
      } catch (error) {
        // Invalid rows must not be reconsidered on every hourly trigger.
        const latestStatus = String(sheet.getRange(row, columns['Render status']).getValue()).trim();
        if (!latestStatus) sheet.getRange(row, columns['Render status']).setValue('DISPATCH ERROR: ' + error.message.slice(0, 250));
        Logger.log('Row ' + row + ' skipped: ' + error.message);
      }
    }
  });
}

function dispatchDraftRow_(sheet, row) {
  const columns = getColumnMap_(sheet);
  requireColumns_(columns, ['Status', 'Raw JSON', 'Render status', 'GitHub workflow', 'Dispatch date', 'Dispatch ID', 'Draft ID']);
  assertApprovalProtection_(sheet, columns);

  const approval = String(sheet.getRange(row, columns.Status).getValue()).trim().toUpperCase();
  if (approval !== 'APPROVED') throw new Error('Rendering blocked: approve this story first.');
  const existing = String(sheet.getRange(row, columns['Render status']).getValue()).trim();
  if (existing) throw new Error('Rendering blocked: existing render status is ' + existing + '.');

  const raw = String(sheet.getRange(row, columns['Raw JSON']).getValue()).trim();
  if (!raw) throw new Error('Raw JSON is empty.');
  validateDraft_(JSON.parse(raw), true);
  const draftId = String(sheet.getRange(row, columns['Draft ID']).getValue()).trim();
  if (!hasApprovalRecord_(draftId, raw)) {
    throw new Error('No valid approval record exists for this exact story. Use the Approve selected story menu; for an older APPROVED row, use Confirm legacy approved story.');
  }

  const props = PropertiesService.getScriptProperties();
  const token = props.getProperty('GITHUB_TOKEN');
  const owner = props.getProperty('GITHUB_OWNER');
  const repo = props.getProperty('GITHUB_REPO');
  if (!token || !owner || !repo) throw new Error('GITHUB_TOKEN, GITHUB_OWNER and GITHUB_REPO Script Properties are required.');

  if (countDispatchesToday_(sheet, columns) >= DAILY_RENDER_LIMIT) {
    throw new Error('Daily limit reached: maximum ' + DAILY_RENDER_LIMIT + ' render dispatches per day.');
  }

  const dispatchId = Utilities.getUuid();
  const now = new Date();
  const endpoint = 'https://api.github.com/repos/' + encodeURIComponent(owner) + '/' +
    encodeURIComponent(repo) + '/actions/workflows/render-reel.yml/dispatches';

  // Write an idempotency marker before the network call. An uncertain request
  // is deliberately not auto-retried, to avoid duplicate paid image renders.
  sheet.getRange(row, columns['Render status']).setValue('RENDER SUBMITTING');
  sheet.getRange(row, columns['Dispatch ID']).setValue(dispatchId);
  sheet.getRange(row, columns['Dispatch date']).setValue(now);
  if (columns['Render started at']) sheet.getRange(row, columns['Render started at']).clearContent();
  if (columns['Render completed at']) sheet.getRange(row, columns['Render completed at']).clearContent();
  if (columns['Run status']) sheet.getRange(row, columns['Run status']).setValue('DISPATCHING');
  if (columns['Run conclusion']) sheet.getRange(row, columns['Run conclusion']).clearContent();
  if (columns['GitHub run ID']) sheet.getRange(row, columns['GitHub run ID']).clearContent();
  if (columns['Artifact ID']) sheet.getRange(row, columns['Artifact ID']).clearContent();
  if (columns['Artifact URL']) sheet.getRange(row, columns['Artifact URL']).clearContent();
  sheet.getRange(row, columns['GitHub workflow']).clearContent();

  let response;
  try {
    response = UrlFetchApp.fetch(endpoint, {
      method: 'post',
      contentType: 'application/json',
      headers: {
        Authorization: 'Bearer ' + token,
        Accept: 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28'
      },
      payload: JSON.stringify({
        ref: 'main',
        inputs: {draft_json: raw, dispatch_id: dispatchId}
      }),
      muteHttpExceptions: true
    });
  } catch (error) {
    sheet.getRange(row, columns['Render status']).setValue('DISPATCH UNKNOWN — VERIFY GITHUB');
    if (columns['Run status']) sheet.getRange(row, columns['Run status']).setValue('UNKNOWN');
    return {accepted: false, uncertain: true, message: 'Network result is uncertain. Verify GitHub Actions before retrying.'};
  }

  const http = response.getResponseCode();
  if (http !== 204) {
    sheet.getRange(row, columns['Render status']).setValue('DISPATCH ERROR: HTTP ' + http);
    if (columns['Run status']) sheet.getRange(row, columns['Run status']).setValue('DISPATCH ERROR');
    return {accepted: false, uncertain: false, message: 'GitHub rejected dispatch: HTTP ' + http + '. Check token permissions and workflow file.'};
  }

  // A very fast workflow callback may have populated the run ID while the
  // dispatch request was returning. Never overwrite that newer callback state.
  const knownRunId = columns['GitHub run ID'] ? String(sheet.getRange(row, columns['GitHub run ID']).getValue()).trim() : '';
  if (!knownRunId) {
    sheet.getRange(row, columns['Render status']).setValue('RENDER QUEUED');
    if (columns['Run status']) sheet.getRange(row, columns['Run status']).setValue('QUEUED — WAITING FOR RUN CALLBACK');
  }
  return {accepted: true, uncertain: false, message: 'GitHub accepted the render dispatch. Run ID will appear when the workflow callback arrives.'};
}

function countDispatchesToday_(sheet, columns) {
  if (!columns['Dispatch date'] || sheet.getLastRow() < 2) return 0;
  const today = Utilities.formatDate(new Date(), TZ, 'yyyy-MM-dd');
  const values = sheet.getRange(2, columns['Dispatch date'], sheet.getLastRow() - 1, 1).getValues();
  return values.filter(item => {
    const value = item[0];
    if (value instanceof Date) return Utilities.formatDate(value, TZ, 'yyyy-MM-dd') === today;
    return String(value).trim() === today;
  }).length;
}

function resetFailedDispatch() {
  const sheet = getDraftSheet_();
  const range = SpreadsheetApp.getActiveRange();
  if (!range || range.getSheet().getSheetId() !== sheet.getSheetId() || range.getRow() < 2) {
    throw new Error('Select a failed story row in Reel Drafts first.');
  }
  const row = range.getRow();
  const columns = getColumnMap_(sheet);
  requireColumns_(columns, ['Render status', 'Dispatch date', 'Dispatch ID', 'Status', 'Draft ID']);
  assertApprovalProtection_(sheet, columns);
  const status = String(sheet.getRange(row, columns['Render status']).getValue()).trim().toUpperCase();
  if (!status.startsWith('DISPATCH ERROR')) {
    throw new Error('Only a definite DISPATCH ERROR can be reset. Do not reset DISPATCH UNKNOWN until GitHub has been checked.');
  }
  const ui = SpreadsheetApp.getUi();
  const choice = ui.alert('Reset failed dispatch?', 'This clears the failed dispatch marker so the approved story can be submitted again. Continue?', ui.ButtonSet.YES_NO);
  if (choice !== ui.Button.YES) return;

  ['Render status', 'Dispatch date', 'Dispatch ID', 'GitHub workflow', 'GitHub run ID', 'Run status',
   'Artifact ID', 'Artifact URL', 'Render started at', 'Render completed at', 'Run conclusion'].forEach(name => {
    if (columns[name]) sheet.getRange(row, columns[name]).clearContent();
  });
  ui.alert('Dispatch marker cleared. The approved story can be submitted again.');
}

/**
 * GitHub Actions callback endpoint. The shared secret is checked before any
 * spreadsheet write. Deploy the web app to execute as the owner and allow
 * anonymous access; the secret authenticates this POST endpoint.
 */
function doPost(e) {
  try {
    const bodyText = e && e.postData && e.postData.contents;
    if (!bodyText) throw new Error('Missing POST body.');
    const payload = JSON.parse(bodyText);
    const expected = PropertiesService.getScriptProperties().getProperty('GITHUB_CALLBACK_SECRET');
    if (!expected || !payload.secret || payload.secret !== expected) {
      return jsonOutput_({success: false, error: 'Unauthorized'}, ContentService.MimeType.JSON);
    }
    if (!payload.dispatch_id || !payload.run_id || !payload.status) {
      throw new Error('dispatch_id, run_id and status are required.');
    }

    const sheet = getDraftSheet_();
    const columns = getColumnMap_(sheet);
    requireColumns_(columns, ['Dispatch ID', 'Render status', 'GitHub run ID', 'Run status', 'GitHub workflow']);
    const lastRow = sheet.getLastRow();
    if (lastRow < 2) throw new Error('No draft rows exist.');

    const ids = sheet.getRange(2, columns['Dispatch ID'], lastRow - 1, 1).getDisplayValues();
    let targetRow = 0;
    for (let i = 0; i < ids.length; i++) {
      if (String(ids[i][0]).trim() === String(payload.dispatch_id).trim()) {
        targetRow = i + 2;
        break;
      }
    }
    if (!targetRow) throw new Error('No sheet row matches this dispatch_id.');

    const runUrl = String(payload.run_url || '');
    if (runUrl && !/^https:\/\/github\.com\/[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+\/actions\/runs\/[0-9]+$/.test(runUrl)) {
      throw new Error('Invalid GitHub run URL.');
    }

    const status = String(payload.status).toUpperCase();
    sheet.getRange(targetRow, columns['GitHub run ID']).setValue(String(payload.run_id));
    sheet.getRange(targetRow, columns['Run status']).setValue(status);
    if (runUrl) sheet.getRange(targetRow, columns['GitHub workflow']).setValue(runUrl);

    if (status === 'RUNNING') {
      sheet.getRange(targetRow, columns['Render status']).setValue('RENDER RUNNING');
      if (columns['Render started at']) sheet.getRange(targetRow, columns['Render started at']).setValue(new Date());
    } else if (['SUCCESS', 'FAILED', 'CANCELLED'].indexOf(status) !== -1) {
      sheet.getRange(targetRow, columns['Render status']).setValue('RENDER ' + status);
      if (columns['Render completed at']) sheet.getRange(targetRow, columns['Render completed at']).setValue(new Date());
      if (columns['Run conclusion']) sheet.getRange(targetRow, columns['Run conclusion']).setValue(String(payload.conclusion || status).toLowerCase());
      if (payload.artifact_id && columns['Artifact ID']) sheet.getRange(targetRow, columns['Artifact ID']).setValue(String(payload.artifact_id));
      if (payload.artifact_url && columns['Artifact URL']) {
        const artifactUrl = String(payload.artifact_url);
        if (/^https:\/\/github\.com\//.test(artifactUrl)) sheet.getRange(targetRow, columns['Artifact URL']).setValue(artifactUrl);
      }
    } else {
      throw new Error('Unsupported callback status: ' + status);
    }

    return jsonOutput_({success: true, row: targetRow, status: status}, ContentService.MimeType.JSON);
  } catch (error) {
    return jsonOutput_({success: false, error: error.message}, ContentService.MimeType.JSON);
  }
}

function doGet(e) {
  const params = e && e.parameter ? e.parameter : {};
  const response = params.action === 'dashboard' ? getDashboardData_() : {
    success: true,
    project: 'Tamil Cinematic Reels',
    service: 'Apps Script Backend',
    status: 'online',
    message: 'Backend connected successfully',
    timestamp: new Date().toISOString()
  };
  const json = JSON.stringify(response);
  if (params.callback) {
    if (!/^[A-Za-z_$][A-Za-z0-9_$]*$/.test(params.callback)) {
      return jsonOutput_({success: false, error: 'Invalid callback'}, ContentService.MimeType.JSON);
    }
    return ContentService.createTextOutput(params.callback + '(' + json + ');')
      .setMimeType(ContentService.MimeType.JAVASCRIPT);
  }
  return jsonOutput_(response, ContentService.MimeType.JSON);
}

function jsonOutput_(value, mimeType) {
  return ContentService.createTextOutput(JSON.stringify(value)).setMimeType(mimeType);
}

function getDashboardData_() {
  const sheet = getDraftSheet_();
  const lastRow = sheet.getLastRow();
  const lastCol = sheet.getLastColumn();
  if (lastRow < 2 || lastCol < 1) {
    return {success: true, project: 'Tamil Cinematic Reels', totalDrafts: 0, approvedDrafts: 0, queuedRenders: 0, drafts: [], timestamp: new Date().toISOString()};
  }

  const values = sheet.getRange(1, 1, lastRow, lastCol).getDisplayValues();
  const headers = values[0].map(value => String(value).trim());
  const index = name => headers.indexOf(name);
  const drafts = [];
  const scriptProps = PropertiesService.getScriptProperties().getProperties();
  let approved = 0;
  let active = 0;

  for (let i = 1; i < values.length; i++) {
    const row = values[i];
    const get = name => index(name) >= 0 ? row[index(name)] : '';
    const status = get('Status');
    const renderStatus = get('Render status');
    const upperRender = String(renderStatus).trim().toUpperCase();
    const draftId = get('Draft ID');
    let approvalVerified = false;
    const approvalRecord = scriptProps[approvalRecordKey_(draftId)];
    if (String(status).trim().toUpperCase() === 'APPROVED' && approvalRecord) {
      try { approvalVerified = JSON.parse(approvalRecord).hash === approvalHash_(get('Raw JSON')); } catch (error) { approvalVerified = false; }
    }
    if (approvalVerified) approved++;
    if (['RENDER QUEUED', 'RENDER SUBMITTING', 'RENDER RUNNING'].indexOf(upperRender) !== -1) active++;

    drafts.push({
      rowNumber: i + 1,
      createdAt: get('Created at'),
      status: status,
      approvalVerified: approvalVerified,
      title: get('Title'),
      hook: get('Hook'),
      renderStatus: renderStatus,
      githubStatus: get('Run status'),
      workflowUrl: get('GitHub workflow'),
      githubRunUrl: get('GitHub workflow'),
      runId: get('GitHub run ID'),
      dispatchId: get('Dispatch ID'),
      artifactId: get('Artifact ID'),
      artifactUrl: get('Artifact URL'),
      renderStartedAt: get('Render started at'),
      renderCompletedAt: get('Render completed at'),
      runConclusion: get('Run conclusion')
    });
  }
  drafts.reverse();
  return {
    success: true,
    project: 'Tamil Cinematic Reels',
    totalDrafts: lastRow - 1,
    approvedDrafts: approved,
    queuedRenders: active,
    drafts: drafts.slice(0, 20),
    timestamp: new Date().toISOString()
  };
}

function auditRenderDispatchLimit() {
  const sheet = getDraftSheet_();
  const columns = getColumnMap_(sheet);
  requireColumns_(columns, ['Dispatch date', 'Status', 'Render status']);
  let pending = 0;
  if (sheet.getLastRow() >= 2) {
    const rows = sheet.getRange(2, 1, sheet.getLastRow() - 1, sheet.getLastColumn()).getValues();
    rows.forEach(row => {
      if (String(row[columns.Status - 1]).trim().toUpperCase() === 'APPROVED' &&
          String(row[columns['Render status'] - 1]).trim() === '') pending++;
    });
  }
  const sentToday = countDispatchesToday_(sheet, columns);
  const result = {
    success: true,
    date: Utilities.formatDate(new Date(), TZ, 'yyyy-MM-dd'),
    dispatchAttemptsToday: sentToday,
    remainingDailyCapacity: Math.max(0, DAILY_RENDER_LIMIT - sentToday),
    approvedPendingDrafts: pending,
    limit: DAILY_RENDER_LIMIT,
    githubDispatchTriggered: false
  };
  Logger.log(JSON.stringify(result, null, 2));
  return result;
}

function requireColumns_(columns, names) {
  names.forEach(name => { if (!columns[name]) throw new Error('Missing column: ' + name + '. Run Prepare Phase 2 and tracking columns.'); });
}

/** Optional: run manually to create one draft immediately for testing. */
function testOneDraft() { createReelDraft(); }
