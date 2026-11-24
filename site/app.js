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

const map = L.map("map", {
  zoomControl: true, maxZoom: 19, minZoom: 9,
  maxBounds: [[53.20, -2.90], [53.75, -1.70]], maxBoundsViscosity: 0.8,
}).setView([53.481, -2.235], 13);
// If the page loads in a hidden tab the map measures 0x0; re-measure when it becomes visible.
document.addEventListener("visibilitychange", () => { if (!document.hidden) map.invalidateSize(); });
window.addEventListener("resize", () => map.invalidateSize());
// OpenFreeMap: free vector tiles, no key, production use allowed (https://openfreemap.org).
L.maplibreGL({
  style: "https://tiles.openfreemap.org/styles/positron",
  attribution: '<a href="https://openfreemap.org" target="_blank">OpenFreeMap</a> © <a href="https://www.openmaptiles.org/" target="_blank">OpenMapTiles</a> Data from <a href="https://www.openstreetmap.org/copyright" target="_blank">OpenStreetMap</a>',
}).addTo(map);
const layer = L.markerClusterGroup({
  maxClusterRadius: 40, spiderfyOnMaxZoom: true, showCoverageOnHover: false,
  iconCreateFunction: (cluster) => {
    // Colour the cluster by its most common owner type.
    const counts = {};
    for (const m of cluster.getAllChildMarkers()) counts[m.options.ownerType] = (counts[m.options.ownerType] || 0) + 1;
    const top = Object.entries(counts).sort((a, b) => b[1] - a[1])[0][0];
    const n = cluster.getChildCount();
    const size = n < 10 ? 28 : n < 50 ? 34 : 42;
    return L.divIcon({
      html: `<div style="background:${COLORS[top] || COLORS.unknown}">${n}</div>`,
      className: "cluster", iconSize: [size, size],
    });
  },
}).addTo(map);

const state = { country: "", type: "", ptype: "", owner: "", parking: false };
// Parking/storage and ground-rent interests are hidden unless asked for.
const MINOR = new Set(["parking", "ground_rent"]);
const isMinor = (p) => MINOR.has(p.property_type) || p.parking_only;
const ownerKey = (p) => p.ultimate_owner || p.registered_owner || p.name;
let features = [];

fetch("data/properties.geojson").then((r) => r.json()).then((gj) => {
  features = gj.features;
  fillSelect("f-country", unique((p) => p.ultimate_country || ""), countryName);
  fillSelect("f-type", Object.keys(TYPE_LABELS).filter((t) => features.some((f) => f.properties.owner_type === t)), (t) => TYPE_LABELS[t]);
  fillSelect("f-ptype", unique((p) => p.property_type), (s) => (s[0].toUpperCase() + s.slice(1)).replace("_", " "));
  render();
  const b = L.latLngBounds(features.map((f) => [f.geometry.coordinates[1], f.geometry.coordinates[0]]));
  map.invalidateSize();
  if (b.isValid() && map.getSize().x > 0) map.fitBounds(b.pad(0.05), { maxZoom: 14 });
});

function unique(fn) {
  return [...new Set(features.map((f) => fn(f.properties)))].sort();
}
function fillSelect(id, values, label) {
  const el = document.getElementById(id);
  for (const v of values) el.insertAdjacentHTML("beforeend", `<option value="${esc(v)}">${esc(label(v))}</option>`);
}

const filters = { country: "f-country", type: "f-type", ptype: "f-ptype" };
for (const [k, id] of Object.entries(filters)) {
  document.getElementById(id).addEventListener("change", (e) => { state[k] = e.target.value; render(); });
}
document.getElementById("f-parking").addEventListener("change", (e) => { state.parking = e.target.checked; render(); });
document.getElementById("reset").addEventListener("click", () => {
  for (const [k, id] of Object.entries(filters)) { state[k] = ""; document.getElementById(id).value = ""; }
  state.owner = ""; state.parking = false; document.getElementById("f-parking").checked = false;
  render();
});
function setOwner(o) { state.owner = o; render(); }

function matches(p, skip) {
  return (skip === "country" || !state.country || (p.ultimate_country || "") === state.country)
    && (skip === "type" || !state.type || p.owner_type === state.type)
    && (!state.ptype || p.property_type === state.ptype)
    && (skip === "owner" || !state.owner || ownerKey(p) === state.owner)
    && (state.parking || state.ptype === p.property_type || !isMinor(p));
}

