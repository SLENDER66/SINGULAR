# Changelog

## 3.16.0 — Voir ce qui part, pour les trois facultés

Trois facultés font sortir quelque chose de sa machine. Deux affichaient ce
qui partirait, une non — et les deux qui l'affichaient en montraient moins que
ce qui partait.

**La conversation n'avait aucun aperçu.** C'est pourtant elle qui envoie le
plus — le rapport du jour **et** tout le fil des tours précédents — et elle
part de son téléphone. « Il a le droit de relire ce qui est dit de lui avant
que ça parte » est la règle qu'on s'était donnée pour le bouton de recherche ;
elle ne valait pas pour la seule faculté où elle comptait le plus.

**`analyse` et `offres` cachaient l'instruction système.** Leur `--blanc`
promettait « exactement ce qui quittera la machine » et montrait le contexte
seul. L'instruction part aussi : elle le nomme, elle cite sa constitution, et
pour la recherche elle porte la garantie qui compte — « tu ne postules jamais ».

- `parle --blanc`, et un bloc dépliable sous le bouton 💬 comme sous le 🔎.
- Les trois aperçus comprennent maintenant l'instruction.
- `test_ce_qui_part.py` capture ce que le client reçoit réellement et exige que
  l'aperçu le couvre **dans les deux sens** : un aperçu qui montre moins
  rassure sur ce qu'il cache, un aperçu qui montre plus fait croire à une fuite
  qui n'existe pas — et la fois d'après on ne le lit plus.
- Mesure au passage, pour la rassurer : ce qui part reste la Notice et les
  agrégats, jamais la base. Pas d'empreintes de chaîne, pas de score par
  décision. Un test le tient.

## 3.15.0 — Un fichier d'état ne peut plus exister à moitié

Trois fichiers portent quelque chose qu'il ne peut pas reconstituer : son fil
de conversation, sa clé d'accès, et ses candidatures. Les trois étaient écrits
par un `write_text`, qui tronque le fichier puis écrit dedans. **Entre les
deux, il n'y a rien.**

