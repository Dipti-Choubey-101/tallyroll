(() => {
"use strict";

const $ = (s, el = document) => el.querySelector(s);
const REDUCED = matchMedia("(prefers-reduced-motion: reduce)").matches;
const sleep = ms => new Promise(r => setTimeout(r, REDUCED ? 0 : ms));
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const S = { cats: [], settings: {}, status: {}, rows: [], month: "all", q: "", only: "all", cat: "", queue: [], busy: false, fresh: null, pillow: true };
const catById = id => S.cats.find(c => c.id === id) || { id: "other", name: "Other", color: "#9aa39e" };

/* ---------- helpers ---------- */
async function api(path, opts = {}) {
  const res = await fetch(path, opts);
  let data = null;
  try { data = await res.json(); } catch (_) {}
  if (!res.ok) throw new Error((data && data.error) || "Something went wrong (" + res.status + ")");
  return data;
}
function money(n, cur) {
  if (n === null || n === undefined || n === "") return "–";
  cur = cur || S.settings.currency || "INR";
  try { return new Intl.NumberFormat(cur === "INR" ? "en-IN" : "en", { style: "currency", currency: cur, maximumFractionDigits: 2 }).format(n); }
  catch (_) { return cur + " " + Number(n).toFixed(2); }
}
function moneyShort(n, cur) { // no decimals for big figures
  cur = cur || S.settings.currency || "INR";
  try { return new Intl.NumberFormat(cur === "INR" ? "en-IN" : "en", { style: "currency", currency: cur, maximumFractionDigits: 0 }).format(n); }
  catch (_) { return cur + " " + Math.round(n); }
}
const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
function dayParts(iso) { if (!iso) return null; const [y, m, d] = iso.split("-").map(Number); return { y, m, d }; }
function monthLabel(ym) { const [y, m] = ym.split("-").map(Number); return new Date(y, m - 1, 1).toLocaleDateString("en", { month: "long", year: "numeric" }); }
function toast(msg, bad) {
  const t = document.createElement("div"); t.className = "toast" + (bad ? " bad" : ""); t.textContent = msg;
  $("#toasts").appendChild(t); setTimeout(() => t.remove(), bad ? 7000 : 3500);
}

/* ---------- status ---------- */
async function refreshStatus() {
  try { S.status = await api("/api/status"); } catch (_) { S.status = {}; }
  const st = S.status, el = $("#status"), b = $("#banner");
  let cls = "bad", txt = "Not connected", banner = "";
  if (st.demo) { cls = "warn"; txt = "Demo mode"; banner = "<b>Demo mode is on.</b> Tallyroll only knows the eight sample bills right now. Turn it off in Settings to read your own bills with Gemma."; }
  else if (!st.ollama) { cls = "bad"; txt = "Ollama is not running"; banner = "<b>Ollama is not running.</b> Open the Ollama app (the llama icon in your taskbar or Start menu), wait a few seconds, then try again. Want a quick look first? Turn on demo mode in Settings."; }
  else if (!st.model_installed) { cls = "warn"; txt = "Gemma is not installed yet"; banner = "<b>Gemma is not installed yet.</b> Close this page, double-click <code>setup-model.bat</code> in the Tallyroll folder, then come back. It is a one-time download of about 3 GB."; }
  else { cls = "ok"; txt = "Gemma ready, on this computer"; }
  el.className = "status " + cls; $("#statusText").textContent = txt;
  b.hidden = !banner; b.className = "banner" + (cls === "bad" ? " bad" : ""); b.innerHTML = banner;
  $("#footModel").textContent = st.demo ? "Demo mode" : "Model: " + (S.settings.model || "");
  if (!S.busy) setLcd(st.demo || (st.ollama && st.model_installed) ? "ready, drop a bill" : "not ready, see the note above", st.demo || (st.ollama && st.model_installed) ? "" : "off");
}

/* ---------- data + derived views ---------- */
async function loadRows() { S.rows = await api("/api/receipts"); renderAll(); }
function viewRows() {
  const q = S.q.trim().toLowerCase();
  return S.rows.filter(r => {
    if (S.month !== "all" && !(r.date || "").startsWith(S.month)) return false;
    if (S.only === "check" && r.status !== "review") return false;
    if (S.cat && r.category !== S.cat) return false;
    if (q && !(r.vendor + " " + r.items.map(i => i.name).join(" ")).toLowerCase().includes(q)) return false;
    return true;
  }).sort((a, b) => (b.date || "0").localeCompare(a.date || "0") || b.added.localeCompare(a.added));
}
function monthRows() { return S.rows.filter(r => S.month === "all" || (r.date || "").startsWith(S.month)); }

/* ---------- render ---------- */
function renderAll() { renderMonths(); renderFigures(); renderFilters(); renderLedger(); renderCats(); renderExport(); }

function renderMonths() {
  const months = [...new Set(S.rows.map(r => (r.date || "").slice(0, 7)).filter(Boolean))].sort().reverse();
  const sel = $("#month");
  if (S.month !== "all" && !months.includes(S.month)) S.month = "all";
  sel.innerHTML = '<option value="all">All months</option>' + months.map(m => `<option value="${m}">${monthLabel(m)}</option>`).join("");
  sel.value = S.month;
}
function renderFigures() {
  const rows = monthRows(), cur = S.settings.currency || "INR";
  const mine = rows.filter(r => (r.currency || cur) === cur && r.total != null);
  const other = rows.filter(r => (r.currency || cur) !== cur && r.total != null).length;
  const spent = mine.reduce((a, r) => a + r.total, 0), tax = mine.reduce((a, r) => a + (r.tax || 0), 0);
  const check = rows.filter(r => r.status === "review").length;
  $("#figures").innerHTML = `
    <div class="fig"><div class="lab">Spent${S.month === "all" ? "" : " in " + monthLabel(S.month).split(" ")[0]}</div><div class="val">${rows.length ? moneyShort(spent, cur) : "–"}</div><div class="sub">${other ? other + " bill" + (other > 1 ? "s" : "") + " in another currency not added in" : "Everything on the bills, tax included"}</div></div>
    <div class="fig"><div class="lab">Tax on those bills</div><div class="val">${rows.length ? moneyShort(tax, cur) : "–"}</div><div class="sub">Handy for GST or VAT returns</div></div>
    <div class="fig"><div class="lab">Bills read</div><div class="val">${rows.length}</div><div class="sub">${rows.length ? "Each one saved on this computer" : "Nothing yet"}</div></div>
    <div class="fig ${check ? "alert" : ""}"><div class="lab">Need a look</div><div class="val">${check}</div><div class="sub">${check ? '<button id="showCheck">Show me which</button>' : (rows.length ? "All clear" : "Nothing yet")}</div></div>`;
  const b = $("#showCheck"); if (b) b.onclick = () => { S.only = "check"; renderFilters(); renderLedger(); $("#ledger").scrollIntoView({ behavior: REDUCED ? "auto" : "smooth", block: "center" }); };
}
function renderFilters() {
  const n = monthRows().filter(r => r.status === "review").length;
  $("#filters").innerHTML = `<button class="chip" data-o="all" aria-pressed="${S.only === "all"}">All bills</button><button class="chip" data-o="check" aria-pressed="${S.only === "check"}">Need a look${n ? " (" + n + ")" : ""}</button>`;
  $("#filters").querySelectorAll(".chip").forEach(c => c.onclick = () => { S.only = c.dataset.o; renderFilters(); renderLedger(); });
}
function renderLedger() {
  const rows = viewRows(), el = $("#ledger");
  if (!rows.length) {
    el.innerHTML = S.rows.length
      ? `<div class="empty"><h3>No bills match</h3><p>Try another month, clear the search, or switch the filter back to all bills.</p><button class="btn ghost" id="resetF">Clear filters</button></div>`
      : `<div class="empty"><h3>No bills yet</h3><p>Drop photos of your supplier bills on the printer above. Nothing to hand? Load the sample bills and watch how it works.</p><button class="btn primary" id="emptySamples">Try the sample bills</button></div>`;
    const r = $("#resetF"); if (r) r.onclick = () => { S.q = ""; S.only = "all"; S.cat = ""; S.month = "all"; $("#search").value = ""; renderAll(); };
    const s = $("#emptySamples"); if (s) s.onclick = loadSamples;
    return;
  }
  el.innerHTML = rows.map(r => {
    const d = dayParts(r.date), c = catById(r.category);
    const items = r.items.length ? r.items.slice(0, 4).map(i => i.name).join(", ") : (r.notes || "No line items read");
    const opts = S.cats.map(x => `<option value="${x.id}" ${x.id === r.category ? "selected" : ""}>${esc(x.name)}</option>`).join("");
    return `<div class="row ${S.fresh === r.id ? "fresh" : ""}" role="row" data-id="${r.id}" tabindex="0">
      <div class="r-date">${d ? `<b>${String(d.d).padStart(2, "0")}</b>${MON[d.m - 1]}` : `<b>–</b>no date`}</div>
      <div class="r-main"><div class="r-vendor"><span style="overflow:hidden;text-overflow:ellipsis">${esc(r.vendor) || "Unknown vendor"}</span>${r.status === "review" ? `<span class="flag" title="${esc(r.problems.join("; "))}">Check</span>` : ""}${r.demo ? '<span class="demo-tag">demo</span>' : ""}</div><div class="r-items">${esc(items)}</div></div>
      <div class="r-cat"><span class="sw-dot" style="background:${c.color}"></span><select aria-label="Category for ${esc(r.vendor)}">${opts}</select></div>
      <div class="r-amt">${money(r.total, r.currency)}${r.tax ? `<small>tax ${money(r.tax, r.currency)}</small>` : ""}</div></div>`;
  }).join("");
  S.fresh = null;
  el.querySelectorAll(".row").forEach(row => {
    const id = row.dataset.id;
    row.addEventListener("click", e => { if (e.target.closest(".r-cat")) return; openDrawer(id); });
    row.addEventListener("keydown", e => { if (e.key === "Enter" && e.target === row) openDrawer(id); });
    const sel = $("select", row);
    sel.addEventListener("change", async () => {
      try { const u = await api("/api/receipts/" + id, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ category: sel.value }) }); replaceRow(u); toast("Moved to " + catById(sel.value).name); }
      catch (e) { toast(e.message, true); }
    });
  });
}
function renderCats() {
  const rows = monthRows().filter(r => r.total != null && (r.currency || S.settings.currency) === S.settings.currency);
  const sums = {}; rows.forEach(r => sums[r.category] = (sums[r.category] || 0) + r.total);
  const list = Object.entries(sums).sort((a, b) => b[1] - a[1]), max = list.length ? list[0][1] : 1;
  const total = list.reduce((a, [, v]) => a + v, 0) || 1;
  $("#cats").innerHTML = `<h3>Where the money went</h3>` + (list.length
    ? `<div style="margin-top:10px">` + list.map(([id, v]) => { const c = catById(id); return `<button class="cat" data-c="${id}" aria-pressed="${S.cat === id}"><div class="cat-top"><span>${esc(c.name)}</span><span>${moneyShort(v)}</span></div><div class="cat-bar" title="${Math.round(v / total * 100)}% of spend"><i style="width:${Math.max(3, v / max * 100)}%;background:${c.color}"></i></div></button>`; }).join("") + `</div>`
    : `<p class="none">Once bills are read, spending by category shows up here. Click a category to filter the list.</p>`);
  $("#cats").querySelectorAll(".cat").forEach(b => b.onclick = () => { S.cat = S.cat === b.dataset.c ? "" : b.dataset.c; renderCats(); renderLedger(); });
}
function renderExport() {
  const m = S.month === "all" ? "" : "?month=" + S.month;
  $("#exportBtn").href = "/api/export.csv" + m;
  $("#exportNote").textContent = S.rows.length ? `One row per bill${S.month === "all" ? "" : " from " + monthLabel(S.month)}, with date, vendor, category, total and tax. Opens in Excel.` : "One row per bill, with date, vendor, category, total and tax. Opens in Excel.";
}
function replaceRow(u) { const i = S.rows.findIndex(r => r.id === u.id); if (i >= 0) S.rows[i] = u; renderAll(); }

