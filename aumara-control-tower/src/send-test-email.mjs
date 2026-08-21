import { sendMail } from './mailer.mjs';

if (process.env.AUMARA_TEST_EMAIL_CONFIRMED !== 'true') {
  throw new Error('Test email refused: set AUMARA_TEST_EMAIL_CONFIRMED=true');
}

const to = process.env.AUMARA_TEST_TO || 'elcidspain@gmail.com';

const data = await sendMail({
  to,
  subject: 'AUMARA Control Tower — Resend E2E test',
  html: '<h2>AUMARA Control Tower</h2><p>Resend email path is working.</p>',
  text: 'AUMARA Control Tower\n\nResend email path is working.',
  tags: [
    { name: 'project', value: 'aumara' },
    { name: 'source', value: 'e2e-test' }
  ],
  idempotencyKey: process.env.AUMARA_TEST_EMAIL_IDEMPOTENCY_KEY
});

console.log(JSON.stringify({ ok: true, provider: 'resend', to, data }, null, 2));
