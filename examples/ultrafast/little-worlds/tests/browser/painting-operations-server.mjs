// Isolated end-to-end painting fixture. No model or external service calls.
// Run: node tests/browser/painting-operations-server.mjs
// Open http://127.0.0.1:5193/?space=iris and sign in as Iris.
// Use Paint with words: "paint the whole canvas green", "shapes", or "flood".
// Include "slow" to leave time to exercise Stop during model inference.
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { once } from 'node:events';
import { createServer as createHttpServer } from 'node:http';
import { setTimeout as delay } from 'node:timers/promises';
import { randomUUID } from 'node:crypto';
import { createServer } from 'vite';
import { createApp } from '../../server/index.mjs';
import { paintingProposal } from '../fixtures/painting/index.mjs';

const root = fileURLToPath(new URL('../../', import.meta.url));
const noNetwork = async () => { throw new Error('External services are disabled in the painting browser fixture.'); };
const disabledAdapter = { keyAvailable: false, respond: noNetwork };
const reply = text => ({ output: [{ type: 'message', role: 'assistant', content: [{ type: 'output_text', text }] }], metrics: { servedTier: 'ultrafast' } });
const toolCall = (name, args) => ({ output: [{ type: 'function_call', call_id: randomUUID(), name, arguments: JSON.stringify(args) }], metrics: { servedTier: 'ultrafast' } });
const shape = (kind, x1, y1, x2, y2, color, filled = true, width = 1) => ({ kind, x1, y1, x2, y2, color, filled, width });

