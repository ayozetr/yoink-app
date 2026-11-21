// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Ayoze Torres

//! YouTube PO-token sourcing (off / manual / auto) and the WebView mint bridge.
//!
//! A PO (proof-of-origin) token lets yt-dlp satisfy YouTube's "confirm you're not
//! a bot" wall without cookies. `AppSettings.po_token_mode` decides where tokens
//! come from:
//!
//! - `"off"` — never send one.
//! - `"manual"` — send the token(s) the user pasted in Settings (`po_token`).
//! - `"auto"` — mint a fresh session GVS token locally in the app's WebView
//!   (bgutils-js), falling back to the manual token(s) when minting is unavailable
//!   (the headless CLI has no WebView).
//!
//! The web GVS token (for a logged-out download) is bound to the session's
//! `visitor_data`, not to the video — so one minted token is reused for every
//! video and yt-dlp must be handed the *same* `visitor_data` alongside it.
//!
//! The backend can't run Google's BotGuard JavaScript; the app's WebView can. So a
//! download that needs a token submits a mint job to the in-process [`Broker`] and
//! blocks (with a timeout); the WebView — running a loop that long-polls the
//! `/api/po-token/*` endpoints — mints it with bgutils-js (its network proxied
//! back through [`proxy`], so the WebView never leaves `127.0.0.1`) and posts the
//! result, unblocking the waiter. See `docs/po-token-webview.md`.

use std::collections::HashMap;
use std::net::IpAddr;
use std::sync::{Mutex, OnceLock};
use std::time::{Duration, Instant};

use axum::{
    extract::Json,
    http::StatusCode,
    response::{IntoResponse, Response},
};
use base64::prelude::{Engine as _, BASE64_STANDARD};
use regex::Regex;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use tokio::sync::{oneshot, Notify};

// How long a poller is parked waiting for a job before returning empty (so the
// WebView can re-issue its long-poll). Comfortably under a proxy/idle timeout.
const POLL_WAIT: Duration = Duration::from_secs(25);
// A WebView counts as "present" if it long-polled within this window — used to
// skip the mint (and its timeout) on the headless CLI, where nothing polls.
const POLLER_FRESH: Duration = Duration::from_secs(60);
// The session token + visitor_data are reused for this long before re-minting.
const TOKEN_TTL: Duration = Duration::from_secs(6 * 3600);
// How long to wait for the WebView to mint before giving up (a cold mint runs the
// BotGuard attestation, ~1–4 s; a warm one ~1 s).
const MINT_TIMEOUT: Duration = Duration::from_secs(10);
// After a mint failure, stop attempting for this long and just fall back, so a
// broken minter doesn't add a failed round-trip to every download.
const MINT_BACKOFF: Duration = Duration::from_secs(5 * 60);

// ---------------------------------------------------------------- the broker

struct Job {
    created_at: Instant,
    dispatched: bool,
    tx: Option<oneshot::Sender<Option<MintResult>>>,
}

struct Inner {
    jobs: HashMap<String, Job>,
    last_poll: Option<Instant>,
    seq: u64,
}

/// The WebView's minted answer.
pub struct MintResult {
    pub token: String,
    pub visitor_data: String,
}

/// Thread-safe queue of mint jobs awaiting the WebView, plus their results. The
/// producer is a download task; the consumer is the `/pending` HTTP handler.
pub struct Broker {
    inner: Mutex<Inner>,
    new_job: Notify,
}

impl Broker {
    /// True if the WebView long-polled recently — i.e. minting can be attempted
    /// (otherwise, e.g. on the headless CLI, don't submit and block for nothing).
    pub fn has_active_poller(&self) -> bool {
        let g = self.inner.lock().unwrap();
        g.last_poll.is_some_and(|t| t.elapsed() < POLLER_FRESH)
    }

    /// Enqueue a mint job and block until the WebView fulfills it or `timeout`.
    pub async fn submit_mint(&self, timeout: Duration) -> Option<MintResult> {
        let (tx, rx) = oneshot::channel();
        let id = {
            let mut g = self.inner.lock().unwrap();
            g.seq += 1;
            let id = format!("job-{}", g.seq);
            g.jobs.insert(
                id.clone(),
                Job {
                    created_at: Instant::now(),
                    dispatched: false,
                    tx: Some(tx),
                },
            );
            id
        };
        self.new_job.notify_waiters(); // wake a parked poller
        let res = tokio::time::timeout(timeout, rx).await;
        self.inner.lock().unwrap().jobs.remove(&id);
        match res {
            Ok(Ok(Some(r))) => Some(r),
            _ => None,
        }
    }

