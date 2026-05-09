// Electricians NOW telemetry worker
// Receives HMAC-signed event batches from the iOS app, stores them in
// Cloudflare KV, and exposes a read endpoint for triage.
//
// Routes:
//   POST /ingest   — body: {events:[...], session_id, app_version, device}
//                    headers: X-Sig: hmac-sha256-hex(body, HMAC_KEY)
//                    Returns 204 on success, 401 on bad signature.
//   GET  /events?since=<iso>&limit=200
//                    headers: Authorization: Bearer <READ_TOKEN>
//                    Returns {events: [...]}
//
// Required env bindings:
//   HMAC_KEY      — shared secret with the iOS app
//   READ_TOKEN    — bearer token for /events
//   TELEMETRY_KV  — KV namespace binding for storage

async function hmacHex(key, message) {
  const enc = new TextEncoder();
  const cryptoKey = await crypto.subtle.importKey(
    'raw', enc.encode(key),
    { name: 'HMAC', hash: 'SHA-256' },
    false, ['sign']
  );
  const sig = await crypto.subtle.sign('HMAC', cryptoKey, enc.encode(message));
  return Array.from(new Uint8Array(sig))
    .map(b => b.toString(16).padStart(2, '0'))
    .join('');
}

function timingSafeEqual(a, b) {
  if (a.length !== b.length) return false;
  let result = 0;
  for (let i = 0; i < a.length; i++) result |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return result === 0;
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (request.method === 'POST' && url.pathname === '/ingest') {
      const body = await request.text();
      const sig = request.headers.get('X-Sig') || '';
      const expected = await hmacHex(env.HMAC_KEY, body);
      if (!timingSafeEqual(sig, expected)) {
        return new Response('bad signature', { status: 401 });
      }
      let payload;
      try { payload = JSON.parse(body); }
      catch { return new Response('bad json', { status: 400 }); }

      const events = payload.events || [];
      const sessionId = payload.session_id || 'unknown';
      const ts = new Date();
      const dateKey = ts.toISOString().slice(0, 10);

      // Each event gets its own KV entry for granular retrieval.
      let seq = 0;
      for (const ev of events) {
        const key = `telemetry/${dateKey}/${ts.getTime()}_${sessionId}_${seq++}`;
        await env.TELEMETRY_KV.put(key, JSON.stringify({
          ...ev,
          _session: sessionId,
          _app_version: payload.app_version,
          _device: payload.device,
          _received_at: ts.toISOString(),
        }), { expirationTtl: 60 * 60 * 24 * 30 });  // 30 day retention
      }
      return new Response(null, { status: 204 });
    }

    if (request.method === 'GET' && url.pathname === '/events') {
      const auth = request.headers.get('Authorization') || '';
      if (auth !== `Bearer ${env.READ_TOKEN}`) {
        return new Response('unauthorized', { status: 401 });
      }
      const since = url.searchParams.get('since') || '1970-01-01';
      const limit = Math.min(parseInt(url.searchParams.get('limit') || '200'), 1000);
      const sinceDate = since.slice(0, 10);

      const list = await env.TELEMETRY_KV.list({ prefix: `telemetry/`, limit });
      const wanted = list.keys.filter(k => k.name.split('/')[1] >= sinceDate);
      const events = [];
      for (const k of wanted) {
        const v = await env.TELEMETRY_KV.get(k.name);
        if (v) events.push(JSON.parse(v));
      }
      events.sort((a, b) => (a._received_at < b._received_at ? -1 : 1));
      return new Response(JSON.stringify({ events, count: events.length }, null, 2), {
        headers: { 'content-type': 'application/json' }
      });
    }

    if (url.pathname === '/health') {
      return new Response('ok');
    }

    return new Response('not found', { status: 404 });
  }
};
