/* =============================================================
   TechTracker — app.js  (Complete rewrite)
   API: http://localhost:8001
============================================================= */

const API = 'http://localhost:8001';
const LS_NL = 'techtracker_newsletters';
const LS_LB = 'techtracker_lookback';
const LS_THEME = 'techtracker_theme';
const LS_YT = 'techtracker_yt_channels';   // YouTube channel URLs

// ── DOM refs ──────────────────────────────────────────────────
const $ = id => document.getElementById(id);

const sidebar = $('sidebar');
const main = $('main');
const collapseBtn = $('collapseBtn');
const mobileMenuBtn = $('mobileMenuBtn');
const statusDot = $('statusDot');
const statusText = $('statusText');
const nlTagsPreview = $('nlTagsPreview');
const themeToggle = $('themeToggle');
const themeIcon = $('themeIcon');
const toastEl = $('toast');

// Updates
const updatesHero = $('updatesHero');
const getUpdatesBtn = $('getUpdatesBtn');
const getUpdatesBtnTxt = $('getUpdatesBtnText');
const updatesSpinner = $('updatesSpinner');
const heroHint = $('heroHint');
const newsFeed = $('newsFeed');
const newsList = $('newsList');
const feedCount = $('feedCount');
const feedTime = $('feedTime');
const feedBanner = $('feedBanner');
const refreshUpdatesBtn = $('refreshUpdatesBtn');

// History
const historyContainer = $('historyContainer');
const refreshHistoryBtn = $('refreshHistoryBtn');

// Calendar
const calendarFeed = $('calendarFeed');
const calNewsList = $('calNewsList');
const calFeedCount = $('calFeedCount');
const calFeedDate = $('calFeedDate');
const calFeedSource = $('calFeedSource');

// Configure
const configPills = $('configPills');
const configEmptyHint = $('configEmptyHint');
const configInput = $('configInput');
const configAddBtn = $('configAddBtn');
const saveConfigBtn = $('saveConfigBtn');
const lookbackSelect = $('lookbackSelect');
// YouTube configure
const ytPills = $('ytPills');
const ytEmptyHint = $('ytEmptyHint');
const ytInput = $('ytInput');
const ytAddBtn = $('ytAddBtn');
const saveYtBtn = $('saveYtBtn');

// Connectors
const gmailClientId = $('gmailClientId');
const gmailClientSecret = $('gmailClientSecret');
const gmailRefreshToken = $('gmailRefreshToken');
const saveGmailCreds = $('saveGmailCreds');
const youtubeApiKey = $('youtubeApiKey');
const saveYoutubeCreds = $('saveYoutubeCreds');

// Hover card
const hoverCard = $('hoverCard');
const hcSource = $('hcSource');
const hcTitle = $('hcTitle');
const hcDesc = $('hcDesc');
const hcClose = $('hcClose');
const hcAiBtn = $('hcAiBtn');
const hcSelectHint = $('hcSelectHint');

// Chat widget
const chatFab = $('chatFab');
const chatWidget = $('chatWidget');
const chatBadge = $('chatBadge');
const cwMessages = $('cwMessages');
const cwInput = $('cwInput');
const cwSendBtn = $('cwSendBtn');
const chatClose = $('chatClose');
const chatClear = $('chatClear');

// ── State ─────────────────────────────────────────────────────
let configuredNewsletters = [];
let ytChannels = [];   // YouTube channel URLs
let sidebarCollapsed = false;
let isDark = true;
let chatMsgCount = 0;
let hoverCardItem = null;
let hoverLeaveTimer = null;
let chatLoading = false;

// Calendar state
let calYear = new Date().getFullYear();
let calMonth = new Date().getMonth();
let calSelectedDate = null;
let calAvailDates = new Set();

// Chat session memory — unique per page load so each session has its own history
const CHAT_SESSION_ID = 'sess_' + Math.random().toString(36).slice(2, 10) + '_' + Date.now();

// ── INIT ──────────────────────────────────────────────────────
function init() {
    loadTheme();
    loadConfig();
    bindSidebar();
    bindNavTabs();
    bindUpdatesTab();
    bindCalendarTab();
    bindHistoryTab();
    bindConfigureTab();
    bindConnectorsTab();
    bindHoverCard();
    bindChatWidget();
    checkHealth();
    setInterval(checkHealth, 15_000);
}

// ═══════════════════════════════════════════════════════════════
// THEME
// ═══════════════════════════════════════════════════════════════
function loadTheme() {
    const saved = localStorage.getItem(LS_THEME) || 'dark';
    applyTheme(saved);
}

function applyTheme(theme) {
    isDark = theme === 'dark';
    document.documentElement.setAttribute('data-theme', theme);
    themeIcon.textContent = isDark ? '🌙' : '☀️';
    localStorage.setItem(LS_THEME, theme);
}