    /// Claim the oldest undispatched job for the WebView (long-poll). Blocks up to
    /// `wait`; returns the job id or `None` when there's nothing to mint.
    pub async fn next_job(&self, wait: Duration) -> Option<String> {
        let deadline = Instant::now() + wait;
        loop {
            // Register interest before checking, so a job submitted during the
            // check still wakes us (no lost notification).
            let notified = self.new_job.notified();
            tokio::pin!(notified);
            notified.as_mut().enable();

            {
                let mut g = self.inner.lock().unwrap();
                g.last_poll = Some(Instant::now());
                let mut oldest: Option<(String, Instant)> = None;
                for (id, j) in g.jobs.iter() {
                    if !j.dispatched && oldest.as_ref().is_none_or(|(_, t)| j.created_at < *t) {
                        oldest = Some((id.clone(), j.created_at));
                    }
                }
                if let Some((id, _)) = oldest {
                    g.jobs.get_mut(&id).unwrap().dispatched = true;
                    return Some(id);
                }
            }

            let remaining = deadline.saturating_duration_since(Instant::now());
            if remaining.is_zero() {
                return None;
            }
            let _ = tokio::time::timeout(remaining, notified.as_mut()).await;
        }
    }

    /// Deliver the WebView's result (or `None` on failure). Returns true if the job
    /// was still waiting; a late result (job already timed out) is dropped.
    pub fn complete(&self, id: &str, result: Option<MintResult>) -> bool {
        let mut g = self.inner.lock().unwrap();
        match g.jobs.get_mut(id) {
            Some(job) => {
                if let Some(tx) = job.tx.take() {
                    let _ = tx.send(result);
                }
                true
            }
            None => false,
        }
    }
}

/// Process-wide broker singleton.
pub fn broker() -> &'static Broker {
    static B: OnceLock<Broker> = OnceLock::new();
    B.get_or_init(|| Broker {
        inner: Mutex::new(Inner {
            jobs: HashMap::new(),
            last_poll: None,
            seq: 0,
        }),
        new_job: Notify::new(),
    })
}

// ------------------------------------------------------ session cache + mint

struct MintState {
    // (token, visitor_data, expiry on the monotonic clock).
    session: Option<(String, String, Instant)>,
    // Time until which minting is skipped after a failure.
    backoff_until: Option<Instant>,
}

fn mint_state() -> &'static Mutex<MintState> {
    static S: OnceLock<Mutex<MintState>> = OnceLock::new();
    S.get_or_init(|| {
        Mutex::new(MintState {
            session: None,
            backoff_until: None,
        })
    })
}

/// Drop the cached session token + any backoff (on a settings change, and tests).
pub fn clear_cache() {
    let mut s = mint_state().lock().unwrap();
    s.session = None;
    s.backoff_until = None;
}

fn session_get() -> Option<(String, String)> {
    let s = mint_state().lock().unwrap();
    match &s.session {
        Some((t, v, exp)) if *exp > Instant::now() => Some((t.clone(), v.clone())),
        _ => None,
    }
}

fn session_set(token: String, visitor_data: String) {
    mint_state().lock().unwrap().session = Some((token, visitor_data, Instant::now() + TOKEN_TTL));
}

async fn mint_via_webview() -> Option<(String, String)> {
    if !broker().has_active_poller() {
        return None;
    }
    {
        let s = mint_state().lock().unwrap();
        if s.backoff_until.is_some_and(|u| Instant::now() < u) {
            return None;
        }
    }
    let result = broker().submit_mint(MINT_TIMEOUT).await;
    {
        let mut s = mint_state().lock().unwrap();
        s.backoff_until = if result.is_some() {
            None
        } else {
            Some(Instant::now() + MINT_BACKOFF)
        };
    }
    match &result {
        Some(_) => crate::log_line("auto-PO: minted a session GVS token in the WebView"),
        None => crate::log_line(&format!(
            "auto-PO: WebView mint failed/timed out; backing off {}s",
            MINT_BACKOFF.as_secs()
        )),
    }
    result.map(|r| (r.token, r.visitor_data))
}

/// The session (token, visitor_data) pair — cached, minting once when needed.
async fn mint_session() -> Option<(String, String)> {
    if let Some(cached) = session_get() {
        return Some(cached);
    }
    let minted = mint_via_webview().await?;
    session_set(minted.0.clone(), minted.1.clone());
    Some(minted)
}

