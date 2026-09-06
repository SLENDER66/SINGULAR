// Le Sage, côté navigateur. Aucun cadriciel, aucune étape de compilation :
// ce fichier est envoyé tel quel, donc il reste lisible et modifiable.
"use strict";

// Le jeton arrive une fois dans l'adresse, puis vit ici. Une PWA ajoutée à
// l'écran d'accueil démarre sur `start_url`, sans le paramètre : sans ça,
// l'icône ouvrirait une app qui ne sait plus s'authentifier.
const TOKEN_KEY = "singular.sage.token";

function token() {
  const fromUrl = new URLSearchParams(location.search).get("k");
  if (fromUrl) {
    try { localStorage.setItem(TOKEN_KEY, fromUrl); } catch (_) { /* mode privé */ }
    // Le jeton reste dans l'adresse. Il en était retiré pour faire propre, et
    // ça cassait l'installation : « Sur l'écran d'accueil » enregistre
    // l'adresse affichée, donc une adresse déjà nettoyée de sa clé. L'icône
    // ouvrait une app qui ne savait plus s'authentifier.
    return fromUrl;
  }
  try { return localStorage.getItem(TOKEN_KEY) || ""; } catch (_) { return ""; }
}

/// La clé, telle qu'on peut la coller : une adresse entière ou le jeton seul.
function readSuppliedToken(raw) {
  const text = raw.trim();
  if (!text) return "";
  const match = text.match(/[?&]k=([^&\s]+)/);
  return match ? decodeURIComponent(match[1]) : text;
}

async function api(path, options = {}) {
  const headers = { "Content-Type": "application/json" };
  const key = token();
  if (key) headers["X-Sage-Token"] = key;
  const response = await fetch(path, { ...options, headers });
  const payload = await response.json().catch(() => ({ message: "réponse illisible" }));
  if (!response.ok) {
    const failure = new Error(payload.message || `erreur ${response.status}`);
    failure.status = response.status;
    throw failure;
  }
  return payload;
}

const $ = (id) => document.getElementById(id);
const el = (tag, className, text) => {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
};

// --- rendu -------------------------------------------------------------------

function renderNotice(notice) {
  $("headline").textContent = notice.headline;
  const moment = new Date(notice.generated_at);
  $("subline").textContent = moment.toLocaleDateString("fr-FR", {
    weekday: "long", day: "numeric", month: "long",
  });

  const container = $("items");
  container.replaceChildren();
  for (const item of notice.items) {
    const card = el("article", `item ${item.severity}`);
    card.append(el("h3", null, item.title));
    if (item.detail) card.append(el("p", null, item.detail));
    if (item.action === "add") {
      const button = el("button", null, "Enregistrer une décision");
      button.addEventListener("click", openAdd);
      card.append(button);
    } else if (item.action && item.action.startsWith("resolve ")) {
      const entryId = item.action.slice("resolve ".length);
      const button = el("button", null, "Trancher maintenant");
      button.addEventListener("click", () => openResolve(entryId));
      card.append(button);
    }
    container.append(card);
  }
  renderFigures(notice.report);
}

function figure(value, label, warn) {
  const box = el("div", warn ? "figure warn" : "figure");
  box.append(el("div", "value", value), el("div", "label", label));
  return box;
}

function renderFigures(report) {
  if (!report || !report.decisions) { $("numbers").hidden = true; return; }
  const percent = (x) => `${Math.round(x * 100)}%`;
  const boxes = [
    figure(`${report.hours_total}h`, "engagées en tout"),
    figure(`${report.hours_that_worked}h`, "ont produit le résultat attendu",
           report.hours_that_worked === 0 && report.resolved > 0),
    // Même condition que l'observation qui l'accompagne : s'alarmer d'heures
    // sans verdict n'a de sens qu'une fois qu'un verdict a pu être rendu.
    figure(`${report.hours_unresolved}h`, "encore sans verdict",
           report.resolved > 0 && report.hours_unresolved > report.hours_that_worked),
    figure(String(report.overdue), "à trancher", report.overdue > 0),
  ];
  if (report.overconfidence !== null && report.resolved >= 3) {
    const gap = report.overconfidence;
    boxes.push(figure(
      `${gap > 0 ? "+" : ""}${percent(gap)}`,
      gap > 0 ? "de surconfiance" : "de sous-confiance",
      Math.abs(gap) >= 0.15,
    ));
    boxes.push(figure(percent(report.hit_rate), `arrivent, sur ${percent(report.mean_probability)} annoncés`));
  }
  $("figures").replaceChildren(...boxes);
  $("numbers").hidden = false;
}

function renderOpen(entries) {
  const open = entries.filter((entry) => entry.status === "OPEN");
  if (!open.length) { $("open-list").hidden = true; return; }
  open.sort((a, b) => a.due_at.localeCompare(b.due_at));

  const list = $("open-entries");
  list.replaceChildren();
  for (const entry of open) {
    const late = entry.overdue_days > 0;
    const row = el("li", late ? "entry late" : "entry");
    row.append(el("span", "title", entry.title));
    row.append(el("span", "meta", late
      ? `+${entry.overdue_days}j · ${Math.round(entry.probability * 100)}%`
      : `${Math.round(entry.probability * 100)}% · ${entry.tier_label}`));
    row.addEventListener("click", () => openResolve(entry.entry_id));
    list.append(row);
  }
  $("open-list").hidden = false;
}