/* ---------- printer ---------- */
function setLcd(text, led) { $("#lcdText").textContent = text; const l = $("#led"); l.className = "led" + (led ? " " + led : ""); }
let timerId = null;
function startClock() { const t0 = Date.now(); const tick = () => { const s = Math.floor((Date.now() - t0) / 1000); $("#lcdTime").textContent = Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0"); }; tick(); timerId = setInterval(tick, 500); }
function stopClock() { clearInterval(timerId); $("#lcdTime").textContent = ""; }
function feedPaper(html) {
  const p = $("#paper"); p.classList.remove("feed"); p.innerHTML = html; void p.offsetWidth; p.classList.add("feed");
}
function showScan(file, label) {
  const url = URL.createObjectURL(file);
  feedPaper(`<div class="scan"><img alt="The bill being read" src="${url}"></div><div class="scan-cap">${esc(label)}</div>`);
  return url;
}
async function printReceipt(r) {
  const p = $("#paper"); p.classList.remove("feed"); p.innerHTML = ""; void p.offsetWidth; p.classList.add("feed");
  const d = dayParts(r.date), shown = r.items.slice(0, 3), more = r.items.length - shown.length;
  const lines = [];
  lines.push(`<div class="p-vendor">${esc(r.vendor) || "Unknown vendor"}</div>`);
  lines.push(`<div class="p-meta">${d ? d.d + " " + MON[d.m - 1] + " " + d.y : "date not found"}${r.payment ? " · " + esc(r.payment) : ""}</div><div class="p-rule"></div>`);
  shown.forEach(i => lines.push(`<div class="p-row"><span>${esc(i.name)}</span><i></i><span>${i.amount == null ? "" : money(i.amount, r.currency)}</span></div>`));
  if (more > 0) lines.push(`<div class="p-more">+ ${more} more line${more > 1 ? "s" : ""}</div>`);
  if (!r.items.length) lines.push(`<div class="p-more">No line items could be read</div>`);
  lines.push(`<div class="p-rule"></div>`);
  if (r.tax) lines.push(`<div class="p-row"><span>Tax</span><i></i><span>${money(r.tax, r.currency)}</span></div>`);
  lines.push(`<div class="p-row total"><span>Total</span><i></i><span>${money(r.total, r.currency)}</span></div>`);
  const c = catById(r.category);
  lines.push(`<div class="stamp-row">${r.status === "review" ? `<div class="stamp check">Check me</div>` : ""}<div class="stamp" style="color:${c.color}">${esc(c.name)}</div></div>`);
  for (const html of lines) {
    const t = document.createElement("div"); t.className = "line-in"; t.innerHTML = html; p.appendChild(t); await sleep(130);
  }
}
function resetPaperIdle() {
  const p = $("#paper"); p.innerHTML = ""; p.classList.remove("feed");
  p.innerHTML = `<div class="p-idle"><div class="p-title">Drop bills here</div><div class="p-sub">or click anywhere on this printer</div><div class="perf"></div><div class="p-sub small">Each bill prints out here<br>as soon as it has been read.</div></div>`;
}

/* ---------- queue ---------- */
function enqueue(files) {
  const ok = [...files].filter(f => /^image\/(png|jpe?g|webp)$/.test(f.type) || /\.(png|jpe?g|webp)$/i.test(f.name));
  const bad = files.length - ok.length;
  if (bad) toast(bad + " file" + (bad > 1 ? "s were" : " was") + " skipped. Tallyroll reads JPG, PNG and WEBP photos. For a PDF, take a screenshot of it.", true);
  ok.forEach(f => S.queue.push({ id: Math.random().toString(36).slice(2), file: f, name: f.name, state: "wait", msg: "waiting" }));
  renderQueue(); runQueue();
}
function renderQueue() {
  const q = S.queue.slice(-4);
  $("#queue").innerHTML = q.map(i => `<div class="q-item ${i.state}"><span class="nm">${esc(i.name)}</span><span class="st">${esc(i.msg)}</span></div>`).join("");
  $("#queue").scrollTop = $("#queue").scrollHeight;
}
async function runQueue() {
  if (S.busy) return; S.busy = true;
  const press = $("#drop"); press.classList.add("busy");
  let done = 0, failed = 0;
  while (true) {
    const item = S.queue.find(i => i.state === "wait"); if (!item) break;
    const total = S.queue.length, n = S.queue.indexOf(item) + 1;
    item.state = "run"; item.msg = "reading…"; renderQueue();
    setLcd(`reading bill ${n} of ${total}`, "busy"); stopClock(); startClock();
    const url = showScan(item.file, "Gemma is reading " + item.name);
    try {
      const rec = await api("/api/scan?filename=" + encodeURIComponent(item.name), { method: "POST", headers: { "Content-Type": "application/octet-stream" }, body: item.file });
      item.state = "done"; item.msg = rec.seconds + "s"; done++;
      S.rows.push(rec); S.fresh = rec.id; renderAll();
      stopClock(); setLcd("printing", "busy");
      await printReceipt(rec); await sleep(900);
    } catch (e) {
      item.state = "fail"; item.msg = e.message; failed++; renderQueue(); toast(e.message, true);
      if (/Ollama|installed|not reach/i.test(e.message)) { S.queue.forEach(i => { if (i.state === "wait") { i.state = "fail"; i.msg = "skipped"; } }); }
      await sleep(500);
    }
    URL.revokeObjectURL(url); renderQueue();
  }
  stopClock(); press.classList.remove("busy"); S.busy = false;
  setLcd(done ? `done, ${done} bill${done > 1 ? "s" : ""} read` : "ready, drop a bill", done ? "" : "off");
  if (!done) resetPaperIdle();
  if (done) toast(done + " bill" + (done > 1 ? "s" : "") + " added" + (failed ? ", " + failed + " could not be read" : ""));
  setTimeout(() => { S.queue = S.queue.filter(i => i.state === "wait" || i.state === "run"); renderQueue(); }, 6000);
  refreshStatus();
}
async function loadSamples() {
  try {
    const names = await api("/api/samples"); const files = [];
    for (const n of names) { const b = await (await fetch("/samples/" + encodeURIComponent(n))).blob(); files.push(new File([b], n, { type: b.type })); }
    enqueue(files);
  } catch (e) { toast(e.message, true); }
}

/* ---------- drawer ---------- */
let lastFocus = null;
function openDrawer(id) {
  const r = S.rows.find(x => x.id === id); if (!r) return;
  lastFocus = document.activeElement;
  const cats = S.cats.map(c => `<option value="${c.id}" ${c.id === r.category ? "selected" : ""}>${esc(c.name)}</option>`).join("");
  const items = r.items.length ? `<div class="d-items">${r.items.map(i => `<div><span>${esc(i.name)}</span><span>${i.amount == null ? "" : money(i.amount, r.currency)}</span></div>`).join("")}</div>` : "";
  $("#drawer").innerHTML = `
    <div class="d-head"><h2>${esc(r.vendor) || "Bill details"}</h2><button class="icon-btn" id="dClose" aria-label="Close"><svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg></button></div>
    <div class="d-body">
      ${r.problems.length ? `<div class="problems"><b>Please check:</b> ${esc(r.problems.join(", "))}. Fix it below and save, and it moves out of the "Need a look" list.</div>` : ""}
      <div class="d-img"><img id="dImg" alt="Photo of the bill" src="/api/image/${r.id}"></div>
      <label class="field"><span>Vendor</span><input id="fVendor" value="${esc(r.vendor)}"></label>
      <div class="grid2">
        <label class="field"><span>Date</span><input id="fDate" type="date" value="${esc(r.date)}"></label>
        <label class="field"><span>Paid by</span><input id="fPay" value="${esc(r.payment)}" placeholder="Cash, UPI, card…"></label>
        <label class="field"><span>Total (${esc(r.currency)})</span><input class="mono" id="fTotal" inputmode="decimal" value="${r.total == null ? "" : Number(r.total).toFixed(2)}"></label>
        <label class="field"><span>Tax (${esc(r.currency)})</span><input class="mono" id="fTax" inputmode="decimal" value="${r.tax == null ? "" : Number(r.tax).toFixed(2)}"></label>
      </div>
      <label class="field"><span>Category</span><select id="fCat">${cats}</select></label>
      <label class="field"><span>Note</span><input id="fNotes" value="${esc(r.notes)}" placeholder="Anything worth remembering"></label>
      ${items ? `<div class="field"><span>Line items</span>${items}</div>` : ""}
      <div class="meta">${r.demo ? "Sample bill, filled in by demo mode." : `Read by ${esc(r.model)} in ${r.seconds}s on this computer.`} ${r.edited ? "You have edited this bill." : ""}</div>
    </div>
    <div class="d-foot"><button class="btn danger" id="dDel">Delete bill</button><button class="btn primary" id="dSave">Save changes</button></div>`;
  $("#scrim").hidden = false; requestAnimationFrame(() => { $("#scrim").classList.add("on"); $("#drawer").classList.add("on"); });
  $("#drawer").setAttribute("aria-hidden", "false");
  $("#dClose").focus();
  $("#dClose").onclick = closeDrawer; $("#scrim").onclick = closeDrawer;
  $("#dImg").onclick = e => e.target.classList.toggle("big");
  $("#dSave").onclick = async () => {
    try {
      const u = await api("/api/receipts/" + id, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ vendor: $("#fVendor").value, date: $("#fDate").value, payment: $("#fPay").value, total: $("#fTotal").value, tax: $("#fTax").value, category: $("#fCat").value, notes: $("#fNotes").value }) });
      replaceRow(u); closeDrawer(); toast("Saved");
    } catch (e) { toast(e.message, true); }
  };
  $("#dDel").onclick = async () => {
    if (!confirm("Delete this bill and its photo from this computer?")) return;
    try { await api("/api/receipts/" + id, { method: "DELETE" }); S.rows = S.rows.filter(x => x.id !== id); renderAll(); closeDrawer(); toast("Deleted"); }
    catch (e) { toast(e.message, true); }
  };
}
function closeDrawer() {
  $("#scrim").classList.remove("on"); $("#drawer").classList.remove("on"); $("#drawer").setAttribute("aria-hidden", "true");
  setTimeout(() => { $("#scrim").hidden = true; }, 220);
  if (lastFocus && lastFocus.focus) lastFocus.focus();
}
document.addEventListener("keydown", e => { if (e.key === "Escape" && $("#drawer").classList.contains("on")) closeDrawer(); });