Reproduit sur le suivi de candidatures : 1266 octets sains, 635 après une
coupure au milieu de l'écriture — Ctrl+C, un portable qu'on referme — et
l'outil refuse alors de démarrer sur `Unterminated string starting at:
line 27`. Une erreur de parseur JSON, à quelqu'un qui débute en code. Son
historique n'est pas perdu au sens strict ; il est illisible, ce qui revient au
même.

`Quota` faisait déjà l'écriture en deux temps, exactement pour cette raison.
C'était donc la troisième fois que le même oubli se payait : la règle a un
domicile, et `test_ecriture_atomique.py` échoue à la place du prochain lecteur.

- `singular/fichiers.py` écrit à côté, ferme, puis remplace. `os.replace` est
  atomique sur Windows comme sur Unix : une coupure laisse soit l'ancien
  fichier intact, soit le nouveau complet, jamais un mélange.
- Le provisoire est nettoyé même sur `KeyboardInterrupt` — c'est précisément
  l'interruption dont ce module protège, et un provisoire abandonné bloquerait
  l'écriture suivante.
- **La clé d'accès était écrite en clair, puis resserrée à 0600.** Entre les
  deux, le secret était lisible par tout le monde. Les droits se posent
  maintenant à la création du fichier, avant qu'il contienne quoi que ce soit.
- Le prototype de suivi garde sa propre copie de six lignes, par `pathlib` :
  ajouter `os` à ses imports élargirait la promesse « ce script ne contacte
  aucun serveur » que garde `test_proto_suivi.py`, pour un gain nul.
- Le détecteur du test ne cherche que `write_text` et `open(..., "w")`. Ma
  première version attrapait aussi `wfile.write` — la socket HTTP du Sage — et
  un test qui crie au loup finit désactivé.

## 3.14.0 — Deux dépenses en même temps s'écrasaient l'une l'autre

Le serveur du Sage répond au téléphone ; la ligne de commande sert au clavier.
Les deux écrivent le même fichier de compteur, et lisaient toutes deux le total
avant d'écrire chacune le sien.

Mesuré, pas supposé — huit processus, quarante dépenses :

    9 ont planté (FileNotFoundError)
    22 enregistrées sur 40  ->  18 perdues

Le fichier provisoire portait un nom fixe : deux écrivains s'en disputaient un
seul, et le second ne le retrouvait plus. Sur le téléphone, ça se serait vu
comme une panne de l'app — après une réponse déjà payée.

Et ce qui est perdu coûte deux fois : le compte sous-estime la dépense, donc la
garde qui refuse sur crédit épuisé refuse trop tard, et le plafond de soixante
réponses par jour pouvait être dépassé pareillement. C'est la faute déjà payée
sur le journal — deux verdicts simultanés acceptés — transposée à son argent.

- Le fichier provisoire porte le numéro du processus : plus de collision.
- Un fichier verrou sérialise lire-puis-écrire. Un fichier plutôt que `fcntl`
  ou `msvcrt` : il est sur Windows, et une garde qui ne marche que sur la
  machine du développeur n'est pas une garde. Un verrou abandonné plus de cinq
  secondes est repris — un processus tué en le tenant condamnerait l'outil.
- Après correction, la même sonde : 40 sur 40, zéro plantage.
- La première version du test de concurrence **passait sans le verrou** : des
  processus lancés par `spawn` mettent si longtemps à démarrer qu'ils ne se
  rencontrent jamais. Il ne prouvait rien. Refait avec des fils et une
  barrière, il tombe quand on retire le verrou.
- La garde « aucun prix écrit dans ce dépôt » refusait `5.0 secondes` comme un
  tarif. Elle avait raison sur le fond et tort sur la forme : une garde qui
  crie au loup finit désactivée. Les nombres à virgule qui ne sont pas des prix
  se déclarent maintenant, avec ce qu'ils mesurent, et un témoin refuse une
  déclaration dont le nom a disparu.

## 3.13.0 — Le budget cessait de compter dès qu'on se servait de l'outil

Trois trous dans la seule chose qui protège ses cinq dollars.

**Le gabarit de tarifs ne nommait qu'un modèle.** La conversation tourne sur
Sonnet ; l'analyse et la recherche d'offres tournent sur Opus. Une seule
recherche mettait donc dans le compte un modèle sans tarif — et `cout_usd`
refuse de répondre dès qu'il en manque un. L'affichage en dollars disparaissait
pour de bon, remplacé par « écris tes tarifs dans… », ce qu'il avait déjà fait.

**Et la garde du crédit s'éteignait avec.** Elle lit `restant_usd`, qui vaut
`None` dans ce cas : la route qui refuse une dépense sur crédit épuisé ne se
déclenchait plus du tout. Une garde qui s'éteint quand on se sert de l'outil
est pire que pas de garde — et c'est le branchement du bouton 🔎, la veille,
qui a rendu le cas atteignable en un geste.

**`python -m singular analyse` dépensait sans rien enregistrer.** Même cause
que pour la recherche l'avant-veille : la fonction ne rendait pas son coût,
donc l'appelant ne pouvait pas l'écrire. Le solde affiché sur le téléphone
était faux de tout ce qui avait été analysé au clavier.

- Le gabarit est généré depuis les modèles réels. `test_parle_budget.py` refuse
  qu'une faculté dépense sur un modèle qui n'y figure pas : une quatrième
  faculté échouera au test au lieu d'aveugler le budget en silence.
- La garde compte sur `restant_au_mieux_usd` — ce qui reste en ignorant ce
  qu'on ne sait pas chiffrer. Il surestime, donc il refuse tard, jamais trop
  tôt : si même en oubliant une dépense le crédit est fini, il est fini.
- Quand un modèle manque, la phrase le **nomme** au lieu de renvoyer écrire des
  tarifs déjà écrits, et donne ce qui reste au plus.
- `analyser()` rend son coût comme ses deux jumelles, et le CLI l'enregistre.
- `_consommation` remonte dans `analyse`, que les trois facultés importent déjà.
  Il vivait dans `parle`, ce qui forçait `offres` à emprunter un nom privé au
  module voisin et interdisait à `analyse` de s'en servir — donc `analyse` ne
  comptait rien. Le cercle d'imports est cassé au passage.

## 3.12.0 — Taper « 75 » ne fait plus perdre tout ce qu'on vient d'écrire

`python -m singular add` pose huit questions. Deux fautes de saisie s'y payaient
cher, et aucune n'était de sa faute.

Taper **75** en pensant pourcents passait les six questions suivantes, puis
échouait à l'écriture sur `probability must be strictly between 0 and 1` — en
anglais, et surtout **après coup** : tout ce qui venait d'être saisi était
perdu, et un outil censé prendre trente secondes en redemandait autant.

Taper **0,75**, avec la virgule décimale d'un clavier français, rendait
`could not convert string to float: '0,75'`. Une saisie qui n'avait rien de
fautif, refusée par un message de machine.

- Les trois questions numériques valident sur place, dans sa langue, et disent
  quoi écrire : « entre 0.05 et 0.95, pas en pourcents - pour 75 %, ecris
  0.75 ». `_ask` reboucle : il corrige un chiffre, pas huit.
- La virgule et les espaces se lisent partout de la même façon — « 1 500 »
  vaut 1500. La question du gain avait son propre nettoyage ; elle passe
  maintenant par le même.
- `test_saisie_au_clavier.py` vérifie que ce qu'une question accepte est
  exactement ce que `DecisionJournal.add` accepte. Deux écritures de la même
  règle finissent par diverger, et celle qui se tromperait ferait perdre la
  saisie à la question suivante.
- Aucun message neuf ne contient de caractère que sa console Windows ne sait
  pas afficher : `test_windows_console.py` a attrapé un tiret cadratin et une
  espace fine insécable au passage, et il avait raison.

## 3.11.0 — Une règle, un domicile : les vignettes cessent de contredire les phrases

La correction de la calibration avait laissé quatre copies vivantes. La
vignette dorée du rapport gardait « écart ≥ 15 % et 3 verdicts » et s'allumait
donc en alerte pendant que la phrase, juste en dessous, expliquait qu'il était
trop tôt pour conclure. Deux réponses contradictoires à la même question, sur
le même écran — dans l'app web et dans le port iOS.

Et `python -m singular review`, que personne ne regardait parce qu'il est au
clavier, tenait la pire version : **son propre seuil de 5 %, sans minimum de
verdicts**. Après le tout premier verdict, il imprimait en rouge
« surconfiance de +75 % - tu crois plus que ce qui arrive ». Sur un pari.

C'est la troisième fois que le même défaut se produit — une phrase corrigée,
sa vignette qui garde l'ancienne condition — donc la règle n'a plus qu'un
domicile et `tests/test_une_seule_regle_par_phrase.py` échoue si une interface
la refait.

- `calibration_verdict()` calcule l'écart, la rareté et la conclusion une fois.
  La Notice le rend avec le rapport ; les trois interfaces lisent `conclusive`.
- La même garde manquait sur la ligne des heures de `review` : elle passait au
  rouge dès la première décision, alors que son échéance était dans deux
  semaines. C'est le défaut déjà payé, à un quatrième endroit.
- Un test du dépôt figeait ce défaut : il exigeait que `review` imprime
  « surconfiance » après un seul verdict. Il exige maintenant l'inverse, et un
  second cas vérifie que le rouge revient quand il est mérité.
- `is_due` est exposé sur chaque décision ouverte. « Échue » et « en retard »
  ne sont pas la même chose : le jour dit, le retard vaut zéro jour, et la
  ligne restait grise pendant que le rapport la mettait en tête. Elle affiche
  maintenant « aujourd'hui ».

## 3.10.1 — Le rapport ne parle plus au nom d'un document qui se tait

« C'est la définition que ta constitution donne de confondre activité et
résultat. » Elle n'en donne aucune : `constitution.md` nomme le piège dans sa
mission — « sans confondre activité et résultat » — et s'arrête là. Le seuil,
lui, est un choix de ce rapport.

Ce n'est pas un détail de ton. Un outil qui invoque un document que son auteur
a écrit lui-même, pour lui prêter une règle qu'il ne contient pas, rend cette
règle inattaquable : on ne discute pas sa propre constitution. C'est la règle
de provenance du dépôt, appliquée aux phrases plutôt qu'aux données.

- L'observation dit désormais d'où vient la mesure, et que c'est la sienne.
- Les deux autres phrases qui parlent au nom du document — la hiérarchie et le
  « juger sur son levier et son coût » — sont exactes ; un test les relie
  maintenant au texte de `constitution.md` et refuse toute attribution neuve.
- Le port Swift porte la même phrase, et les vecteurs la figent.

## 3.10.0 — La calibration ne conclut plus avant d'en avoir le droit

C'est la question pour laquelle ce journal existe : « est-ce que mes 70 %
arrivent 7 fois sur 10 ? » Elle était mal répondue.

Dès trois verdicts, la Notice affirmait « sur 3 verdicts, ce n'est plus de la
malchance » et enchaînait sur « baisse tes probabilités d'autant ». Sur trois
paris à 75 %, n'en gagner qu'un arrive **une fois sur six** par pur hasard.
L'outil conseillait donc de corriger un jugement que rien ne montrait faux — et
corriger un jugement juste, c'est le dérégler.

- La Notice calcule maintenant, exactement, à quelle fréquence des probabilités
  justes produiraient un écart au moins aussi grand, et affiche le nombre :
  « une fois sur 6 », « une fois sur 117 ». En dessous d'une fois sur vingt elle
  conclut ; au-dessus elle montre l'écart et dit de ne pas le corriger.
- Le calcul est exact, pas approché par la moyenne des probabilités. Deux paris
  à 5 % et un à 95 %, tous perdus : c'est le pari sûr qui parle, et une moyenne
  à 35 % l'effacerait. Une fois sur 21 — le Sage le dit ; avec la moyenne il se
  serait tu.
- Il reste déterministe : de l'arithmétique sur des flottants, sans réseau,
  sans modèle, dans le même ordre des deux côtés du portage.
- Un seuil plat aurait été faux dans les deux sens : trois verdicts à 75 % ne
  prouvent rien, mais quatre paris à 90 % tous perdus valent une chance sur dix
  mille et méritent d'être dits. C'est l'écart **et** le nombre.
- Le port Swift porte le même calcul. Deux vecteurs de parité neufs le tiennent,
  un de chaque côté du seuil ; le cas d'arrondi a été refait pour qu'il continue
  de séparer les deux formules de `Numbers.round`.
- `review()` expose `resolved_probabilities` : la moyenne seule ne permettait
  pas de répondre.

## 3.9.1 — La leçon est la sienne, ou rien

Le journal écrivait dans le champ « leçon », quand Thomas n'en donnait pas :

    Forecast DEC-138fee1a was incorrect: predicted 0.75, observed 0.

Une phrase de machine, en anglais, dans un outil français, dans le champ prévu
pour ce que *lui* a compris — et gravée pour de bon, puisqu'une entrée tranchée
ne se réécrit plus. L'app lui offre pourtant un champ pour l'écrire : le
laisser vide faisait écrire la machine à sa place.

Elle n'apprenait rien : la probabilité, le statut et le score de Brier sont
déjà dans l'entrée, et cette phrase ne fait que les redire. Elle coûtait, en
revanche, la seule chose qui compte — on ne distinguait plus « il n'a rien
noté » de « il a noté ceci ». C'est la règle de provenance du dépôt, celle qui
lui a déjà coûté un CV faux et un marché écarté, appliquée cette fois à ce que
l'outil écrit sur lui.

- `resolve()` enregistre sa phrase, ou rien. `abandon()` garde la raison qu'il
  donne, qui est déjà la sienne.
- Le port Swift faisait déjà juste — `lesson.isEmpty ? nil : lesson`. C'est le
  moteur de référence qui divergeait, et rien ne le disait : les vecteurs de
  parité couvrent la Notice, pas les champs que le journal écrit.
- La chaîne n'est pas touchée : la leçon n'entre pas dans l'empreinte.

## 3.9.0 — L'échéance tombe le jour dit, pas le lendemain

Le seul geste que cet outil réclame à son auteur est de rendre son verdict à
l'échéance. Il le réclamait un jour trop tard, systématiquement.

`due_at` vaut `created_at + horizon_days`, donc il porte l'heure de l'écriture.
Comparé comme un instant, un horizon de 14 jours pris un soir à 20 h n'échoit
qu'à 20 h le quatorzième jour. Thomas écrit ses décisions le soir et ouvre son
rapport le matin : le matin du jour dit, le rapport se contentait d'un INFO
« la prochaine échéance tombe aujourd'hui », noyé dans la liste. La carte
« À trancher aujourd'hui » n'arrivait en tête que le lendemain.

Deux documents promettaient l'inverse, et c'est le code qui avait tort :
`A_FAIRE.md` — « la carte passera en haut, À trancher aujourd'hui » — et le CLI
lui-même, qui imprime « verdict attendu le 20/09/2026 » au moment de
l'enregistrement.

- `Entry.due_on` est le jour de l'échéance ; `is_due`, `days_until_due` et
  `overdue_days` comptent en jours de calendrier. `due()` et la phrase
  « prochaine échéance » passent par eux.
- Le retard se comptait en secondes tronquées : il manquait une demi-journée à
  chaque fois. Sept jours de retard s'annonçaient comme six, et le passage en
  CRITIQUE — « passé une semaine » — arrivait un jour après ce que sa propre
  phrase promet.
- La faute était à trois endroits parce que chacun refaisait le calcul. La
  règle a maintenant un domicile, et `test_journal.py` refuse qu'un module
  reconvertisse `due_at` pour autre chose que l'afficher.
- Le test qui couvrait l'horizon vérifiait le treizième jour et le quinzième,
  et sautait le quatorzième — la frontière même. C'est là que c'était faux.
- Rien de tout cela ne touche la chaîne d'intégrité : `due_at` est dérivé et
  n'entre pas dans l'empreinte. Les journaux existants restent vérifiables.
- Le port Swift porte la même correction, et les vecteurs de parité couvrent
  désormais le cas « écrite le soir, relue le matin » et son versant « la
  veille au soir ». Ils ne le couvraient pas : tous les journaux y étaient
  écrits et relus à la même heure, et les deux moteurs tombaient d'accord pour
  une mauvaise raison.

## 3.8.0 — Le bouton 🔎 : chercher depuis le téléphone

« Chercher pour moi » était le point 5 de sa liste et le seul qui n'existait
qu'au clavier : depuis son téléphone, il ne pouvait pas l'atteindre. C'est
maintenant le troisième rond de l'app.

- `GET /api/offres` montre ce qui partirait — son profil, le même texte que
  `offres --blanc` — sans clé et sans rien dépenser. `POST /api/offres`
  cherche.
- La route ne peut pas écrire dans le journal : elle rend du texte, et
  `test_sage_offres.py` le vérifie sur le journal lui-même, pas sur
  l'instruction donnée au modèle. L'autorité reste lui, avant toute action.
- Le verrou est **le même objet** que celui de la conversation. Deux verrous
  distincts auraient laissé une recherche et une réponse partir ensemble, sur
  un crédit vérifié une seule fois : c'est la course qui vide les cinq dollars
  sans que rien ne l'ait refusée.
- `chercher()` rend maintenant son coût, comme sa jumelle `parle.repondre()`.
  Il ne le rendait pas, donc une recherche ne se comptait nulle part : le solde
  affiché sur le téléphone était faux de tout ce qui avait été cherché. Compté
  des deux côtés désormais, au clavier comme dans l'app.
- Les liens des offres sont cliquables sans que le texte du modèle devienne du
  HTML : chaque morceau est posé par le DOM, et seuls `http://` et `https://`
  deviennent des liens. Ce que rend l'agent vient d'annonces lues sur le web.
