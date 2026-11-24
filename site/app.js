const TYPE_LABELS = {
  state: "State-linked", institutional: "Institutional", corporate: "Corporate",
  individual: "Individual", unknown: "Unknown / opaque",
};
const COLORS = Object.fromEntries(Object.keys(TYPE_LABELS).map(
  (t) => [t, getComputedStyle(document.documentElement).getPropertyValue(`--${t}`).trim()]));
const COUNTRY_NAMES = new Intl.DisplayNames(["en"], { type: "region" });
const countryName = (c) => {
  if (!c) return "Not established";
  try { return COUNTRY_NAMES.of(c) || c; } catch { return c; }
};
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const gbp = (n) => n ? "£" + Number(n).toLocaleString("en-GB") : null;

// --- Kinds of place: each has its own marker shape --------------------------
const KINDS = {
  homes:       { label: "Homes & flats", shape: "square" },
  hospitality: { label: "Hotels, pubs & restaurants", shape: "diamond" },
  land:        { label: "Land & sites", shape: "triangle" },
  other:       { label: "Offices, shops & other", shape: "circle" },
  venue:       { label: "Food & drink firms", shape: "star" },
  minor:       { label: "Parking & ground rents", shape: "ring" },
};
const kindOf = (p) => p.business_type ? "venue"
  : (p.parking_only || p.property_type === "parking" || p.property_type === "ground_rent") ? "minor"
  : p.property_type === "residential" ? "homes"
  : p.property_type === "hospitality" ? "hospitality"
  : p.property_type === "land" ? "land" : "other";

function shapeSVG(shape, color, size = 12, stroke = "#fff") {
  const h = size / 2, w = 1.6;
  const body = {
    square: `<rect x="${w}" y="${w}" width="${size - 2 * w}" height="${size - 2 * w}" rx="1.5"/>`,
    diamond: `<path d="M${h} ${w * 0.6}L${size - w * 0.6} ${h}L${h} ${size - w * 0.6}L${w * 0.6} ${h}Z"/>`,
    triangle: `<path d="M${h} ${w}L${size - w} ${size - w * 1.2}H${w}Z"/>`,
    circle: `<circle cx="${h}" cy="${h}" r="${h - w}"/>`,
    star: `<path d="${star(h, h, h - w * 0.4, (h - w) * 0.45)}"/>`,
    ring: `<circle cx="${h}" cy="${h}" r="${h - w * 1.6}" fill="#fff" stroke="${color}" stroke-width="${w * 1.6}"/>`,
  }[shape];
  return `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" fill="${color}" stroke="${stroke}" stroke-width="${w}" stroke-linejoin="round">${body}</svg>`;
}
function star(cx, cy, r1, r2) {
  let d = "";
  for (let i = 0; i < 10; i++) {
    const r = i % 2 ? r2 : r1, a = Math.PI / 5 * i - Math.PI / 2;
    d += `${i ? "L" : "M"}${(cx + r * Math.cos(a)).toFixed(2)} ${(cy + r * Math.sin(a)).toFixed(2)}`;
  }
  return d + "Z";
}

// --- Map ------------------------------------------------------------------------
const map = L.map("map", {
  zoomControl: true, maxZoom: 19, minZoom: 9,
  maxBounds: [[53.20, -2.90], [53.75, -1.70]], maxBoundsViscosity: 0.8,
}).setView([53.4795, -2.2425], 14);
// If the page loads in a hidden tab the map measures 0x0; re-measure when it becomes visible.
document.addEventListener("visibilitychange", () => { if (!document.hidden) map.invalidateSize(); });
window.addEventListener("resize", () => map.invalidateSize());

