// POST /api/corrections — store a suggested correction for manual review.
// Submissions go to a PRIVATE Vercel Blob store under corrections/YYYY-MM-DD/.
// Nothing here changes the map; the editor reviews them and edits
// data/curated/overrides.csv by hand.
//
// Defences: same-origin only, JSON only, small bodies only, length limits per
// field, control characters stripped, a hidden honeypot field, a minimum time
// between opening the form and sending it, and a per-IP rate limit. The IP is
// used only for that limit and is never stored.
import { put } from "@vercel/blob";

const LIMITS = { property_id: 40, property_name: 200, correction: 4000, source: 1000, contact: 200 };
const MAX_BODY = 16 * 1024;          // bytes
const MIN_FILL_MS = 3000;            // humans take longer than this to write a correction
const RATE = { max: 5, windowMs: 10 * 60 * 1000 };

const reply = (body, status = 200) =>
  Response.json(body, { status, headers: { "Cache-Control": "no-store" } });

// Best-effort limit per server instance (Vercel reuses warm instances).
const hits = new Map();
function rateLimited(ip) {
  const now = Date.now();
  const recent = (hits.get(ip) || []).filter((t) => now - t < RATE.windowMs);
  recent.push(now);
  hits.set(ip, recent);
  if (hits.size > 5000) for (const [k, v] of hits) if (now - v.at(-1) > RATE.windowMs) hits.delete(k);
  return recent.length > RATE.max;
}

// Keep newlines and tabs; drop other control and bidi-override characters.
const clean = (v) => v.replace(/\r\n?/g, "\n").replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F‪-‮⁦-⁩]/g, "").trim();

function sameOrigin(request) {
  const origin = request.headers.get("origin");
  if (!origin) return false;
  try {
    return new URL(origin).host === (request.headers.get("x-forwarded-host") || request.headers.get("host"));
  } catch {
    return false;
  }
}

export async function POST(request) {
  if (!sameOrigin(request)) return reply({ error: "Forbidden" }, 403);
  if (!(request.headers.get("content-type") || "").startsWith("application/json")) {
    return reply({ error: "Expected JSON" }, 415);
  }
  if (Number(request.headers.get("content-length")) > MAX_BODY) return reply({ error: "Too large" }, 413);

  const ip = (request.headers.get("x-forwarded-for") || "").split(",")[0].trim() || "unknown";
  if (rateLimited(ip)) return reply({ error: "Too many suggestions. Please try again later." }, 429);

  let body;
  try {
    const text = await request.text();
    if (text.length > MAX_BODY) return reply({ error: "Too large" }, 413);
    body = JSON.parse(text);
  } catch {
    return reply({ error: "Invalid JSON" }, 400);
  }
  if (!body || typeof body !== "object" || Array.isArray(body)) return reply({ error: "Invalid JSON" }, 400);

  // Bots: a filled honeypot, or a form sent too soon after opening. Pretend it worked.
  const opened = Number(body.opened_at);
  if (body.website || !opened || Date.now() - opened < MIN_FILL_MS) return reply({ ok: true });

  const record = {};
  for (const [key, max] of Object.entries(LIMITS)) {
    const v = typeof body[key] === "string" ? clean(body[key]) : "";
    if (v.length > max) return reply({ error: `${key} is too long` }, 400);
    record[key] = v;
  }
  if (record.correction.length < 10) return reply({ error: "Please describe the correction" }, 400);
  if (record.contact && !/^[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+$/.test(record.contact)) {
    return reply({ error: "Please check the email address" }, 400);
  }
  if (record.property_id && !/^[\w.:-]+$/.test(record.property_id)) return reply({ error: "Invalid property" }, 400);

  const now = new Date();
  const id = `${now.toISOString().replace(/[:.]/g, "-")}-${crypto.randomUUID().slice(0, 8)}`;
  try {
    await put(`corrections/${now.toISOString().slice(0, 10)}/${id}.json`,
      JSON.stringify({ id, received_at: now.toISOString(), status: "new", ...record }, null, 2), {
        access: "private",
        contentType: "application/json",
        addRandomSuffix: false,
      });
  } catch (err) {
    console.error("corrections: store failed", err?.message);
    return reply({ error: "Could not save. Please try again." }, 500);
  }
  return reply({ ok: true, id });
}