- Son profil disait « il ne cherche pas d'alternance ». Ce qu'il a dit est
  « une reprise d'études en alternance m'intéresse, mais je n'ai ni école ni
  entreprise à ce jour » — marqué DIT dans `proto/suivi_candidatures.py`. Le
  durcissement était une déduction non marquée, qui faisait écarter des
  annonces qu'il aurait voulu voir. Remis à ce qu'il a dit.
- La garde d'origine — celle qui empêche une page web quelconque d'agir en son
  nom — est désormais vérifiée sur **toutes** les routes `/api/`, lues dans le
  source plutôt qu'énumérées à la main. `/api/offres` est la première qui
  dépense de l'argent réel.
- `test_offres.py` ne vérifiait la coupure que sur les imports, ce qui
  interdisait aussi le branchement demandé sans rien prouver de plus. Il coupe
  maintenant le module pour de bon et refait tout le parcours gratuit.

## 3.7.1 — The report stops reproaching what could not have been done

One defect, found in three places. The Sage told Thomas, the morning after he
recorded his first decision, « Aucune décision sur Stabilité » — in ATTENTION,
as the report's headline. He had written one line. The foundation has two
rungs, and one line cannot occupy two: the reproach described arithmetic, not
conduct, and nothing he could have done that morning would have avoided it.