function render() {
  layer.clearLayers();
  const shown = features.filter((f) => matches(f.properties));
  for (const f of shown) {
    const p = f.properties;
    const [lon, lat] = f.geometry.coordinates;
    L.circleMarker([lat, lon], {
      radius: 7, weight: 1.5, color: "#fff", fillColor: COLORS[p.owner_type] || COLORS.unknown, fillOpacity: 0.9,
      ownerType: p.owner_type,
    }).bindTooltip(esc(p.name)).on("click", () => openPanel(p)).addTo(layer);
  }
  const titles = shown.reduce((n, f) => n + (f.properties.title_count || 1), 0);
  document.getElementById("shown").textContent = `${shown.length.toLocaleString()} locations · ${titles.toLocaleString()} titles`;
  const chip = document.getElementById("owner-chip");
  chip.hidden = !state.owner;
  chip.innerHTML = state.owner ? `Owner: ${esc(state.owner)} <button type="button" aria-label="Clear owner filter">×</button>` : "";
  if (state.owner) chip.querySelector("button").onclick = () => setOwner("");
  renderCounters();
}

function renderCounters() {
  // Counters reflect the other active filters so they stay useful as filters.
  const byType = {}, byCountry = {};
  for (const f of features) {
    const p = f.properties;
    if (matches(p, "type")) byType[p.owner_type] = (byType[p.owner_type] || 0) + 1;
    if (matches(p, "country")) { const c = p.ultimate_country || ""; byCountry[c] = (byCountry[c] || 0) + 1; }
  }
  document.getElementById("type-counters").innerHTML = Object.keys(TYPE_LABELS).filter((t) => byType[t]).map((t) =>
    `<button class="counter" data-type="${t}" aria-pressed="${state.type === t}"><span class="dot" style="background:${COLORS[t]}"></span>${TYPE_LABELS[t]} <b>${byType[t]}</b></button>`).join("");
  const top = Object.entries(byCountry).filter(([c]) => c).sort((a, b) => b[1] - a[1]).slice(0, 5);
  document.getElementById("country-counters").innerHTML = top.map(([c, n]) =>
    `<button class="counter" data-country="${esc(c)}" aria-pressed="${state.country === c}">${esc(countryName(c))} <b>${n}</b></button>`).join("");
  document.querySelectorAll("[data-type]").forEach((b) => b.onclick = () => toggle("type", b.dataset.type));
  document.querySelectorAll("[data-country]").forEach((b) => b.onclick = () => toggle("country", b.dataset.country));
}

function toggle(key, value) {
  state[key] = state[key] === value ? "" : value;
  document.getElementById(filters[key]).value = state[key];
  render();
}

const FLAG_TEXT = {
  multiple_bo: "More than one person or company is registered as having control. The chain below follows one of them.",
  mixed_uk_foreign: "Control is shared between UK and non-UK owners.",
  multiple_foreign_countries: "Non-UK owners from more than one country share control.",
  cycle: "The ownership records loop back on themselves; the chain stops where the loop begins.",
  max_hops: "The chain was stopped after eight steps.",
  curated_controller: "The last step was added by hand from a published source (linked), because the register names a fund manager's founder rather than the funds.",
  inferred_ground_rent: "Probably a ground-rent interest: the owner holds the freeholds of many individual houses, which are usually sold to residents on long leases. The residents own their homes.",
};
function flagNote(flags) {
  const lines = (flags || []).map((f) => FLAG_TEXT[f.split("@")[0]]).filter(Boolean);
  return lines.length ? `<p class="note">${[...new Set(lines)].map(esc).join("<br>")}</p>` : "";
}

