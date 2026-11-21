// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Ayoze Torres
//
// The PO-token minter, standalone build for the native UI's hidden WebView.
//
// A port of src/lib/poTokenMinter.ts to plain JS with no app imports: it runs the
// same loop (long-poll /pending, mint a session GVS token with bgutils-js whose
// network is tunnelled through /proxy, POST /result) against the local backend.
// The backend port is injected as `window.YOINK_PORT` by the host WebView.

import { getChallenge, BotGuardClient } from "bgutils-js/botguard";
import { WebPoMinter } from "bgutils-js/webpo";
import { buildURL, GOOG_API_KEY } from "bgutils-js/utils";

const PORT = (typeof window !== "undefined" && window.YOINK_PORT) || 8756;
const API = `http://127.0.0.1:${PORT}/api`;
const REQUEST_KEY = "O43z0dpjhgX20SCx4KAo";
const REFRESH_MARGIN_MS = 5 * 60 * 1000;

let minter = null;
let minterExpiresAt = 0;
let visitorData = null;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function toB64(bytes) {
  let s = "";
  for (const b of bytes) s += String.fromCharCode(b);
  return btoa(s);
}
function fromB64(b64) {
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

// bgutils' network, tunnelled through the backend so this WebView only ever
// connects to 127.0.0.1.
const proxiedFetch = async (input, init) => {
  const url =
    typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
  const headers = {};
  new Headers(init?.headers).forEach((v, k) => (headers[k] = v));
  let bodyB64 = null;
  const body = init?.body;
  if (typeof body === "string") bodyB64 = toB64(new TextEncoder().encode(body));
  else if (body instanceof Uint8Array) bodyB64 = toB64(body);
  else if (body instanceof ArrayBuffer) bodyB64 = toB64(new Uint8Array(body));

  const res = await fetch(`${API}/po-token/proxy`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ url, method: init?.method ?? "GET", headers, body_b64: bodyB64 }),
  });
  if (!res.ok) throw new Error(`po-token proxy failed: ${res.status}`);
  const d = await res.json();
  const text = new TextDecoder().decode(fromB64(d.body_b64));
  return new Response(text, { status: d.status, headers: d.headers });
};

async function buildMinter() {
  const challenge = await getChallenge({ requestKey: REQUEST_KEY, fetchFunction: proxiedFetch });
  const interpreterJs =
    challenge.interpreterJavascript?.privateDoNotAccessOrElseSafeScriptWrappedValue;
  if (!interpreterJs || !challenge.program || !challenge.globalName) {
    throw new Error("BotGuard challenge missing interpreter/program");
  }
  // eslint-disable-next-line no-new-func
  new Function(interpreterJs)();
  const client = await BotGuardClient.create({
    program: challenge.program,
    globalName: challenge.globalName,
    globalObject: window,
  });
  const webPoSignalOutput = [];
  const botguardResponse = await client.snapshot({ webPoSignalOutput });
  const res = await proxiedFetch(buildURL("GenerateIT", false), {
    method: "POST",
    headers: {
      "content-type": "application/json+protobuf",
      "x-goog-api-key": GOOG_API_KEY,
      "x-user-agent": "grpc-web-javascript/0.1",
    },
    body: JSON.stringify([REQUEST_KEY, botguardResponse]),
  });
  const it = await res.json();
  const integrityToken = it[0];
  const estimatedTtlSecs = it[1] ?? 3600;
  const built = await WebPoMinter.create({ integrityToken, estimatedTtlSecs }, webPoSignalOutput);
  return { minter: built, ttlMs: estimatedTtlSecs * 1000 };
}

async function ensureMinter() {
  if (minter && Date.now() < minterExpiresAt) return minter;
  const { minter: built, ttlMs } = await buildMinter();
  minter = built;
  minterExpiresAt = Date.now() + Math.max(0, ttlMs - REFRESH_MARGIN_MS);
  return minter;
}

async function fetchVisitorData() {
  if (visitorData) return visitorData;
  const res = await proxiedFetch("https://www.youtube.com/?hl=en", {
    headers: { "accept-language": "en-US,en;q=0.9" },
  });
  const html = await res.text();
  const m =
    html.match(/"visitorData"\s*:\s*"([^"]+)"/) || html.match(/"VISITOR_DATA"\s*:\s*"([^"]+)"/);
  if (!m) throw new Error("visitor_data not found on youtube.com");
  visitorData = JSON.parse(`"${m[1]}"`);
  return visitorData;
}

async function mintSession() {
  const vd = await fetchVisitorData();
  const token = await (await ensureMinter()).mintAsWebsafeString(vd);
  return { token, visitorData: vd };
}

async function loop() {
  for (;;) {
    let res;
    try {
      res = await fetch(`${API}/po-token/pending`);
    } catch {
      await sleep(3000);
      continue;
    }
    if (res.status === 204) continue;
    if (!res.ok) {
      await sleep(3000);
      continue;
    }
    const job = await res.json();
    let token = null;
    let visitor = null;
    let error;
    try {
      const r = await mintSession();
      token = r.token;
      visitor = r.visitorData;
    } catch (err) {
      minter = null;
      visitorData = null;
      error = err instanceof Error ? `${err.name}: ${err.message}` : String(err);
    }
    try {
      await fetch(`${API}/po-token/result`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ id: job.id, token, visitor_data: visitor, error }),
      });
    } catch {
      /* backend job times out and falls back */
    }
  }
}

loop();
