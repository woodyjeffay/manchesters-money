// POST /api/corrections — store a suggested correction for manual review.
// Submissions go to a PRIVATE Vercel Blob store under corrections/YYYY-MM-DD/.
// Nothing here changes the map; the editor reviews them and edits
// data/curated/overrides.csv by hand.
import { put } from "@vercel/blob";

const LIMITS = { property_id: 40, property_name: 200, correction: 4000, source: 1000, contact: 200 };

export async function POST(request) {
  let body;
  try {
    body = await request.json();
  } catch {
    return Response.json({ error: "Invalid JSON" }, { status: 400 });
  }

  // Honeypot: real users never fill this hidden field.
  if (body.website) return Response.json({ ok: true });

  const clean = {};
  for (const [key, max] of Object.entries(LIMITS)) {
    const v = typeof body[key] === "string" ? body[key].trim() : "";
    if (v.length > max) return Response.json({ error: `${key} is too long` }, { status: 400 });
    clean[key] = v;
  }
  if (clean.correction.length < 10) {
    return Response.json({ error: "Please describe the correction" }, { status: 400 });
  }

  const now = new Date();
  const id = `${now.toISOString().replace(/[:.]/g, "-")}-${crypto.randomUUID().slice(0, 8)}`;
  const record = { id, received_at: now.toISOString(), status: "new", ...clean };

  await put(`corrections/${now.toISOString().slice(0, 10)}/${id}.json`, JSON.stringify(record, null, 2), {
    access: "private",
    contentType: "application/json",
    addRandomSuffix: false,
  });
  return Response.json({ ok: true, id });
}