// --------------------------------------------------- yt-dlp extractor-args

// The web-based clients we hand the session GVS token to. yt-dlp applies a
// `<client>.gvs` token only when it uses that client, so listing several is
// harmless; `mweb` is the one that reliably yields the GVS-gated formats when
// logged out (plain `web` degrades to images-only), which is why `player_client`
// also adds `mweb`.
const WEB_CLIENTS: &[&str] = &["mweb", "web", "web_safari", "web_embedded"];

fn parse_manual(raw: Option<&str>) -> Vec<String> {
    raw.map(|r| {
        r.split(',')
            .map(str::trim)
            .filter(|t| !t.is_empty())
            .map(String::from)
            .collect()
    })
    .unwrap_or_default()
}

/// The 11-char YouTube video id in a watch/shorts/embed/live/youtu.be URL, if any.
pub fn youtube_video_id(url: &str) -> Option<String> {
    static RE: OnceLock<Regex> = OnceLock::new();
    let re = RE.get_or_init(|| {
        Regex::new(r"(?:v=|/shorts/|/embed/|/live/|youtu\.be/)([\w-]{11})").unwrap()
    });
    re.captures(url).map(|c| c[1].to_string())
}

/// The `youtube` `--extractor-args` value for **metadata/search** (manual tokens
/// only; never mints — mirrors the Python `network_options` layer). `None` when
/// off or no manual token is set.
pub fn info_extractor_args(settings: &crate::AppSettings) -> Option<String> {
    if settings.po_token_mode == "off" {
        return None;
    }
    let manual = parse_manual(settings.po_token.as_deref());
    (!manual.is_empty()).then(|| format!("youtube:po_token={}", manual.join(",")))
}

/// The `youtube` `--extractor-args` value for a **download**: in auto mode the
/// minted session GVS token (bound to `visitor_data`, which yt-dlp needs alongside
/// it) handed to the web clients with `mweb` added to the client list, plus any
/// manual tokens; otherwise the manual token(s) passthrough. `None` when off, or
/// when auto can't mint and no manual token is set.
pub async fn download_extractor_args(url: &str, settings: &crate::AppSettings) -> Option<String> {
    if settings.po_token_mode == "off" {
        return None;
    }
    let manual = parse_manual(settings.po_token.as_deref());
    if settings.po_token_mode == "auto" && youtube_video_id(url).is_some() {
        if let Some((token, visitor_data)) = mint_session().await {
            let mut tokens: Vec<String> = WEB_CLIENTS
                .iter()
                .map(|c| format!("{c}.gvs+{token}"))
                .collect();
            tokens.extend(manual);
            return Some(format!(
                "youtube:po_token={};player_client=default,mweb;visitor_data={visitor_data}",
                tokens.join(",")
            ));
        }
    }
    (!manual.is_empty()).then(|| format!("youtube:po_token={}", manual.join(",")))
}

// --------------------------------------------------- `/api/po-token/*` routes

/// A blank page served so the hidden minter WebView runs in the backend's own
/// origin — its `/api/po-token/*` fetches are then same-origin (no CORS). The
/// minter binary injects the bundled bgutils loop as an initialization script.
pub async fn host_page() -> axum::response::Html<&'static str> {
    axum::response::Html(
        "<!doctype html><html><head><meta charset=\"utf-8\"><title>yoink-minter</title></head><body></body></html>",
    )
}

#[derive(Serialize)]
pub struct MintJob {
    pub id: String,
}

/// Long-poll for the next mint job; 204 when there's nothing to do.
pub async fn pending() -> Response {
    match broker().next_job(POLL_WAIT).await {
        Some(id) => {
            crate::log_line("auto-PO: dispatched a mint job to the WebView");
            Json(MintJob { id }).into_response()
        }
        None => StatusCode::NO_CONTENT.into_response(),
    }
}

#[derive(Deserialize)]
pub struct MintResultIn {
    pub id: String,
    pub token: Option<String>,
    pub visitor_data: Option<String>,
    #[serde(default)]
    pub error: Option<String>,
}

/// Fulfill a mint job with the token + visitor_data the WebView produced.
pub async fn result(Json(r): Json<MintResultIn>) -> Json<Value> {
    if let Some(e) = r.error.as_deref().filter(|e| !e.is_empty()) {
        crate::log_line(&format!("auto-PO: WebView mint failed: {e}"));
    }
    let payload = match (r.token, r.visitor_data) {
        (Some(t), Some(v)) if !t.is_empty() && !v.is_empty() => Some(MintResult {
            token: t,
            visitor_data: v,
        }),
        _ => None,
    };
    if payload.is_some() {
        crate::log_line("auto-PO: WebView returned a token");
    }
    let delivered = broker().complete(&r.id, payload);
    Json(json!({ "ok": delivered }))
}

