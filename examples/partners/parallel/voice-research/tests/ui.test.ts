import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { chromium } from "playwright";

test("cards retain independent findings and reject stale or replayed snapshots", async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage();
    await page.route("http://cookbook.test/**", async route => {
      const path = new URL(route.request().url()).pathname;
      const file = path === "/" ? "index.html" : path.slice(1);
      let body = await readFile(new URL("../public/" + file, import.meta.url));
      if (file === "app.js")
        body = Buffer.from(
          body.toString() +
            '\nwindow.testCaption = appendCaption; window.testSnapshot = data => uiEvent({type:"task",data});',
        );
      await route.fulfill({
        body,
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
    const send = (id: string, version: number, summary: string, state = "researching", revision = 1) =>
      page.evaluate(data => (window as any).testSnapshot(data), {
        task_id: id,
        version,
        revision,
        task: { request: id, location: null, date: null, constraints: [] },
        summary,
        state,
        sources: [{ url: "https://example.com/", title: "Evidence" }],
      });
    await send("A", 1, "First");
    await send("B", 1, "Second", "completed");
    await send("A", 2, "First\n\nMore", "completed");
    await send("A", 1, "Old");
    await send("A", 2, "Replay");
    assert.equal(await page.locator("article").count(), 2);
    assert.deepEqual(
      await page.locator("article").evaluateAll(nodes => nodes.map(n => n.getAttribute("data-task-id"))),
      ["B", "A"],
    );
    assert.equal(await page.locator('[data-task-id="A"] .task-summary').innerText(), "First\n\nMore");
    await send("A", 3, "", "researching", 2);
    await send("A", 3, "Stale", "completed", 1);
    assert.equal(await page.locator('[data-task-id="A"] .task-summary').innerText(), "");
    assert.equal(await page.locator('[data-task-id="B"] .task-summary').innerText(), "Second");
    await send("A", 4, "Kept", "cancelled", 2);
    assert.equal(await page.locator('[data-task-id="A"] .task-state').innerText(), "Cancelled");
    assert.equal(await page.locator('[data-task-id="A"] a').getAttribute("href"), "https://example.com/");
    await page.evaluate(() =>
      (window as any).testSnapshot({
        task_id: "B",
        version: 2,
        revision: 1,
        task: { request: "Current answer", location: null, date: null, constraints: [] },
        state: "completed",
        summary: "Old answer\n\nCorrection",
        current_summary: "Correction",
        display_title: "Short title",
        display_items: [{ heading: "Finding", detail: "Supported details" }],
        sources: [],
        current_sources: [
          { url: "https://example.com/current", title: "Current evidence" },
          { url: "javascript:alert(1)", title: "Unsafe" },
        ],
      }),
    );
    assert.equal(await page.locator('[data-task-id="B"] .task-summary').innerText(), "Finding\nSupported details");
    assert.equal(await page.locator('[data-task-id="B"] h3').innerText(), "Short title");
    assert.equal(await page.locator('[data-task-id="B"] a').count(), 1);
    // A later abstention replaces the current recommendation, even with no citations.
    await page.evaluate(() =>
      (window as any).testSnapshot({
        task_id: "B",
        version: 3,
        revision: 1,
        task: { request: "Current answer", location: null, date: null, constraints: [] },
        state: "completed",
        outcome: "insufficient_evidence",
        summary: "Old supported recommendation",
        sources: [{ url: "https://example.com/old", title: "Old" }],
        current_summary: "The evidence conflicts.",
        display_items: [],
        current_sources: [],
      }),
    );
    assert.equal(await page.locator('[data-task-id="B"] .task-state').innerText(), "Not enough evidence");
    assert.equal(await page.locator('[data-task-id="B"] .task-state span').count(), 0);
    assert.equal(await page.locator('[data-task-id="B"] .task-summary').innerText(), "The evidence conflicts.");
    assert.equal(await page.locator('[data-task-id="B"] a').count(), 0);
    await page.evaluate(() =>
      (window as any).testSnapshot({
        task_id: "B",
        version: 4,
        revision: 2,
        task: { request: "Current answer", location: null, date: null, constraints: [] },
        state: "failed",
        summary: "Provisional earlier advice",
        sources: [{ url: "https://example.com/old", title: "Old" }],
        current_summary: "",
        display_items: [],
        current_sources: [],
      }),
    );
    assert.equal(await page.locator('[data-task-id="B"] .task-state').innerText(), "Could not finish");
    assert.equal(await page.locator('[data-task-id="B"] .task-summary').innerText(), "");
    assert.equal(await page.locator('[data-task-id="B"] a').count(), 0);
    assert.equal(await page.locator("#request-count").innerText(), "2 requests");
    assert.equal(await page.locator("#captions").isVisible(), false);
    await page.getByText("Conversation transcript", { exact: true }).click();
    assert.equal(await page.locator("#captions").isVisible(), true);
    await page.evaluate(() =>
      (window as any).testCaption({ type: "session.input_transcript.delta", delta: "Hello", start_ms: 0, end_ms: 100 }),
    );
    assert.equal(await page.locator(".user-turn .speaker").innerText(), "You");
    assert.equal(await page.locator(".user-turn p").innerText(), "Hello");
    assert.equal(await page.locator("#recording, #run, #session-note").count(), 0);
    await page.setViewportSize({ width: 390, height: 844 });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
  } finally {
    await browser.close();
  }
});
