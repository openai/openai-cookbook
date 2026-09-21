// Public ChatGPT Admin API only. No credentials, response bodies, or names are logged.
const BASE_URL = 'https://api.chatgpt.com/v1';
const DAY_MS = 86400000;
const HISTORY_MAX_AGE_MS = 60000;
const SOURCES = new Set([
  'individual_override', 'workspace_default', 'group_default', 'role_based_personal_budget',
]);

const fail = (code, details = {}) => Object.assign(new Error(code), { code, ...details });
const validId = value => typeof value === 'string' && /^[A-Za-z0-9_-]{1,160}$/.test(value);
const validUnit = unit => unit === 'credit' || unit === 'usd';
const clone = value => structuredClone(value);

function normalizedEmail(value) {
  if (typeof value !== 'string') throw fail('EMAIL_INVALID');
  const email = value.trim().toLowerCase();
  if (!/^[^\s@]+@[^\s@]+$/.test(email)) throw fail('EMAIL_INVALID');
  return email;
}

function directoryMember(row) {
  if (!row || row.object !== 'workspace.user' || !validId(row.id) ||
      !Object.hasOwn(row, 'email') || (row.email !== null && typeof row.email !== 'string')) {
    throw fail('MEMBER_PAGE_INCONSISTENT');
  }
  if (row.email !== null) normalizedEmail(row.email);
  return { userId: row.id, email: row.email };
}

// JSON numeric counters are approximate. Reject unsafe magnitudes, then round upward
// to millionths. Policy arithmetic subsequently uses decimal strings, never floats.
function decimal(value, { usage = false } = {}) {
  if (typeof value === 'number') {
    if (!Number.isFinite(value) || value < 0 || value > Number.MAX_SAFE_INTEGER / 1e6) {
      throw fail('AMOUNT_PRECISION_UNSAFE');
    }
    value = String(value);
    if (/e/i.test(value)) {
      const [coefficient, power] = value.toLowerCase().split('e');
      const [whole, fraction = ''] = coefficient.split('.');
      const digits = whole + fraction;
      const position = whole.length + Number(power);
      value = position <= 0 ? '0.' + '0'.repeat(-position) + digits :
        position >= digits.length ? digits + '0'.repeat(position - digits.length) :
          digits.slice(0, position) + '.' + digits.slice(position);
    }
  }
  if (typeof value !== 'string' || !/^\d+(?:\.\d+)?$/.test(value) || value.length > 80) {
    throw fail('AMOUNT_UNAVAILABLE');
  }
  let [whole, fraction = ''] = value.split('.');
  whole = BigInt(whole).toString();
  if (usage && fraction.length > 6) {
    let scaled = BigInt(whole) * 1000000n + BigInt(fraction.slice(0, 6));
    if (/[1-9]/.test(fraction.slice(6))) scaled += 1n;
    whole = (scaled / 1000000n).toString();
    fraction = (scaled % 1000000n).toString().padStart(6, '0');
  }
  fraction = fraction.replace(/0+$/, '');
  return fraction ? `${whole}.${fraction}` : whole;
}

function capAmount(value, unit) {
  if (!validUnit(unit)) throw fail('UNIT_UNAVAILABLE');
  const amount = decimal(value);
  if (unit === 'credit' && (amount.includes('.') || BigInt(amount) > 2147483647n)) {
    throw fail('CREDIT_CAP_OUT_OF_RANGE');
  }
  if (unit === 'usd' && (amount.split('.')[1]?.length ?? 0) > 2) {
    throw fail('USD_CAP_PRECISION_INVALID');
  }
  return amount;
}