The sentence was also false. « 4h sont allées ailleurs » summed `hours_total`,
which included the 4h he had put on Revenus — the second rung of the very
foundation it was naming. It called « ailleurs » exactly where the hours were.

- `foundation_item` now waits for at least as many decisions as the foundation
  has rungs, and counts only the hours actually spent outside it. With no hours
  outside, the empty rung is stated as INFO — a fact worth knowing, not a
  reproach to make.
- The same premature reproach had already been paid for once, on « heures
  engagées sans verdict », and fixed in one place only. This was the second.
  The third was `python -m singular review`, which held its own copy of the
  rule (`list(Tier)[:2]`) and reproached from the first decision too.
- Third occurrence, so the repository's own rule applies: stop correcting it,
  make it impossible. The rule now has one home. `review` calls
  `foundation_item` and prints its sentence; `tests/test_reproche_premature.py`
  fails if any module re-derives the founding rungs or rewrites the phrase.
- The Swift port and the committed notice vectors carry the same correction,
  with vectors for both sides of it.

## 3.7.0 — The Sage in daily use: concurrency, business fields, faculties

The journal went into real daily use on a phone. Everything below was found by
using it, not by reading it.

Security — the journal and the Sage:

- `resolve()` and `abandon()` read the status, refused if it was not open, then
  wrote — three steps, no lock. Measured with four concurrent processes: two
  contradictory verdicts accepted on the same decision, and the loser was told
  its own verdict had been recorded while the journal kept the other one. The
  tool lied about what it had just written, and calibration is computed from
  the stored verdict. Closed twice over: `BEGIN IMMEDIATE` before the read, and
  a conditional `UPDATE ... AND status=OPEN` whose `rowcount` is checked.
  Either alone suffices — verified by disabling them separately.