// OpenFreeMap "positron" (free, no key: https://openfreemap.org), recoloured to a warm paper palette.
const BASE = {
  background: "#f3ece1", park: "#dfe7d0", landcover_wood: "#d7e2c6", water: "#a9cbdd", waterway: "#a9cbdd",
  landuse_residential: "#efe6d8", building: "#e7dccb", "aeroway-area": "#efe6d8",
};
fetch("https://tiles.openfreemap.org/styles/positron").then((r) => r.json()).then((style) => {
  for (const l of style.layers) {
    const p = l.paint ||= {};
    if (BASE[l.id]) p[l.type === "line" ? "line-color" : l.type === "background" ? "background-color" : "fill-color"] = BASE[l.id];
    if (l.id === "building") p["fill-outline-color"] = "#dccdb7";
    if (/casing/.test(l.id)) p["line-color"] = "#e3d5c0";
    if (/highway_minor|highway_path/.test(l.id)) p["line-color"] = "#fffaf2";
    if (/highway_(major|motorway).*inner/.test(l.id)) p["line-color"] = "#fff7ea";
    if (/^railway/.test(l.id) && !/dash/.test(l.id)) p["line-color"] = "#d4c6b1";
    if (/^railway.*dash/.test(l.id)) p["line-color"] = "#f3ece1";
    if (/^boundary/.test(l.id)) p["line-color"] = "#c9b9a2";
    if (l.type === "symbol" && p["text-color"]) {
      p["text-color"] = /water/.test(l.id) ? "#4a7591" : /label_(city|town)/.test(l.id) ? "#2a2520" : "#6f665b";
      p["text-halo-color"] = "#f6efe4";
    }
  }
  L.maplibreGL({
    style,
    attribution: '<a href="https://openfreemap.org" target="_blank">OpenFreeMap</a> © <a href="https://www.openmaptiles.org/" target="_blank">OpenMapTiles</a> Data from <a href="https://www.openstreetmap.org/copyright" target="_blank">OpenStreetMap</a>',
  }).addTo(map);
});

// Individual markers when zoomed in (so shapes are readable); neutral clusters when zoomed out.
const layer = L.markerClusterGroup({
  maxClusterRadius: 45, disableClusteringAtZoom: 14, spiderfyOnMaxZoom: false, showCoverageOnHover: false,
  iconCreateFunction: (cluster) => {
    const n = cluster.getChildCount();
    const size = n < 10 ? 28 : n < 100 ? 34 : 42;
    return L.divIcon({ html: `<div>${n}</div>`, className: "cluster", iconSize: [size, size] });
  },
}).addTo(map);
const zoomClass = () => map.getContainer().classList.toggle("z-far", map.getZoom() < 14);
map.on("zoomend", zoomClass); zoomClass();

// --- State and data ---------------------------------------------------------------
const state = { area: "", country: "", type: "", kind: "", owner: "", q: "" };
const ownerKey = (p) => p.ultimate_owner || p.registered_owner || p.name;
let features = [];   // property titles (grouped by building)
let venues = [];     // food & drink businesses
const all = () => features.concat(venues);

fetch("data/venues.geojson").then((r) => r.ok ? r.json() : { features: [] }).then((gj) => {
  venues = gj.features; render();
}).catch(() => {});

fetch("data/properties.geojson").then((r) => r.json()).then((gj) => {
  features = gj.features;
  const m = gj.meta || {};
  const month = (ym) => ym ? new Date(ym + "-01").toLocaleDateString("en-GB", { month: "long", year: "numeric" }) : null;
  document.getElementById("updated").textContent = gj.generated
    ? `Updated ${new Date(gj.generated).toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" })}`
      + (m.ocod ? ` · Land Registry ${month(m.ocod)}` : "") : "";
  const areas = unique((p) => p.area || "").filter(Boolean);
  fillSelect("f-area", areas, (a) => a);
  document.getElementById("f-area").hidden = areas.length < 2;
  if (areas.length > 1) document.getElementById("tagline").textContent =
    `Property in ${areas.slice(0, -1).join(", ")} and ${areas.at(-1)} controlled from outside the UK.`;
  render();
  // Open on the city centre, where the holdings are densest; the list and clusters show the rest.
  map.invalidateSize();
  map.setView([53.4795, -2.2425], 14);
});

function unique(fn) {
  return [...new Set(features.map((f) => fn(f.properties)))].sort((a, b) => String(a).localeCompare(String(b)));
}
function fillSelect(id, values, label) {
  const el = document.getElementById(id);
  for (const v of values) el.insertAdjacentHTML("beforeend", `<option value="${esc(v)}">${esc(label(v))}</option>`);
}

