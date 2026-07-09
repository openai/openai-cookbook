import 'dotenv/config';
import http from 'node:http';
import { sendMail, guestAccessEmail } from './mailer.mjs';

const PORT = Number(process.env.PORT || 8787);
const TOKEN = process.env.AUMARA_WEBHOOK_TOKEN || '';

function json(res, status, body) {
  const data = JSON.stringify(body);
  res.writeHead(status, {
    'content-type': 'application/json; charset=utf-8',
    'cache-control': 'no-store'
  });
  res.end(data);
}

async function readJson(req) {
  const chunks = [];
  for await (const chunk of req) chunks.push(chunk);
  const raw = Buffer.concat(chunks).toString('utf8');
  if (!raw) return {};
  return JSON.parse(raw);
}

function authorised(req) {
  if (!TOKEN) return true;
  const header = req.headers.authorization || '';
  const token = header.startsWith('Bearer ') ? header.slice(7) : req.headers['x-aumara-token'];
  return token === TOKEN;
}

const server = http.createServer(async (req, res) => {
  try {
    const url = new URL(req.url, `http://${req.headers.host || 'localhost'}`);

    if (req.method === 'GET' && url.pathname === '/health') {
      return json(res, 200, {
        ok: true,
        service: 'aumara-control-tower',
        env: process.env.AUMARA_ENV || 'local',
        mail_from: process.env.AUMARA_MAIL_FROM || null,
        reply_to: process.env.AUMARA_MAIL_REPLY_TO || null
      });
    }

    if (req.method === 'POST' && url.pathname === '/send') {
      if (!authorised(req)) return json(res, 401, { ok: false, error: 'unauthorised' });
      const body = await readJson(req);
      const to = body.to || body.email || body.guestEmail || body.guest_email;
      if (!to) return json(res, 400, { ok: false, error: 'missing recipient email' });

      const email = body.subject && (body.html || body.text)
        ? { subject: body.subject, html: body.html, text: body.text || stripHtml(body.html || '') }
        : guestAccessEmail(body);

      const data = await sendMail({
        to,
        subject: email.subject,
        html: email.html,
        text: email.text,
        tags: [
          { name: 'project', value: 'aumara' },
          { name: 'source', value: body.source || 'manual-webhook' }
        ]
      });

      return json(res, 200, { ok: true, provider: 'resend', data });
    }

    if (req.method === 'POST' && url.pathname === '/webhooks/beds24') {
      if (!authorised(req)) return json(res, 401, { ok: false, error: 'unauthorised' });
      const body = await readJson(req);
      const email = body.email || body.guestEmail || body.guest_email || body.mail;
      if (!email) return json(res, 202, { ok: false, status: 'ignored', reason: 'missing guest email' });

      const composed = guestAccessEmail({ ...body, source: 'beds24' });
      const data = await sendMail({
        to: email,
        subject: composed.subject,
        html: composed.html,
        text: composed.text,
        tags: [
          { name: 'project', value: 'aumara' },
          { name: 'source', value: 'beds24' }
        ]
      });
      return json(res, 200, { ok: true, provider: 'resend', data });
    }

    return json(res, 404, { ok: false, error: 'not found' });
  } catch (error) {
    return json(res, 500, { ok: false, error: error.message });
  }
});

function stripHtml(value) {
  return String(value).replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();
}

server.listen(PORT, () => {
  console.log(JSON.stringify({ ok: true, service: 'aumara-control-tower', port: PORT }));
});
