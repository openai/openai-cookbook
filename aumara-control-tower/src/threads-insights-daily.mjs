import { Resend } from '@resend/node';

const required = [
  'THREADS_ACCESS_TOKEN',
  'THREADS_USER_ID',
  'AIRTABLE_PAT',
  'AIRTABLE_BASE_ID',
  'AIRTABLE_THREADS_TABLE_ID',
];

for (const key of required) {
  if (!process.env[key]) {
    throw new Error(`Missing required environment variable: ${key}`);
  }
}

const GRAPH = process.env.THREADS_GRAPH_BASE || 'https://graph.threads.net/v1.0';
const sprintStart = process.env.THREADS_SPRINT_START || '2026-06-26';
const sprintEnd = process.env.THREADS_SPRINT_END || '2026-07-25';
const targetViews = Number(process.env.THREADS_TARGET_VIEWS || 100000);

function unix(date, endOfDay = false) {
  const suffix = endOfDay ? 'T23:59:59Z' : 'T00:00:00Z';
  return Math.floor(new Date(`${date}${suffix}`).getTime() / 1000);
}

async function getJson(url) {
  const response = await fetch(url);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(`HTTP ${response.status} for ${url}: ${JSON.stringify(body)}`);
  }
  return body;
}

function withToken(path, params = {}) {
  const url = new URL(`${GRAPH}${path}`);
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') {
      url.searchParams.set(key, String(value));
    }
  }
  url.searchParams.set('access_token', process.env.THREADS_ACCESS_TOKEN);
  return url.toString();
}

async function fetchAllThreads() {
  let url = withToken(`/${process.env.THREADS_USER_ID}/threads`, {
    fields: 'id,text,timestamp,media_type,permalink',
    since: unix(sprintStart),
    until: unix(sprintEnd, true),
    limit: 100,
  });

  const rows = [];
  while (url) {
    const page = await getJson(url);
    rows.push(...(page.data || []));
    url = page.paging?.next || null;
  }
  return rows;
}

async function fetchMediaInsights(mediaId) {
  const body = await getJson(withToken(`/${mediaId}/insights`, {
    metric: 'views,likes,replies,reposts,quotes,shares',
  }));

  const metrics = {};
  for (const item of body.data || []) {
    const value = item.total_value?.value ?? item.values?.[0]?.value ?? 0;
    metrics[item.name] = Number(value || 0);
  }
  return metrics;
}

async function fetchUserInsights() {
  const body = await getJson(withToken(`/${process.env.THREADS_USER_ID}/threads_insights`, {
    metric: 'views,likes,replies,reposts,quotes,followers_count',
    since: unix(sprintStart),
    until: unix(sprintEnd, true),
  }));

  const metrics = {};
  for (const item of body.data || []) {
    if (item.name === 'views' && Array.isArray(item.values)) {
      metrics.profile_views = item.values.reduce((sum, row) => sum + Number(row.value || 0), 0);
    } else {
      metrics[item.name] = Number(item.total_value?.value ?? item.values?.[0]?.value ?? 0);
    }
  }
  return metrics;
}

async function airtableCreate(fields) {
  const endpoint = `https://api.airtable.com/v0/${process.env.AIRTABLE_BASE_ID}/${process.env.AIRTABLE_THREADS_TABLE_ID}`;
  const response = await fetch(endpoint, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${process.env.AIRTABLE_PAT}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ records: [{ fields }], typecast: true }),
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(`Airtable HTTP ${response.status}: ${JSON.stringify(body)}`);
  }
  return body;
}

async function sendSummary(summary) {
  if (!process.env.RESEND_API_KEY) return { skipped: true };
  const resend = new Resend(process.env.RESEND_API_KEY);
  return resend.emails.send({
    from: process.env.AUMARA_MAIL_FROM || 'AUMARA El Cid <onboarding@resend.dev>',
    to: process.env.AUMARA_TEST_TO || 'elcidspain@gmail.com',
    replyTo: process.env.AUMARA_MAIL_REPLY_TO || 'elcidspain@gmail.com',
    subject: `Threads Metrics — ${summary.date}`,
    text: summary.text,
  });
}

const threads = await fetchAllThreads();
const enriched = [];
for (const thread of threads) {
  try {
    enriched.push({ ...thread, insights: await fetchMediaInsights(thread.id) });
  } catch (error) {
    enriched.push({ ...thread, insights: {}, insight_error: error.message });
  }
}

const contentViews = enriched.reduce((sum, row) => sum + Number(row.insights.views || 0), 0);
const user = await fetchUserInsights();
const remainingViews = Math.max(0, targetViews - contentViews);
const today = new Date();
const end = new Date(`${sprintEnd}T23:59:59Z`);
const remainingDays = Math.max(1, Math.ceil((end - today) / 86400000));
const requiredDailyPace = Math.ceil(remainingViews / remainingDays);
const topPosts = [...enriched]
  .sort((a, b) => Number(b.insights.views || 0) - Number(a.insights.views || 0))
  .slice(0, 5);

const capturedAt = new Date().toISOString();
const checkpointName = `${capturedAt.slice(0, 10)} Threads API checkpoint`;
const notes = [
  `Sprint: ${sprintStart}–${sprintEnd}`,
  `Content views: ${contentViews}`,
  `Profile views (separate metric): ${user.profile_views || 0}`,
  `Remaining to ${targetViews}: ${remainingViews}`,
  `Required daily pace: ${requiredDailyPace}`,
  `Threads read: ${threads.length}`,
  `Top posts: ${topPosts.map((p) => `${p.insights.views || 0} — ${(p.text || '').replace(/\s+/g, ' ').slice(0, 90)}`).join(' | ')}`,
].join('\n');

await airtableCreate({
  Checkpoint: checkpointName,
  'Captured at': capturedAt,
  Source: 'Threads API',
  'Recent views': contentViews,
  Followers: Number(user.followers_count || 0),
  Verified: true,
  Notes: notes,
});

const summary = {
  date: capturedAt.slice(0, 10),
  text: [
    `Threads API checkpoint`,
    `Content views in sprint: ${contentViews}/${targetViews}`,
    `Remaining: ${remainingViews}`,
    `Required pace: ${requiredDailyPace}/day over ${remainingDays} days`,
    `Followers: ${user.followers_count || 0}`,
    `Profile views (separate): ${user.profile_views || 0}`,
    '',
    'Top posts:',
    ...topPosts.map((p, index) => `${index + 1}. ${p.insights.views || 0} views — ${(p.text || '').replace(/\s+/g, ' ').slice(0, 140)}`),
  ].join('\n'),
};

await sendSummary(summary);
console.log(JSON.stringify({ summary, topPosts }, null, 2));