const filters = { area: "f-area", country: "f-country" };
for (const [k, id] of Object.entries(filters)) {
  document.getElementById(id).addEventListener("change", (e) => { state[k] = e.target.value; render(); });
}
let qTimer;
document.getElementById("q").addEventListener("input", (e) => {
  clearTimeout(qTimer);
  qTimer = setTimeout(() => { state.q = e.target.value.trim().toLowerCase(); render(); }, 150);
});
document.getElementById("reset").addEventListener("click", () => {
  Object.assign(state, { area: "", country: "", type: "", kind: "", owner: "", q: "" });
  for (const id of Object.values(filters)) document.getElementById(id).value = "";
  document.getElementById("q").value = "";
  render();
});
function setOwner(o) { state.owner = o; render(); if (o) document.getElementById("panel").hidden = true; }

const haystack = (p) => (p._hay ||= [p.name, p.address, p.postcode, p.registered_owner, p.ultimate_owner, p.operator,
  countryName(p.ultimate_country)].filter(Boolean).join(" ").toLowerCase());

function matches(p, skip) {
  const k = kindOf(p);
  return (!state.area || p.area === state.area)
    && (skip === "country" || !state.country || (p.ultimate_country || "") === state.country)
    && (skip === "type" || !state.type || p.owner_type === state.type)
    && (skip === "owner" || !state.owner || ownerKey(p) === state.owner)
    && (!state.q || haystack(p).includes(state.q))
    // Parking/storage and ground rents are hidden unless that card is chosen.
    && (skip === "kind" ? true : state.kind ? k === state.kind : k !== "minor");
}

let shown = [];
function render() {
  layer.clearLayers();
  shown = all().filter((f) => matches(f.properties));
  const markers = shown.map((f) => {
    const p = f.properties, k = kindOf(p);
    const [lon, lat] = f.geometry.coordinates;
    const size = (p.title_count || 1) >= 20 ? 22 : (p.title_count || 1) >= 5 ? 18 : 15;
    return L.marker([lat, lon], {
      icon: L.divIcon({ className: "mk", html: shapeSVG(KINDS[k].shape, COLORS[p.owner_type] || COLORS.unknown, size),
        iconSize: [size, size] }),
      riseOnHover: true,
    }).bindTooltip(`<b>${esc(p.name)}</b><br>${esc(KINDS[k].label)} · ${esc(p.ultimate_owner || p.registered_owner || "")}`)
      .on("click", () => openPanel(p));
  });
  layer.addLayers(markers);
  const chip = document.getElementById("owner-chip");
  chip.hidden = !state.owner;
  chip.innerHTML = state.owner ? `Owner: ${esc(state.owner)} <button type="button" aria-label="Clear owner filter">×</button>` : "";
  if (state.owner) chip.querySelector("button").onclick = () => setOwner("");
  renderCards();
  renderCounters();
  renderList();
}

function renderCards() {
  const n = {};
  for (const f of all()) if (matches(f.properties, "kind")) { const k = kindOf(f.properties); n[k] = (n[k] || 0) + 1; }
  const kinds = Object.keys(KINDS).filter((k) => n[k] || (k === "venue" && venues.length));
  document.getElementById("kind-cards").innerHTML = kinds.map((k) => `
    <button type="button" class="card ${state.kind && state.kind !== k ? "dim" : ""}" data-kind="${k}" aria-pressed="${state.kind === k}">
      <b>${(n[k] || 0).toLocaleString()}</b>
      <span>${shapeSVG(KINDS[k].shape, "#2a2520", 11, "none")}${KINDS[k].label}</span>
    </button>`).join("");
  document.querySelectorAll("[data-kind]").forEach((b) => b.onclick = () => { state.kind = state.kind === b.dataset.kind ? "" : b.dataset.kind; render(); });
}

