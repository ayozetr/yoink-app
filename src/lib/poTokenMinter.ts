/**
 * PO-token minter — the WebView side of zero-config `po_token_mode: "auto"`.
 *
 * The backend can't run YouTube's BotGuard JavaScript, so it asks this WebView to
 * mint per-video PO tokens with `bgutils-js`. bgutils' own network (the BotGuard
 * Create / GenerateIT calls) can't reach Google under the app's CSP, so it's
 * routed through the backend's `/api/po-token/proxy` — this WebView only ever
 * talks to 127.0.0.1.
 *
 * `startPoTokenMinter()` runs a background loop: long-poll `/api/po-token/pending`
 * for a video id the backend needs a token for, mint it, and POST the result. The
 * BotGuard integrity token (video-independent, valid ~hours) is minted once and
 * the `WebPoMinter` reused for subsequent videos.
 *
 * NOTE: the end-to-end mint (the real BotGuard attestation against Google) can
 * only be validated live; see docs/po-token-webview.md. Everything up to the
 * bgutils calls (the loop, the proxied fetch, the result POST) is structural.
 */
import { apiUrl } from "./apiBase";

// The well-known YouTube BotGuard request key (a public constant, not a secret).
const REQUEST_KEY = "O43z0dpjhgX20SCx4KAo";
// Re-attest a little before the integrity token's TTL so a mint never uses a
// just-expired one. bgutils reports the TTL; this is the safety margin.
const REFRESH_MARGIN_MS = 5 * 60 * 1000;

interface WebPoMinterLike {
  mintAsWebsafeString(contentBinding: string): Promise<string>;
}

let minter: WebPoMinterLike | null = null;
let minterExpiresAt = 0;
let started = false;

/** base64 of a byte buffer (binary-safe). */
function toBase64(bytes: Uint8Array): string {
  let binary = "";
  for (const b of bytes) binary += String.fromCharCode(b);
  return btoa(binary);
}

/** bytes from a base64 string. */
function fromBase64(b64: string): Uint8Array {
  const binary = atob(b64);
  const out = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) out[i] = binary.charCodeAt(i);
  return out;
}

/** A `fetch`-compatible function that tunnels bgutils' requests through the
 * backend proxy, so this WebView never connects to Google directly. */
const proxiedFetch: typeof fetch = async (input, init) => {
  const url =
    typeof input === "string"
      ? input
      : input instanceof URL
        ? input.toString()
        : input.url;
  const headers: Record<string, string> = {};
  new Headers(init?.headers).forEach((v, k) => (headers[k] = v));

  let bodyB64: string | null = null;
  const body = init?.body;
  if (typeof body === "string") {
    bodyB64 = toBase64(new TextEncoder().encode(body));
  } else if (body instanceof Uint8Array) {
    bodyB64 = toBase64(body);
  } else if (body instanceof ArrayBuffer) {
    bodyB64 = toBase64(new Uint8Array(body));
  }
  // bgutils only ever sends a string or byte body; other BodyInit kinds
  // (Blob/FormData/stream) don't occur here and are left unset.

  const res = await fetch(apiUrl("/po-token/proxy"), {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ url, method: init?.method ?? "GET", headers, body_b64: bodyB64 }),
  });
  if (!res.ok) throw new Error(`po-token proxy failed: ${res.status}`);
  const data = (await res.json()) as {
    status: number;
    headers: Record<string, string>;
    body_b64: string;
  };
  // BotGuard's endpoints answer with JSON/text, so decode to a string (an
  // unambiguous BodyInit); bgutils reads it back via .json()/.text().
  const text = new TextDecoder().decode(fromBase64(data.body_b64));
  return new Response(text, { status: data.status, headers: data.headers });
};