/* ---------- settings ---------- */
const dlg = $("#settings");
$("#openSettings").onclick = () => {
  $("#sModel").value = S.settings.model; $("#sCurrency").value = S.settings.currency; $("#sUrl").value = S.settings.ollama_url;
  $("#sDayFirst").checked = !!S.settings.day_first; $("#sDemo").checked = !!S.settings.demo; dlg.showModal();
};
$("#saveSettings").onclick = async e => {
  e.preventDefault();
  try {
    S.settings = await api("/api/settings", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ model: $("#sModel").value, currency: $("#sCurrency").value, ollama_url: $("#sUrl").value, day_first: $("#sDayFirst").checked, demo: $("#sDemo").checked }) });
    dlg.close(); toast("Settings saved"); await refreshStatus(); renderAll();
  } catch (err) { toast(err.message, true); }
};
$("#clearAll").onclick = async () => {
  if (!confirm("Delete every bill and photo saved by Tallyroll on this computer? This cannot be undone.")) return;
  await api("/api/clear", { method: "POST" }); S.rows = []; dlg.close(); renderAll(); resetPaperIdle(); toast("All bills deleted");
};

/* ---------- wiring ---------- */
const press = $("#drop"), fileInput = $("#file");
$("#pick").onclick = e => { e.stopPropagation(); fileInput.click(); };
$("#trySamples").onclick = loadSamples;
press.addEventListener("click", e => { if (e.target.closest(".queue")) return; fileInput.click(); });
press.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); fileInput.click(); } });
fileInput.addEventListener("change", () => { if (fileInput.files.length) enqueue(fileInput.files); fileInput.value = ""; });
let depth = 0;
const hasFiles = e => e.dataTransfer && [...e.dataTransfer.types].includes("Files");
addEventListener("dragenter", e => { if (!hasFiles(e)) return; e.preventDefault(); depth++; $("#veil").classList.add("on"); press.classList.add("over"); });
addEventListener("dragover", e => { if (hasFiles(e)) e.preventDefault(); });
addEventListener("dragleave", e => { if (!hasFiles(e)) return; depth = Math.max(0, depth - 1); if (!depth) { $("#veil").classList.remove("on"); press.classList.remove("over"); } });
addEventListener("drop", e => { if (!hasFiles(e)) return; e.preventDefault(); depth = 0; $("#veil").classList.remove("on"); press.classList.remove("over"); enqueue(e.dataTransfer.files); });
$("#month").onchange = e => { S.month = e.target.value; renderFigures(); renderFilters(); renderLedger(); renderCats(); renderExport(); };
$("#search").oninput = e => { S.q = e.target.value; renderLedger(); };

(async function init() {
  try {
    const cfg = await api("/api/config"); S.cats = cfg.categories; S.settings = cfg.settings; S.pillow = cfg.pillow;
  } catch (e) { toast("Tallyroll could not start: " + e.message, true); return; }
  await Promise.all([refreshStatus(), loadRows()]);
  setInterval(() => { if (!S.busy) refreshStatus(); }, 8000);
})();
})();