- The schema migration could fail with "duplicate column name" when two
  processes opened the journal at once: the version check and the `ALTER TABLE`
  ran in a deferred transaction. Now `BEGIN IMMEDIATE`.
- Any web page open on the machine while the Sage was running could write to
  the journal and render verdicts — `127.0.0.1` was trusted wholesale, and the
  browser is somebody. Refused on three facts the calling page does not
  control: the Host header must be an address, the Origin must match, and the
  body must be declared JSON.
- The access token file is now created 0600, and existing files are tightened
  on startup.
- The token guard no longer depends on how the server was asked to start:
  `--host 0.0.0.0` without `--lan` served the personal journal to the whole
  network with an empty token. Absence of a token now refuses.
- A double tap sent two verdicts, or recorded the same decision twice. One
  submit lock per form in the web app, and the 409 now reads in French.

Journal — schema v2:

- Entries carry `expected_gain_eur` and `reversibility`. Business fields enter
  the integrity payload only when set, so v1 entries keep their exact payload
  and stay verifiable. Real migration by `ALTER TABLE`, not
  `CREATE TABLE IF NOT EXISTS`.
- The report adds expected gain, hours spent on decisions with no stated gain,
  and open irreversible decisions.

Faculties — the parts that call a model, and can all be cut:

- `singular/analyse.py` comments the already-computed report.
  `analyse --blanc` prints exactly what would leave the machine and sends
  nothing; a test pins it to the same string that is sent.