themeToggle.addEventListener('click', () => applyTheme(isDark ? 'light' : 'dark'));

// ═══════════════════════════════════════════════════════════════
// CONFIG
// ═══════════════════════════════════════════════════════════════
function loadConfig() {
    const saved = localStorage.getItem(LS_NL);
    configuredNewsletters = saved ? JSON.parse(saved) : [];
    const lb = localStorage.getItem(LS_LB);
    if (lb) lookbackSelect.value = lb;
    // YouTube channels
    const ytSaved = localStorage.getItem(LS_YT);
    ytChannels = ytSaved ? JSON.parse(ytSaved) : [];
    renderConfigPills();
    renderYtPills();
    renderNlPreview();
    updateHeroHint();
}

function saveConfig() {
    localStorage.setItem(LS_NL, JSON.stringify(configuredNewsletters));
    localStorage.setItem(LS_LB, lookbackSelect.value);
    renderNlPreview();
    updateHeroHint();
    showToast('✅ Configuration saved!');
}

function addCfgNl(name) {
    const v = name.trim().toLowerCase();
    if (!v || configuredNewsletters.includes(v)) return;
    configuredNewsletters.push(v);
    renderConfigPills();
    updateSuggestionChips();
}

function removeCfgNl(name) {
    configuredNewsletters = configuredNewsletters.filter(n => n !== name);
    renderConfigPills();
    updateSuggestionChips();
}

function renderConfigPills() {
    configPills.innerHTML = '';
    configEmptyHint.classList.toggle('hidden', configuredNewsletters.length > 0);
    configuredNewsletters.forEach(nl => {
        const el = document.createElement('div');
        el.className = 'cfg-pill';
        el.innerHTML = `<span>${nlLabel(nl)}</span><button class="cfg-pill-remove" title="Remove">×</button>`;
        el.querySelector('.cfg-pill-remove').onclick = () => removeCfgNl(nl);
        configPills.appendChild(el);
    });
}

function renderNlPreview() {
    nlTagsPreview.innerHTML = '';
    configuredNewsletters.slice(0, 4).forEach(nl => {
        const t = document.createElement('span');
        t.className = 'nl-tag-preview';
        t.textContent = nlLabel(nl);
        nlTagsPreview.appendChild(t);
    });
    if (configuredNewsletters.length > 4) {
        const m = document.createElement('span');
        m.className = 'nl-tag-preview';
        m.textContent = `+${configuredNewsletters.length - 4}`;
        nlTagsPreview.appendChild(m);
    }
}

function updateHeroHint() {
    if (!heroHint) return;
    heroHint.textContent = configuredNewsletters.length === 0
        ? '⚠️ No newsletters configured — go to Configure tab first.'
        : `Monitoring: ${configuredNewsletters.map(nlLabel).join(', ')}`;
}

function updateSuggestionChips() {
    document.querySelectorAll('.s-chip').forEach(c =>
        c.classList.toggle('used', configuredNewsletters.includes(c.dataset.nl))
    );
}

// ═══════════════════════════════════════════════════════════════
// SIDEBAR
// ═══════════════════════════════════════════════════════════════
function bindSidebar() {
    collapseBtn.addEventListener('click', () => {
        sidebarCollapsed = !sidebarCollapsed;
        sidebar.classList.toggle('collapsed', sidebarCollapsed);
        main.classList.toggle('sidebar-collapsed', sidebarCollapsed);
    });
    mobileMenuBtn.addEventListener('click', () => sidebar.classList.toggle('mobile-open'));
    document.addEventListener('click', e => {
        if (window.innerWidth <= 800
            && !sidebar.contains(e.target)
            && e.target !== mobileMenuBtn) {
            sidebar.classList.remove('mobile-open');
        }
    });
}

// ═══════════════════════════════════════════════════════════════
// TAB NAVIGATION
// ═══════════════════════════════════════════════════════════════
function bindNavTabs() {
    document.querySelectorAll('.nav-item[data-tab]').forEach(btn => {
        btn.addEventListener('click', () => switchTab(btn.dataset.tab));
    });
}

function switchTab(tab) {
    document.querySelectorAll('.nav-item[data-tab]').forEach(b =>
        b.classList.toggle('active', b.dataset.tab === tab)
    );
    document.querySelectorAll('.tab-panel').forEach(p => {
        p.classList.toggle('active', p.id === `tab-${tab}`);
        p.classList.toggle('hidden', p.id !== `tab-${tab}`);
    });
    if (tab === 'history') loadHistory();
    if (tab === 'calendar') loadAvailableDates();
    if (tab === 'configure') updateSuggestionChips();
    if (window.innerWidth <= 800) sidebar.classList.remove('mobile-open');
    hideHoverCard();
}

