const ORIGIN = 'https://linux.do';
const json = (data, status = 200) => Response.json(data, { status, headers: { 'Cache-Control': 'no-store' } });
const problem = (code, status = 400) => Object.assign(new Error(code), { status });

async function boundedText(message, limit) {
  if (Number(message.headers.get('content-length')) > limit) throw problem('body_too_large', 413);
  if (!message.body) return '';
  const reader = message.body.getReader();
  const chunks = [];
  let size = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    size += value.length;
    if (size > limit) { await reader.cancel(); throw problem('body_too_large', 413); }
    chunks.push(value);
  }
  const bytes = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.length; }
  return new TextDecoder().decode(bytes);
}

function normalizeCookie(raw) {
  if (typeof raw !== 'string') throw problem('paste_only_t_value');
  let token = raw.trim().replace(/^_t=/, '');
  if (!token || token.length > 8192 || /[^\x21-\x7e]|;/.test(token)) throw problem('paste_only_t_value');
  return '_t=' + encodeURIComponent(token).replace(/%25/g, '%').replace(/[!'()*]/g, c => '%' + c.charCodeAt(0).toString(16).toUpperCase());
}

async function authorized(request, env) {
  if (!env.POC_TOKEN || env.POC_TOKEN.length < 32) return false;
  const expected = 'Bearer ' + env.POC_TOKEN;
  const supplied = request.headers.get('Authorization') || '';
  if (supplied.length !== expected.length) return false;
  const digest = s => crypto.subtle.digest('SHA-256', new TextEncoder().encode(s));
  const [a, b] = await Promise.all([digest(expected), digest(supplied)]);
  return new Uint8Array(a).every((v, i) => v === new Uint8Array(b)[i]);
}

export default {
  async fetch(request, env) {
    if (!await authorized(request, env)) return json({ error: 'unauthorized' }, 401);
    const path = new URL(request.url).pathname;
    if (!['/status', '/probe', '/cookie', '/whoami', '/search', '/topic'].includes(path)) return json({ error: 'not_found' }, 404);
    if (request.method !== 'POST') return json({ error: 'use_post' }, 405);
    return env.SESSION.get(env.SESSION.idFromName('personal-test')).fetch(request);
  }
};

export class Session {
  constructor(ctx, env) { this.ctx = ctx; this.env = env; this.queue = Promise.resolve(); this.pending = 0; }

  async fetch(request) {
    if (!await authorized(request, this.env)) return json({ error: 'unauthorized' }, 401);
    if (this.pending >= 4) return json({ error: 'busy' }, 429);
    this.pending++;
    // ponytail: one personal session; keep read -> fetch -> cookie rotation serialized.
    const operation = this.queue.then(() => this.handle(request));
    this.queue = operation.catch(() => {});
    try { return await operation; }
    catch (e) { return json({ error: e.status ? e.message : 'request_failed' }, e.status || 502); }
    finally { this.pending--; }
  }

  async handle(request) {
    const path = new URL(request.url).pathname;
    let input;
    try { input = JSON.parse(await boundedText(request, 12000) || '{}'); }
    catch (e) { if (e.status) throw e; throw problem('invalid_json'); }
    if (!input || typeof input !== 'object' || Array.isArray(input)) throw problem('invalid_json');
    const state = await this.ctx.storage.get('session') || { rotations: 0 };
    if (path === '/status') return json({ configured: !!state.cookie, rotations: state.rotations, validated_at: state.validated_at || null });
    let target;
    if (path === '/probe') target = '/site.json';
    else if (path === '/cookie' || path === '/whoami') target = '/session/current.json';
    else if (path === '/search') {
      if (typeof input.q !== 'string' || !input.q.trim() || input.q.length > 200) throw problem('invalid_query');
      target = '/search.json?' + new URLSearchParams({ q: input.q.trim(), page: '1' });
    } else if (path === '/topic') {
      if (!Number.isSafeInteger(input.id) || input.id <= 0) throw problem('invalid_topic_id');
      target = '/t/' + input.id + '.json';
    } else throw problem('not_found', 404);

    const candidate = path === '/cookie';
    const cookie = path === '/probe' ? '' : candidate ? normalizeCookie(input.cookie) : state.cookie;
    if (path !== '/probe' && !cookie) throw problem('cookie_required', 409);
    const headers = { Accept: 'application/json', 'User-Agent': 'LinuxDo-Workers-PoC/0.1', 'X-Requested-With': 'XMLHttpRequest' };
    // Header-only control, NOT TLS impersonation; only allowed on the anonymous probe.
    if (path === '/probe' && input.browser_headers === true) headers['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36';
    if (cookie) headers.Cookie = cookie;
    const response = await fetch(ORIGIN + target, { headers, redirect: 'manual', signal: AbortSignal.timeout(15000) });
    const meta = { upstream_status: response.status, challenge: response.headers.get('cf-mitigated') === 'challenge', content_type: response.headers.get('content-type') || '' };
    let nextCookie = cookie;
    let rotation = false;
    for (const setCookie of response.headers.getSetCookie()) {
      if (!setCookie.startsWith('_t=')) continue;
      const value = setCookie.split(';', 1)[0];
      const deleted = value === '_t=' || /(?:^|;)\s*max-age=0(?:;|$)/i.test(setCookie);
      const updated = deleted ? '' : normalizeCookie(value);
      rotation ||= updated !== nextCookie;
      nextCookie = updated;
    }
    // Save a current session's rotation even if the body later fails to parse.
    if (!candidate && cookie && rotation) {
      state.cookie = nextCookie;
      state.rotations++;
      await this.ctx.storage.put('session', state);
    }
    const body = await boundedText(response, 2 * 1024 * 1024);
    let data;
    try { data = JSON.parse(body); } catch { /* Never echo HTML/challenge pages or cookie headers. */ }
    if (!response.ok || meta.challenge || !data) return json({ error: meta.challenge ? 'cloudflare_challenge' : 'upstream_rejected', ...meta }, 502);
    if (path === '/probe') return json({ ok: true, ...meta, categories: data.categories?.length ?? null });
    if (path === '/cookie' || path === '/whoami') {
      if (!data.current_user?.id || !nextCookie) return json({ error: 'not_logged_in', ...meta }, 401);
      state.cookie = nextCookie;
      state.validated_at = new Date().toISOString();
      if (candidate && rotation) state.rotations++;
      await this.ctx.storage.put('session', state);
      return json({ ok: true, ...meta, user: { id: data.current_user.id, username: data.current_user.username }, cookie_rotated: rotation, rotations: state.rotations });
    }
    if (path === '/search') return json({ ok: true, ...meta, page: 1, topics: (data.topics || []).slice(0, 10).map(t => ({ id: t.id, title: t.title, url: ORIGIN + '/t/' + t.id })), post_count: data.posts?.length || 0, cookie_rotated: rotation });
    return json({ ok: true, ...meta, id: data.id, title: data.title, url: ORIGIN + '/t/' + data.id, posts: (data.post_stream?.posts || []).slice(0, 3).map(p => ({ post_number: p.post_number, cooked: (p.cooked || '').slice(0, 10000) })), cookie_rotated: rotation });
  }
}
