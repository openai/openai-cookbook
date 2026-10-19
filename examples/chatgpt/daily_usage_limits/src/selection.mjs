const fail = code => Object.assign(new Error(code), { code });
const requireThat = (condition, code) => { if (!condition) throw fail(code); };
const validId = value => typeof value === 'string' && /^[A-Za-z0-9_-]{1,160}$/.test(value);
const sorted = values => [...new Set(values)].sort();
const same = (left, right) => JSON.stringify(left) === JSON.stringify(right);

export function normalizeEmail(value) {
  requireThat(typeof value === 'string', 'EMAIL_SELECTOR_INVALID');
  const email = value.trim().toLowerCase();
  requireThat(email.length <= 320 && /^[^\s@]+@[^\s@]+$/.test(email), 'EMAIL_SELECTOR_INVALID');
  return email;
}

export function normalizeCohort(cohort) {
  requireThat(['all', 'selected'].includes(cohort?.mode), 'COHORT_MODE_INVALID');
  const userIds = cohort.userIds ?? [];
  const emails = cohort.emails ?? [];
  const groupIds = cohort.groupIds ?? [];
  requireThat(Array.isArray(userIds) && userIds.every(validId), 'USER_IDS_INVALID');
  requireThat(Array.isArray(groupIds) && groupIds.every(validId), 'GROUP_IDS_INVALID');
  requireThat(Array.isArray(emails), 'EMAIL_SELECTORS_INVALID');
  const requested = { userIds: sorted(userIds), emails: sorted(emails.map(normalizeEmail)), groupIds: sorted(groupIds) };
  const count = requested.userIds.length + requested.emails.length + requested.groupIds.length;
  requireThat(cohort.mode === 'all' ? count === 0 : count > 0, 'COHORT_IDS_INVALID');
  return { mode: cohort.mode, requested };
}

function activeIds(values) {
  requireThat(Array.isArray(values) && values.every(validId) && new Set(values).size === values.length, 'ROSTER_INVALID');
  return [...values].sort();
}

export async function resolveCohort({ config, api }) {
  const { mode, requested } = normalizeCohort(config.cohort);
  const activeUserIds = activeIds(await api.listMembers());
  const active = new Set(activeUserIds);
  const selected = new Set(mode === 'all' ? activeUserIds : requested.userIds);
  const emailBindings = [];
  const groupBindings = [];
  for (const email of requested.emails) {
    requireThat(typeof api.resolveEmail === 'function', 'EMAIL_RESOLUTION_UNAVAILABLE');
    const member = await api.resolveEmail(email);
    requireThat(validId(member?.userId) && normalizeEmail(member.email) === email, 'EMAIL_RESOLUTION_MISMATCH');
    requireThat(active.has(member.userId), 'SELECTED_USER_NOT_ACTIVE_MEMBER');
    selected.add(member.userId);
    emailBindings.push({ email, userId: member.userId });
  }
  for (const groupId of requested.groupIds) {
    requireThat(typeof api.listGroupMembers === 'function', 'GROUP_RESOLUTION_UNAVAILABLE');
    const userIds = activeIds(await api.listGroupMembers(groupId));
    requireThat(userIds.length > 0, 'SELECTED_GROUP_EMPTY');
    requireThat(userIds.every(id => active.has(id)), 'SELECTED_USER_NOT_ACTIVE_MEMBER');
    for (const id of userIds) selected.add(id);
    groupBindings.push({ groupId, userIds });
  }
  const userIds = [...selected].sort();
  requireThat(userIds.length > 0 && (config.maxMembers == null || userIds.length <= config.maxMembers), 'COHORT_SIZE_INVALID');
  requireThat(userIds.every(id => active.has(id)), 'SELECTED_USER_NOT_ACTIVE_MEMBER');
  const selection = { version: 1, mode, requested, resolvedUserIds: userIds, emailBindings, groupBindings };
  return { userIds, activeUserIds, selection };
}

export function validateSavedSelection(config, enrollment) {
  const { mode, requested } = normalizeCohort(config.cohort);
  const ids = enrollment.members.map(member => member.userId).sort();
  const selection = enrollment.selection;
  if (!selection) {
    requireThat(requested.emails.length === 0 && requested.groupIds.length === 0, 'COHORT_SELECTION_REQUIRED');
    if (mode === 'selected') requireThat(same(ids, requested.userIds), 'COHORT_REVIEW_MISMATCH');
    return;
  }
  requireThat(selection.version === 1 && selection.mode === mode && same(selection.requested, requested) &&
    same(selection.resolvedUserIds, ids), 'COHORT_REVIEW_MISMATCH');
  requireThat(Array.isArray(selection.emailBindings) && Array.isArray(selection.groupBindings), 'COHORT_REVIEW_MISMATCH');
  requireThat(same(selection.emailBindings.map(item => item.email), requested.emails) &&
    selection.emailBindings.every(item => validId(item.userId)), 'COHORT_REVIEW_MISMATCH');
  requireThat(same(selection.groupBindings.map(item => item.groupId), requested.groupIds) &&
    selection.groupBindings.every(item => Array.isArray(item.userIds) && item.userIds.length > 0 &&
      item.userIds.every(validId) && same(item.userIds, sorted(item.userIds))), 'COHORT_REVIEW_MISMATCH');
  if (mode === 'selected') {
    const resolved = sorted([...requested.userIds, ...selection.emailBindings.map(item => item.userId),
      ...selection.groupBindings.flatMap(item => item.userIds)]);
    requireThat(same(resolved, ids), 'COHORT_REVIEW_MISMATCH');
  }
}

export async function validateCurrentCohort(config, enrollment, api, { restore = false } = {}) {
  validateSavedSelection(config, enrollment);
  const { mode, requested } = normalizeCohort(config.cohort);
  if (restore || mode === 'all' || (!requested.emails.length && !requested.groupIds.length)) {
    const activeUserIds = activeIds(await api.listMembers());
    return { userIds: mode === 'all' && !restore ? activeUserIds : enrollment.members.map(member => member.userId).sort(),
      activeUserIds, selection: enrollment.selection };
  }
  const current = await resolveCohort({ config, api });
  requireThat(same(current.selection, enrollment.selection), 'COHORT_SELECTION_CHANGED');
  return current;
}