// ═══════════════════════════════════════════════════════════════
// TECH UPDATES TAB
// ═══════════════════════════════════════════════════════════════
function bindUpdatesTab() {
    getUpdatesBtn.addEventListener('click', fetchTodayUpdates);
    refreshUpdatesBtn.addEventListener('click', fetchForceRefresh); // skip cache, go to Gmail
}

async function fetchTodayUpdates() {
    if (!configuredNewsletters.length) {
        showToast('⚠️ Configure newsletters first!');
        switchTab('configure');
        return;
    }
    setUpdatesLoading(true, false);
    try {
        const url = new URL(`${API}/today_updates`);
        url.searchParams.set('newsletters', configuredNewsletters.join(','));
        url.searchParams.set('days', lookbackSelect.value);
        if (ytChannels.length) url.searchParams.set('yt_channels', ytChannels.join(','));
        const res = await fetch(url);
        if (!res.ok) throw new Error(`Server ${res.status}`);
        const data = await res.json();

        if (!data.headlines?.length) {
            showToast('⚠️ ' + (data.message || 'No news found.'));
            return;
        }
        renderNewsFeed(data, newsList, {
            countEl: feedCount, timeEl: feedTime,
            feedEl: newsFeed, heroEl: updatesHero, bannerEl: feedBanner,
            isToday: data.is_today, message: data.message
        });
    } catch (e) {
        showToast(`❌ ${e.message}`);
    } finally {
        setUpdatesLoading(false, false);
    }
}

async function fetchForceRefresh() {
    if (!configuredNewsletters.length) {
        showToast('⚠️ Configure newsletters first!');
        switchTab('configure');
        return;
    }
    showToast('🔄 Syncing Gmail directly… this may take a moment.');
    setUpdatesLoading(true, true);
    try {
        const url = new URL(`${API}/today_updates`);
        url.searchParams.set('newsletters', configuredNewsletters.join(','));
        url.searchParams.set('days', lookbackSelect.value);
        url.searchParams.set('force', 'true');
        if (ytChannels.length) url.searchParams.set('yt_channels', ytChannels.join(','));
        const res = await fetch(url);
        if (!res.ok) throw new Error(`Server ${res.status}`);
        const data = await res.json();

        if (!data.headlines?.length) {
            showToast('⚠️ ' + (data.message || 'No news found.'));
            return;
        }
        renderNewsFeed(data, newsList, {
            countEl: feedCount, timeEl: feedTime,
            feedEl: newsFeed, heroEl: updatesHero, bannerEl: feedBanner,
            isToday: data.is_today, message: data.message
        });
        showToast('✅ Fresh updates from Gmail!');
    } catch (e) {
        showToast(`❌ ${e.message}`);
    } finally {
        setUpdatesLoading(false, true);
    }
}

function setUpdatesLoading(on, isForce = false) {
    getUpdatesBtn.disabled = on;
    if (isForce) {
        getUpdatesBtnTxt.textContent = on ? 'Syncing Gmail…' : '⚡ Get Today\'s Updates';
    } else {
        getUpdatesBtnTxt.textContent = on ? 'Fetching…' : '⚡ Get Today\'s Updates';
    }
    updatesSpinner.classList.toggle('hidden', !on);
}

// ═══════════════════════════════════════════════════════════════
// CALENDAR TAB — full month grid
// ═══════════════════════════════════════════════════════════════
function bindCalendarTab() {
    $('calPrevMonth').addEventListener('click', () => { calMonth--; if (calMonth < 0) { calMonth = 11; calYear--; } renderCalendar(); });
    $('calNextMonth').addEventListener('click', () => { calMonth++; if (calMonth > 11) { calMonth = 0; calYear++; } renderCalendar(); });
    renderCalendar();
}

async function loadAvailableDates() {
    if (!configuredNewsletters.length) return;
    try {
        const url = new URL(`${API}/available_dates`);
        url.searchParams.set('newsletters', configuredNewsletters.join(','));
        const res = await fetch(url);
        if (!res.ok) return;
        const data = await res.json();
        calAvailDates = new Set(data.dates || []);
        renderCalendar(); // re-render with dots
    } catch (e) { /* ignore */ }
}

