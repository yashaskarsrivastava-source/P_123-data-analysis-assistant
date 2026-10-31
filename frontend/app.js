const $ = s => document.querySelector(s);
const I18N = {
 en:{tagline:"Ask questions about your CSV/Excel data in plain language.",login:"Log in",signup:"Sign up",password:"Password",name:"Your name",forgot:"Forgot password? Get a new one by email",getPw:"Email me my password",newChat:"New chat",datasets:"Datasets",drop:"Drop or click to upload CSV / XLSX",history:"History",placeholder:"Ask about your data… e.g. total revenue by region",welcome:"What would you like to know?",noData:"Upload a dataset or pick a sample first.",pwSent:"Password sent to your email. Use it to log in.",validated:"numbers verified",rows:"rows",thinking:"Analysing…",samples:"Try a sample:"},
 hi:{tagline:"अपने CSV/Excel डेटा से सरल भाषा में सवाल पूछें।",login:"लॉग इन",signup:"साइन अप",password:"पासवर्ड",name:"आपका नाम",forgot:"पासवर्ड भूल गए? ईमेल पर नया पाएं",getPw:"मेरा पासवर्ड ईमेल करें",newChat:"नई चैट",datasets:"डेटासेट",drop:"CSV / XLSX अपलोड करने के लिए क्लिक करें",history:"इतिहास",placeholder:"अपने डेटा के बारे में पूछें… जैसे region wise कुल revenue",welcome:"आप क्या जानना चाहते हैं?",noData:"पहले डेटासेट अपलोड करें या सैंपल चुनें।",pwSent:"पासवर्ड आपके ईमेल पर भेज दिया गया है।",validated:"संख्याएं सत्यापित",rows:"पंक्तियां",thinking:"विश्लेषण हो रहा है…",samples:"सैंपल आज़माएं:"},
 es:{tagline:"Haz preguntas sobre tus datos CSV/Excel en lenguaje natural.",login:"Iniciar sesión",signup:"Registrarse",password:"Contraseña",name:"Tu nombre",forgot:"¿Olvidaste tu contraseña? Recibe una nueva por correo",getPw:"Enviar mi contraseña por correo",newChat:"Nuevo chat",datasets:"Conjuntos de datos",drop:"Suelta o haz clic para subir CSV / XLSX",history:"Historial",placeholder:"Pregunta sobre tus datos… p. ej. ingresos totales por región",welcome:"¿Qué quieres saber?",noData:"Primero sube un conjunto de datos o elige uno de muestra.",pwSent:"Contraseña enviada a tu correo.",validated:"cifras verificadas",rows:"filas",thinking:"Analizando…",samples:"Prueba una muestra:"}
};
const SUGGEST = {sales:["total revenue by region","top 3 products by revenue","forecast revenue","find outliers in revenue","segment the records into 4 clusters"],
 employees:["average salary by department","correlation between experience years and salary","find outliers in salary","salary ka ausat kitna hai"],
 students:["average math by grade","correlation between study hours and total score","segment the records into 3 clusters","how many rows are there"]};
const S = {token:localStorage.token, user:null, ds:[], convs:[], conv:null, dsId:null, charts:[], busy:false};
let lang = localStorage.lang || "en", theme = localStorage.theme || (matchMedia("(prefers-color-scheme:dark)").matches ? "dark" : "light");
const t = k => (I18N[lang] || I18N.en)[k] || I18N.en[k];
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));

async function api(path, opts = {}) {
  const h = {Authorization: "Bearer " + (S.token || "")};
  if (opts.body && !(opts.body instanceof FormData)) { h["Content-Type"] = "application/json"; opts.body = JSON.stringify(opts.body); }
  const r = await fetch("/api" + path, {...opts, headers: h});
  const d = await r.json().catch(() => ({}));
  if (!r.ok) { if (r.status === 401 && S.token) logout(); throw new Error(typeof d.detail === "string" ? d.detail : "Request failed"); }
  return d;
}
function applyI18n() {
  document.documentElement.lang = lang;
  document.querySelectorAll("[data-i18n]").forEach(e => e.textContent = t(e.dataset.i18n));
  document.querySelectorAll("[data-i18n-ph]").forEach(e => e.placeholder = t(e.dataset.i18nPh));
  $("#lang").value = lang; renderCur(); if (!S.conv) renderEmpty();
}
function setTheme(x) { theme = x; localStorage.theme = x; document.documentElement.dataset.theme = x; }