- `singular/offres.py` searches the web for engineering-office job offers and
  proposes at most five. It cannot apply, write, or decide — it imports
  neither the journal nor the execution boundary, and a test reads the imports.
- `singular/parle.py` is a conversation that already knows the day's report and
  the previous thread. Bounded to twenty exchanges, single cached system block,
  per-turn token accounting. It cannot write to the journal.
- Continuous conversation is affordable because the thread itself is cached up
  to the last recorded turn, not just the system prefix: without that the whole
  history is rebilled at full price every turn, and the twentieth costs twenty
  times the first. `parle` defaults to `claude-sonnet-5` for the same reason —
  the one faculty whose default differs, because it is the only one called
  twenty times in an evening.
- Spending is counted for life, per model, and never resets with the daily cap.
  The repository holds no prices at all — a hardcoded tariff would age silently
  and would be used to decide when to stop — so `~/.singular/tarifs.json` holds
  the owner's own figures and credit, and until it does the conversation talks
  in tokens and never in dollars. A test refuses any price written into the
  code.
- The Sage serves that conversation to the phone at `/api/parle` — the first
  route in the app that can spend money, and the reason the isolation test's
  allowlist now names it. Three refusals stand before the spend: an empty or
  oversized question, a turn already in flight (server-side, not just in the
  browser), a daily cap of sixty answers held on disk so a restart cannot reset
  it, and — once tariffs are known — a refusal before the call when the credit
  is spent. A cut faculty costs nothing and consumes no quota, and the report,
  the journal and the verdicts keep working while it is cut.
- None of them can leak the key: `tests/test_facultes_sans_fuite.py` discovers
  every module that refuses with `AnalyseIndisponible` and checks both the
  shape of its messages and what actually escapes when the SDK fails. An
  `APIResponseValidationError` used to traverse all four handlers and reach the
  screen — and, through the Sage's JSON error body, the browser.

Packaging:

- `singular/__init__.py` resolves its exports lazily. The journal and the Sage
  now import on a bare Python with nothing installed; a broken submodule still
  reports its real cause rather than an `AttributeError`.

## 3.6.0 — Artifact Identity, Bounded Integrity, and the Sage

Security — artifact identity:

- `artifact_fingerprint` now covers the whole code object (constants recursing into nested code, global and attribute names, varnames, freevars, cellvars, argument counts, flags) plus a function's defaults and keyword defaults. It hashed `co_code` alone, so two same-named implementations differing only in which URL they post to were one artifact — the substitution the durable capability record exists to refuse.
- A class's non-`__code__` attributes now count too: properties through their getter/setter/deleter, `functools.partial` through its target and bound arguments, callable instances through their `__call__`, and constants by value. Mutable class attributes are recorded by type only, so a cache cannot revoke a live capability.
- Execution capability schema is v2. A v1 row's fingerprint cannot be recomputed and cannot be trusted, so opening a v1 database revokes every binding with a reason naming the rotation.
- `ExecutionCapabilityRegistry.attach()` attaches the durable store before writing bindings, so a partial failure leaves the registry stricter rather than reverting to in-memory verification, and refuses to replace an already-attached store. `revoke()` writes durably first, so a failed write can no longer leave a token dead in this process and ACTIVE in the next.
- `improvement_registry.artifact_fingerprint` no longer falls back to `str()`: data is canonicalised by value and type, code by the boundary's code identity, and an object that can state neither is refused rather than fingerprinted by its memory address. Schema is v3.

Integrity and recovery:

- The durable integrity scan reads every table in one deferred read transaction. Executions and mission statuses were read at different instants, so a concurrent writer could show the scan a contradiction that never existed — and the boundary refuses every execution while the scan is dirty.
- The execution gate scans the mission being executed rather than the whole database. One bad row anywhere used to shut every mission permanently, with no supported repair. `check()` with no argument remains the operator's whole-database view.
- `executions(mission_id)` and `external_effects(execution_key)` are indexed.

Journal:

- A decision recorded with an integer cost broke the hash chain from its first entry, permanently: the value was fingerprinted as written and read back as a float. Values are canonicalised before fingerprinting.

The Sage:

- Added `singular/sage/`: an observation engine that turns the journal into a daily report, and a standard-library web app installable on a phone's home screen. It is advisory by construction — a test refuses any import of the execution boundary from the package.
- Added `ios/SingularSage/`: the same engine as a native SwiftUI iPhone app, pinned to the Python implementation by generated vectors that assert identical output text.

## 3.5.2 — Governed Control Plane & Continuous Improvement

- Added `SingularControlPlane` as the canonical top-level lifecycle surface for build -> attest -> execute -> observe outcome.
- Added `ControlPlaneDecision` so a validated decision and its durable attestation travel together at the orchestration layer.
- Added a durable outcome ledger binding forecast, actual result, execution status and exact decision context fingerprint.
- Added a human-reviewed learning queue and bounded self-improvement engine; observed error can create a test proposal, never silent policy mutation.
- Added `TemporalAdvisor` forecast signals with explicit non-authorizing semantics.
- Hardened `DecisionAttestationStore` so `:memory:` instances remain valid across internal SQLite connections.
- Expanded execution-boundary static auditing to detect aliases of the durable executor and direct calls to its inner validated methods outside the canonical adapter/service.
- Added regression coverage for the top-level control plane and the learning lifecycle.

## 3.5.1 — Execution Boundary Hardening

- Made durable execution itself require a valid, active `DecisionAttestationStore` record; the inner executor can no longer bypass durable issuance/revocation checks.
- Bound durable execution identities to the exact `ValidatedTrajectoryDecision.context_fingerprint`, preventing a distinct decision context from reusing the same mission/action execution identity.
- Routed handler execution, external-effect execution and external-effect reconciliation through the strict validated boundary surface.
- Added a static/dynamic `ExecutionBoundaryAuditor` for production call-site bypass detection, direct inner-executor detection and deny-by-default raw API probes.
- Added a canonical `ValidatedDecisionService` lifecycle surface so production callers can build, attest, execute and revoke decisions without manually sequencing security-critical primitives.
- Added a durable outcome ledger that binds forecast, actual outcome, execution status and decision context for calibration and replay-safe learning.
- Added a human-reviewed learning proposal queue and a bounded self-improvement engine; measured error can produce strategy tests, but never automatic policy or authorization mutation.
- Strengthened historical reasoning so contested evidence remains counterevidence instead of inflating pattern support.
- Added explicit temporal forecast signals for collective cognition while preserving a non-authorizing boundary.
- Expanded adversarial tests for attestation, restart, replay identity, external-effect routing, temporal authority separation and continuous-learning governance.

## 3.5.0 — Fail-Closed Validated Execution Boundary