/** Run the full BotGuard attestation and build a reusable WebPoMinter. */
async function buildMinter(): Promise<{ minter: WebPoMinterLike; ttlMs: number }> {
  // Dynamic import so bgutils-js is code-split out of the main bundle — it's only
  // pulled in when auto-PO actually runs (the desktop app in auto mode).
  const [{ getChallenge, BotGuardClient }, { WebPoMinter }, { buildURL, GOOG_API_KEY }] =
    await Promise.all([
      import("bgutils-js/botguard"),
      import("bgutils-js/webpo"),
      import("bgutils-js/utils"),
    ]);

  const challenge = await getChallenge({
    requestKey: REQUEST_KEY,
    fetchFunction: proxiedFetch,
  });
  const interpreterJs =
    challenge.interpreterJavascript?.privateDoNotAccessOrElseSafeScriptWrappedValue;
  if (!interpreterJs || !challenge.program || !challenge.globalName) {
    throw new Error("BotGuard challenge missing interpreter/program");
  }

  // Load the BotGuard VM into this realm, then snapshot it. `new Function` is how
  // BotGuard's interpreter is meant to be run (that's the whole mechanism); the
  // code is Google's BotGuard interpreter fetched over the guarded proxy.
  // eslint-disable-next-line @typescript-eslint/no-implied-eval, @typescript-eslint/no-unsafe-call
  new Function(interpreterJs)();
  const client = await BotGuardClient.create({
    program: challenge.program,
    globalName: challenge.globalName,
    globalObject: window,
  });
  const webPoSignalOutput: unknown[] = [];
  const botguardResponse = await client.snapshot({
    webPoSignalOutput: webPoSignalOutput as never,
  });

  // Exchange the snapshot for an integrity token (GenerateIT), proxied.
  const res = await proxiedFetch(buildURL("GenerateIT", false), {
    method: "POST",
    headers: {
      "content-type": "application/json+protobuf",
      "x-goog-api-key": GOOG_API_KEY,
      "x-user-agent": "grpc-web-javascript/0.1",
    },
    body: JSON.stringify([REQUEST_KEY, botguardResponse]),
  });
  const it = (await res.json()) as [string, number];
  const integrityToken = it[0];
  const estimatedTtlSecs = it[1] ?? 3600;

  const built = await WebPoMinter.create(
    { integrityToken, estimatedTtlSecs },
    webPoSignalOutput as never,
  );
  return { minter: built, ttlMs: estimatedTtlSecs * 1000 };
}

/** A ready WebPoMinter, (re)attesting when the cached one is missing/expired. */
async function ensureMinter(): Promise<WebPoMinterLike> {
  if (minter && Date.now() < minterExpiresAt) return minter;
  const { minter: built, ttlMs } = await buildMinter();
  minter = built;
  minterExpiresAt = Date.now() + Math.max(0, ttlMs - REFRESH_MARGIN_MS);
  return minter;
}

async function mint(videoId: string): Promise<string> {
  return (await ensureMinter()).mintAsWebsafeString(videoId);
}

/** Start the long-poll loop that services the backend's mint requests. Idempotent;
 * returns a stop function. Runs until stopped (or the page unloads). */
export function startPoTokenMinter(): () => void {
  if (started) return () => {};
  started = true;
  let stopped = false;

  const backoff = () => new Promise((r) => setTimeout(r, 3000));

  const loop = async () => {
    while (!stopped) {
      let res: Response;
      try {
        res = await fetch(apiUrl("/po-token/pending"));
      } catch {
        await backoff(); // backend not up yet / transient — retry
        continue;
      }
      if (res.status === 204) continue; // long-poll returned empty — poll again
      if (!res.ok) {
        await backoff();
        continue;
      }
      const job = (await res.json()) as { id: string; video_id: string };
      let token: string | null;
      let error: string | undefined;
      try {
        token = await mint(job.video_id);
      } catch (err) {
        minter = null; // force re-attestation next time
        token = null; // report the failure so the backend falls back
        error = err instanceof Error ? `${err.name}: ${err.message}` : String(err);
      }
      try {
        await fetch(apiUrl("/po-token/result"), {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ id: job.id, token, error }),
        });
      } catch {
        // Result POST failed — the backend job just times out and falls back.
      }
    }
  };

  void loop();
  return () => {
    stopped = true;
    started = false;
  };
}
