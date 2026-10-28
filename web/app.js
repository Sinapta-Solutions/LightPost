import { guides } from './guides.js';

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const esc = (text = '') =>
  String(text).replace(
    /[&<>"']/g,
    (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c],
  );
const icons = {
  docs: '<path d="M4 4h6a3 3 0 0 1 3 3v14a4 4 0 0 0-4-2H4zm16 0h-4a3 3 0 0 0-3 3v14a4 4 0 0 1 4-2h3Z"/>',
  compose: '<path d="m16 3 5 5-12 12-6 1 1-6Z"/><path d="m14 5 5 5"/>',
  posts:
    '<rect x="4" y="5" width="16" height="16" rx="2"/><path d="M8 3v4m8-4v4M4 11h16m-12 4h3m3 0h2"/>',
  accounts:
    '<circle cx="9" cy="8" r="3"/><path d="M3 21v-3a6 6 0 0 1 12 0v3m2-16a3 3 0 0 1 0 6m1 4a5 5 0 0 1 3 4v2"/>',
  settings:
    '<path d="M4 7h16M4 17h16"/><circle cx="9" cy="7" r="3" fill="currentColor" stroke="none"/><circle cx="16" cy="17" r="3" fill="currentColor" stroke="none"/>',
};
const icon = (name) =>
  `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden="true">${icons[name] || ''}</svg>`;
const brand =
  '<a class="brand" href="/" aria-label="LightPost home"><img src="/favicon.svg" alt="" />LightPost</a>';
const platformLogos = new Set([
  'bluesky',
  'mastodon',
  'x',
  'instagram',
  'threads',
  'discord',
  'telegram',
  'facebook',
  'linkedin',
  'tiktok',
  'pinterest',
  'google-business',
]);
const mark = (platform) =>
  `<span class="platform-mark ${esc(platform)}" aria-hidden="true">${platformLogos.has(platform) ? `<img src="/logos/${platform}.svg" alt="" width="20" height="20" decoding="async" />` : icon('accounts')}</span>`;
const badge = (status) =>
  `<span class="badge ${esc(status)}" role="status">${['queued', 'publishing', 'sending', 'processing'].includes(status) ? '<span class="sending-spinner" aria-hidden="true"></span>' : ''}${esc({ needs_review: 'Check platform', uncertain: 'Check platform', cancelled: 'Cancelled', partial: 'Partly delivered', blocked: 'Paused', publishing: 'Sending', sending: 'Sending', processing: 'Processing', queued: 'Queued', published: 'Published' }[status] || status)}</span>`;
const root = $('#root');
const modal = $('#modal');
const pages = ['compose', 'posts', 'accounts', 'settings', 'docs'];
let state,
  page = pages.includes(location.hash.slice(1).split('/')[0])
    ? location.hash.slice(1).split('/')[0]
    : 'compose',
  filter = 'all',
  offset = 0,
  postList = [],
  postTotal = 0;
let composer = freshComposer();
const dirtyForms = new Set();
let regionVisible = false;
const browserZone = Intl.DateTimeFormat().resolvedOptions().timeZone;
function freshComposer() {
  return {
    text: '',
    accountIds: [],
    mediaIds: [],
    alts: {},
    id: null,
    scheduledAt: '',
    xAllowLinks: false,
    contentOptions: {},
  };
}
function toast(message) {
  $('#toast').textContent = message;
  $('#toast').classList.add('visible');
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => $('#toast').classList.remove('visible'), 5000);
}
async function api(path, { method = 'GET', body } = {}) {
  const response = await fetch('/api' + path, {
    method,
    headers: body instanceof FormData ? {} : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : body instanceof FormData ? body : JSON.stringify(body),
  });
  const result = await response.json();
  if (response.status === 401) {
    renderLogin();
    throw Error('Your session ended. Sign in again.');
  }
  if (!response.ok) throw Error(result.error || 'Request failed.');
  return result;
}
function hasXLink(text) {
  return /https?:\/\/|www\.|(?:[\p{L}\p{N}-]+\.)+[\p{L}]{2,}(?:[/:?#]\S*)?/iu.test(text);
}
function retryAccountIds(post) {
  const latest = new Map((post.results || []).map((result) => [result.accountId, result.status]));
  return post.accountIds.filter((id) => !['published', 'simulated'].includes(latest.get(id)));
}
function confirmXCost(text, count, action) {
  const rate = hasXLink(text) ? 0.2 : 0.015;
  return new Promise((resolve) => {
    let accepted = false;
    openDialog(
      'Confirm X (Twitter) API cost',
      `<p>Estimated posting charge: <strong>$${(rate * count).toFixed(3)} USD</strong> for ${count} X (Twitter) account(s), at $${rate.toFixed(3)} per post${hasXLink(text) ? ' containing a URL' : ''}.</p><p class="small-text muted">X (Twitter) charges your developer account when delivery is attempted, including scheduled deliveries. Other API calls, taxes and retries may add charges. Rates may change before delivery.</p><p><a href="https://docs.x.com/x-api/getting-started/pricing" target="_blank" rel="noopener noreferrer">Check X (Twitter) pricing ↗</a></p><div class="actions"><button type="button" id="x-cost-cancel">Cancel</button><button type="button" class="primary" id="x-cost-confirm">Confirm & ${esc(action)}</button></div>`,
    );
    modal.addEventListener('close', () => resolve(accepted), { once: true });
    $('#x-cost-cancel').onclick = () => closeDialog();
    $('#x-cost-confirm').onclick = () => {
      accepted = true;
      closeDialog();
    };
  });
}
function regionLabel(value = browserZone) {
  return `<button type="button" class="quiet small region-value ${regionVisible ? '' : 'is-blurred'}" data-action="toggle-region" aria-expanded="${regionVisible}" aria-label="${regionVisible ? 'Hide region' : 'Show region'}">${esc(value)}</button>`;
}
function dateText(value) {
  if (!value) return 'No date set';
  try {
    return new Intl.DateTimeFormat(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
      timeZoneName: 'short',
      timeZone: browserZone,
    })
      .formatToParts(new Date(value))
      .map((part) => (part.type === 'timeZoneName' ? regionLabel(part.value) : esc(part.value)))
      .join('');
  } catch {
    return esc(new Date(value).toLocaleString());
  }
}
function localInput(value) {
  const date = value ? new Date(value) : new Date();
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}T${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`;
}
function safeLink(value) {
  try {
    const url = new URL(value);
    return url.protocol === 'https:' ? url.href : '';
  } catch {
    return '';
  }
}
function themeToggle() {
  const dark = window.lightpostTheme?.current() === 'dark';
  return `<button type="button" class="quiet small theme-toggle" data-action="toggle-theme" role="switch" aria-label="Dark theme" aria-checked="${dark}" title="Switch to ${dark ? 'light' : 'dark'} theme"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden="true"><path d="M20.5 14A8.5 8.5 0 0 1 10 3.5 8.5 8.5 0 1 0 20.5 14Z" /></svg><span>Dark theme</span><span class="theme-switch" aria-hidden="true"></span></button>`;
}
function renderLanding() {
  document.title = 'LightPost — your publishing desk';
  root.innerHTML = `<div class="landing"><header class="landing-header">${brand}<div class="landing-header-actions">${themeToggle()}<a class="button" href="/app">Open workspace ↗</a></div></header><main><section class="landing-hero"><h1>Automate posting to all of your socials from one dashboard</h1><div class="hero-platforms">${[
    ['bluesky', 'Bluesky'],
    ['mastodon', 'Mastodon'],
    ['x', 'X (Twitter)'],
    ['instagram', 'Instagram'],
    ['facebook', 'Facebook Pages'],
    ['threads', 'Threads'],
    ['discord', 'Discord'],
    ['telegram', 'Telegram'],
    ['linkedin', 'LinkedIn'],
    ['tiktok', 'TikTok'],
    ['pinterest', 'Pinterest'],
    ['google-business', 'Google Business Profile'],
  ]
    .map(([platform, name]) => `<span role="img" aria-label="${name}">${mark(platform)}</span>`)
    .join(
      '',
    )}</div><p class="hero-description">One post. Your accounts. A time that works.<br>A small, open-source publishing desk you can self-host.</p><a class="button primary hero-cta" href="/app">Start creating <span aria-hidden="true">→</span></a><p class="hero-note">Free to self-host · MIT licensed · Your data stays with you</p></section><section class="landing-bottom"><div><h2>Write it once</h2><p>Choose several accounts, including multiple accounts on the same platform. Send your post to them together.</p></div><div><h2>Put it on the calendar</h2><p>Draft today, publish later. Your queue stays in SQLite and resumes when your server comes back online.</p></div><div><h2>Keep it small</h2><p>Async Python, a plain browser interface, and no external database. Run it on your own computer or server.</p></div></section></main><footer class="landing-footer">LightPost is independent and not affiliated with Post Bridge. Bluesky, Mastodon, X (Twitter), Instagram, Threads, Discord, Telegram, LinkedIn and Facebook Pages. Platform API fees may apply.</footer></div>`;
}
function renderShell() {
  document.title = 'LightPost — workspace';
  root.innerHTML = `<aside class="sidebar">${brand}<nav class="nav" aria-label="Workspace">${[
    ['compose', 'New post'],
    ['posts', 'Posts'],
    ['accounts', 'Accounts'],
    ['settings', 'Settings'],
    ['docs', 'Setup Guide'],
  ]
    .map(
      ([key, label]) =>
        `<button data-page="${key}" class="${page === key ? 'active' : ''}">${icon(key)}${label}${key === 'posts' ? ` <span class="count">(${state.total})</span>` : ''}</button>`,
    )
    .join(
      '',
    )}</nav><div class="side-bottom"><p><span class="status-dot"></span>Local workspace<br>Python async · SQLite</p><a href="/api/export" download>Export post history ↗</a></div></aside><main class="app-main"><header class="topbar"><strong>${esc(state.settings.name)}</strong><div class="topbar-right">${themeToggle()}<span class="region-toggle">Region: ${regionLabel()}</span>${state.authEnabled ? '<button class="quiet small" data-action="logout">Sign out</button>' : `<span><span class="status-dot"></span>On your server</span>`}</div></header><div class="page" id="page"></div></main>`;
  renderPage();
}
function renderPage() {
  const navCount = $('.nav .count');
  if (navCount) navCount.textContent = `(${state.total})`;
  $$('.nav button').forEach((button) => {
    button.classList.toggle('active', button.dataset.page === page);
    button.setAttribute('aria-current', button.dataset.page === page ? 'page' : 'false');
  });
  if (page === 'compose') renderCompose();
  if (page === 'posts') renderPosts();
  if (page === 'accounts') renderAccounts();
  if (page === 'settings') renderSettings();
  if (page === 'docs') renderDocs();
}
function requiredContent(platform, kind) {
  return (platform === 'instagram' && kind === 'image') || (platform === 'x' && kind === 'text');
}
function instagramLast(items, platform = (item) => item.platform) {
  return [...items].sort(
    (a, b) => Number(platform(a) === 'instagram') - Number(platform(b) === 'instagram'),
  );
}
function renderCompose() {
  const available = instagramLast(state.accounts);
  $('#page').innerHTML =
    `<div class="page-header"><div><h1>${composer.id ? 'Edit post' : 'New post'}</h1><p>Write once. Choose where it goes.</p></div><span class="eyebrow">Your publishing desk</span></div><div class="compose-grid"><form id="post-form" class="panel"><div class="panel-heading">Post details<span class="muted small-text">${composer.id ? 'Editing saved post' : 'Not yet saved'}</span></div><div class="panel-body"><div class="destination-heading"><span class="label">Publish to</span>${available.length ? '<label class="select-all-accounts"><input type="checkbox" id="select-all-accounts" /> Select all</label>' : ''}</div><div class="account-options">${available.length ? available.map((a) => `<div class="account-option"><label class="account-select"><input type="checkbox" name="account" value="${esc(a.id)}" ${composer.accountIds.includes(a.id) ? 'checked' : ''} />${mark(a.platform)}<span class="account-info"><strong>${esc(a.name)}</strong><span>${esc(a.handle)}</span></span></label><div class="content-options">${['text', 'image'].map((kind) => `<label><span${requiredContent(a.platform, kind) ? ' class="required-toggle" tabindex="0"' : ''}><input type="checkbox" role="switch" data-content-account="${esc(a.id)}" data-content-kind="${kind}" aria-label="${esc(a.handle)}: ${kind}" ${requiredContent(a.platform, kind) || composer.contentOptions[a.id]?.[kind] !== false ? 'checked' : ''} ${requiredContent(a.platform, kind) ? 'disabled aria-description="Required for this platform"' : ''} />${requiredContent(a.platform, kind) ? '<span class="required-toggle-tooltip" role="tooltip">Required for this platform</span>' : ''}</span>${kind === 'text' ? 'Text' : 'Image'}</label>`).join('')}</div></div>`).join('') : '<div class="notice">Connect an account to get started. <button type="button" class="small" data-action="connect">Connect account</button></div>'}</div><label class="label" for="post-text">Your post</label><textarea id="post-text" name="text" placeholder="What would you like to share?" maxlength="10000">${esc(composer.text)}</textarea><div class="compose-tools"><div><button type="button" class="small image-url-button" data-action="source-image">Add Image</button><button type="button" class="small saved-library-button" data-action="library">Saved Library</button></div><span class="counter" id="counter"></span></div><div class="char-hints" id="char-hints"></div><div id="attachments" class="attachments"></div><div id="destination-notice"></div><div id="x-options" hidden><label class="x-link-option"><input type="checkbox" id="x-allow-links" ${composer.xAllowLinks ? 'checked' : ''} /> Allow links — X (Twitter) charges $0.20 per post per X (Twitter) account.</label><p class="small-text muted" id="x-cost-estimate"></p></div><div class="schedule-box"><div class="field"><label for="scheduled-at">Schedule date & time</label><input type="datetime-local" id="scheduled-at" value="${esc(composer.scheduledAt || localInput())}" required /></div></div><p class="error" id="post-error" role="alert"></p><div class="actions"><button type="submit" value="draft">Save draft</button><button type="submit" value="scheduled">Schedule</button><button type="submit" class="primary" value="now">Publish now ↗</button></div><p class="form-footnote">Publish now sends to your selected accounts.<br>Images: up to 1 MB each. X (Twitter): up to four images. Instagram: one public JPEG. Threads: text or one public JPEG. Other channels: up to four imported images.</p></div></form><aside class="preview-column"><div class="preview-topline"><span class="eyebrow">Post preview</span><span class="muted small-text">Content preview</span></div><div class="panel preview-card"><div class="preview-user"><span class="avatar" id="preview-avatar">${esc(state.settings.name.slice(0, 1).toUpperCase())}</span><div><strong id="preview-name">${esc(state.settings.name)}</strong><span id="preview-destination">Select your accounts</span></div></div><div class="preview-text" id="preview-text"></div><div class="preview-images" id="preview-images"></div><div class="preview-meta"><span>♡ &nbsp; ◯ &nbsp; ↗</span><span>Just now</span></div></div><p class="preview-note">The final appearance depends on the platform. Your content is sent as written, with no AI edits.</p><div class="note-box"><h3>One post, several destinations.</h3><p>You can select multiple accounts on the same platform. Each delivery gets its own result, so a failed destination does not hide successful ones.</p></div></aside></div>`;
  renderAttachments();
  updatePreview();
}
function readComposer() {
  if (!$('#post-form')) return;
  composer.text = $('#post-text').value;
  composer.accountIds = $$('input[name="account"]:checked').map((input) => input.value);
  composer.scheduledAt = $('#scheduled-at').value;
  composer.xAllowLinks = $('#x-allow-links').checked;
  for (const input of $$('[data-content-account]')) {
    const options = (composer.contentOptions[input.dataset.contentAccount] ||= {});
    options[input.dataset.contentKind] = input.checked;
  }
}
function needsPublicImage() {
  return state.accounts.some(
    (account) =>
      composer.accountIds.includes(account.id) &&
      ['instagram', 'threads'].includes(account.platform) &&
      composer.contentOptions[account.id]?.image !== false,
  );
}
function savedImageIssue(media) {
  if (needsPublicImage() && !media?.publicSource)
    return 'Instagram and Threads need a public JPEG URL. Import this image using Add Image.';
  if (
    !media?.publicSource &&
    state.accounts.some(
      (account) =>
        account.platform === 'discord' &&
        composer.accountIds.includes(account.id) &&
        composer.contentOptions[account.id]?.image !== false,
    )
  )
    return 'Discord needs a public image URL. Import this image using Add Image.';
  return '';
}
function updatePreview() {
  readComposer();
  const selectAll = $('#select-all-accounts');
  if (selectAll) {
    const accounts = $$('input[name="account"]');
    const selectedCount = accounts.filter((input) => input.checked).length;
    selectAll.checked = accounts.length > 0 && selectedCount === accounts.length;
    selectAll.indeterminate = selectedCount > 0 && selectedCount < accounts.length;
  }
  const selected = instagramLast(state.accounts.filter((a) => composer.accountIds.includes(a.id)));
  $('#preview-text').textContent = composer.text || 'Your words will appear here.';
  $('#preview-text').classList.toggle('preview-placeholder', !composer.text);
  $('#counter').textContent = `${[...composer.text].length} characters`;
  const account = selected[0];
  const previewOptions = composer.contentOptions[account?.id] || {};
  $('#preview-text').hidden = previewOptions.text === false;
  $('#preview-images').hidden = previewOptions.image === false;
  $('#preview-name').textContent = account?.name || state.settings.name;
  $('#preview-avatar').innerHTML = account
    ? mark(account.platform)
    : esc(state.settings.name.slice(0, 1).toUpperCase());
  $('#preview-destination').textContent = account
    ? account.handle + (selected.length > 1 ? ` · +${selected.length - 1} more` : '')
    : 'Select an account to preview';
  $('#char-hints').innerHTML = [...new Set(selected.map((a) => a.platform))]
    .map((platform) => {
      const meta = state.platforms.find((p) => p.id === platform);
      const photoCaption =
        platform === 'telegram' &&
        composer.mediaIds.length > 0 &&
        selected.some(
          (a) => a.platform === 'telegram' && composer.contentOptions[a.id]?.image !== false,
        );
      return meta
        ? `<span>${esc(meta.name)} · ${photoCaption ? 1024 : meta.limit} ${platform === 'x' ? 'weighted ' : ''}character${photoCaption ? ' caption' : ''} limit</span>`
        : '';
    })
    .join('');
  const xCount = selected.filter((a) => a.platform === 'x').length;
  const link = hasXLink(composer.text);
  $('#x-options').hidden = !xCount || !link;
  $('#x-cost-estimate').textContent = xCount
    ? `Estimated X (Twitter) posting cost: $${((link ? 0.2 : 0.015) * xCount).toFixed(3)} USD across ${xCount} X (Twitter) account(s). ${link && !composer.xAllowLinks ? 'Enable links above or remove the URL to continue.' : 'You will confirm before scheduling or publishing.'} Rates may change; excludes other API calls and taxes.`
    : '';
  const needsPublic = selected.some(
    (a) =>
      ['instagram', 'threads'].includes(a.platform) &&
      composer.contentOptions[a.id]?.image !== false,
  );

  $('[data-action="library"]').hidden = false;
  $('#destination-notice').innerHTML = needsPublic
    ? '<div class="notice">Instagram needs one public JPEG. Threads can post text, or one public JPEG. Choose a URL-imported image from Saved Library, or use Add Image.</div>'
    : '';
}
function renderAttachments() {
  $('#attachments').innerHTML = composer.mediaIds
    .map((id) => {
      const media = state.media.find((m) => m.id === id);
      return `<div class="attachment"><img src="/api/media/${encodeURIComponent(id)}" alt="${esc(media?.alt || '')}" /><button type="button" data-remove-image="${esc(id)}" aria-label="Remove ${esc(media?.name || 'image')}">×</button><input data-alt="${esc(id)}" aria-label="Alt text for ${esc(media?.name || 'image')}" placeholder="Describe the image (alt text)" maxlength="1000" value="${esc(composer.alts[id] ?? media?.alt ?? '')}" /></div>`;
    })
    .join('');
  $('#preview-images').innerHTML = composer.mediaIds
    .map((id) => `<img src="/api/media/${encodeURIComponent(id)}" alt="Attached image" />`)
    .join('');
}
function renderPosts() {
  $('#page').innerHTML =
    `<div class="page-header"><div><h1>Posts</h1><p>Your drafts, upcoming posts, and delivery receipts.</p></div><button class="primary" data-page="compose">＋ New post</button></div><div class="tabs" aria-label="Post status">${[
      ['all', 'All posts'],
      ['scheduled', 'Scheduled'],
      ['draft', 'Drafts'],
      ['published', 'Published'],
      ['attention', 'Needs attention'],
    ]
      .map(
        ([key, label]) =>
          `<button data-filter="${key}" class="${filter === key ? 'active' : ''}" ${filter === key ? 'aria-current="true"' : ''}>${label}</button>`,
      )
      .join('')}</div><div id="post-list"></div><div id="pagination"></div>`;
  renderPostList();
}
function renderPostList() {
  if (!$('#post-list')) return;
  const posts =
    filter === 'attention'
      ? postList.filter((p) => ['failed', 'partial', 'needs_review', 'blocked'].includes(p.status))
      : postList;
  $('#post-list').className = posts.length ? 'post-list' : '';
  $('#post-list').innerHTML = posts.length
    ? posts
        .map((post) => {
          const latest = instagramLast(
            Object.values(Object.fromEntries((post.results || []).map((r) => [r.accountId, r]))),
            (result) => state.accounts.find((account) => account.id === result.accountId)?.platform,
          );
          return `<article class="post-row"><div class="post-row-top"><span class="post-time">${dateText(post.scheduledAt || post.finishedAt || post.createdAt)}</span>${post.status === 'published' ? '<span class="post-published">PUBLISHED</span>' : badge(post.status)}</div><div class="post-content-card">${(post.mediaIds || []).length ? `<div class="post-thumbnail"><img src="/api/media/${encodeURIComponent(post.mediaIds[0])}" alt="${esc(post.alts?.[post.mediaIds[0]] || state.media.find((m) => m.id === post.mediaIds[0])?.alt || 'Attached image')}" loading="lazy" />${post.mediaIds.length > 1 ? `<span class="post-image-count" aria-label="${post.mediaIds.length} attached images">+${post.mediaIds.length - 1}</span>` : ''}</div>` : ''}${post.text ? `<p class="post-text">${esc(post.text)}</p>` : ''}</div>${
            !latest.length
              ? `<div class="post-accounts">${instagramLast(
                  post.accountIds,
                  (id) => state.accounts.find((account) => account.id === id)?.platform,
                )
                  .map((id) => {
                    const account = state.accounts.find((a) => a.id === id);
                    return `<span>${account ? mark(account.platform) : ''}<strong>${esc(account?.handle || 'Disconnected account')}</strong></span>`;
                  })
                  .join('')}</div>`
              : ''
          }${post.message ? `<div class="notice warning">${esc(post.message)}</div>` : ''}${
            latest.length
              ? `<div class="receipts">${latest
                  .map((r) => {
                    const a = state.accounts.find((a) => a.id === r.accountId);
                    const link = safeLink(r.url);
                    const message =
                      a?.platform === 'x' &&
                      r.status === 'published' &&
                      r.message === 'Published text only. Images were omitted for X.'
                        ? ''
                        : r.message;
                    return `<div class="receipt">${a ? mark(a.platform) : ''}<strong>${esc(a?.handle || 'Account')}</strong> · ${r.status === 'published' ? '<span class="published-check" role="img" aria-label="Published" title="Published"><svg viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="9"/><path d="m5.8 10 2.7 2.7 5.7-5.4"/></svg></span>' : badge(r.status)} ${link ? `<a href="${esc(link)}" target="_blank" rel="noopener noreferrer">View post ↗</a>` : ''}${message ? `<p>${esc(message)}</p>` : ''}</div>`;
                  })
                  .join('')}</div>`
              : ''
          }<div class="row-actions">${['draft', 'scheduled', 'blocked'].includes(post.status) ? `<button class="quiet small" data-edit="${esc(post.id)}">Edit</button>` : ''}${!['queued', 'publishing', 'processing'].includes(post.status) ? `<button class="quiet small" data-duplicate="${esc(post.id)}">Duplicate</button>` : ''}${['failed', 'partial', 'needs_review', 'cancelled'].includes(post.status) ? `<button class="small" data-retry="${esc(post.id)}">Retry unsuccessful</button>` : ''}${['scheduled', 'queued', 'publishing', 'processing'].includes(post.status) ? `<button class="quiet small" data-cancel="${esc(post.id)}">${post.status === 'scheduled' ? 'Cancel schedule' : 'Cancel posting'}</button>` : `<button class="quiet small danger" data-delete-post="${esc(post.id)}">Delete</button>`}</div></article>`;
        })
        .join('')
    : `<div class="empty"><span class="eyebrow">A little space to plan</span><h2>${filter === 'all' ? 'Your first post starts here.' : 'Nothing here yet.'}</h2><p>Draft something, choose your accounts, and publish it now or schedule a time.</p><button class="primary" data-page="compose">Create a post →</button></div>`;
  $('#pagination').innerHTML =
    postTotal > 50
      ? `<div class="pagination"><button class="small" data-paging="prev" ${offset === 0 ? 'disabled' : ''}>← Previous</button><span>${offset + 1}–${Math.min(offset + 50, postTotal)} of ${postTotal}</span><button class="small" data-paging="next" ${offset + 50 >= postTotal ? 'disabled' : ''}>Next →</button></div>`
      : '';
}
function renderAccounts() {
  $('#page').innerHTML =
    `<div class="page-header"><div><h1>Accounts</h1><p>Connect your own accounts. Add more than one per platform.</p></div><button class="primary" data-action="connect">＋ Connect account</button></div>${state.accounts.length ? `<div class="account-grid">${state.accounts.map((a) => `<article class="panel account-card"><div class="account-card-top">${mark(a.platform)}<div class="account-info"><strong>${esc(a.name)}</strong><span>${esc(a.handle)}</span></div>${badge('connected')}</div><p>${esc(state.platforms.find((p) => p.id === a.platform)?.content || '')} · Credentials stored encrypted on your server.</p><div class="row-actions"><button class="small" data-reconnect="${esc(a.id)}">Reconnect</button><button class="quiet small danger" data-disconnect="${esc(a.id)}">Disconnect</button></div></article>`).join('')}</div>` : '<div class="panel empty"><h2>Bring your accounts together.</h2><p>Connect Discord webhooks, Bluesky, Mastodon, X (Twitter), Instagram, Threads, Telegram, LinkedIn or Facebook Pages. Each connection is verified before its credentials are stored.</p><button class="primary" data-action="connect">Connect your first account</button></div>'}`;
}
function renderDocs() {
  const guide = guides.find((item) => item.id === location.hash.split('/')[1]);
  if (!guide) {
    $('#page').innerHTML =
      `<div class="page-header"><div><h1>Setup Guide</h1><p>Connect your own accounts, one step at a time.</p></div></div><div class="docs-guides">${guides.map((item) => `<a class="panel docs-platform" href="#docs/${item.id}">${mark(item.id)}<span><strong>${esc(item.name)}</strong><small>${esc(item.account)}</small></span><span aria-hidden="true">→</span></a>`).join('')}</div><div class="note-box"><h3>Reliable scheduling</h3><p>Keep it powered on with its clock synchronized. A missed schedule runs after restart. Check delivery receipts before retrying. Back up your data directory and encryption key together.</p></div>`;
    return;
  }
  $('#page').innerHTML =
    `<a class="docs-back" href="#docs">← All platforms</a><div class="page-header guide-header"><div><h1>${esc(guide.name)} setup</h1><p>${esc(guide.account)}</p></div><button class="primary" data-connect-platform="${guide.id}">Connect ${esc(guide.name)}</button></div><p class="small-text muted">Follow these steps to connect an account you own.</p><article class="docs-article">${guide.id === 'instagram' ? '' : `<p>${esc(guide.approval)}</p><p>${esc(guide.credentials)}</p>`}${guide.steps
      .map((step, index) => {
        const item = typeof step === 'string' ? { title: guide.titles[index], text: step } : step;
        return `<section class="docs-section docs-step" id="${guide.id}-step-${index + 1}"><div><p><strong>Step ${index + 1}:</strong> ${item.link ? `Navigate to <a href="${esc(item.link.url)}" target="_blank" rel="noopener noreferrer">${esc(item.link.label)}</a> ` : ''}${esc(item.text)}</p>${(item.images || []).map((image) => `<figure><img class="docs-screenshot" src="${esc(image.src)}" alt="${esc(image.alt)}" loading="lazy" />${image.caption ? `<figcaption>${esc(image.caption)}</figcaption>` : ''}</figure>`).join('')}</div></section>`;
      })
      .join(
        '',
      )}</article><div class="docs-links">${guide.links.map(([label, url]) => `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(label)} ↗</a>`).join('')}</div>`;
}

function renderSettings() {
  $('#page').innerHTML =
    `<div class="page-header"><div><h1>Settings</h1><p>A small workspace, on your own terms.</p></div></div><div class="settings-grid"><form class="panel panel-body" id="settings-form"><h2>Workspace</h2><div class="field"><label for="workspace-name">Name</label><input id="workspace-name" name="name" required maxlength="80" value="${esc(state.settings.name)}" /></div><div class="field"><span class="label">Your timezone</span><p>${regionLabel()}</p><p class="small-text muted">Schedule inputs and post times both use your browser’s timezone automatically.</p></div><p class="error" id="settings-error" role="alert"></p><button class="primary" type="submit">Save settings</button></form><div class="panel panel-body"><h2>Your server</h2><p>Async Python · SQLite · three concurrent delivery slots.<br>No cloud service, external database, or AI generation.</p><p>Pending schedules resume after a restart. Missed posts are sent when the server starts again. Uncertain deliveries require a check before retrying.</p><p>Account credentials are encrypted. Content exports omit credentials and image files. For a full backup, stop the server and copy the data directory and your encryption key together.</p><a class="button" href="/api/export" download>Export post history ↗</a></div></div><h2 class="section-label">IMAGE LIBRARY</h2><p class="small-text muted">Reuse uploaded images in future posts. Images not used by a saved post can be removed.</p><div class="account-grid">${state.media.map((m) => `<div class="panel panel-body library-item"><img class="library-thumbnail" src="/api/media/${encodeURIComponent(m.id)}" alt="${esc(m.alt || m.name)}" loading="lazy" /><span class="small-text">${esc(m.name)}</span><button class="small quiet danger" data-delete-media="${esc(m.id)}">Remove image</button></div>`).join('') || '<p class="small-text muted">No images uploaded.</p>'}</div>`;
}
function openDialog(title, html) {
  modal.innerHTML = `<div class="dialog-header"><h2 id="modal-title">${esc(title)}</h2><button type="button" data-action="close-modal" aria-label="Close dialog">×</button></div><div class="dialog-content">${html}</div>`;
  modal.showModal();
}
function closeDialog() {
  dirtyForms.delete('connect-form');
  dirtyForms.delete('url-form');
  modal.close();
}
modal.addEventListener('close', () => {
  modal.innerHTML = '';
  dirtyForms.delete('connect-form');
  dirtyForms.delete('url-form');
});
async function connectDialog(id, platform) {
  const existing = state.accounts.find((a) => a.id === id);
  const defaults = existing ? await api(`/accounts/${encodeURIComponent(id)}/connection`) : null;
  openDialog(
    existing ? 'Reconnect account' : 'Connect an account',
    `<form id="connect-form" autocomplete="off"><input type="hidden" name="id" value="${esc(id || '')}" /><div class="field">${existing ? `<strong>${existing.platform === 'x' ? 'X (Twitter)' : esc(state.platforms.find((p) => p.id === existing.platform)?.name || existing.platform)}</strong><input type="hidden" id="platform" name="platform" value="${esc(existing.platform)}" />` : `<label for="platform">Platform</label><select id="platform" name="platform">${state.platforms.map((p) => `<option value="${p.id}" ${platform === p.id ? 'selected' : ''}>${p.id === 'x' ? 'X (Twitter)' : esc(p.name)}</option>`).join('')}</select>`}</div><div id="connect-fields"></div><p class="error" id="connect-error" role="alert"></p><div class="actions"><button type="button" data-action="close-modal">Cancel</button><button type="submit" class="primary">Verify & connect</button></div><p class="form-footnote">Credentials stay on your server and are stored encrypted. Use an app password or developer token, never your regular password.</p></form>`,
  );
  renderConnectFields(defaults);
}
function renderConnectFields(defaults = null) {
  const platform = $('#platform').value;
  const meta = state.platforms.find((p) => p.id === platform);
  const field = (name, label, placeholder = '', type = 'password', required = true, value = '') => {
    const saved = defaults?.savedFields.includes(name);
    const savedSecret = saved && type === 'password';
    return `<div class="field"><label for="credential-${name}">${label}${savedSecret ? ' · Saved' : ''}</label><input id="credential-${name}" name="${name}" type="${type}" placeholder="${savedSecret ? '•••••••• (saved — enter a replacement to change)' : placeholder}" value="${esc(defaults?.values[name] ?? value)}" ${required && !saved ? 'required' : ''} autocomplete="off" spellcheck="false" /></div>`;
  };
  $('#connect-fields').innerHTML =
    `${defaults ? '<p class="notice">Your saved credentials are ready to use. Leave saved fields blank to keep them, or enter replacements.</p>' : ''}<p class="dialog-help">${esc(meta.help)} <button type="button" class="quiet small" data-guide="${esc(platform)}">Open Setup Guide →</button>${platform === 'linkedin' ? ' <a href="https://developer.linkedin.com/" target="_blank" rel="noopener noreferrer">Open developer portal ↗</a>' : ''}</p>${platform === 'facebook' ? field('pageId', 'Facebook Page ID', 'Your numeric Page ID', 'text') + field('secret', 'Page access token') : platform === 'telegram' ? field('chatId', 'Channel username or ID', '@yourchannel or -1001234567890', 'text') + field('secret', 'Bot token from BotFather') : platform === 'discord' ? field('secret', 'Discord server webhook URL', 'https://discord.com/api/webhooks/…') : ['instagram', 'threads', 'linkedin'].includes(platform) ? field('secret', platform === 'linkedin' ? 'Member access token' : 'Long-lived user access token') : platform === 'bluesky' ? field('handle', 'Bluesky handle', 'you.bsky.social', 'text') + field('instance', 'Home server (optional)', 'https://bsky.social', 'url', false) + field('secret', 'App password', 'xxxx-xxxx-xxxx-xxxx') : platform === 'mastodon' ? field('instance', 'Mastodon instance', 'https://mastodon.social', 'url', true, 'https://mastodon.social') + field('secret', 'Access token') : field('apiKey', 'Consumer Key (OAuth 1.0)') + field('apiSecret', 'Consumer Secret (OAuth 1.0)') + field('secret', 'Access Token (OAuth 1.0)') + field('tokenSecret', 'Access Token Secret (OAuth 1.0)')}`;
}
async function reloadState() {
  state = await api('/state');
  if (filter === 'all' && offset === 0) {
    postList = state.posts;
    postTotal = state.total;
  } else await loadPosts();
}
async function loadPosts() {
  const result = await api(
    `/posts?offset=${offset}&status=${filter === 'all' ? '' : encodeURIComponent(filter)}`,
  );
  postList = result.posts;
  postTotal = result.total;
}
async function navigate(next, platform) {
  readComposer();
  history.replaceState(null, '', '#' + next + (next === 'docs' && platform ? '/' + platform : ''));
  page = next;
  if (next === 'posts') await loadPosts();
  renderPage();
}
function renderLogin() {
  state = undefined;
  root.innerHTML = `<main class="signin"><div class="signin-header">${brand}${themeToggle()}</div><h1>Your workspace</h1><form id="login-form"><div class="field"><label for="password">Workspace password</label><input type="password" name="password" id="password" required autocomplete="current-password" /></div><p class="error" id="login-error" role="alert"></p><button class="primary" type="submit">Sign in →</button></form></main>`;
}
async function runAction(button, work, errorTarget) {
  button.disabled = true;
  const originalLabel = button.innerHTML;
  if (errorTarget === '#connect-error') {
    button.textContent = 'Verifying…';
    $('#connect-error').textContent = '';
  }
  try {
    await work();
  } catch (error) {
    const target = errorTarget && $(errorTarget);
    if (target) target.textContent = error.message;
    else toast(error.message);
  } finally {
    if (button.isConnected) {
      button.disabled = false;
      if (errorTarget === '#connect-error') button.innerHTML = originalLabel;
    }
  }
}
document.addEventListener('submit', async (event) => {
  event.preventDefault();
  const form = event.target;
  if (form.dataset.submitting) return;
  form.dataset.submitting = 'true';
  $$('button[type="submit"]', form).forEach((b) => {
    b.disabled = true;
  });
  const button = event.submitter || $('button[type="submit"]', form);
  if (form.getAttribute('id') === 'post-form') {
    await runAction(
      button,
      async () => {
        readComposer();
        if (!composer.accountIds.length) throw Error('Select at least one account.');
        for (const [id, alt] of Object.entries(composer.alts)) {
          const media = state.media.find((m) => m.id === id);
          if (composer.mediaIds.includes(id) && alt !== (media?.alt || ''))
            await api(`/media/${id}`, { method: 'PUT', body: { alt } });
        }
        const status = button.value;
        const date = new Date(composer.scheduledAt);
        if (status === 'scheduled' && (!composer.scheduledAt || Number.isNaN(date.getTime())))
          throw Error('Choose a date and time.');
        const xAccounts = state.accounts.filter(
          (a) => a.platform === 'x' && composer.accountIds.includes(a.id),
        );
        if (status !== 'draft' && xAccounts.length) {
          if (hasXLink(composer.text) && !composer.xAllowLinks)
            throw Error(
              'Links are disabled for X (Twitter). Enable Allow links or remove the URL.',
            );
          if (
            !(await confirmXCost(
              composer.text,
              xAccounts.length,
              status === 'scheduled' ? 'schedule' : 'publish',
            ))
          )
            return;
        }
        await api('/posts', {
          method: 'POST',
          body: {
            ...composer,
            xCostConfirmed: status !== 'draft' && xAccounts.length > 0,
            status,
            scheduledAt: status === 'scheduled' ? date.toISOString() : null,
          },
        });
        composer = freshComposer();
        await reloadState();
        filter = 'all';
        offset = 0;
        postList = state.posts;
        postTotal = state.total;
        dirtyForms.delete('post-form');
        page = 'posts';
        history.replaceState(null, '', '#posts');
        renderPage();
        toast(
          status === 'now'
            ? 'Post queued. Delivery results will appear here.'
            : status === 'scheduled'
              ? 'Post scheduled.'
              : 'Draft saved.',
        );
      },
      '#post-error',
    );
  } else if (form.getAttribute('id') === 'url-form') {
    await runAction(
      button,
      async () => {
        if (composer.mediaIds.length >= 4) throw Error('Choose up to four images.');
        const media = await api('/media/url', {
          method: 'POST',
          body: Object.fromEntries(new FormData(form)),
        });
        dirtyForms.add('post-form');
        composer.mediaIds.push(media.id);
        state.media.push(media);
        closeDialog();
        renderAttachments();
        updatePreview();
        toast('Public image attached. Keep its URL available until publishing finishes.');
      },
      '#url-error',
    );
  } else if (form.getAttribute('id') === 'connect-form') {
    await runAction(
      button,
      async () => {
        const data = Object.fromEntries(new FormData(form));
        data.platform = $('#platform').value;
        await api('/accounts', { method: 'POST', body: data });
        form.reset();
        closeDialog();
        await reloadState();
        renderPage();
        toast('Account verified and connected.');
      },
      '#connect-error',
    );
  } else if (form.getAttribute('id') === 'settings-form') {
    await runAction(
      button,
      async () => {
        await api('/settings', {
          method: 'PUT',
          body: { ...Object.fromEntries(new FormData(form)), timezone: browserZone },
        });
        await reloadState();
        renderShell();
        dirtyForms.delete('settings-form');
        toast('Settings saved.');
      },
      '#settings-error',
    );
  } else if (form.getAttribute('id') === 'login-form') {
    await runAction(
      button,
      async () => {
        await api('/login', { method: 'POST', body: Object.fromEntries(new FormData(form)) });
        form.reset();
        await reloadState();
        renderShell();
      },
      '#login-error',
    );
  }
  delete form.dataset.submitting;
  $$('button[type="submit"]', form).forEach((b) => {
    b.disabled = false;
  });
});
document.addEventListener('input', (event) => {
  if (event.target.closest('#post-form')) {
    if (event.target.id === 'select-all-accounts') {
      $$('input[name="account"]').forEach((input) => {
        input.checked = event.target.checked;
      });
    }
    if (event.target.dataset.alt) composer.alts[event.target.dataset.alt] = event.target.value;
    updatePreview();
  }
});
document.addEventListener('change', async (event) => {
  if (event.target.id === 'platform') renderConnectFields();
});
document.addEventListener('click', async (event) => {
  const button = event.target.closest('button');
  if (!button || (button.type === 'submit' && button.closest('form') && !button.dataset.action))
    return;
  const data = button.dataset;
  if (data.action === 'toggle-theme') {
    window.lightpostTheme.toggle();
    return;
  }
  await runAction(button, async () => {
    if (data.action === 'toggle-region') {
      regionVisible = !regionVisible;
      for (const region of $$('[data-action="toggle-region"]')) {
        region.classList.toggle('is-blurred', !regionVisible);
        region.setAttribute('aria-expanded', String(regionVisible));
        region.setAttribute('aria-label', regionVisible ? 'Hide region' : 'Show region');
      }
      return;
    }
    if (data.page) {
      await navigate(data.page);
      return;
    }
    if (data.filter) {
      filter = data.filter;
      offset = 0;
      await loadPosts();
      renderPosts();
      return;
    }
    if (data.paging) {
      offset += data.paging === 'next' ? 50 : -50;
      await loadPosts();
      renderPostList();
      return;
    }
    if (data.removeImage) {
      dirtyForms.add('post-form');
      composer.mediaIds = composer.mediaIds.filter((id) => id !== data.removeImage);
      renderAttachments();
      updatePreview();
      return;
    }
    if (data.pickImage) {
      const issue = savedImageIssue(state.media.find((media) => media.id === data.pickImage));
      if (issue) throw Error(issue);
      dirtyForms.add('post-form');
      if (composer.mediaIds.length >= 4) throw Error('Choose up to four images.');
      if (!composer.mediaIds.includes(data.pickImage)) composer.mediaIds.push(data.pickImage);
      closeDialog();
      renderAttachments();
      updatePreview();
      return;
    }
    if (data.guide) {
      closeDialog();
      await navigate('docs', data.guide);
      return;
    }
    if (data.connectPlatform) {
      await connectDialog(undefined, data.connectPlatform);
      return;
    }
    if (data.reconnect) {
      await connectDialog(data.reconnect);
      return;
    }
    if (data.disconnect) {
      if (!confirm('Disconnect this account? Published posts stay on the platform.')) return;
      await api(`/accounts/${data.disconnect}`, { method: 'DELETE' });
      await reloadState();
      renderAccounts();
      return;
    }
    if (data.edit || data.duplicate) {
      const post = postList.find((p) => p.id === (data.edit || data.duplicate));
      composer = {
        ...freshComposer(),
        text: post.text,
        accountIds: post.accountIds.filter((id) => state.accounts.some((a) => a.id === id)),
        mediaIds: [...(post.mediaIds || [])],
        id: data.edit ? post.id : null,
        xAllowLinks: false,
        contentOptions: structuredClone(post.contentOptions || {}),
        scheduledAt: data.edit && post.scheduledAt ? localInput(post.scheduledAt) : '',
      };
      await navigate('compose');
      return;
    }
    if (data.retry) {
      const post = postList.find((p) => p.id === data.retry);
      const xCount = retryAccountIds(post).filter((id) =>
        state.accounts.some((a) => a.id === id && a.platform === 'x'),
      ).length;
      if (xCount && !(await confirmXCost(post.text, xCount, 'retry'))) return;
      await api(`/posts/${data.retry}/retry`, {
        method: 'POST',
        body: { xCostConfirmed: xCount > 0 },
      });
      await reloadState();
      renderPosts();
      toast('Unsuccessful destinations queued for retry.');
      return;
    }
    if (data.cancel) {
      const post = postList.find((p) => p.id === data.cancel);
      const pending = ['scheduled', 'queued'].includes(post?.status);
      if (
        !confirm(
          pending
            ? 'Cancel this posting? The post will be saved as a draft.'
            : 'Cancel further posting attempts? Posts already published will remain online, and requests already sent may still finish.',
        )
      )
        return;
      const cancelled = await api(`/posts/${data.cancel}/cancel`, { method: 'POST', body: {} });
      await reloadState();
      renderPosts();
      toast(
        cancelled.status === 'draft'
          ? 'Posting cancelled. Post saved as a draft.'
          : 'Further posting attempts cancelled.',
      );
      return;
    }
    if (data.deletePost) {
      if (!confirm('Delete this workspace record? External posts will remain on their platforms.'))
        return;
      await api(`/posts/${data.deletePost}`, { method: 'DELETE' });
      await reloadState();
      renderPosts();
      return;
    }
    if (data.deleteMedia) {
      await api(`/media/${data.deleteMedia}`, { method: 'DELETE' });
      await reloadState();
      renderSettings();
      return;
    }
    if (data.action === 'logout') {
      await api('/logout', { method: 'POST', body: {} });
      composer = freshComposer();
      dirtyForms.clear();
      renderLogin();
      return;
    }
    if (data.action === 'connect') await connectDialog();
    if (data.action === 'close-modal') closeDialog();
    if (data.action === 'library')
      openDialog(
        'Saved Library',
        `<p class="small-text muted">Select a saved image to attach it.</p><div class="library">${
          state.media
            .map((m) => {
              const issue = savedImageIssue(m);
              return `<button type="button" data-pick-image="${esc(m.id)}" ${issue ? `disabled title="${esc(issue)}"` : ''}><img loading="lazy" src="/api/media/${encodeURIComponent(m.id)}" alt="${esc(m.alt || m.name)}" /><small>${esc(m.name)}</small>${issue ? `<small class="library-unavailable">${esc(issue)}</small>` : ''}</button>`;
            })
            .join('') ||
          '<p class="small-text muted">No saved images yet. Use Add Image to import one.</p>'
        }</div>`,
      );
    if (data.action === 'source-image')
      openDialog(
        'Add a public image',
        `<form id="url-form"><p class="dialog-help">Instagram and Threads need a JPEG that Meta can fetch over public HTTPS. Paste a direct image URL from your own website or media host. Your server can stay private. Keep the image available until the scheduled post finishes.</p><div class="field"><label for="image-url">Direct JPEG URL</label><input id="image-url" name="url" type="url" placeholder="https://your-website.com/image.jpg" required maxlength="2048" /></div><p class="error" id="url-error" role="alert"></p><div class="actions"><button type="button" data-action="close-modal">Cancel</button><button type="submit" class="primary">Import image</button></div></form>`,
      );
  });
});
async function init() {
  if (!/^\/app\/?$/.test(location.pathname)) {
    renderLanding();
    return;
  }
  try {
    const session = await api('/session');
    if (!session.authenticated) {
      renderLogin();
      return;
    }
    await reloadState();
    if (page === 'posts') await loadPosts();
    renderShell();
  } catch (error) {
    root.innerHTML = `<main class="signin">${brand}<h1>Unable to open workspace</h1><p class="error">${esc(error.message)}</p><button data-action="reload">Try again</button></main>`;
    $('[data-action="reload"]').onclick = () => location.reload();
  }
}
let refreshingPosts = false;
let lastPostRefresh = 0;
async function refreshPostStatus(force = false) {
  if (!state || document.hidden || refreshingPosts) return;
  const active = state.posts.some((p) => ['queued', 'publishing', 'processing'].includes(p.status));
  if (page !== 'posts' && !active) return;
  if (!force && Date.now() - lastPostRefresh < (active ? 2000 : 10000)) return;
  refreshingPosts = true;
  lastPostRefresh = Date.now();
  try {
    await reloadState();
    if (page === 'posts') renderPostList();
    const count = $('.nav .count');
    if (count) count.textContent = `(${state.total})`;
  } catch {
    /* Keep unsaved content intact when the server is offline. */
  } finally {
    refreshingPosts = false;
  }
}
setInterval(() => refreshPostStatus(), 2000);
document.addEventListener('visibilitychange', () => {
  if (!document.hidden) refreshPostStatus(true);
});
window.addEventListener('focus', () => refreshPostStatus(true));
window.addEventListener('beforeunload', (event) => {
  readComposer();
  if ([...dirtyForms].some((id) => id === 'post-form' || document.getElementById(id))) {
    event.preventDefault();
    event.returnValue = '';
  }
});
for (const type of ['input', 'change']) {
  document.addEventListener(type, (event) => {
    const form = event.target.closest('form');
    if (form) dirtyForms.add(form.getAttribute('id'));
  });
}
window.addEventListener('hashchange', async () => {
  const next = location.hash.slice(1).split('/')[0];
  if (state && pages.includes(next)) {
    readComposer();
    page = next;
    if (page === 'posts') await loadPosts();
    renderPage();
    window.scrollTo(0, 0);
  }
});

for (const type of ['pointerover', 'pointermove']) {
  document.addEventListener(type, (event) => {
    const toggle = event.target.closest('.required-toggle');
    if (!toggle) return;
    const bounds = toggle.getBoundingClientRect();
    const x = Math.max(104, Math.min(window.innerWidth - 104, event.clientX));
    toggle.style.setProperty('--tooltip-x', `${x - bounds.left}px`);
    toggle.style.setProperty('--tooltip-y', `${event.clientY - bounds.top}px`);
  });
}

init();