function renderCounters() {
  // Counts reflect the other active filters, so they stay useful as filters.
  const byType = {}, byCountry = {};
  for (const f of all()) {
    const p = f.properties;
    if (matches(p, "type")) byType[p.owner_type] = (byType[p.owner_type] || 0) + 1;
    if (matches(p, "country") && p.ultimate_country) byCountry[p.ultimate_country] = (byCountry[p.ultimate_country] || 0) + 1;
  }
  document.getElementById("type-counters").innerHTML = Object.keys(TYPE_LABELS).filter((t) => byType[t]).map((t) =>
    `<button class="counter" data-type="${t}" aria-pressed="${state.type === t}"><span class="dot" style="background:${COLORS[t]}"></span>${TYPE_LABELS[t]} <b>${byType[t].toLocaleString()}</b></button>`).join("");
  document.querySelectorAll("[data-type]").forEach((b) => b.onclick = () => { state.type = state.type === b.dataset.type ? "" : b.dataset.type; render(); });
  const sel = document.getElementById("f-country");
  const opts = Object.entries(byCountry).sort((a, b) => b[1] - a[1]);
  if (state.country && !byCountry[state.country]) opts.unshift([state.country, 0]);
  sel.innerHTML = `<option value="">All countries</option>` + opts.map(([c, n]) =>
    `<option value="${esc(c)}">${esc(countryName(c))} (${n.toLocaleString()})</option>`).join("");
  sel.value = state.country;
}

// Places in the current map view, biggest holdings first.
function renderList() {
  const bounds = map.getBounds();
  const inView = shown.filter((f) => bounds.contains([f.geometry.coordinates[1], f.geometry.coordinates[0]]));
  document.getElementById("shown").textContent = `${inView.length.toLocaleString()} places in view`;
  const top = inView.sort((a, b) => (b.properties.title_count || 1) - (a.properties.title_count || 1)).slice(0, 60);
  const list = document.getElementById("place-list");
  list.innerHTML = top.map((f, i) => {
    const p = f.properties, k = kindOf(p);
    return `<li data-i="${i}">${shapeSVG(KINDS[k].shape, COLORS[p.owner_type] || COLORS.unknown, 12)}
      <div><div class="nm">${esc(p.name)}</div>
      <div class="sub">${esc(p.ultimate_owner || p.registered_owner || "Owner not established")} · ${esc(countryName(p.ultimate_country))}</div></div>
      <span class="n">${(p.title_count || 1) > 1 ? `${p.title_count} titles` : ""}</span></li>`;
  }).join("") + (inView.length > top.length ? `<li class="more">+ ${(inView.length - top.length).toLocaleString()} more. Zoom in or search.</li>` : "");
  list.querySelectorAll("li[data-i]").forEach((li) => li.onclick = () => {
    const f = top[+li.dataset.i];
    map.setView([f.geometry.coordinates[1], f.geometry.coordinates[0]], Math.max(map.getZoom(), 16));
    openPanel(f.properties);
    setSheet(false);
  });
}
map.on("moveend", () => { if (features.length) renderList(); });

const FLAG_TEXT = {
  multiple_bo: "Several owners are registered. The chain follows one.",
  mixed_uk_foreign: "Control is shared with a UK owner.",
  multiple_foreign_countries: "The owners are based in more than one country.",
  cycle: "The company records loop back on themselves.",
  max_hops: "The chain was cut off after eight companies.",
  curated_controller: "The last link is added by us from the published source shown, because the register names a fund manager's founder.",
  venue_office_match: "Operator matched by name and registered address.",
  venue_name_match: "Operator matched by name only. The hygiene register doesn't say who runs a business.",
  venue_brand: "Branches of this brand may be run by franchisees.",
  inferred_ground_rent: "Probably a ground rent. Residents usually own the homes on long leases.",
};
function flagNote(flags) {
  const lines = [...new Set((flags || []).map((f) => FLAG_TEXT[f.split("@")[0]]).filter(Boolean))];
  return lines.length ? `<ul class="note">${lines.map((l) => `<li>${esc(l)}</li>`).join("")}</ul>` : "";
}
const fmtDate = (d) => d ? new Date(d).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" }) : "";