- Added an immutable, tamper-evident `ValidatedTrajectoryDecision` as the sole executable authorization artifact.
- Bound validated execution to the exact handler target, or for external effects to provider implementation, provider name, operation and payload fingerprint.
- Disabled raw durable action, effect and reconciliation entry points; callers must present a validated decision.
- Closed direct execution bypasses in ToolFabric, MissionAutopilot and Empire AutopilotSupervisor.
- Added a mandatory construction pipeline: domain state -> Human Optimization -> exact Trajectory Optimization -> Trajectory Engine -> Global Decision Gate -> validated decision.
- Persisted the source domain/intervention/interaction inputs and re-ran deterministic human and trajectory optimization during validation to resist forged portfolios.
- Added strict `ActionRequest` validation for finite, bounded security-relevant numeric inputs and nonblank identifiers.
- Added adversarial tests for handler, provider, operation and payload substitution plus direct execution bypasses.
- Added durable `DecisionAttestationStore` issuance/revocation with TTL and exact context binding.
- Added evidence-bounded historical memory and probabilistic future reasoning, with explicit canonical facts, contested evidence, assumptions, horizon uncertainty and non-authorizing future scenarios.
- Kept the new execution boundary fail-closed until all production callers are migrated and CI is green.

## 3.4.3 — Interaction-Aware Trajectory Optimization

- Added a dedicated trajectory layer that evaluates portfolios rather than only individual interventions.
- Added explicit pairwise synergy and conflict effects with confidence discounting.
- Added exact deterministic portfolio evaluation for up to 22 candidates.
- Added fail-closed rejection beyond the exact search safety limit instead of silently presenting an approximation as optimal.
- Added regression coverage proving synergy can overturn individual rankings and conflicts can invalidate an otherwise attractive combination.
- Kept trajectory optimization recommendation-only; it cannot authorize execution or mutate governance.

## 3.4.2 — Decision Audit Hardening

- Replaced the large-search-space greedy fallback with deterministic branch-and-bound using an admissible optimistic bound and an explicit node budget.
- Preserved an explicit heuristic fallback only when the branch-and-bound budget is exhausted, with `exact=False` surfaced as a warning condition.
- Added duplicate cross-domain interaction rejection so the same causal edge cannot be silently double-counted.
- Made missing domain state auditable through explicit warnings instead of silently dropping interventions.
- Stopped the `DomainHypothesis` bridge from equating evidence strength with causal confidence; callers can now provide causal confidence explicitly.
- Added regression coverage for duplicate interactions, missing-state auditability and conservative causal bridging.

## 3.4.1 — Optimization Quality Hardening

- Replaced greedy small-portfolio selection with deterministic exact portfolio optimization for search spaces up to 22 candidates.
- Added deterministic tie-breaking for reproducible decisions.
- Added an explicit large-search-space heuristic fallback warning rather than presenting a heuristic as globally optimal.
- Preserved capacity, domain-diversification and governance constraints during portfolio selection.
- Added regression coverage proving the optimizer avoids a classic greedy-knapsack failure.

## 3.4.0 — Canonical Human Optimization

- Consolidated the two Human Optimization implementations around `singular.human_optimization`.
- Preserved the historical `singular.human_optimizer` API as a compatibility facade with no independent optimization math.
- Added target-aware domain state, dependency-aware bottleneck detection and cross-domain interaction strength.
- Added intervention dimensions for causal confidence, capacity, reversibility, time-to-result, recurrence and cross-domain impact.
- Added explicit expected global gain, capacity accounting and uncertainty reporting.
- Added a bridge from `DomainHypothesis` to the canonical intervention model.
- Integrated Human Optimization into `GlobalDecisionGate` as advisory decision context; it cannot authorize execution.
- Added regression, edge-case, capacity, uncertainty and global-control integration tests.

## 3.3.0
- Added durable SQLite persistence for missions, approvals and audit events.
- Added deterministic idempotency-key primitive.
- Added restart-safe `DurableMissionRuntime`.
- Strengthened ORANGE governance: preparation is allowed, execution requires human approval.
- Kept RED/BLACK fail-closed behavior.

## 3.2.0
- Added governed specialist workforce routing.
- Added deterministic Red Team pre-execution gate.
- Added defense-in-depth governed executor.
- Added 4 governance/workforce tests.

## 3.1.0 — Production Foundation

- Added typed environment configuration and safe defaults.
- Added defense-in-depth action policy for autonomy boundaries.
- Added append-only in-memory audit trail.
- Added health/readiness checks.
- Isolated the optional OpenAI Agents SDK runtime boundary.
- Added GitHub Actions CI for Python 3.11–3.13.
- Added Ruff and mypy development configuration.
- Fixed V3 action preparation so an explicitly supplied delegation contract is actually routed to the Governor.
- Added security, autonomy and architecture documentation.
