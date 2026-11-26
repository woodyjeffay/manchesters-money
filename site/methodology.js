// "About the data" page. The text lives in copy/methodology.md so it can be edited on GitHub.
fetch("copy/methodology.md", { cache: "no-cache" }).then((r) => {
  if (!r.ok) throw new Error(r.status);
  return r.text();
}).then((md) => {
  const el = document.getElementById("method");
  el.innerHTML = marked.parse(md.replace(/<!--[\s\S]*?-->/g, ""));
  el.removeAttribute("aria-busy");
  // External links open in a new tab; in-page anchors still work.
  el.querySelectorAll('a[href^="http"]').forEach((a) => { a.target = "_blank"; a.rel = "noopener noreferrer"; });
  if (location.hash) document.getElementById(location.hash.slice(1))?.scrollIntoView();
}).catch(() => {
  document.getElementById("method").innerHTML =
    '<p>This page could not be loaded. Please refresh, or read it on <a href="https://github.com/woodyjeffay/manchesters-money/blob/main/site/copy/methodology.md">GitHub</a>.</p>';
});

// --- CSV of everything on the map (properties and food & drink businesses) ----
const COLS = ["id", "kind", "name", "address", "postcode", "area", "registered_owner", "ultimate_owner",
  "ultimate_country", "owner_type", "property_type", "title_count", "title_numbers", "evidence", "sources"];
const NOTE = "Contains HM Land Registry data (c) Crown copyright and database right 2026, Companies House data and Food Standards Agency data, all licensed under the Open Government Licence v3.0.";

// Quote where needed, and stop spreadsheet apps treating text as a formula (=, +, -, @ at the start).
function cell(v) {
  let s = Array.isArray(v) ? v.join(" | ") : String(v ?? "");
  if (/^[=+\-@\t\r]/.test(s)) s = "'" + s;
  return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

document.getElementById("download-csv").addEventListener("click", async (e) => {
  const btn = e.currentTarget, status = document.getElementById("download-status");
  btn.disabled = true;
  status.textContent = " Preparing…";
  try {
    const get = (u) => fetch(u).then((r) => r.ok ? r.json() : { features: [] });
    const [props, venues] = await Promise.all([get("data/properties.geojson"), get("data/venues.geojson")]);
    const rows = [...(props.features || []), ...(venues.features || [])].map((f) => f.properties).map((p) => p.business_type
      ? { ...p, kind: "business", registered_owner: p.operator, property_type: p.business_type, evidence: "name match" }
      : { ...p, kind: "property", title_count: p.title_count || 1 });
    if (!rows.length) throw new Error("empty");
    const csv = [COLS.join(","), ...rows.map((r) => COLS.map((c) => cell(r[c])).join(",")), "", cell(NOTE)].join("\n");
    const a = Object.assign(document.createElement("a"), {
      href: URL.createObjectURL(new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8" })), download: "manchesters-money.csv" });
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    status.textContent = ` ${rows.length.toLocaleString("en-GB")} rows.`;
  } catch {
    status.textContent = " Sorry, the download failed. Please try again.";
  }
  btn.disabled = false;
});
