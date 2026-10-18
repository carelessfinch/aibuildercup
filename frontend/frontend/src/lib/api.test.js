/**
 * @jest-environment node
 */
import fs from "fs";
import path from "path";
import { ReadableStream, TextDecoderStream } from "stream/web";
import { consumeSse } from "./api";

// CRA's Jest node environment predates the WHATWG stream globals.
global.TextDecoderStream = global.TextDecoderStream || TextDecoderStream;

// A real research-api stream (sse-starlette frames every line with "\r\n").
const LIVE = fs.readFileSync(path.join(__dirname, "__fixtures__", "escalated-run.sse"), "utf8");

function responseFrom(chunks) {
  const encoder = new TextEncoder();
  const body = new ReadableStream({
    start(controller) {
      chunks.forEach((chunk) => controller.enqueue(encoder.encode(chunk)));
      controller.close();
    },
  });
  return { body };
}

async function collect(chunks) {
  const seen = [];
  await consumeSse(responseFrom(chunks), (event, data) => seen.push({ event, data }));
  return seen;
}

test("parses research-api CRLF frames down to the final escalated report", async () => {
  const seen = await collect([LIVE]);
  const types = seen.map((e) => e.event);
  expect(types).toContain("escalated");
  const final = seen.find((e) => e.event === "escalated");
  expect(final.data.data.report.reviews.length).toBeGreaterThan(0);
  expect(final.data.data.report.sign_off).toBe("escalated");
});

test("gets the same events whatever the chunk boundaries, including a split \\r\\n", async () => {
  const whole = await collect([LIVE]);
  const tiny = [];
  for (let i = 0; i < LIVE.length; i += 7) tiny.push(LIVE.slice(i, i + 7));
  expect(await collect(tiny)).toEqual(whole);
  const cut = LIVE.indexOf("\r\n\r\n") + 1;
  expect(await collect([LIVE.slice(0, cut), LIVE.slice(cut)])).toEqual(whole);
});

test("still parses LF frames (rag-api chat) and a final frame with no blank line", async () => {
  const seen = await collect(['event: token\ndata: {"t":"a"}\n\nevent:done\ndata: {"ok":true}']);
  expect(seen).toEqual([
    { event: "token", data: { t: "a" } },
    { event: "done", data: { ok: true } },
  ]);
});
