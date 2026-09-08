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
  renderFigures(notice.report, notice.calibration);
}

function figure(value, label, warn) {
  const box = el("div", warn ? "figure warn" : "figure");
  box.append(el("div", "value", value), el("div", "label", label));
  return box;
}

// Le verdict de calibration vient du moteur, il ne se refait pas ici.
//
// Cette vignette gardait sa propre règle -- « écart ≥ 15 % et 3 verdicts » --
// et s'allumait donc en alerte pendant que la phrase, juste en dessous,
// expliquait qu'il était trop tôt pour conclure. Deux réponses contradictoires
// à la même question, sur le même écran. C'est la deuxième vignette à survivre
// à la correction de sa phrase : la première est gardée par
// `test_the_hours_figure_waits_for_a_verdict_before_warning`.
function renderFigures(report, calibration) {
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
  if (calibration) {
    const gap = calibration.gap;
    boxes.push(figure(
      `${gap > 0 ? "+" : ""}${percent(gap)}`,
      gap > 0 ? "de surconfiance" : "de sous-confiance",
      calibration.conclusive,
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
    // « Échue » et « en retard » ne sont pas la même chose. Le jour dit, le
    // retard vaut zéro jour et la décision demande pourtant son verdict : la
    // ligne restait grise pendant que le rapport la mettait en tête.
    const late = entry.is_due;
    const row = el("li", late ? "entry late" : "entry");
    row.append(el("span", "title", entry.title));
    const retard = entry.overdue_days > 0 ? `+${entry.overdue_days}j` : "aujourd'hui";
    row.append(el("span", "meta", late
      ? `${retard} · ${Math.round(entry.probability * 100)}%`
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

// Un envoi a la fois par formulaire, et les boutons grises pendant ce temps.
//
// Le serveur local met un instant a repondre, et rien ne bougeait a l'ecran :
// on appuie une seconde fois. Pour « trancher », ca envoyait deux verdicts
// contradictoires -- le journal les refuse depuis, mais le message qui
// revenait etait le sien, technique et en anglais. Pour « enregistrer », rien
// ne les refuse : deux appuis font deux decisions identiques et legitimes, des
// heures comptees double, et une calibration faussee le jour du verdict.
//
// Un seul verrou pour les deux : la meme verite ecrite deux fois finit par
// diverger, et celle-ci est trop subtile pour qu'on remarque la derive.
const envoisEnCours = new Set();

function griser(boutons, grise) {
  // `$` rend `null` pour un identifiant absent. Griser un bouton est un
  // confort ; empecher le double envoi est la garantie. Les lier ferait
  // qu'un identifiant renomme dans le HTML casserait l'enregistrement
  // lui-meme -- une panne bien pire que celle qu'on previent. Le verrou
  // vit donc dans l'ensemble, pas dans le DOM.
  for (const id of boutons) {
    const bouton = $(id);
    if (bouton) bouton.disabled = grise;
  }
}

async function envoyerUneFois(cle, boutons, action) {
  if (envoisEnCours.has(cle)) return;
  envoisEnCours.add(cle);
  griser(boutons, true);
  try {
    await action();
  } finally {
    envoisEnCours.delete(cle);
    griser(boutons, false);
  }
}

async function submitAdd(event) {
  event.preventDefault();
  await envoyerUneFois("add", ["add-submit"], () => submitAddOnce());
}

async function submitAddOnce() {
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
        // Transmis tels quels, en texte : « » veut dire non renseigne, et
        // Number("") vaut 0 -- ce qui inventerait un gain nul a chaque
        // decision non chiffree, exactement ce que le champ sert a distinguer.
        expected_gain_eur: data.get("expected_gain_eur"),
        reversibility: data.get("reversibility"),
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

// Un seul verdict a la fois. Deux boutons cote a cote, aucun verrou : un
// double appui -- ou l'impatience quand le serveur local met un instant --
// envoyait deux verdicts, et le second revenait en 409 avec le message
// technique du journal, en anglais, le jour meme ou l'on tranche. Pire :
// appuyer sur l'autre bouton tentait d'enregistrer le verdict inverse.
//
// Le journal refuse deja la double ecriture cote serveur. Ici on evite
// qu'elle soit tentee, ce qui n'est pas la meme chose : la garde du serveur
// protege la verite, celle-ci protege ce qu'on comprend en appuyant.
async function submitResolve(happened) {
  await envoyerUneFois("resolve", ["resolve-yes", "resolve-no"],
                       () => submitResolveOnce(happened));
}

async function submitResolveOnce(happened) {
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
    // 409 : quelqu'un d'autre a tranche entre-temps -- l'autre appareil, ou
    // une fenetre restee ouverte. Ce n'est pas une panne, et le message brut
    // du journal ne le dit pas dans une langue qu'on lit un matin.
    showFormError("resolve-error", error.status === 409
      ? "Cette décision a déjà été tranchée. Ferme et rouvre pour voir le verdict enregistré."
      : error.message);
  }
}

// --- parler ------------------------------------------------------------------

// La seule chose de cette app qui coûte de l'argent. Trois conséquences,
// toutes visibles à l'écran plutôt qu'écrites dans un fichier : ce qu'il
// reste de la journée est affiché avant qu'on tape, le coût du tour est
// affiché après, et le bouton se grise pendant. On ne corrige pas ce qu'on ne
// voit pas, et une facture est exactement ce qu'on ne voit pas.

function renderThread(tours) {
  const fil = $("parle-thread");
  fil.textContent = "";
  for (const tour of tours) {
    fil.appendChild(el("div", `tour ${tour.role}`, tour.content));
  }
  fil.scrollTop = fil.scrollHeight;
}

// Deux chiffres, et ils ne disent pas la même chose. Le premier borne la
// journée ; le second est le crédit acheté, qui ne repart jamais à zéro. Sans
// le second, on peut respecter le plafond tous les jours et vider les cinq
// dollars sans l'avoir vu venir.
function renderRemaining(etat) {
  const reste = etat.restants;
  const jour = reste > 0
    ? `${reste} réponses restantes aujourd'hui sur ${etat.plafond}.`
    : "Plafond du jour atteint. Demain, ou depuis le clavier.";
  $("parle-cost").hidden = false;
  $("parle-cost").textContent = `${jour} ${etat.bilan || ""}`.trim();
}

async function openParle() {
  $("parle-error").hidden = true;
  $("parle-cost").hidden = true;
  $("parle-dialog").showModal();
  try {
    const etat = await api("/api/parle");
    renderThread(etat.tours);
    renderRemaining(etat);
  } catch (error) {
    showFormError("parle-error", error.message);
  }
}

async function submitParle(event) {
  if (event) event.preventDefault();
  await envoyerUneFois("parle", ["parle-submit"], () => submitParleOnce());
}

async function submitParleOnce() {
  const question = $("parle-input").value.trim();
  if (!question) return;
  $("parle-error").hidden = true;
  // La question monte dans le fil tout de suite : sinon rien ne bouge pendant
  // les dizaines de secondes que met une réponse, et on rappuie.
  $("parle-thread").appendChild(el("div", "tour user", question));
  $("parle-thread").appendChild(el("div", "tour assistant", "…"));
  $("parle-thread").scrollTop = $("parle-thread").scrollHeight;
  try {
    const rendu = await api("/api/parle", {
      method: "POST",
      body: JSON.stringify({ question }),
    });
    $("parle-input").value = "";
    const etat = await api("/api/parle");
    renderThread(etat.tours);
    const cache = rendu.cout.cache_lu ? `, ${rendu.cout.cache_lu} relus du cache` : "";
    $("parle-cost").hidden = false;
    $("parle-cost").textContent =
      `${rendu.cout.entree} jetons envoyés${cache}, ${rendu.cout.sortie} rendus.`
      + ` ${rendu.restants} restantes aujourd'hui. ${rendu.bilan || ""}`;
  } catch (error) {
    // Chaque refus dit quoi faire. Un code HTTP nu, sur un téléphone, se lit
    // comme une panne -- et deux de ceux-là n'en sont pas.
    const messages = {
      429: "Plafond de réponses atteint pour aujourd'hui. Demain, ou depuis le clavier.",
      409: "Une réponse est déjà en train d'arriver. Laisse-la venir.",
    };
    showFormError("parle-error", messages[error.status] || error.message);
    const etat = await api("/api/parle").catch(() => null);
    if (etat) renderThread(etat.tours);
  }
}

// --- chercher des offres -----------------------------------------------------

// Le premier agent, et le seul endroit de l'app ou quelque chose cherche pour
// lui. Il ne postule pas : ce n'est pas une consigne dans une instruction --
// une consigne se contourne par une tournure de phrase -- c'est que la route
// n'importe pas le journal et ne rend que du texte. `test_sage_isolation.py`
// le lit sur les imports plutot que sur les intentions.
//
// Ce qui coute est affiche comme pour la conversation, et pour la meme raison :
// une recherche web ramene des pages entieres, donc elle coute nettement plus
// qu'un tour de parole sur le meme credit.

// Les liens deviennent cliquables sans que le texte du modele devienne du HTML.
// Une offre se lit sur un telephone : recopier une adresse a la main ne se fait
// pas. Mais construire la page avec `innerHTML` a partir de ce qu'un modele
// rend ouvrirait l'app a ce que le modele a lu sur le web -- une annonce peut
// contenir n'importe quoi. On decoupe donc le texte, et chaque morceau est pose
// par le DOM : seuls `http://` et `https://` deviennent des liens, jamais un
// autre schema, et jamais une balise.
const ADRESSES = /(https?:\/\/[^\s<>"')\]]+)/g;

function texteAvecLiens(texte) {
  const bloc = el("div", "tour offres");
  for (const morceau of texte.split(ADRESSES)) {
    if (!morceau) continue;
    if (/^https?:\/\//.test(morceau)) {
      const lien = el("a", null, morceau);
      lien.href = morceau;
      lien.target = "_blank";
      lien.rel = "noopener noreferrer";
      bloc.appendChild(lien);
    } else {
      bloc.appendChild(document.createTextNode(morceau));
    }
  }
  return bloc;
}

function renderOffresRestant(etat) {
  const reste = etat.restants;
  const jour = reste > 0
    ? `${reste} appels restants aujourd'hui sur ${etat.plafond}.`
    : "Plafond du jour atteint. Demain, ou depuis le clavier.";
  $("offres-cost").hidden = false;
  $("offres-cost").textContent =
    `${jour} Une recherche coûte plus qu'une réponse. ${etat.bilan || ""}`.trim();
}

async function openOffres() {
  $("offres-error").hidden = true;
  $("offres-cost").hidden = true;
  $("offres-dialog").showModal();
  try {
    const etat = await api("/api/offres");
    $("offres-contexte").textContent = etat.contexte;
    renderOffresRestant(etat);
  } catch (error) {
    showFormError("offres-error", error.message);
  }
}

async function submitOffres(event) {
  if (event) event.preventDefault();
  await envoyerUneFois("offres", ["offres-submit"], () => submitOffresOnce());
}

async function submitOffresOnce() {
  const precision = $("offres-input").value.trim();
  $("offres-error").hidden = true;
  // Quelque chose bouge tout de suite : une recherche met des dizaines de
  // secondes, et un ecran fige se fait retaper dessus.
  const resultat = $("offres-resultat");
  resultat.textContent = "";
  resultat.appendChild(el("div", "tour assistant", "Recherche en cours…"));
  try {
    const rendu = await api("/api/offres", {
      method: "POST",
      body: JSON.stringify({ precision }),
    });
    resultat.textContent = "";
    resultat.appendChild(texteAvecLiens(rendu.offres));
    resultat.appendChild(el("div", "tour assistant",
      "Rien n'a été envoyé à personne. À toi de décider."));
    resultat.scrollTop = 0;
    const cache = rendu.cout.cache_lu ? `, ${rendu.cout.cache_lu} relus du cache` : "";
    $("offres-cost").hidden = false;
    $("offres-cost").textContent =
      `${rendu.cout.entree} jetons envoyés${cache}, ${rendu.cout.sortie} rendus.`
      + ` ${rendu.restants} restants aujourd'hui. ${rendu.bilan || ""}`;
  } catch (error) {
    // Les memes refus que la conversation, dans la meme langue : sur un
    // telephone, un code HTTP nu se lit comme une panne, et aucun de ceux-la
    // n'en est une.
    const messages = {
      429: "Plafond atteint pour aujourd'hui. Demain, ou depuis le clavier.",
      409: "Une réponse est déjà en train d'arriver. Laisse-la venir.",
      402: "D'après tes tarifs, ton crédit est épuisé.",
      503: "La recherche est coupée : pas de clé, pas de réseau, ou le service refuse."
           + " Le reste de l'app marche sans.",
    };
    resultat.textContent = "";
    showFormError("offres-error", messages[error.status] || error.message);
  }
}

async function oublierParle() {
  await envoyerUneFois("parle-oubli", ["parle-oubli"], async () => {
    try {
      const etat = await api("/api/parle/oubli", { method: "POST", body: "{}" });
      renderThread(etat.tours);
      renderRemaining(etat);
      $("parle-error").hidden = true;
    } catch (error) {
      showFormError("parle-error", error.message);
    }
  });
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

$("offres-button").addEventListener("click", openOffres);
$("offres-close").addEventListener("click", () => $("offres-dialog").close());
$("offres-form").addEventListener("submit", submitOffres);
$("parle-button").addEventListener("click", openParle);
$("parle-close").addEventListener("click", () => $("parle-dialog").close());
$("parle-form").addEventListener("submit", submitParle);
$("parle-oubli").addEventListener("click", oublierParle);

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
