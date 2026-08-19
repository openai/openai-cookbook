import { client } from './mailer.mjs';

const resend = client();
const result = await resend.domains.list();

if (result.error) {
  console.error(JSON.stringify({ ok: false, provider: 'resend', error: result.error }, null, 2));
  process.exit(1);
}

console.log(JSON.stringify({
  ok: true,
  provider: 'resend',
  check: 'domains.list',
  data: result.data
}, null, 2));