export async function startPaintingOperationsServer({ apiPort = 4394, webPort = 5193, columns = 192, rows = 128 } = {}) {
  const temporary = await mkdtemp(join(tmpdir(), 'little-worlds-painting-browser-'));
  const calls = [];
  const proposal = await paintingProposal({ columns, rows });
  const spaceAgentAdapter = {
    keyAvailable: true, model: 'painting-browser-fixture', tier: 'ultrafast',
    async respond({ input, signal, tools }) {
      const prompt = String(input.filter(item => item.role === 'user').at(-1)?.content || '');
      const results = input.filter(item => item.type === 'function_call_output');
      const context = String(input.find(item => item.role === 'developer')?.content || '');
      const stateText = context.split(/\nCurrent shared state[^\n]*:\n/)[1];
      const state = JSON.parse(stateText);
      const view = state.extras.canvas;
      if (view.columns !== columns || view.rows !== rows || view.pixels.length !== columns * rows) throw new Error('The agent did not receive the complete authoritative canvas projection.');
      const counts = {};
      for (const pixel of view.pixels) counts[pixel] = (counts[pixel] || 0) + 1;
      const call = { prompt, round: results.length + 1, columns, rows, counts, tools: tools.map(tool => tool.name), status: 'running' };
      calls.push(call);
      try {
        await delay(/slow/i.test(prompt) ? 1800 : 180, undefined, { signal });
        if (results.some(result => !JSON.parse(result.output).ok)) throw new Error('A mocked painting operation failed its real reducer validation.');
        let response;
        if (/flood/i.test(prompt)) {
          if (!results.length) response = toolCall('paint_shapes', { columns, rows, shapes: [shape('rect', 20, 20, columns - 21, rows - 21, 4, false, 2)] });
          else if (results.length === 1) response = toolCall('flood_fill', { columns, rows, x: Math.floor(columns / 2), y: Math.floor(rows / 2), color: 2 });
          else {
            if (view.pixels[Math.floor(rows / 2) * columns + Math.floor(columns / 2)] !== '2') throw new Error('The flood-fill center was not colored.');
            response = reply('Filled the enclosed region yellow; the surrounding canvas is preserved.');
          }
        } else if (/shapes|rectangle|ellipse/i.test(prompt)) {
          if (!results.length) response = toolCall('paint_shapes', { columns, rows, shapes: [
            shape('rect', 8, 8, Math.floor(columns / 2) - 1, rows - 9, 3),
            shape('ellipse', Math.floor(columns / 2) + 8, 8, columns - 9, rows - 9, 2),
            shape('line', 8, rows - 9, columns - 9, 8, 1, true, 3),
          ] });
          else response = reply('Painted the rectangle, ellipse, and diagonal line across the canvas.');
        } else {
          const color = /blue|cobalt/i.test(prompt) ? 0 : /yellow/i.test(prompt) ? 2 : 3;
          if (!results.length) response = toolCall('fill_canvas', { columns, rows, color });
          else {
            if (view.pixels !== String(color).repeat(columns * rows)) throw new Error('The full-canvas fill left uncovered pixels.');
            response = reply(`Painted all ${columns * rows} pixels ${color === 3 ? 'green' : color === 2 ? 'yellow' : 'blue'}.`);
          }
        }
        call.status = 'completed';
        call.operation = response.output[0].name || 'verified-completion';
        return response;
      } catch (error) {
        call.status = signal.aborted ? 'cancelled' : 'failed';
        call.error = error.message;
        throw error;
      }
    },
  };
  let instance, apiServer, webServer, closing;
  const close = () => closing ||= (async () => {
    await webServer?.close();
    if (apiServer) {
      apiServer.closeAllConnections();
      await new Promise(done => apiServer.close(done));
    }
    await instance?.close();
    await rm(temporary, { recursive: true, force: true });
  })();
  try {
    instance = await createApp({
      dataDir: join(temporary, 'data'),
      seedOverride: { source: proposal.source, tests: proposal.tests, state: { projects: [], contributions: [], extras: {} } },
      adapter: disabledAdapter, comparisonAdapter: disabledAdapter, progressEstimator: noNetwork,
      spaceAgentAdapter, apiKey: '', generateIcons: false,
      healthAdapter: disabledAdapter, voiceAdapter: disabledAdapter,
      newsFetchImpl: noNetwork, voiceFetchImpl: noNetwork, voiceResponsesFetchImpl: noNetwork,
    });
    const service = await instance.directory.serviceFor('iris');
    await service.action({ actor: 'iris', revisionId: service.store.read().currentRevisionId, action: {
      type: 'paint_pixels', columns, rows, cells: [0, Math.floor(rows / 2) * columns + Math.floor(columns / 2), columns * rows - 1].map(cell => ({ cell, color: 0 })),
    } });
    apiServer = createHttpServer((request, response) => {
      if (request.method === 'GET' && request.url === '/api/_fixture/painting') {
        response.writeHead(200, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' });
        response.end(JSON.stringify({ columns, rows, calls }));
      } else instance.app(request, response);
    }).listen(apiPort, '127.0.0.1');
    await once(apiServer, 'listening');
    const actualApiPort = apiServer.address().port;
    webServer = await createServer({
      root, configFile: join(root, 'vite.config.ts'),
      server: { host: '127.0.0.1', port: webPort, strictPort: true, proxy: { '/api': { target: `http://127.0.0.1:${actualApiPort}`, changeOrigin: false } } },
    });
    await webServer.listen();
    return { url: `http://127.0.0.1:${webServer.httpServer.address().port}/?space=iris`, apiUrl: `http://127.0.0.1:${actualApiPort}`, temporary, instance, calls, close };
  } catch (error) { await close(); throw error; }
}

if (process.argv[1] && pathToFileURL(resolve(process.argv[1])).href === import.meta.url) {
  const fixture = await startPaintingOperationsServer();
  console.log(`Painting browser fixture: ${fixture.url}`);
  console.log('Sign in as Iris; use Paint with words for "paint the whole canvas green", "shapes", or "flood". Add "slow" to test Stop.');
  console.log(`Temporary data only: ${fixture.temporary}`);
  const stop = async () => { await fixture.close(); process.exit(0); };
  process.on('SIGINT', stop);
  process.on('SIGTERM', stop);
}