function normalizedRule(rule, unit, source) {
  if (!rule || !['limited', 'unlimited'].includes(rule.type)) throw fail('CAP_UNAVAILABLE');
  const knownFields = new Set(['type', 'limit', 'limit_amount', 'limit_expires_at']);
  if (Object.keys(rule).some(key => !knownFields.has(key))) throw fail('UNKNOWN_CAP_FIELD');
  const cap = { type: rule.type, unit, ...(source ? { source } : {}) };
  if (rule.type === 'limited') {
    if (rule.limit_amount != null) {
      if (Object.keys(rule.limit_amount).some(key => !['amount', 'unit'].includes(key))) {
        throw fail('UNKNOWN_CAP_FIELD');
      }
      if (rule.limit_amount.unit !== unit) throw fail('CAP_UNIT_MISMATCH');
      if (rule.limit != null) throw fail('AMBIGUOUS_CAP_AMOUNT');
      cap.amount = capAmount(rule.limit_amount.amount, unit);
    } else {
      if (unit !== 'credit' || !Number.isSafeInteger(rule.limit)) throw fail('CAP_AMOUNT_UNAVAILABLE');
      cap.amount = capAmount(String(rule.limit), unit);
    }
  } else if (rule.limit != null || rule.limit_amount != null) {
    throw fail('AMBIGUOUS_CAP_AMOUNT');
  }
  if (rule.limit_expires_at != null) {
    if (!Number.isFinite(Date.parse(rule.limit_expires_at))) throw fail('CAP_EXPIRY_INVALID');
    cap.expiresAt = new Date(rule.limit_expires_at).toISOString();
  }
  return cap;
}

function overrideRule(override) {
  if (override === null || (Array.isArray(override) && override.length === 0)) return null;
  if (!Array.isArray(override) || override.length !== 1) throw fail('OVERRIDE_NOT_RESTORABLE');
  return override[0];
}

function normalizeSettings(settings, unit) {
  if (!settings || !Object.hasOwn(settings, 'override')) throw fail('BEFORE_STATE_UNAVAILABLE');
  const rule = overrideRule(settings.override);
  const effective = settings.effective;
  if (!SOURCES.has(effective?.source?.kind)) throw fail('CAP_SOURCE_UNAVAILABLE');
  if (Object.keys(effective).some(key => !['limit', 'source'].includes(key)) ||
      (settings.inherited && (Object.keys(settings.inherited).some(key => !['limit', 'source'].includes(key)) ||
        !SOURCES.has(settings.inherited.source?.kind)))) throw fail('UNKNOWN_EFFECTIVE_FIELD');
  if ((rule !== null) !== (effective.source.kind === 'individual_override')) {
    throw fail('OVERRIDE_SOURCE_MISMATCH');
  }
  const normalized = {
    override: rule ? normalizedRule(rule, unit) : null,
    effective: { limit: normalizedRule(effective.limit, unit), source: effective.source },
    inherited: settings.inherited ? {
      limit: normalizedRule(settings.inherited.limit, unit), source: settings.inherited.source,
    } : null,
  };
  if (rule && JSON.stringify(normalized.override) !== JSON.stringify(normalized.effective.limit)) {
    throw fail('OVERRIDE_EFFECTIVE_MISMATCH');
  }
  return normalized;
}

function stable(value) {
  if (Array.isArray(value)) return value.map(stable);
  if (value && typeof value === 'object') {
    return Object.fromEntries(Object.keys(value).sort().map(key => [key, stable(value[key])]));
  }
  return value;
}

// Restore comparisons accept equivalent decimal encodings and null/[] inheritance,
// but retain source identifiers and inherited fallback configuration.
export function settingsEquivalent(left, right, unit) {
  return JSON.stringify(stable(normalizeSettings(left, unit))) ===
    JSON.stringify(stable(normalizeSettings(right, unit)));
}

export function matchesTarget(snapshot, { amount, unit, periodEnd }) {
  if (snapshot.unit !== unit || !Number.isFinite(Date.parse(periodEnd))) return false;
  const normalized = normalizeSettings(snapshot.settings, unit);
  const rule = normalized.override;
  return rule?.type === 'limited' && rule.amount === capAmount(amount, unit) &&
    normalized.effective.source.kind === 'individual_override' &&
    Date.parse(rule.expiresAt) === Date.parse(periodEnd) &&
    snapshot.cap.type === 'limited' && snapshot.cap.amount === rule.amount &&
    snapshot.cap.source === 'individual_override' &&
    Date.parse(snapshot.cap.expiresAt) === Date.parse(periodEnd);
}