fn default_method() -> String {
    "GET".into()
}

#[derive(Deserialize)]
pub struct ProxyRequest {
    pub url: String,
    #[serde(default = "default_method")]
    pub method: String,
    #[serde(default)]
    pub headers: HashMap<String, String>,
    pub body_b64: Option<String>,
}

#[derive(Serialize)]
pub struct ProxyResponse {
    pub status: u16,
    pub headers: HashMap<String, String>,
    pub body_b64: String,
}

// Only bgutils-js's own traffic (YouTube + Google's BotGuard attestation) may be
// proxied — this endpoint forwards a WebView-chosen request server-side, so it's
// scoped to Google-owned hosts to keep it from becoming a general open proxy.
const ALLOWED_SUFFIXES: &[&str] = &[
    ".youtube.com",
    ".google.com",
    ".googleapis.com",
    ".gstatic.com",
    ".googlevideo.com",
    ".ytimg.com",
];
const PROXY_TIMEOUT: Duration = Duration::from_secs(15);
const PROXY_MAX_BYTES: usize = 4 * 1024 * 1024; // BotGuard payloads are small

fn host_allowed(host: Option<&str>) -> bool {
    let Some(h) = host else { return false };
    let low = h.to_lowercase();
    ALLOWED_SUFFIXES
        .iter()
        .any(|s| low == s[1..] || low.ends_with(s))
}

fn ip_is_public(ip: IpAddr) -> bool {
    match ip {
        IpAddr::V4(v4) => {
            let o = v4.octets();
            !(v4.is_private()
                || v4.is_loopback()
                || v4.is_link_local()
                || v4.is_broadcast()
                || v4.is_unspecified()
                || o[0] == 0
                || (o[0] == 100 && (o[1] & 0xc0) == 0x40) // 100.64/10 CGNAT
                || (o[0] == 192 && o[1] == 0 && o[2] == 0) // 192.0.0/24
                || (o[0] == 192 && o[1] == 0 && o[2] == 2) // 192.0.2/24 TEST-NET
                || o[0] >= 240) // reserved / 240.0.0.0+
        }
        IpAddr::V6(v6) => {
            let seg = v6.segments();
            !(v6.is_loopback()
                || v6.is_unspecified()
                || (seg[0] & 0xfe00) == 0xfc00 // fc00::/7 unique-local
                || (seg[0] & 0xffc0) == 0xfe80) // fe80::/10 link-local
        }
    }
}

/// True if the host resolves to (or is) a non-public address — SSRF guard, so a
/// Google-looking name that points at a private/loopback IP is refused.
async fn host_is_blocked(host: Option<&str>) -> bool {
    let Some(h) = host else { return true };
    if let Ok(ip) = h.parse::<IpAddr>() {
        return !ip_is_public(ip);
    }
    match tokio::net::lookup_host((h, 443u16)).await {
        Ok(addrs) => {
            let addrs: Vec<_> = addrs.collect();
            addrs.is_empty() || addrs.iter().any(|a| !ip_is_public(a.ip()))
        }
        Err(_) => true,
    }
}

