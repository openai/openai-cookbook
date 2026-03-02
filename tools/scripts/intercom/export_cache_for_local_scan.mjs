#!/usr/bin/env node

/**
 * Export Intercom conversations to cache for local keyword iteration.
 * Run from tools/scripts/intercom. Requires INTERCOM_ACCESS_TOKEN in .env (workspace root).
 *
 * Usage:
 *   node export_cache_for_local_scan.mjs --from 2025-01-21 --to 2025-01-28
 *   node export_cache_for_local_scan.mjs --from 2025-01-21 --to 2025-01-28 --team 2334166   # Primeros 90 días inbox
 *
 * Output: plugins/colppy-customer-success/skills/intercom-developer-api-research/cache/conversations_YYYY-MM-DD_YYYY-MM-DD.json
 */

import fs from 'fs';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';
import dotenv from 'dotenv';

import {
  fetchConversationIds,
  getConversationDetails,
  getContactDetails,
  extractTags,
  buildConversationText,
} from './intercom-api-helpers.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const WORKSPACE_ROOT = join(__dirname, '..', '..', '..');
dotenv.config({ path: join(WORKSPACE_ROOT, '.env') });

import axios from 'axios';

const CACHE_PATH = join(
  WORKSPACE_ROOT,
  'plugins',
  'colppy-customer-success',
  'skills',
  'intercom-developer-api-research',
  'cache'
);

function firstDefined(obj, keys) {
  for (const key of keys) {
    if (Object.prototype.hasOwnProperty.call(obj, key) && obj[key] !== null && obj[key] !== undefined) {
      return obj[key];
    }
  }
  return null;
}

export function extractUserTypeAttributes(customAttributes = {}) {
  const esContador = firstDefined(customAttributes, [
    'es_contador',
    'Es_contador',
    'Es Contador',
    'es contador',
    'Es contador',
  ]);
  const rolWizard = firstDefined(customAttributes, [
    'rol_wizard',
    'Rol_wizard',
    'Rol wizard',
    '¿Cuál es tu rol? wizard',
    'Cuál es tu rol? wizard',
    'Cual es tu rol? wizard',
  ]);
  return { es_contador: esContador, rol_wizard: rolWizard };
}

function parseArgs() {
  const args = process.argv.slice(2);
  const opts = { from: null, to: null, team: null };
  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--from' && args[i + 1]) opts.from = args[++i];
    else if (args[i] === '--to' && args[i + 1]) opts.to = args[++i];
    else if (args[i] === '--team' && args[i + 1]) opts.team = args[++i];
  }
  return opts;
}

async function main() {
  const { from: fromDate, to: toDate, team: teamId } = parseArgs();
  if (!fromDate || !toDate) {
    console.error('Usage: node export_cache_for_local_scan.mjs --from YYYY-MM-DD --to YYYY-MM-DD [--team TEAM_ID]');
    process.exit(1);
  }

  const token = process.env.INTERCOM_ACCESS_TOKEN;
  if (!token) {
    console.error('INTERCOM_ACCESS_TOKEN not found. Add it to .env at workspace root.');
    process.exit(1);
  }

  const api = axios.create({
    baseURL: 'https://api.intercom.io',
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: 'application/json',
      'Content-Type': 'application/json',
      'Intercom-Version': '2.13',
    },
    timeout: 30000,
  });

  const teamLabel = teamId ? ` team ${teamId}` : '';
  console.log(`Fetching conversation IDs (${fromDate} to ${toDate}${teamLabel})...`);
  const ids = await fetchConversationIds(api, fromDate, toDate, null, null, teamId);
  console.log(`Found ${ids.length} conversations. Fetching details...`);

  const conversations = [];
  const batchSize = 5;
  for (let i = 0; i < ids.length; i += batchSize) {
    const batch = ids.slice(i, i + batchSize);
    const results = await Promise.all(
      batch.map(async (id) => {
        try {
          const conv = await getConversationDetails(api, id);
          const tags = extractTags(conv);
          const { parts } = buildConversationText(conv);
          const contactRef = conv.contacts?.contacts?.[0] || conv.contacts?.[0];
          const contactId = contactRef?.id || null;
          let contactEmail = contactRef?.email || conv.source?.author?.email || null;
          let es_contador = null;
          let rol_wizard = null;
          if (contactId) {
            const contact = await getContactDetails(api, contactId);
            if (contact?.custom_attributes) {
              const extracted = extractUserTypeAttributes(contact.custom_attributes);
              es_contador = extracted.es_contador;
              rol_wizard = extracted.rol_wizard;
            }
            if (!contactEmail && contact?.email) contactEmail = contact.email;
          }
          return {
            conversation_id: id,
            created_at: conv.created_at ? new Date(conv.created_at * 1000).toISOString() : '',
            state: conv.state,
            contact_email: contactEmail,
            contact_es_contador: es_contador,
            contact_rol_wizard: rol_wizard,
            tags,
            parts: parts.map((p) => ({
              author_type: p.author_type,
              body: p.body,
              created_at: p.created_at ? new Date(p.created_at * 1000).toISOString() : null,
            })),
          };
        } catch (e) {
          console.error(`Failed to fetch ${id}:`, e.message);
          return null;
        }
      })
    );
    for (const r of results) if (r) conversations.push(r);
    if ((i + batchSize) % 50 === 0 || i + batchSize >= ids.length) {
      console.log(`  Fetched ${Math.min(i + batchSize, ids.length)}/${ids.length}`);
    }
  }

  if (!fs.existsSync(CACHE_PATH)) fs.mkdirSync(CACHE_PATH, { recursive: true });
  const teamSuffix = teamId ? `_team${teamId}` : '';
  const outFile = `conversations_${fromDate}_${toDate}${teamSuffix}.json`;
  const outPath = join(CACHE_PATH, outFile);
  fs.writeFileSync(
    outPath,
    JSON.stringify(
      {
        from_date: fromDate,
        to_date: toDate,
        state: null,
        team_assignee_id: teamId || null,
        topic: teamId ? 'Primeros 90 días' : 'Colppy API integration',
        saved_at: new Date().toISOString(),
        conversations,
      },
      null,
      2
    ),
    'utf8'
  );
  console.log(`\nSaved ${conversations.length} conversations to:\n  ${outPath}`);
  console.log(`\nRun local scan (from plugin dir):`);
  console.log(`  cd plugins/colppy-customer-success`);
  console.log(`  node scripts/local_scan.mjs --cache skills/intercom-developer-api-research/cache/${outFile}`);
}

const isDirectRun = process.argv[1] &&
  fileURLToPath(import.meta.url).endsWith(process.argv[1].replace(/^.*[\\/]/, ''));

if (isDirectRun) {
  main().catch((e) => {
    console.error(e);
    process.exit(1);
  });
}
