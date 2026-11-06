// Runs the real app.js in a browser with simulated WebRTC and server endpoints.
import { chromium } from "playwright";
import { readFile } from "node:fs/promises";
import assert from "node:assert/strict";
import test from "node:test";
const root = new URL("../", import.meta.url);
test("browser closes on SSE loss, bounds shutdown, and waits for server finalization", async () => {
  const browser = await chromium.launch({ headless: true });
  async function setup({ stallClose = false, stallExport = false } = {}) {
    const page = await browser.newPage();
    await page.addInitScript(() => {
      window.mock = { stopped: false, closeCalls: 0, runReads: 0, finalized: false };
      const timeout = AbortSignal.timeout.bind(AbortSignal);
      AbortSignal.timeout = ms => timeout(ms === 18000 || ms === 5000 ? 100 : ms);
      class AudioContextStub {
        resume() {
          return Promise.resolve();
        }
        close() {
          return Promise.resolve();
        }
        createChannelMerger() {
          return { connect() {} };
        }
        createMediaStreamDestination() {
          return { stream: {} };
        }
        createMediaStreamSource() {
          return { connect() {} };
        }
      }
      window.AudioContext = AudioContextStub;
      Object.defineProperty(navigator, "mediaDevices", {
        value: {
          getUserMedia: async () => ({
            getTracks: () => [
              {
                stop() {
                  window.mock.stopped = true;
                },
              },
            ],
          }),
        },
      });
      window.MediaRecorder = { isTypeSupported: () => false };
      window.RTCPeerConnection = class {
        constructor() {
          window.mock.peer = this;
          this.iceGatheringState = "complete";
          this.connectionState = "connected";
        }
        addTrack() {}
        createOffer() {
          return Promise.resolve({ type: "offer", sdp: "v=0" });
        }
        setLocalDescription(d) {
          this.localDescription = d;
          return Promise.resolve();
        }
        createDataChannel() {
          return (window.mock.channel = { close() {} });
        }
        setRemoteDescription() {
          setTimeout(() => window.mock.channel.onmessage({ data: JSON.stringify({ type: "session.started" }) }), 0);
          return Promise.resolve();
        }
        close() {
          this.connectionState = "closed";
        }
      };
      window.EventSource = class extends EventTarget {
        constructor() {
          super();
          window.mock.sse = this;
        }
        close() {
          this.closed = true;
        }
      };
    });
    await page.route("http://cookbook.test/**", async route => {
      const path = new URL(route.request().url()).pathname;
      if (path === "/api/session")
        return route.fulfill({ json: { session: { id: "live_fake" }, transport: { sdp: "v=0" } } });
      if (path === "/api/close") {
        await page.evaluate(() => window.mock.closeCalls++);
        if (stallClose) return;
        await page.evaluate(() => (window.mock.finalized = true));
        return route.fulfill({ json: { confirmed: true } });
      }
      if (path === "/api/run") {
        if (stallExport) return;
        await page.evaluate(() => window.mock.runReads++);
        return route.fulfill({
          json: { id: "live_fake", closed: await page.evaluate(() => window.mock.finalized), events: [] },
        });
      }
      const file = path === "/" ? "index.html" : path.slice(1);
      return route.fulfill({
        body: await readFile(new URL("public/" + file, root)),
        contentType: file.endsWith(".woff2")
          ? "font/woff2"
          : file.endsWith(".svg")
            ? "image/svg+xml"
            : file.endsWith(".js")
              ? "text/javascript"
              : file.endsWith(".css")
                ? "text/css"
                : "text/html",
      });
    });
    await page.goto("http://cookbook.test/");
    await page.evaluate(() => window.cookbook.start());
    return page;
  }
  try {
    let page = await setup();
    await page.evaluate(() => window.mock.sse.onerror());
    await page.waitForFunction(() => document.querySelector("#status").textContent === "Conversation ended");
    assert.equal(await page.evaluate(() => window.mock.stopped), true);
    assert.equal(await page.evaluate(() => window.mock.peer.connectionState), "closed");
    assert.match(await page.locator("#error").innerText(), /Lost the app connection/);
    await page.close();
    page = await setup({ stallClose: true });
    await page.evaluate(() => window.cookbook.close());
    assert.equal(await page.evaluate(() => window.mock.stopped), true);
    assert.equal(await page.locator("#start").isEnabled(), true);
    assert.equal(await page.evaluate(() => window.cookbook.snapshot().closed), false);
    assert.equal(await page.locator("#recording, #run").count(), 0);
    await page.close();
    page = await setup({ stallExport: true });
    await page.evaluate(() => window.cookbook.close());
    assert.equal(await page.locator("#start").isEnabled(), true);
    assert.equal(await page.evaluate(() => window.mock.stopped), true);
    await page.close();
    page = await setup();
    await page.evaluate(() =>
      window.mock.channel.onmessage({ data: JSON.stringify({ type: "session.closed", usage: { seconds: 2 } }) }),
    );
    await page.waitForFunction(() => document.querySelector("#status").textContent === "Conversation ended");
    const downloaded = await page.evaluate(() => ({
      client: window.cookbook.snapshot(),
      closeCalls: window.mock.closeCalls,
    }));
    assert.equal(downloaded.closeCalls, 1);
    assert.equal(downloaded.client.closed, true);
    assert.equal(await page.evaluate(() => window.mock.runReads), 0);
  } finally {
    await browser.close();
  }
});