function renderCalendar() {
    const today = new Date();
    const nowY = today.getFullYear();
    const nowM = today.getMonth();
    const nowD = today.getDate();

    // Month label
    const label = new Date(calYear, calMonth, 1).toLocaleDateString(undefined, { month: 'long', year: 'numeric' });
    $('calMonthYear').textContent = label;

    // First weekday offset (Mon=0)
    const firstDay = new Date(calYear, calMonth, 1).getDay();
    const startOffset = (firstDay + 6) % 7;
    const daysInMonth = new Date(calYear, calMonth + 1, 0).getDate();

    const grid = $('calGrid');
    grid.innerHTML = '';

    // Empty leading cells
    for (let i = 0; i < startOffset; i++) {
        const empty = document.createElement('div');
        empty.className = 'cal-cell empty';
        grid.appendChild(empty);
    }

    for (let d = 1; d <= daysInMonth; d++) {
        const dateStr = `${calYear}-${String(calMonth + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
        const isToday = (d === nowD && calMonth === nowM && calYear === nowY);
        const isFuture = new Date(calYear, calMonth, d) > today;
        const isSelected = dateStr === calSelectedDate;
        const hasData = calAvailDates.has(dateStr);

        const cell = document.createElement('div');
        let cls = 'cal-cell';
        if (isToday) cls += ' today';
        if (isFuture) cls += ' future';
        if (isSelected) cls += ' selected';
        if (hasData) cls += ' has-data';
        cell.className = cls;
        cell.textContent = d;
        cell.title = dateStr;

        if (!isFuture) {
            cell.addEventListener('click', () => selectCalDate(dateStr));
        }
        grid.appendChild(cell);
    }
}

async function selectCalDate(dateStr) {
    calSelectedDate = dateStr;
    renderCalendar();

    if (!configuredNewsletters.length) {
        showToast('⚠️ Configure newsletters first!'); switchTab('configure'); return;
    }

    const loadingEl = $('calLoading');
    const hintEl = $('calSidebarHint');
    if (loadingEl) loadingEl.classList.remove('hidden');

    try {
        const url = new URL(`${API}/calendar_updates`);
        url.searchParams.set('date', dateStr);
        url.searchParams.set('newsletters', configuredNewsletters.join(','));
        if (ytChannels.length) url.searchParams.set('yt_channels', ytChannels.join(','));
        const res = await fetch(url);
        if (!res.ok) throw new Error(`Server ${res.status}`);
        const data = await res.json();

        if (!data.headlines?.length) {
            showToast(data.message || `No updates for ${dateStr}.`);
            calendarFeed.classList.add('hidden');
            return;
        }

        renderNewsFeed(data, calNewsList, {
            countEl: calFeedCount, timeEl: calFeedDate, feedEl: calendarFeed,
        });
        calFeedDate.textContent = formatDateDisplay(dateStr);

        // Show source badge
        if (calFeedSource) {
            calFeedSource.textContent = data.source === 'cache' ? '⚡ Cached' : '🔄 Fresh';
            calFeedSource.classList.remove('hidden');
        }

        // If this date has data, add to avail set
        if (data.headlines.length > 0) calAvailDates.add(dateStr);
        renderCalendar();

        // Scroll to feed
        calendarFeed.scrollIntoView({ behavior: 'smooth', block: 'start' });
    } catch (e) {
        showToast(`❌ ${e.message}`);
    } finally {
        if (loadingEl) loadingEl.classList.add('hidden');
    }
}

// ═══════════════════════════════════════════════════════════════
// SHARED: RENDER NEWS FEED
// ═══════════════════════════════════════════════════════════════
function renderNewsFeed(data, listEl, opts = {}) {
    const { countEl, timeEl, feedEl, heroEl, bannerEl, isToday, message } = opts;

    if (heroEl) heroEl.classList.add('hidden');
    if (feedEl) feedEl.classList.remove('hidden');

    if (countEl) countEl.textContent = `${data.count} news items`;
    if (timeEl && !opts.skipTime) timeEl.textContent = `Updated ${new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;

    if (bannerEl) {
        if (!isToday && isToday !== undefined) {
            bannerEl.textContent = '📅 Showing latest available (no new items today)';
            bannerEl.classList.remove('hidden');
        } else {
            bannerEl.classList.add('hidden');
        }
    }

    listEl.innerHTML = '';
    data.headlines.forEach((item, i) => {
        const el = document.createElement('div');
        el.className = 'news-item';
        el.dataset.title = item.title || '';
        el.dataset.desc = item.description || '';
        el.dataset.source = item.source || '';

        el.innerHTML = `
      <span class="news-num">${String(i + 1).padStart(2, '0')}</span>
      <span class="news-dot"></span>
      <div class="news-item-body">
        <span class="news-item-title">${esc(item.title || '')}</span>
        ${item.source ? `<span class="news-source-badge">${esc(item.source)}</span>` : ''}
        <span class="news-hover-hint">hover ✦</span>
      </div>`;
        listEl.appendChild(el);
    });
}

// ═══════════════════════════════════════════════════════════════
// HOVER CARD (interactive)
// ═══════════════════════════════════════════════════════════════
function bindHoverCard() {
    // Mouse enters a news item → show card
    document.addEventListener('mouseover', e => {
        const item = e.target.closest('.news-item');
        if (item && item.dataset.desc) {
            clearTimeout(hoverLeaveTimer);
            showHoverCard(item);
        }
    });

    // Mouse leaves news item → maybe hide (with delay for card transition)
    document.addEventListener('mouseout', e => {
        const item = e.target.closest('.news-item');
        if (item && !item.contains(e.relatedTarget)) {
            scheduleHideCard();
        }
    });

    // Mouse enters the card → keep open
    hoverCard.addEventListener('mouseenter', () => clearTimeout(hoverLeaveTimer));
    hoverCard.addEventListener('mouseleave', () => scheduleHideCard());

    // Close button
    hcClose.addEventListener('click', hideHoverCard);

    // Detect text selection to update button label
    hoverCard.addEventListener('mouseup', () => {
        const sel = window.getSelection()?.toString().trim();
        if (sel && sel.length > 4) {
            hcAiBtn.textContent = '✨ Summarise Selected';
            hcAiBtn.dataset.selectedText = sel;
            hcSelectHint.textContent = 'Selected text:  "' + sel.slice(0, 40) + (sel.length > 40 ? '…' : '') + '"';
        } else {
            hcAiBtn.textContent = '✨ AI Summarise';
            hcAiBtn.dataset.selectedText = '';
            hcSelectHint.textContent = 'Select text above to refine, or:';
        }
    });

    // AI Summarise button
    hcAiBtn.addEventListener('click', () => {
        const selected = hcAiBtn.dataset.selectedText?.trim();
        const textToSend = selected || (hcDesc.textContent + ' ' + hcTitle.textContent);
        triggerAiSummarise(textToSend);
        hideHoverCard();
    });
}

function showHoverCard(item) {
    hoverCardItem = item;
    hcSource.textContent = (item.dataset.source || '').toUpperCase();
    hcTitle.textContent = item.dataset.title || '';
    hcDesc.textContent = item.dataset.desc || '';
    hcAiBtn.textContent = '✨ AI Summarise';
    hcAiBtn.dataset.selectedText = '';
    hcSelectHint.textContent = 'Select text above to refine, or:';

    hoverCard.classList.remove('hidden');
    positionHoverCard(item);
}

function positionHoverCard(item) {
    const rect = item.getBoundingClientRect();
    const cardW = 340;   // fixed card width
    const gap = 14;
    const pad = 10;

    hoverCard.classList.remove('tail-left', 'tail-right');

    // Prefer RIGHT side of the item
    let left = rect.right + gap;
    let preferRight = left + cardW <= window.innerWidth - pad;

    if (!preferRight) {
        // Fall back to LEFT side
        left = rect.left - cardW - gap;
        hoverCard.classList.add('tail-right');
        if (left < pad) left = pad;
    } else {
        hoverCard.classList.add('tail-left');
    }

    // Vertically: centre on the item row, then clamp to viewport
    const cardH = hoverCard.offsetHeight || 240;
    let top = rect.top + rect.height / 2 - 54;
    if (top + cardH > window.innerHeight - pad) top = window.innerHeight - cardH - pad;
    if (top < pad) top = pad;

    hoverCard.style.top = top + 'px';
    hoverCard.style.left = left + 'px';
}

function scheduleHideCard() {
    hoverLeaveTimer = setTimeout(hideHoverCard, 180);
}

function hideHoverCard() {
    hoverCard.classList.add('hidden');
    hoverCardItem = null;
}

// ═══════════════════════════════════════════════════════════════
// CHAT WIDGET
// ═══════════════════════════════════════════════════════════════
function bindChatWidget() {
    chatFab.addEventListener('click', () => {
        chatWidget.classList.toggle('hidden');
        if (!chatWidget.classList.contains('hidden')) {
            cwMessages.scrollTop = cwMessages.scrollHeight;
            cwInput.focus();
        }
    });
    chatClose.addEventListener('click', () => chatWidget.classList.add('hidden'));

    chatClear.addEventListener('click', () => {
        cwMessages.innerHTML = `
      <div class="cw-welcome">
        <div class="cw-welcome-icon">🤖</div>
        <p>Chat cleared. Hover a news item and click <strong>✨ AI Summarise</strong> to start.</p>
      </div>`;
        chatMsgCount = 0;
        chatBadge.classList.add('hidden');
    });

    cwSendBtn.addEventListener('click', sendChatMessage);
    cwInput.addEventListener('keydown', e => {
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendChatMessage(); }
    });
}

async function sendChatMessage() {
    const text = cwInput.value.trim();
    if (!text || chatLoading) return;
    cwInput.value = '';
    appendUserMsg(text);
    await callChatSummarise(text);
}

// Called from hover card AI button
async function triggerAiSummarise(text) {
    // Open the chat widget
    chatWidget.classList.remove('hidden');
    appendUserMsg(`🔍 Deep dive: ${text.length > 80 ? text.slice(0, 80) + '…' : text}`);
    await callChatSummarise(text);
}

async function callChatSummarise(text) {
    if (chatLoading) return;
    chatLoading = true;
    cwSendBtn.disabled = true;

    const loadingEl = appendAiLoading();

    try {
        const url = new URL(`${API}/chat_summarise`);
        url.searchParams.set('text', text);
        url.searchParams.set('newsletters', configuredNewsletters.join(',') || 'all');
        url.searchParams.set('session_id', CHAT_SESSION_ID);
        const res = await fetch(url);
        if (!res.ok) throw new Error(`Server ${res.status}`);
        const data = await res.json();
        loadingEl.remove();
        appendAiMsg(data.summary, `${data.sources_count} sources · ${data.urls_fetched} URLs`);
    } catch (e) {
        loadingEl.remove();
        appendAiMsg(`❌ Error: ${e.message}`);
    } finally {
        chatLoading = false;
        cwSendBtn.disabled = false;
    }
}

function appendUserMsg(text) {
    removeWelcome();
    const div = document.createElement('div');
    div.className = 'cw-msg cw-msg-user';
    div.innerHTML = `
    <div class="cw-bubble">${esc(text)}</div>
    <div class="cw-msg-time">${now()}</div>`;
    cwMessages.appendChild(div);
    cwMessages.scrollTop = cwMessages.scrollHeight;
    updateBadge();
}

function appendAiMsg(text, meta = '') {
    const div = document.createElement('div');
    div.className = 'cw-msg cw-msg-ai';
    div.innerHTML = `
    <div class="cw-bubble">${parseMarkdown(text)}</div>
    <div class="cw-msg-time">🤖 TechTracker AI${meta ? ' · ' + meta : ''} · ${now()}</div>`;
    cwMessages.appendChild(div);
    cwMessages.scrollTop = cwMessages.scrollHeight;
    updateBadge();
}

function appendAiLoading() {
    const div = document.createElement('div');
    div.className = 'cw-msg cw-msg-ai';
    div.innerHTML = `<div class="cw-loading-bubble"><span></span><span></span><span></span></div>`;
    cwMessages.appendChild(div);
    cwMessages.scrollTop = cwMessages.scrollHeight;
    return div;
}

function removeWelcome() {
    const w = cwMessages.querySelector('.cw-welcome');
    if (w) w.remove();
}

function updateBadge() {
    chatMsgCount++;
    if (chatWidget.classList.contains('hidden')) {
        chatBadge.textContent = chatMsgCount;
        chatBadge.classList.remove('hidden');
    }
}

// ═══════════════════════════════════════════════════════════════
// HISTORY TAB
// ═══════════════════════════════════════════════════════════════
function bindHistoryTab() {
    refreshHistoryBtn.addEventListener('click', loadHistory);
}

async function loadHistory() {
    historyContainer.innerHTML = `<div class="loading-state"><span class="spinner-md"></span><p>Loading…</p></div>`;
    try {
        const res = await fetch(`${API}/chat_history?limit=50`);
        const data = await res.json();
        historyContainer.innerHTML = '';

        if (!Array.isArray(data) || !data.length) {
            historyContainer.innerHTML = `<div class="history-empty"><p>No AI chat history yet.<br/>Summarise a news item to get started.</p></div>`;
            return;
        }

        data.forEach(item => {
            // Skip auto daily updates — only show manual AI summaries
            if (item.user_query?.startsWith('[Auto]')) return;

            const cards = document.createElement('div');
            cards.className = 'history-card';
            const tags = (item.newsletters_followed || '')
                .split(',').map(s => s.trim()).filter(Boolean)
                .map(t => `<span class="hcs-nl-tag">${esc(t)}</span>`).join('');

            cards.innerHTML = `
        <div class="hcs-top">
          <div class="hcs-query">${esc(item.user_query || '')}</div>
          <div class="hcs-time">${formatTime(item.created_at)}</div>
        </div>
        ${tags ? `<div class="hcs-nl-tags">${tags}</div>` : ''}
        <div class="hcs-toggle">
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 9 12 15 18 9"/></svg>
          Show response
        </div>
        <div class="hcs-body">${esc((item.agent_response || '').slice(0, 1000))}</div>`;

            const toggle = cards.querySelector('.hcs-toggle');
            const body = cards.querySelector('.hcs-body');
            toggle.addEventListener('click', () => {
                const open = body.classList.toggle('open');
                toggle.innerHTML = open
                    ? `<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="18 15 12 9 6 15"/></svg> Hide response`
                    : `<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 9 12 15 18 9"/></svg> Show response`;
            });
            historyContainer.appendChild(cards);
        });

        if (!historyContainer.children.length) {
            historyContainer.innerHTML = `<div class="history-empty"><p>No AI summaries yet. Use ✨ AI Summarise on a news item!</p></div>`;
        }
    } catch {
        historyContainer.innerHTML = `<div class="history-empty"><p>⚠️ Could not load history. Is the backend running?</p></div>`;
    }
}

// ═══════════════════════════════════════════════════════════════
// CONFIGURE TAB
// ═══════════════════════════════════════════════════════════════
function bindConfigureTab() {
    // Newsletters
    const addInput = () => {
        const v = configInput.value.replace(/,/g, '').trim();
        if (v) { addCfgNl(v); configInput.value = ''; }
    };
    configInput.addEventListener('keydown', e => {
        if (e.key === 'Enter' || e.key === ',') { e.preventDefault(); addInput(); }
    });
    configInput.addEventListener('blur', addInput);
    configAddBtn.addEventListener('click', addInput);

    document.querySelectorAll('.s-chip:not(.yt-chip)').forEach(c =>
        c.addEventListener('click', () => { addCfgNl(c.dataset.nl); updateSuggestionChips(); })
    );
    saveConfigBtn.addEventListener('click', saveConfig);
    lookbackSelect.addEventListener('change', () => localStorage.setItem(LS_LB, lookbackSelect.value));

    // YouTube channels
    const addYtInput = () => {
        const v = ytInput.value.trim();
        if (v) { addYtChannel(v); ytInput.value = ''; }
    };
    ytInput.addEventListener('keydown', e => {
        if (e.key === 'Enter') { e.preventDefault(); addYtInput(); }
    });
    ytInput.addEventListener('blur', addYtInput);
    ytAddBtn.addEventListener('click', addYtInput);

    document.querySelectorAll('.yt-chip').forEach(c =>
        c.addEventListener('click', () => addYtChannel(c.dataset.url))
    );
    saveYtBtn.addEventListener('click', saveYtChannels);
}

// YouTube channel helpers
function addYtChannel(url) {
    url = url.trim();
    if (!url || ytChannels.includes(url)) return;
    if (!url.startsWith('http')) { showToast('⚠️ Please enter a full YouTube URL'); return; }
    ytChannels.push(url);
    renderYtPills();
}

function removeYtChannel(url) {
    ytChannels = ytChannels.filter(u => u !== url);
    renderYtPills();
}

function renderYtPills() {
    if (!ytPills) return;
    ytPills.innerHTML = '';
    ytEmptyHint.classList.toggle('hidden', ytChannels.length > 0);
    ytChannels.forEach(url => {
        const label = url.split('@').pop()?.split('/')[0] || url;
        const el = document.createElement('div');
        el.className = 'cfg-pill cfg-pill-yt';
        el.innerHTML = `<span>▶️ ${esc(label)}</span><button class="cfg-pill-remove" title="Remove">×</button>`;
        el.querySelector('.cfg-pill-remove').onclick = () => removeYtChannel(url);
        ytPills.appendChild(el);
    });
}

function saveYtChannels() {
    localStorage.setItem(LS_YT, JSON.stringify(ytChannels));
    showToast('✅ YouTube channels saved!');
}

// ═══════════════════════════════════════════════════════════════
// BACKEND HEALTH
// ═══════════════════════════════════════════════════════════════
async function checkHealth() {
    try {
        const res = await fetch(`${API}/`, { signal: AbortSignal.timeout(4000) });
        if (res.ok) {
            statusDot.className = 'status-dot online';
            statusText.textContent = 'Backend online';
            return;
        }
    } catch { }
    statusDot.className = 'status-dot offline';
    statusText.textContent = 'Backend offline';
}

// ═══════════════════════════════════════════════════════════════
// MARKDOWN PARSER (for chat responses)
// ═══════════════════════════════════════════════════════════════
function parseMarkdown(md) {
    if (!md) return '';
    const lines = md.split('\n');
    let html = '', inUl = false;
    const closeUl = () => { if (inUl) { html += '</ul>'; inUl = false; } };

    // Format inline: bold, italic, code, AND hyperlinks [text](url)
    const fmt = t => t
        .replace(/\[([^\]]+)\]\((https?:\/\/[^)]+)\)/g, (_, linkText, url) =>
            `<a href="${url}" target="_blank" rel="noopener noreferrer">${esc(linkText)}</a>`)
        .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.+?)\*/g, '<em>$1</em>')
        .replace(/`(.+?)`/g, '<code>$1</code>')
        // Also auto-link bare https:// URLs that weren't already linked
        .replace(/(?<!href=")(https?:\/\/[^\s<>"']+)/g, url =>
            `<a href="${url}" target="_blank" rel="noopener noreferrer">${url}</a>`);

    for (const line of lines) {
        const t = line.trim();
        if (t.startsWith('## ')) { closeUl(); html += `<h2>${fmt(t.slice(3))}</h2>`; }
        else if (t.startsWith('### ')) { closeUl(); html += `<h3>${fmt(t.slice(4))}</h3>`; }
        else if (t.startsWith('> ')) { closeUl(); html += `<blockquote>${fmt(t.slice(2))}</blockquote>`; }
        else if (t.startsWith('- ') || t.startsWith('* ')) {
            if (!inUl) { html += '<ul>'; inUl = true; }
            html += `<li>${fmt(t.slice(2))}</li>`;
        }
        else if (t === '---') { closeUl(); html += '<hr>'; }
        else if (t === '') { closeUl(); }
        else { closeUl(); html += `<p>${fmt(t)}</p>`; }
    }
    closeUl();
    return html;
}