function openPanel(p) {
  const k = kindOf(p), venue = k === "venue";
  const link = (s) => s ? ` <a href="${esc(s)}" target="_blank" rel="noopener">↗</a>` : "";
  const chain = (p.chain || []).map((s) => `
    <li><div>${esc(s.name || s.company_number || "Unnamed")}${link(s.source)}</div>
      <div class="j">${esc([s.jurisdiction && (s.jurisdiction.length === 2 ? countryName(s.jurisdiction) : s.jurisdiction),
        s.country_of_residence && `lives in ${s.country_of_residence}`, s.company_number && `No. ${s.company_number}`].filter(Boolean).join(" · "))}</div>
      ${s.note ? `<div class="j">${esc(s.note)}</div>` : ""}</li>`).join("");
  const facts = venue ? [
    ["Business", esc(p.business_type)],
    ["Run by", esc(p.operator)],
    ["Hygiene rating", esc(p.rating || "—")],
  ] : [
    ["Registered owner", esc(p.registered_owner || "—")],
    ...(p.title_count > 1 ? [["Titles", p.title_count]] : []),
    ["Tenure", esc(p.tenure || "—")],
    ["Price paid", p.title_count > 1 && p.price_paid ? `${gbp(p.price_paid)} <span class="j">(${p.price_paid_known} of ${p.title_count})</span>` : gbp(p.price_paid) || "—"],
  ];
  document.getElementById("panel-body").innerHTML = `
    <div class="kind">${shapeSVG(KINDS[k].shape, COLORS[p.owner_type] || COLORS.unknown, 12)}${esc(KINDS[k].label)}</div>
    <h2>${esc(p.name)}</h2>
    <p class="addr">${esc([p.address !== p.name ? p.address : null, p.postcode].filter(Boolean).join(", "))}</p>
    <div class="owner">
      <div class="j">Controlled by</div>
      <div class="who">${esc(p.ultimate_owner || "Not known")}</div>
      <div class="j"><span class="badge" style="background:${COLORS[p.owner_type]}">${TYPE_LABELS[p.owner_type] || p.owner_type}</span>
        ${p.ultimate_country ? esc(countryName(p.ultimate_country)) : ""}</div>
    </div>
    <dl>${facts.map(([a, b]) => `<dt>${a}</dt><dd>${b}</dd>`).join("")}</dl>
    ${flagNote(p.flags)}
    ${p.geocode_precision && p.geocode_precision !== "postcode" ? `<p class="j">Pin is approximate: the register gives no postcode.</p>` : ""}
    <details open><summary>How we know</summary><ol class="chain">${chain || "<li>No chain recorded</li>"}</ol></details>
    ${p.titles ? `<details><summary>All ${p.titles.length} titles</summary><ul class="titles">${p.titles.map((t) =>
      `<li><b>${esc(t.title)}</b> ${esc(t.address)}${t.price_paid ? ` · ${gbp(t.price_paid)}` : ""}</li>`).join("")}</ul></details>` : ""}
    ${p.notes ? `<p class="note">${esc(p.notes)}</p>` : ""}
    <details><summary>Sources</summary><ol class="sources">${(p.sources || []).map((s) => `<li><a href="${esc(s)}" target="_blank" rel="noopener">${esc(s.replace(/^https?:\/\/(www\.)?/, ""))}</a></li>`).join("")}</ol></details>
    <div class="panel-actions">
      <button type="button" id="owner-this">Everything they own</button>
      <button type="button" id="suggest-this">Suggest a correction</button>
    </div>
    <p class="j">Checked ${esc(fmtDate(p.last_checked))}${p.evidence === "inferred" ? " · controller is our reading of the register" : ""}</p>`;
  document.getElementById("suggest-this").onclick = () => openCorrection(p);
  document.getElementById("owner-this").onclick = () => setOwner(ownerKey(p));
  const panel = document.getElementById("panel");
  panel.hidden = false;
  panel.scrollTop = 0;
}
document.getElementById("close").addEventListener("click", () => { document.getElementById("panel").hidden = true; });

// --- Corrections -----------------------------------------------------------
const dlg = document.getElementById("correction");
const form = document.getElementById("correction-form");
const statusEl = document.getElementById("c-status");

function openCorrection(p) {
  form.reset();
  statusEl.textContent = "";
  form.property_id.value = p ? p.id : "";
  form.property_name.value = p ? p.name : "";
  const label = document.getElementById("c-property");
  label.hidden = !p;
  if (p) label.textContent = `About: ${p.name} (${p.id})`;
  document.getElementById("c-submit").disabled = false;
  dlg.showModal();
}
document.getElementById("suggest-general").addEventListener("click", (e) => { e.preventDefault(); openCorrection(null); });
document.getElementById("c-cancel").addEventListener("click", () => dlg.close());

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const submit = document.getElementById("c-submit");
  submit.disabled = true;
  statusEl.textContent = "Sending…";
  try {
    const res = await fetch("/api/corrections", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(Object.fromEntries(new FormData(form))),
    });
    const out = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(out.error || `Error ${res.status}`);
    statusEl.textContent = "Thank you. Your suggestion has been received and will be reviewed.";
    setTimeout(() => dlg.close(), 2500);
  } catch (err) {
    statusEl.textContent = `Sorry, that didn't send (${err.message}). Please try again.`;
    submit.disabled = false;
  }
});