// ---------- auth ----------
const msg = (m, err) => { $("#authMsg").textContent = m; $("#authMsg").className = "msg" + (err ? " err" : ""); };
$("#tabLogin").onclick = () => { $("#formLogin").classList.remove("hidden"); $("#formSignup").classList.add("hidden"); $("#tabLogin").classList.add("on"); $("#tabSignup").classList.remove("on"); msg(""); };
$("#tabSignup").onclick = () => { $("#formSignup").classList.remove("hidden"); $("#formLogin").classList.add("hidden"); $("#tabSignup").classList.add("on"); $("#tabLogin").classList.remove("on"); msg(""); };
function afterMail(d, email) {
  $("#tabLogin").click(); $("#lEmail").value = email;
  msg(d.email_sent ? t("pwSent") : "Dev mode (email not configured). Your password: " + d.dev_password);
}
$("#formSignup").onsubmit = async e => { e.preventDefault(); try { const email = $("#sEmail").value; afterMail(await api("/auth/signup", {method:"POST", body:{name:$("#sName").value, email}}), email); } catch (x) { msg(x.message, 1); } };
$("#forgot").onclick = async e => { e.preventDefault(); const email = $("#lEmail").value; if (!email) return msg("Enter your email first.", 1);
  try { afterMail(await api("/auth/reset", {method:"POST", body:{email}}), email); } catch (x) { msg(x.message, 1); } };
$("#formLogin").onsubmit = async e => { e.preventDefault();
  try { const d = await api("/auth/login", {method:"POST", body:{email:$("#lEmail").value, password:$("#lPass").value}}); S.token = localStorage.token = d.token; S.user = d.user; boot(); } catch (x) { msg(x.message, 1); } };
function logout() { delete localStorage.token; S.token = null; location.reload(); }
$("#logout").onclick = logout;

// ---------- boot ----------
async function boot() {
  try { S.user = S.user || await api("/me"); } catch { return; }
  $("#auth").classList.add("hidden"); $("#app").classList.remove("hidden");
  $("#uName").textContent = S.user.name; $("#uEmail").textContent = S.user.email; $("#avatar").textContent = S.user.name[0].toUpperCase();
  const samples = await api("/samples");
  $("#samples").innerHTML = `<small class="muted">${t("samples")}</small>` + samples.map(n => `<button data-s="${esc(n)}">${esc(n.replace(".csv", ""))}</button>`).join("");
  $("#samples").onclick = async e => { const n = e.target.dataset.s; if (!n) return; try { const d = await api("/datasets/sample/" + n, {method:"POST"}); await loadDs(); selectDs(d.id); } catch (x) { alert(x.message); } };
  await loadDs(); await loadConvs(); newChat();
}
async function loadDs() { S.ds = await api("/datasets"); renderDs(); }
async function loadConvs() { S.convs = await api("/conversations"); renderConvs(); }
function renderDs() {
  $("#dsList").innerHTML = S.ds.map(d => `<div class="item ${d.id === S.dsId ? "on" : ""}" data-id="${d.id}"><span title="${esc(d.name)}">📄 ${esc(d.name)}</span><small>${d.rows}</small><button class="x" data-del="${d.id}">✕</button></div>`).join("");
}
$("#dsList").onclick = async e => {
  const del = e.target.dataset.del;
  if (del) { if (confirm("Delete this dataset and its chats?")) { await api("/datasets/" + del, {method:"DELETE"}); if (S.dsId == del) S.dsId = null; await loadDs(); await loadConvs(); newChat(); } return; }
  const it = e.target.closest(".item"); if (it) selectDs(+it.dataset.id);
};
function selectDs(id) { S.dsId = id; S.conv = null; renderDs(); renderCur(); renderEmpty(); renderConvs(); $("#sidebar").classList.remove("open"); }
function renderCur() { const d = S.ds.find(x => x.id === S.dsId); $("#curDs").textContent = d ? `${d.name} · ${d.rows} ${t("rows")}` : ""; }
function renderConvs() {
  $("#convList").innerHTML = S.convs.map(c => `<div class="item ${S.conv && S.conv.id === c.id ? "on" : ""}" data-id="${c.id}"><span>${esc(c.title)}</span><button class="x" data-del="${c.id}">✕</button></div>`).join("");
}
$("#convList").onclick = async e => {
  const del = e.target.dataset.del;
  if (del) { await api("/conversations/" + del, {method:"DELETE"}); if (S.conv && S.conv.id == del) newChat(); await loadConvs(); return; }
  const it = e.target.closest(".item"); if (!it) return;
  const c = S.convs.find(x => x.id === +it.dataset.id); S.conv = c; S.dsId = c.dataset_id; renderDs(); renderCur(); renderConvs();
  const ms = await api("/conversations/" + c.id); $("#chat").innerHTML = ""; S.charts = []; ms.forEach(addMsg); $("#sidebar").classList.remove("open");
};
function newChat() { S.conv = null; if (!S.dsId && S.ds.length) S.dsId = S.ds[0].id; renderDs(); renderCur(); renderEmpty(); renderConvs(); }
$("#newChat").onclick = newChat;

function renderEmpty() {
  S.charts.forEach(c => c.destroy()); S.charts = [];
  const d = S.ds.find(x => x.id === S.dsId), key = d && Object.keys(SUGGEST).find(k => d.name.toLowerCase().includes(k));
  const chips = (SUGGEST[key] || (d ? ["how many rows are there", "summary statistics", "correlation matrix"] : [])).map(q => `<button data-q="${esc(q)}">${esc(q)}</button>`).join("");
  $("#chat").innerHTML = `<div class="empty"><h2>${t("welcome")}</h2><div class="muted">${d ? esc(d.name) : t("noData")}</div><div class="chips">${chips}</div></div>`;
}
$("#chat").onclick = e => { if (e.target.dataset.q) { $("#q").value = e.target.dataset.q; send(); } };