// ═══════════════════════════════════════════════════════════════
// UTILITIES
// ═══════════════════════════════════════════════════════════════
function esc(s) {
    return String(s ?? '')
        .replace(/&/g, '&amp;').replace(/</g, '&lt;')
        .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function nlLabel(nl) {
    return ({
        tldr: 'TLDR', alphasignal: 'AlphaSignal', therundown: 'The Rundown',
        bensbites: "Ben's Bites", hackernewsletter: 'Hacker NL',
        morningbrew: 'Morning Brew', stratechery: 'Stratechery',
    })[nl] || nl.charAt(0).toUpperCase() + nl.slice(1);
}

function formatTime(iso) {
    if (!iso) return '';
    try {
        const d = new Date(iso);
        return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
            + ' ' + d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
    } catch { return iso; }
}

function formatDateDisplay(dateStr) {
    try {
        return new Date(dateStr + 'T00:00:00').toLocaleDateString(undefined,
            { weekday: 'short', year: 'numeric', month: 'short', day: 'numeric' });
    } catch { return dateStr; }
}

function now() {
    return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

let toastTimer;
function showToast(msg, dur = 3500) {
    clearTimeout(toastTimer);
    toastEl.textContent = msg;
    toastEl.classList.remove('hidden');
    toastTimer = setTimeout(() => toastEl.classList.add('hidden'), dur);
}

// Keyboard shortcuts
document.addEventListener('keydown', e => {
    if (e.key === 'Escape') { hideHoverCard(); chatWidget.classList.add('hidden'); }
    if (e.ctrlKey && e.key === '1') switchTab('updates');
    if (e.ctrlKey && e.key === '2') switchTab('history');
    if (e.ctrlKey && e.key === '3') switchTab('calendar');
    if (e.ctrlKey && e.key === '4') switchTab('configure');
    if (e.ctrlKey && e.key === '5') switchTab('connectors');
});

// ═══════════════════════════════════════════════════════════════
// CONNECTORS TAB
// ═══════════════════════════════════════════════════════════════
function bindConnectorsTab() {
    loadConnectors();
    saveGmailCreds.addEventListener('click', () => {
        saveConnector('gmail', {
            client_id: gmailClientId.value,
            client_secret: gmailClientSecret.value,
            refresh_token: gmailRefreshToken.value
        });
    });
    saveYoutubeCreds.addEventListener('click', () => {
        saveConnector('youtube', { api_key: youtubeApiKey.value });
    });
}

async function loadConnectors() {
    try {
        const gmailRes = await fetch(`${API}/get_credentials?service=gmail`);
        const gmailData = await gmailRes.json();
        gmailClientId.value = gmailData.client_id || '';
        gmailClientSecret.value = gmailData.client_secret || '';
        gmailRefreshToken.value = gmailData.refresh_token || '';

        const ytRes = await fetch(`${API}/get_credentials?service=youtube`);
        const ytData = await ytRes.json();
        youtubeApiKey.value = ytData.api_key || '';
    } catch (e) {
        console.warn('Failed to load connectors:', e);
    }
}

async function saveConnector(service, credentials) {
    try {
        const res = await fetch(`${API}/save_credentials`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ service, credentials })
        });
        const data = await res.json();
        if (res.ok) showToast(`✅ ${data.message}`);
        else throw new Error(data.detail || 'Save failed');
    } catch (e) {
        showToast(`❌ ${e.message}`);
    }
}

// Start
init();