// --- Top owners ------------------------------------------------------------
document.getElementById("top-owners").addEventListener("click", () => {
  const owners = {};
  for (const f of all()) {
    const p = f.properties;
    if (!matches(p, "owner")) continue;
    const k = ownerKey(p);
    const o = owners[k] ||= { name: k, country: p.ultimate_country, type: p.owner_type, titles: 0, locations: 0,
                               registeredOnly: !p.ultimate_owner };
    o.titles += p.business_type ? 0 : p.title_count || 1;
    o.locations += 1;
  }
  const rows = Object.values(owners).sort((a, b) => b.titles - a.titles).slice(0, 100);
  document.getElementById("panel-body").innerHTML = `
    <h2>Top owners</h2>
    <p class="addr">By number of titles, within your filters.</p>
    <table class="owners"><thead><tr><th>Owner</th><th>Country</th><th class="n">Titles</th></tr></thead><tbody>
    ${rows.map((o) => `<tr><td><button type="button" class="link-button" data-owner="${esc(o.name)}">${esc(o.name)}</button>
      <div class="j"><span class="dot" style="background:${COLORS[o.type]}"></span> ${TYPE_LABELS[o.type] || o.type}</div></td>
      <td>${esc(countryName(o.country))}</td><td class="n">${o.titles}</td></tr>`).join("")}
    </tbody></table>`;
  document.querySelectorAll("[data-owner]").forEach((b) => b.onclick = () => setOwner(b.dataset.owner));
  document.getElementById("panel").hidden = false;
});

// --- CSV download of what is on screen ---------------------------------------
document.getElementById("download").addEventListener("click", () => {
  const cols = ["id", "kind", "name", "address", "postcode", "area", "registered_owner", "ultimate_owner",
    "ultimate_country", "owner_type", "property_type", "title_count", "title_numbers", "evidence", "sources"];
  const cell = (v) => { const s = Array.isArray(v) ? v.join(" | ") : String(v ?? ""); return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; };
  const rows = shown.map((f) => f.properties).map((p) => p.business_type
    ? { ...p, kind: "business", registered_owner: p.operator, property_type: p.business_type, evidence: "name match" }
    : { ...p, kind: "property", title_count: p.title_count || 1 });
  const note = "Contains HM Land Registry data (c) Crown copyright and database right 2026, Companies House data and Food Standards Agency data, all licensed under the Open Government Licence v3.0.";
  const csv = [cols.join(","), ...rows.map((r) => cols.map((c) => cell(r[c])).join(",")), "", cell(note)].join("\n");
  const a = Object.assign(document.createElement("a"), {
    href: URL.createObjectURL(new Blob([csv], { type: "text/csv" })), download: "manchesters-money.csv" });
  a.click();
  URL.revokeObjectURL(a.href);
});

// --- Phone layout: the sidebar is a bottom sheet -----------------------------
const sheetBtn = document.getElementById("sheet");
function setSheet(open) {
  document.getElementById("sidebar").classList.toggle("open", open);
  sheetBtn.setAttribute("aria-expanded", open);
  sheetBtn.textContent = open ? "Map" : "Filters";
}
sheetBtn.addEventListener("click", () => setSheet(!document.getElementById("sidebar").classList.contains("open")));
document.getElementById("q").addEventListener("focus", () => { if (matchMedia("(max-width: 760px)").matches) setSheet(true); });
// While a detail panel is open, it takes the bottom of the screen on phones.
const panelEl = document.getElementById("panel");
new MutationObserver(() => document.body.classList.toggle("panel-open", !panelEl.hidden))
  .observe(panelEl, { attributes: true, attributeFilter: ["hidden"] });