function openPanel(p) {
  const sourceLink = (s) => s ? ` <a href="${esc(s)}" target="_blank" rel="noopener">source</a>` : "";
  const chain = (p.chain || []).map((s) => `
    <li><div>${esc(s.name || s.company_number || "Unnamed entity")}${sourceLink(s.source)}</div>
      <div class="j">${esc([s.jurisdiction && (s.jurisdiction.length === 2 ? countryName(s.jurisdiction) : s.jurisdiction), s.country_of_residence && `resident: ${s.country_of_residence}`, s.nationality && `nationality: ${s.nationality}`, s.company_number && `No. ${s.company_number}`].filter(Boolean).join(" · "))}</div>${s.note ? `<div class="j">${esc(s.note)}</div>` : ""}</li>`).join("");
  const rows = [
    ["Registered owner", p.registered_owner ? `${esc(p.registered_owner)} <span class="j">(from the register)</span>` : "To be confirmed from Land Registry"],
    ["Ultimately controlled by", `${esc(p.ultimate_owner || "Not established")} <span class="j">(our reading of the chain)</span>`],
    ["Country", esc(countryName(p.ultimate_country))],
    ["Owner type", `<span class="badge" style="background:${COLORS[p.owner_type]}">${TYPE_LABELS[p.owner_type] || p.owner_type}</span>`],
    ...(p.title_count > 1 ? [["Titles", `${p.title_count} at this location`]] : []),
    ["Property type", esc(String(p.property_type).replace("_", " "))],
    ["Tenure", esc(p.tenure || "—")],
    ["Price paid", p.title_count > 1
      ? (p.price_paid ? `${gbp(p.price_paid)} <span class="j">(total for the ${p.price_paid_known} of ${p.title_count} titles with a price)</span>` : "—")
      : gbp(p.price_paid) || "—"],
    ["Evidence", esc(p.evidence)],
    ["Last checked", esc(p.last_checked)],
  ];
  document.getElementById("panel-body").innerHTML = `
    <h2>${esc(p.name)}</h2>
    <p class="addr">${esc([p.address, p.postcode].filter(Boolean).join(", "))}</p>
    ${p.geocode_precision && p.geocode_precision !== "postcode" ? `<p class="note">Location is approximate (placed by ${p.geocode_precision === "street" ? "street name" : "address"}; the register gives no postcode).</p>` : ""}
    ${p.review_status && p.review_status !== "verified" ? `<p class="note review">Awaiting review: ${esc(p.review_status.replace("_", " "))}</p>` : ""}
    <dl>${rows.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join("")}</dl>
    ${flagNote(p.flags)}
    <div class="label">Ownership chain</div>
    <ol class="chain">${chain || "<li>No chain recorded</li>"}</ol>
    ${p.titles ? `<details class="titles"><summary>All ${p.titles.length} titles</summary><ul>${p.titles.map((t) =>
      `<li><b>${esc(t.title)}</b> ${esc(t.address)}${t.price_paid ? ` · ${gbp(t.price_paid)}` : ""}</li>`).join("")}</ul></details>` : ""}
    <p><button type="button" class="link-button" id="owner-this">Show everything owned by ${esc(ownerKey(p))}</button></p>
    ${p.notes ? `<div class="label">Notes</div><p class="note">${esc(p.notes)}</p>` : ""}
    <div class="label">Sources</div>
    <ol class="sources">${(p.sources || []).map((s) => `<li><a href="${esc(s)}" target="_blank" rel="noopener">${esc(s)}</a></li>`).join("")}</ol>
    <p><button type="button" class="link-button" id="suggest-this">Suggest a correction to this entry</button></p>`;
  document.getElementById("suggest-this").onclick = () => openCorrection(p);
  document.getElementById("owner-this").onclick = () => setOwner(ownerKey(p));
  document.getElementById("panel").hidden = false;
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
  for (const f of features) {
    const p = f.properties;
    if (!matches(p, "owner")) continue;
    const k = ownerKey(p);
    const o = owners[k] ||= { name: k, country: p.ultimate_country, type: p.owner_type, titles: 0, locations: 0,
                               registeredOnly: !p.ultimate_owner };
    o.titles += p.title_count || 1;
    o.locations += 1;
  }
  const rows = Object.values(owners).sort((a, b) => b.titles - a.titles).slice(0, 100);
  document.getElementById("panel-body").innerHTML = `
    <h2>Top owners</h2>
    <p class="addr">By number of Land Registry titles, within the current filters. Click a name to show only their property.</p>
    <table class="owners"><thead><tr><th>Owner</th><th>Country</th><th class="n">Titles</th></tr></thead><tbody>
    ${rows.map((o) => `<tr><td><button type="button" class="link-button" data-owner="${esc(o.name)}">${esc(o.name)}</button>
      ${o.registeredOnly ? '<div class="j">registered owner; controller not established</div>' : ""}
      <div class="j"><span class="dot" style="background:${COLORS[o.type]}"></span> ${TYPE_LABELS[o.type] || o.type}</div></td>
      <td>${esc(countryName(o.country))}</td><td class="n">${o.titles}</td></tr>`).join("")}
    </tbody></table>`;
  document.querySelectorAll("[data-owner]").forEach((b) => b.onclick = () => setOwner(b.dataset.owner));
  document.getElementById("panel").hidden = false;
});