// ---------- upload ----------
async function upload(f) { if (!f) return; const fd = new FormData(); fd.append("file", f);
  try { const d = await api("/datasets", {method:"POST", body:fd}); await loadDs(); selectDs(d.id); } catch (x) { alert(x.message); } }
$("#file").onchange = e => { upload(e.target.files[0]); e.target.value = ""; };
["dragover", "dragleave", "drop"].forEach(ev => $("#drop").addEventListener(ev, e => { e.preventDefault(); $("#drop").classList.toggle("over", ev === "dragover"); if (ev === "drop") upload(e.dataTransfer.files[0]); }));

// ---------- chat ----------
function table(cols, rows) {
  return `<div class="tbl"><table><thead><tr>${cols.map(c => `<th>${esc(c)}</th>`).join("")}</tr></thead><tbody>${rows.slice(0, 50).map(r => `<tr>${r.map(v => `<td>${esc(v)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
}
function addMsg(m) {
  if ($("#chat .empty")) $("#chat").innerHTML = "";
  const row = document.createElement("div"); row.className = "row";
  if (m.role === "user") { row.innerHTML = `<div class="user">${esc(m.content)}</div>`; }
  else {
    const r = m.result || {}, ok = !r.error; row.classList.add("bot");
    let h = `<p class="${ok ? "" : "err"}">${esc(m.content)}</p>`;
    if (ok && r.result) {
      const e = r.engine, b = [e.planner === "llm" ? "LLM planner" : `ML router ${Math.round((e.confidence || 0) * 100)}%`, e.explainer === "llm" ? "LLM explanation" : "template explanation", "✓ " + t("validated"), r.result.operation];
      h += `<div class="badges">${b.map(x => `<span class="badge">${esc(x)}</span>`).join("")}</div>`;
      if (r.result.chart) h += `<div class="chartbox"><canvas></canvas></div>`;
      h += table(r.result.columns, r.result.rows);
      h += `<details><summary>Plan</summary><pre>${esc(JSON.stringify(r.plan, null, 2))}</pre></details>`;
    }
    row.innerHTML = h;
    if (ok && r.result && r.result.chart) drawChart(row.querySelector("canvas"), r.result.chart);
  }
  $("#chat").appendChild(row); $("#chat").scrollTop = $("#chat").scrollHeight; return row;
}
function drawChart(cv, c) {
  const css = getComputedStyle(document.documentElement), txt = css.getPropertyValue("--muted"), grid = css.getPropertyValue("--line"), pal = ["#10a37f", "#e07a5f", "#3d85c6"];
  S.charts.push(new Chart(cv, {type: c.type, data: {labels: c.labels, datasets: c.series.map((s, i) => ({label: s.name, data: s.values, backgroundColor: pal[i % 3] + "cc", borderColor: pal[i % 3], tension: .25, spanGaps: false, borderDash: c.type === "line" && s.name === "Forecast" ? [6, 4] : []}))},
    options: {responsive: true, maintainAspectRatio: false, plugins: {legend: {display: c.series.length > 1, labels: {color: txt}}}, scales: {x: {ticks: {color: txt, maxRotation: 60}, grid: {color: grid}}, y: {ticks: {color: txt}, grid: {color: grid}}}}}));
}
async function send() {
  const q = $("#q").value.trim(); if (!q || S.busy) return;
  if (!S.dsId) { alert(t("noData")); return; }
  S.busy = true; $("#q").value = ""; $("#q").style.height = "auto";
  try {
    if (!S.conv) { S.conv = await api("/conversations", {method:"POST", body:{dataset_id:S.dsId}}); S.convs.unshift(S.conv); }
    addMsg({role:"user", content:q}); const wait = addMsg({role:"assistant", content:t("thinking"), result:{}}); 
    const a = await api(`/conversations/${S.conv.id}/ask`, {method:"POST", body:{question:q, language:lang}});
    wait.remove(); addMsg(a); await loadConvs();
  } catch (x) { addMsg({role:"assistant", content:x.message, result:{error:true}}); }
  S.busy = false;
}
$("#send").onclick = send;
$("#q").addEventListener("keydown", e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } });
$("#q").addEventListener("input", e => { e.target.style.height = "auto"; e.target.style.height = e.target.scrollHeight + "px"; });
$("#lang").onchange = e => { lang = localStorage.lang = e.target.value; applyI18n(); };
$("#themeBtn").onclick = () => { setTheme(theme === "dark" ? "light" : "dark"); };
$("#menu").onclick = () => $("#sidebar").classList.toggle("open");

setTheme(theme); applyI18n();
if (S.token) boot();