/// Forward one bgutils-js request to a Google host and return the response.
/// Scoped to Google-owned hosts, http(s), a public address, and a small size cap,
/// so it can't become a general proxy against arbitrary or internal services.
pub async fn proxy(
    Json(req): Json<ProxyRequest>,
) -> Result<Json<ProxyResponse>, (StatusCode, String)> {
    let bad = |m: &str| (StatusCode::BAD_REQUEST, m.to_string());
    let url = reqwest::Url::parse(&req.url).map_err(|_| bad("Invalid URL."))?;
    if !matches!(url.scheme(), "http" | "https")
        || !host_allowed(url.host_str())
        || host_is_blocked(url.host_str()).await
    {
        return Err(bad("URL is not an allowed PO-token host."));
    }
    crate::log_line(&format!(
        "auto-PO: proxying a bgutils request to {}",
        url.host_str().unwrap_or("?")
    ));
    let method = reqwest::Method::from_bytes(req.method.to_uppercase().as_bytes())
        .map_err(|_| bad("Invalid method."))?;
    let body = match req.body_b64.as_deref() {
        Some(b) => Some(
            BASE64_STANDARD
                .decode(b)
                .map_err(|_| bad("Invalid body_b64."))?,
        ),
        None => None,
    };

    let client = reqwest::Client::builder()
        .timeout(PROXY_TIMEOUT)
        .build()
        .map_err(|e| (StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;
    let mut rb = client.request(method, url);
    for (k, v) in &req.headers {
        rb = rb.header(k, v);
    }
    if let Some(b) = body {
        rb = rb.body(b);
    }

    // A non-2xx is a valid answer bgutils-js may need to see (401/403) — reqwest
    // only errors on transport failure, so those bodies flow through naturally.
    let resp = rb
        .send()
        .await
        .map_err(|_| (StatusCode::BAD_GATEWAY, "Upstream request failed.".into()))?;
    let status = resp.status().as_u16();
    let ctype = resp
        .headers()
        .get("content-type")
        .and_then(|v| v.to_str().ok())
        .map(String::from);
    let bytes = resp
        .bytes()
        .await
        .map_err(|_| (StatusCode::BAD_GATEWAY, "Upstream read failed.".into()))?;
    if bytes.len() > PROXY_MAX_BYTES {
        return Err((
            StatusCode::BAD_GATEWAY,
            "Upstream response too large.".into(),
        ));
    }
    let mut headers = HashMap::new();
    if let Some(ct) = ctype {
        headers.insert("content-type".to_string(), ct);
    }
    Ok(Json(ProxyResponse {
        status,
        headers,
        body_b64: BASE64_STANDARD.encode(&bytes),
    }))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn video_id_matches_url_shapes() {
        assert_eq!(
            youtube_video_id("https://youtu.be/dQw4w9WgXcQ").as_deref(),
            Some("dQw4w9WgXcQ")
        );
        assert_eq!(
            youtube_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=1").as_deref(),
            Some("dQw4w9WgXcQ")
        );
        assert_eq!(
            youtube_video_id("https://www.youtube.com/shorts/abcdefghijk").as_deref(),
            Some("abcdefghijk")
        );
        assert_eq!(youtube_video_id("https://soundcloud.com/x/y"), None);
    }

    #[test]
    fn manual_tokens_split_and_clean() {
        assert_eq!(parse_manual(Some(" a , b ,, c ")), vec!["a", "b", "c"]);
        assert!(parse_manual(None).is_empty());
        assert!(parse_manual(Some("  ")).is_empty());
    }

    #[test]
    fn proxy_host_allowlist() {
        assert!(host_allowed(Some("www.youtube.com")));
        assert!(host_allowed(Some("youtube.com")));
        assert!(host_allowed(Some("rr3---sn-x.googlevideo.com")));
        assert!(!host_allowed(Some("youtube.com.evil.test")));
        assert!(!host_allowed(Some("example.com")));
        assert!(!host_allowed(None));
    }

    #[test]
    fn private_ips_are_not_public() {
        for ip in [
            "127.0.0.1",
            "10.0.0.5",
            "192.168.1.1",
            "169.254.1.1",
            "100.64.0.1",
            "::1",
            "fe80::1",
            "fc00::1",
        ] {
            assert!(
                !ip_is_public(ip.parse().unwrap()),
                "{ip} should be non-public"
            );
        }
        for ip in ["8.8.8.8", "142.250.80.46", "2001:4860:4860::8888"] {
            assert!(ip_is_public(ip.parse().unwrap()), "{ip} should be public");
        }
    }

    #[tokio::test]
    async fn broker_submit_without_poller_times_out() {
        clear_cache();
        // No WebView has polled → has_active_poller is false → mint skipped fast.
        assert!(!broker().has_active_poller());
        assert!(mint_via_webview().await.is_none());
    }

    #[tokio::test]
    async fn broker_roundtrip_delivers_result() {
        let b = broker();
        // A poller claims a job, then completes it; the submitter gets the result.
        let submit = tokio::spawn(async { b.submit_mint(Duration::from_secs(5)).await });
        tokio::time::sleep(Duration::from_millis(50)).await;
        let id = b.next_job(Duration::from_secs(2)).await.expect("a job");
        assert!(b.complete(
            &id,
            Some(MintResult {
                token: "T".into(),
                visitor_data: "V".into()
            })
        ));
        let got = submit.await.unwrap().expect("a result");
        assert_eq!((got.token.as_str(), got.visitor_data.as_str()), ("T", "V"));
    }
}