// --- état --------------------------------------------------------------------

let entriesById = new Map();

async function refresh() {
  try {
    const [notice, listing] = await Promise.all([api("/api/notice"), api("/api/entries")]);
    entriesById = new Map(listing.entries.map((entry) => [entry.entry_id, entry]));
    fillTiers(listing.tiers);
    renderNotice(notice);
    renderOpen(listing.entries);
    $("error").hidden = true;
    setLocked(false);
  } catch (error) {
    if (error.status === 401) {
      askForTheToken();
      return;
    }
    $("error").textContent = error.message;
    $("error").hidden = false;
  }
}

/// Sans clé, l'app ne peut rien montrer — mais elle peut demander.
///
/// Le message brut « jeton d'accès manquant ou invalide » laissait sans
/// recours : l'app ajoutée à l'écran d'accueil a son propre stockage, séparé
/// de Safari, et rien dans son interface ne permettait d'en fournir un.
function askForTheToken() {
  $("error").hidden = true;
  setLocked(true);
}

/// Masquer par une classe, pas en touchant chaque section : `#numbers` et
/// `#open-list` portent déjà leur propre `hidden`, que le rendu pilote selon
/// les données. Les rouvrir de force afficherait des cadres vides.
function setLocked(locked) {
  $("app").classList.toggle("locked", locked);
  $("unlock").hidden = !locked;
  $("add-button").hidden = locked;
}

function fillTiers(tiers) {
  const select = $("tier");
  if (select.options.length) return;
  for (const tier of tiers) {
    const option = document.createElement("option");
    option.value = tier.value;
    option.textContent = `${tier.rank}. ${tier.label}`;
    if (tier.value === "REVENUS") option.selected = true;
    select.append(option);
  }
}

// --- enregistrer -------------------------------------------------------------

function openAdd() {
  $("add-error").hidden = true;
  $("add-dialog").showModal();
}

function showFormError(id, message) {
  const node = $(id);
  node.textContent = message;
  node.hidden = false;
}

async function submitAdd(event) {
  event.preventDefault();
  const data = new FormData($("add-form"));
  try {
    await api("/api/entries", {
      method: "POST",
      body: JSON.stringify({
        title: data.get("title"),
        action: data.get("action"),
        predicted: data.get("predicted"),
        probability: Number(data.get("probability")) / 100,
        tier: data.get("tier"),
        cost_hours: Number(data.get("cost_hours")),
        horizon_days: Number(data.get("horizon_days")),
      }),
    });
    $("add-form").reset();
    $("probability-out").textContent = "60 %";
    $("add-dialog").close();
    await refresh();
  } catch (error) {
    showFormError("add-error", error.message);
  }
}

// --- trancher ----------------------------------------------------------------

let resolving = null;

function openResolve(entryId) {
  const entry = entriesById.get(entryId);
  if (!entry) return;
  resolving = entryId;
  $("resolve-predicted").textContent = `« ${entry.predicted} » — tu disais ${Math.round(entry.probability * 100)}%`;
  $("resolve-error").hidden = true;
  $("resolve-dialog").showModal();
}

async function submitResolve(happened) {
  const lesson = new FormData($("resolve-form")).get("lesson") || "";
  try {
    await api(`/api/entries/${resolving}/resolve`, {
      method: "POST",
      body: JSON.stringify({ happened, lesson }),
    });
    $("resolve-form").reset();
    $("resolve-dialog").close();
    await refresh();
  } catch (error) {
    showFormError("resolve-error", error.message);
  }
}

// --- démarrage ---------------------------------------------------------------

$("unlock-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const supplied = readSuppliedToken($("unlock-input").value);
  if (!supplied) return;
  try { localStorage.setItem(TOKEN_KEY, supplied); } catch (_) { /* mode privé */ }
  // Repartir de l'adresse propre à cette app, en portant la clé : c'est ce que
  // « Sur l'écran d'accueil » retiendra si on l'installe depuis ici.
  location.replace(`${location.pathname}?k=${encodeURIComponent(supplied)}`);
});

$("add-button").addEventListener("click", openAdd);
$("add-cancel").addEventListener("click", () => $("add-dialog").close());
$("add-form").addEventListener("submit", submitAdd);
$("probability").addEventListener("input", (event) => {
  $("probability-out").textContent = `${event.target.value} %`;
});
$("resolve-cancel").addEventListener("click", () => $("resolve-dialog").close());
$("resolve-yes").addEventListener("click", () => submitResolve(true));
$("resolve-no").addEventListener("click", () => submitResolve(false));

// Rouvrir l'app depuis l'écran d'accueil doit montrer aujourd'hui, pas la
// dernière fois qu'on l'a regardée.
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") refresh();
});

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("sw.js").catch(() => { /* iOS en http, tant pis */ });
}

refresh();