export function createAdminApi({ apiKey, workspaceId, userIds = [], allowWrites = false,
  fetchImpl = globalThis.fetch, clock = () => new Date().toISOString(), timeoutMs = 15000,
  maxPages = 1000, maxRows = 100000, maxRetryDelayMs = 5000,
  remainingTimeMs = () => Infinity,
  sleep = ms => new Promise(resolve => setTimeout(resolve, ms)) }) {
  if (typeof apiKey !== 'string' || !apiKey.trim()) throw fail('ADMIN_KEY_REQUIRED');
  if (!validId(workspaceId) || !Array.isArray(userIds) || !userIds.every(validId) ||
      new Set(userIds).size !== userIds.length) throw fail('EXPLICIT_IDENTITY_ALLOWLIST_REQUIRED');
  if (![maxPages, maxRows, timeoutMs].every(value => Number.isSafeInteger(value) && value > 0)) {
    throw fail('ADAPTER_BOUNDS_INVALID');
  }
  const allowedUsers = new Set(userIds);
  const workspacePath = `/manage/workspaces/${encodeURIComponent(workspaceId)}`;
  const userPath = userId => {
    if (!allowedUsers.has(userId)) throw fail('IDENTITY_NOT_ALLOWLISTED');
    return `${workspacePath}/usage_limits/users/${encodeURIComponent(userId)}`;
  };
  const now = () => {
    const value = clock();
    if (!Number.isFinite(Date.parse(value))) throw fail('CLOCK_INVALID');
    return new Date(value).toISOString();
  };

  async function request(path, method = 'GET', body) {
    const remaining = remainingTimeMs();
    if (typeof remaining !== 'number' || Number.isNaN(remaining) ||
        remaining <= 5000 || (method === 'PATCH' && remaining < 50000)) {
      throw fail('API_TIME_BUDGET_EXHAUSTED', { retryable: true, outcomeUnknown: false });
    }
    let response;
    try {
      response = await fetchImpl(BASE_URL + path, {
        method, redirect: 'error', signal: AbortSignal.timeout(Math.min(timeoutMs, Math.floor(remaining - 5000))),
        headers: { Authorization: `Bearer ${apiKey}`, 'Content-Type': 'application/json' },
        ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      });
    } catch {
      throw fail(method === 'PATCH' ? 'WRITE_OUTCOME_UNKNOWN' : 'API_READ_TRANSPORT_FAILED',
        { retryable: true, outcomeUnknown: method === 'PATCH' });
    }
    if (!response.ok) {
      const retryAfter = response.headers.get('retry-after');
      const retryAfterMs = retryAfter && /^\d+$/.test(retryAfter) ? Number(retryAfter) * 1000 :
        retryAfter && Number.isFinite(Date.parse(retryAfter)) ?
          Math.max(0, Date.parse(retryAfter) - Date.parse(now())) : null;
      // Response bodies can contain private workspace information. Do not retain them.
      throw fail(`ADMIN_HTTP_${response.status}`, {
        status: response.status, retryAfterMs, conflict: response.status === 409,
        retryable: response.status === 429 || response.status >= 500,
        outcomeUnknown: method === 'PATCH' && response.status >= 500,
      });
    }
    try { return await response.json(); } catch {
      throw fail(method === 'PATCH' ? 'WRITE_OUTCOME_UNKNOWN' : 'API_JSON_UNAVAILABLE',
        { retryable: true, outcomeUnknown: method === 'PATCH' });
    }
  }

  async function verifyWorkspace() {
    const workspace = await request(`${workspacePath}/usage_limits/workspace`);
    if (workspace.id !== workspaceId) throw fail('WORKSPACE_READBACK_MISMATCH');
  }

  function verifyUser(resource, userId) {
    if (resource?.id !== userId || resource.account_user_id !== `${userId}__${workspaceId}`) {
      throw fail('USER_READBACK_MISMATCH');
    }
  }

  function settingsFrom(user) {
    if (!Object.hasOwn(user, 'override_monthly_usage_limit')) throw fail('BEFORE_STATE_UNAVAILABLE');
    return clone({ override: user.override_monthly_usage_limit,
      effective: user.effective_monthly_usage_limit,
      inherited: user.inherited_monthly_usage_limit ?? null });
  }

  async function readSnapshot(userId) {
    const path = userPath(userId);
    await verifyWorkspace();
    const user = await request(path);
    const monthly = await request(`${path}/monthly-usage`);
    verifyUser(user, userId);
    verifyUser(monthly, userId);
    const unit = monthly.current_month_usage_unit;
    if (!validUnit(unit)) throw fail('USAGE_UNIT_UNAVAILABLE');
    const settings = settingsFrom(user);
    normalizeSettings(settings, unit);
    const cap = normalizedRule(settings.effective.limit, unit, settings.effective.source.kind);
    const currentCap = normalizedRule(monthly.effective_monthly_usage_limit, unit, cap.source);
    if (JSON.stringify(cap) !== JSON.stringify(currentCap)) throw fail('CAP_CHANGED_BETWEEN_READS');
    const latest = await request(path);
    verifyUser(latest, userId);
    if (!settingsEquivalent(settings, settingsFrom(latest), unit)) throw fail('SETTINGS_CHANGED_BETWEEN_READS');
    return { workspaceId, userId, unit, usage: decimal(monthly.current_month_usage, { usage: true }),
      cap, settings, observedAt: now() };
  }

  function writeBoundary(unit, periodEnd, notAfter) {
    if (!allowWrites) throw fail('WRITES_DISABLED');
    if (!validUnit(unit)) throw fail('UNIT_UNAVAILABLE');
    const currentTime = Date.parse(now());
    if (notAfter !== undefined && (typeof notAfter !== 'string' ||
        !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?Z$/.test(notAfter) ||
        !Number.isFinite(Date.parse(notAfter)) || Date.parse(notAfter) <= currentTime)) {
      throw fail('OPERATION_REVIEW_EXPIRED');
    }
    if (!Number.isFinite(Date.parse(periodEnd)) || Date.parse(periodEnd) - currentTime < 30000) {
      throw fail('WRITE_PERIOD_EXPIRED');
    }
  }

  async function listMemberDirectory() {
    await verifyWorkspace();
    const members = new Map();
    let after;
    for (let page = 0; page < maxPages; page += 1) {
      const query = new URLSearchParams({ limit: '1000', ...(after ? { after } : {}) });
      const result = await request(`${workspacePath}/users?${query}`);
      if (!result || result.object !== 'list' || !Array.isArray(result.data) || typeof result.has_more !== 'boolean' ||
          result.first_id !== (result.data[0]?.id ?? null) || result.last_id !== (result.data.at(-1)?.id ?? null)) {
        throw fail('MEMBER_PAGE_INVALID');
      }
      for (const row of result.data) {
        const member = directoryMember(row);
        if (members.has(member.userId)) throw fail('MEMBER_PAGE_INCONSISTENT');
        members.set(member.userId, member);
        if (members.size > maxRows) throw fail('MEMBER_ROW_BOUND_EXCEEDED');
      }
      if (!result.has_more) return [...members.values()].sort((left, right) =>
        left.userId < right.userId ? -1 : left.userId > right.userId ? 1 : 0);
      if (!result.data.length || result.last_id === after) throw fail('MEMBER_CURSOR_INVALID');
      after = result.last_id;
    }
    throw fail('MEMBER_PAGE_BOUND_EXCEEDED');
  }

  async function readExactEmail(email) {
    const query = new URLSearchParams({ email, limit: '1' });
    const result = await request(`${workspacePath}/users?${query}`);
    if (!result || result.object !== 'list' || !Array.isArray(result.data) || result.has_more !== false) {
      throw fail('EMAIL_LOOKUP_INVALID');
    }
    if (result.data.length > 1) throw fail('EMAIL_MEMBER_AMBIGUOUS');
    if (result.first_id !== (result.data[0]?.id ?? null) || result.last_id !== (result.data.at(-1)?.id ?? null)) {
      throw fail('EMAIL_LOOKUP_INVALID');
    }
    if (!result.data.length) throw fail('EMAIL_MEMBER_NOT_FOUND');
    const member = directoryMember(result.data[0]);
    if (member.email === null || normalizedEmail(member.email) !== email) throw fail('EMAIL_MEMBER_MISMATCH');
    return member;
  }

  let historyCache;
  function historyIsFresh(observedAt) {
    const age = Date.parse(now()) - Date.parse(observedAt);
    return age >= 0 && age <= HISTORY_MAX_AGE_MS;
  }

  async function fetchHistoryIndex(startMs, endMs) {
    await verifyWorkspace();
    // The API reports observations with eventual updates and no finalized watermark.
    // Age starts before the first page so pagination cannot refresh earlier rows.
    const observedAt = now();
    const byUser = new Map();
    const seenCursors = new Set();
    let cursor;
    let rows = 0;
    for (let page = 0; page < maxPages; page += 1) {
      const query = new URLSearchParams({ start_time: String(startMs / 1000),
        end_time: String(endMs / 1000), limit: '30000', ...(cursor ? { page: cursor } : {}) });
      const result = await request(`/analytics/workspaces/${encodeURIComponent(workspaceId)}/usage?${query}`);
      if (!result || result.object !== 'page' || !Array.isArray(result.data) || typeof result.has_more !== 'boolean') {
        throw fail('HISTORY_PAGE_INVALID');
      }
      rows += result.data.length;
      if (rows > maxRows) throw fail('HISTORY_ROW_BOUND_EXCEEDED');
      for (const row of result.data) {
        if (!row || row.object !== 'workspace.usage.result' || !validId(row.user_id)) throw fail('HISTORY_SCOPE_INVALID');
        if (!byUser.has(row.user_id)) byUser.set(row.user_id, []);
        byUser.get(row.user_id).push(row);
      }
      if (!result.has_more) {
        if (!historyIsFresh(observedAt)) throw fail('HISTORY_STALE');
        return { byUser, observedAt };
      }
      if (typeof result.next_page !== 'string' || !result.next_page || seenCursors.has(result.next_page)) {
        throw fail('HISTORY_CURSOR_INVALID');
      }
      cursor = result.next_page;
      seenCursors.add(cursor);
    }
    throw fail('HISTORY_PAGE_BOUND_EXCEEDED');
  }

  async function readHistoryIndex(startMs, endMs) {
    if (historyCache?.startMs === startMs && historyCache.endMs === endMs) {
      if (historyCache.pending) return historyCache.pending;
      if (historyIsFresh(historyCache.result.observedAt)) return historyCache.result;
    }
    // Retain one range only. Each caller holds its own promise if another range
    // replaces this slot while its pages are still loading.
    const entry = { startMs, endMs };
    historyCache = entry;
    entry.pending = fetchHistoryIndex(startMs, endMs).then(result => {
      if (historyCache === entry) {
        entry.result = result;
        entry.pending = null;
      }
      return result;
    }, error => {
      if (historyCache === entry) historyCache = undefined;
      throw error;
    });
    return entry.pending;
  }

  return {
    readSnapshot,
    listMemberDirectory,
    async listMembers() {
      return (await listMemberDirectory()).map(member => member.userId);
    },
    async resolveEmail(value) {
      const email = normalizedEmail(value);
      await verifyWorkspace();
      return readExactEmail(email);
    },
    async assertMemberActive(userId) {
      userPath(userId); // Enforce the same explicit identity allowlist as cap operations.
      await verifyWorkspace();
      const resource = await request(`${workspacePath}/users/${encodeURIComponent(userId)}`);
      const member = directoryMember(resource);
      if (member.userId !== userId) throw fail('USER_READBACK_MISMATCH');
      // Point GET establishes an accepted member, not active status. Confirm through
      // the documented active-member collection before returning an active identity.
      if (member.email !== null) {
        let active;
        try { active = await readExactEmail(normalizedEmail(member.email)); }
        catch (error) {
          if (error.code === 'EMAIL_MEMBER_NOT_FOUND') throw fail('MEMBER_NOT_ACTIVE');
          throw error;
        }
        if (active.userId !== userId) throw fail('MEMBER_NOT_ACTIVE');
        return active;
      }
      const active = (await listMemberDirectory()).find(item => item.userId === userId);
      if (!active) throw fail('MEMBER_NOT_ACTIVE');
      return active;
    },
    async listGroupMembers(groupId) {
      if (!validId(groupId)) throw fail('GROUP_ID_INVALID');
      await verifyWorkspace();
      const groupPath = `${workspacePath}/groups/${encodeURIComponent(groupId)}`;
      const group = await request(groupPath);
      if (group?.id !== groupId || group.workspace_id !== workspaceId ||
          (group.object !== undefined && group.object !== 'directory.workspace.group')) {
        throw fail('GROUP_READBACK_MISMATCH');
      }
      const ids = new Set();
      const activeIds = [];
      const seenCursors = new Set();
      let cursor;
      for (let page = 0; page < maxPages; page += 1) {
        const query = new URLSearchParams({ limit: '100', order: 'asc', ...(cursor ? { cursor } : {}) });
        const result = await request(`${groupPath}/users?${query}`);
        if (!result || (result.object !== undefined && result.object !== 'list') || !Array.isArray(result.data) ||
            typeof result.has_more !== 'boolean' || !Object.hasOwn(result, 'cursor') ||
            (result.cursor !== null && typeof result.cursor !== 'string') ||
            result.last_id !== (result.data.at(-1)?.id ?? null)) throw fail('GROUP_MEMBER_PAGE_INVALID');
        for (const row of result.data) {
          if (!row || (row.object !== undefined && row.object !== 'compliance.workspace.user') ||
              !validId(row.id) || ids.has(row.id)) throw fail('GROUP_MEMBER_PAGE_INCONSISTENT');
          if (!['active', 'deactivated'].includes(row.status)) throw fail('GROUP_MEMBER_STATUS_INVALID');
          ids.add(row.id);
          if (ids.size > maxRows) throw fail('GROUP_MEMBER_ROW_BOUND_EXCEEDED');
          if (row.status === 'active') activeIds.push(row.id);
        }
        if (!result.has_more) return activeIds.sort();
        if (!result.data.length || typeof result.cursor !== 'string' || !result.cursor || seenCursors.has(result.cursor)) {
          throw fail('GROUP_MEMBER_CURSOR_INVALID');
        }
        cursor = result.cursor;
        seenCursors.add(cursor);
      }
      throw fail('GROUP_MEMBER_PAGE_BOUND_EXCEEDED');
    },
    async setCap(userId, { amount, unit, periodEnd, expectedSettings, expectedUsage, notAfter }) {
      const path = userPath(userId);
      writeBoundary(unit, periodEnd, notAfter);
      const normalized = capAmount(amount, unit);
      const before = await readSnapshot(userId);
      if (before.unit !== unit) throw fail('WRITE_UNIT_MISMATCH');
      if (expectedSettings && !settingsEquivalent(expectedSettings, before.settings, unit)) {
        throw fail('SETTINGS_CHANGED_BEFORE_WRITE');
      }
      if (expectedUsage !== undefined && decimal(expectedUsage, { usage: true }) !== before.usage) {
        throw fail('USAGE_CHANGED_BEFORE_WRITE');
      }
      writeBoundary(unit, periodEnd, notAfter);
      // The engine owns authorization and the journal. The API sets the absolute
      // cap, computes its expiry, and provides no conditional-write parameter.
      await request(path, 'PATCH', { override_monthly_usage_limit: {
        type: 'limited', limit_amount: { amount: normalized, unit }, temporary: true,
      } });
    },
    async restore(userId, { settings, unit, periodEnd, expectedSettings, notAfter }) {
      const path = userPath(userId);
      writeBoundary(unit, periodEnd, notAfter);
      normalizeSettings(settings, unit);
      const savedRule = overrideRule(settings.override);
      let restoredRule = null;
      if (savedRule) {
        const supported = new Set(['type', 'limit', 'limit_amount', 'limit_expires_at']);
        if (Object.keys(savedRule).some(key => !supported.has(key))) throw fail('OVERRIDE_NOT_RESTORABLE');
        const normalized = normalizedRule(savedRule, unit);
        restoredRule = { type: normalized.type };
        if (normalized.type === 'limited') {
          // Preserve the original stored representation, including legacy credits.
          if (savedRule.limit_amount != null) restoredRule.limit_amount = clone(savedRule.limit_amount);
          else restoredRule.limit = savedRule.limit;
        }
        if (normalized.expiresAt) {
          if (Date.parse(normalized.expiresAt) !== Date.parse(periodEnd)) throw fail('TEMPORARY_EXPIRY_NOT_RESTORABLE');
          restoredRule.temporary = true;
        }
      }
      const before = await readSnapshot(userId);
      if (before.unit !== unit) throw fail('WRITE_UNIT_MISMATCH');
      if (expectedSettings && !settingsEquivalent(expectedSettings, before.settings, unit)) {
        throw fail('SETTINGS_CHANGED_BEFORE_WRITE');
      }
      writeBoundary(unit, periodEnd, notAfter);
      await request(path, 'PATCH', { override_monthly_usage_limit: restoredRule });
    },
    async readHistory(userId, { start, end, unit }) {
      userPath(userId);
      if (!validUnit(unit)) throw fail('UNIT_UNAVAILABLE');
      const startMs = Date.parse(start);
      const endMs = Date.parse(end);
      if (![startMs, endMs].every(value => Number.isFinite(value) && value % DAY_MS === 0) ||
          startMs >= endMs || endMs - startMs > 366 * DAY_MS || endMs > Date.parse(now())) {
        throw fail('HISTORY_WINDOW_INVALID');
      }
      const history = await readHistoryIndex(startMs, endMs);
      if (!historyIsFresh(history.observedAt)) throw fail('HISTORY_STALE');
      const amounts = new Map();
      for (const row of history.byUser.get(userId) ?? []) {
        const dateMs = row.start_time * 1000;
        if (!Number.isSafeInteger(row.start_time) || dateMs < startMs || dateMs >= endMs ||
            dateMs % DAY_MS !== 0 || row.end_time !== row.start_time + DAY_MS / 1000) {
          throw fail('HISTORY_ROW_BOUNDARY_INVALID');
        }
        if (row.actor?.type !== 'ACCOUNT_USER' || row.actor.user_id !== userId) throw fail('HISTORY_ACTOR_MISMATCH');
        const date = new Date(dateMs).toISOString().slice(0, 10);
        if (amounts.has(date)) throw fail('HISTORY_DUPLICATE_DAY');
        const value = unit === 'credit' ? row.totals?.credits : row.totals?.cost_usd;
        const other = unit === 'credit' ? row.totals?.cost_usd : row.totals?.credits;
        if (other != null) throw fail('HISTORY_UNIT_TRANSITION');
        amounts.set(date, decimal(value, { usage: true }));
      }
      const days = [];
      for (let dateMs = startMs; dateMs < endMs; dateMs += DAY_MS) {
        const date = new Date(dateMs).toISOString().slice(0, 10);
        if (!amounts.has(date)) throw fail('HISTORY_DAY_UNAVAILABLE');
        days.push({ date, amount: amounts.get(date) });
      }
      return { workspaceId, userId, unit, start: new Date(startMs).toISOString(),
        end: new Date(endMs).toISOString(), observedAt: history.observedAt, days, semantics: 'observed' };
    },
    async waitBeforeRetry(attempt, error = {}) {
      const delay = Math.max(100 * 2 ** Math.min(Math.max(attempt - 1, 0), 5), error.retryAfterMs ?? 0);
      if (!Number.isFinite(delay) || delay > maxRetryDelayMs) throw fail('RETRY_DELAY_REQUIRES_LATER_RUN');
      await sleep(delay);
    },
  };
}
