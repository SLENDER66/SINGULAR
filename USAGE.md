# Le journal — mode d'emploi

Ta constitution dit : *maximiser le progrès réel, sans confondre activité et
résultat.* Cet outil est ce qui la fait respecter. Il ne fait qu'une chose :
il t'oblige à écrire ce que tu attends **avant** d'agir, puis il revient te
demander ce qui s'est passé.

## Installation

Dans le **Terminal** du Mac (Cmd+Espace, tape « Terminal ») :

```sh
python3 --version
```

Il faut **3.11 ou plus**. Le `python3` livré avec macOS est souvent en 3.9, et
l'installation refusera alors de se faire — le message le dira. Dans ce cas,
installe une version récente depuis [python.org](https://www.python.org/downloads/macos/)
et rouvre le Terminal.

Ensuite :

```sh
cd ~/Documents/SINGULAR
python3 -m pip install -e ".[dev]"
```

`python3` et jamais `python` : depuis macOS 12.3 la commande `python` seule
n'existe plus. `python3 -m pip` et jamais `pip` seul : `pip` peut viser un
autre Python que celui qui lancera SINGULAR.

La base vit dans `~/.singular/journal.db`.

## Les cinq commandes

```bash
python3 -m singular apply "Anthropic" "Ingénieur agents"   # une candidature, 5 s
python3 -m singular add                                    # une décision, 30 s
python3 -m singular due                                    # ce qui attend un verdict
python3 -m singular resolve DEC-xxxxxxx --yes|--no         # ce qui s'est passé
python3 -m singular review                                 # où vont tes heures
```

Plus `list`, `abandon DEC-xxx "raison"`, `export` (CSV), `status` (une ligne),
et `import` (reprendre un autre journal, voir plus bas).

### `analyse` — la seule commande qui coûte de l'argent

```bash
python3 -m singular analyse --blanc     # montre ce qui partirait, n'envoie rien
python3 -m singular analyse             # fait commenter la Notice par un modele
```

**`--blanc` ne coûte rien et ne demande rien.** Pas de SDK, pas de clé, pas de
machine allumée : il assemble le rapport en texte et n'appelle personne. Colle le bloc dans
l'app Claude — c'est le même pont que le `6` du prototype, pour le journal.
C'est aujourd'hui le seul chemin qui marche depuis un téléphone seul, et un
test l'impose plutôt que d'en dépendre par chance.

Sans `--blanc`, elle est **coupée par défaut** : sans `ANTHROPIC_API_KEY` dans
l'environnement, elle le dit et affiche la Notice calculée sans elle. Tout le reste de SINGULAR
— journal, chaîne d'intégrité, Notice, calibration — n'a jamais besoin d'elle,
et `tests/test_sage_independence.py` le vérifie plutôt que de le promettre.

Pour l'allumer : `python3 -m pip install -e ".[analyse]"`, puis une clé depuis
console.anthropic.com (compte séparé de l'abonnement Claude, deux facturations).
Mets un plafond mensuel dès le premier jour.

**Lance `--blanc` avant la première vraie fois.** Il affiche exactement le texte
qui quitterait la machine — les observations et les chiffres de la Notice, pas
l'historique de tes décisions — sans contacter personne. C'est la même chaîne
que celle qui part ensuite, et un test l'impose.

Le modèle par défaut est `claude-opus-5`. `SINGULAR_ANALYSE_MODELE=claude-sonnet-5`
coûte environ deux fois moins ; c'est ton arbitrage, pas le mien.
`SINGULAR_ANALYSE_EFFORT` accepte `low`, `medium` (défaut), `high`.

Ce qu'elle ne peut pas faire, et ce n'est pas une consigne mais une absence
d'import : écrire dans ton journal, résoudre une décision, en créer une. Elle
commente un rapport déjà calculé. Elle ne décide jamais à ta place.

### `parle` — la conversation qui connaît ton journal

```bash
python3 -m singular parle                     # une conversation, tu tapes, elle répond
python3 -m singular parle "je fais quoi ?"    # une seule question, une seule réponse
python3 -m singular parle --oubli             # efface le fil, garde le journal
```

C'est la différence exacte entre parler à Claude dans son application et parler
à SINGULAR : **le modèle est le même** — Opus 5, ta clé — mais l'application
repart de zéro à chaque fois, alors qu'ici le rapport du jour et le fil de la
conversation précédente sont déjà là. Le fil vit dans `~/.singular/conversation.json`,
à côté du journal, et survit à la fermeture de la fenêtre.

**Elle n'écrit rien dans ton journal.** Enregistrer une décision reste `add`,
et ce n'est pas une consigne dans son instruction : le module n'importe pas le
journal, `tests/test_parle.py` le vérifie sur les imports. Un système qui
inscrit des décisions parce qu'on en a parlé finit par contenir des choses que
personne n'a décidées.

Trois choses tiennent la facture, dans cet ordre : l'instruction et le rapport
partent en **un seul bloc mis en cache** — payé une fois, relu ensuite ; le fil
est **borné aux vingt derniers échanges**, parce qu'une conversation renvoie
tout son historique à chaque tour ; et chaque réponse affiche
`[N jetons envoyés, M relus du cache, K rendus]`, parce qu'on ne corrige pas ce
qu'on ne voit pas.

Mêmes conditions qu'`analyse` : clé requise, coupée sans elle, le reste de
SINGULAR marche sans. `SINGULAR_PARLE_MODELE` et `SINGULAR_PARLE_EFFORT`
valent pour elle ce que leurs équivalents valent pour `analyse`.

#### Depuis le téléphone

Le Sage sert la conversation dans l'app : le bouton 💬, au-dessus du `+`. Le
serveur tourne sur le Mac, donc ça marche aux mêmes conditions que le reste de
l'app — Mac allumé, même wifi.

La clé se met **dans la fenêtre où tu lances le serveur, avant de le lancer** ;
un serveur déjà démarré ne la verra jamais :

```sh
export ANTHROPIC_API_KEY="sk-ant-..."
python3 -m singular parle "bonjour"
```

`export` ne vaut que pour la fenêtre en cours. Pour ne plus y penser, la même
ligne dans `~/.zshrc` — au prix d'avoir la clé en clair dans un fichier.

C'est la **seule route du Sage qui coûte de l'argent**, et trois choses
tiennent la facture :

- **Vingt réponses par jour.** Le compteur est sur le disque, pas en mémoire :
  un plafond qu'un redémarrage efface n'est pas un plafond. Au-delà, elle dit
  de revenir demain ou de passer par le clavier — où il n'y a pas de plafond,
  parce qu'une commande se tape et qu'un bouton se tapote.
- **Un seul tour à la fois.** Deux appuis feraient deux factures pour une
  question, et la seconde écriture du fil écraserait la première. Refusé côté
  serveur, pas seulement dans le navigateur.
- **Ce qu'il reste et ce que ça a coûté** sont écrits sous chaque réponse.

Sans clé, le bouton répond qu'elle est coupée — et la Notice, le journal, les
verdicts continuent exactement comme avant. `tests/test_sage_parle.py` le
vérifie en fabriquant la panne, plutôt que de le promettre.

#### Ce que ça coûte, avec tes chiffres et pas les miens

**SINGULAR ne connaît aucun prix, et c'est voulu.** Les tarifs changent, ce
dépôt ne se met pas à jour tout seul, et un chiffre faux ici servirait à
décider quand s'arrêter. Un test refuse tout tarif écrit en dur dans le code.

#### Voir ce qui part, avant que ça parte

```bash
python3 -m singular parle --blanc "ta question"
```

Les trois facultés qui sortent quelque chose de ta machine te montrent
d'abord ce qui partirait, sans rien envoyer : `analyse --blanc`,
`offres --blanc`, `parle --blanc`, et le même texte dans un bloc dépliable
sous les boutons 💬 et 🔎 de l'app.

L'aperçu comprend **l'instruction système**, pas seulement tes données : elle
te nomme, elle cite ta constitution, et pour la recherche elle porte la
garantie qui compte — « tu ne postules jamais ». Elle part à chaque appel et tu
ne la voyais nulle part.

La conversation est celle qui envoie le plus : le rapport du jour **et** tout
le fil des tours précédents. C'était la seule sans aperçu.

`test_ce_qui_part.py` capture ce que le service reçoit réellement et exige que
l'aperçu le couvre — dans les deux sens. Un aperçu qui montre moins rassure sur
ce qu'il cache ; un aperçu qui montre plus fait croire à une fuite qui n'existe
pas, et la fois d'après on ne le lit plus.

Tant que tu ne lui as rien dit, la conversation compte des jetons. Pour qu'elle
parle en dollars :

```bash
python3 -m singular parle --tarifs     # affiche le fichier à remplir
```

Colle-le dans `~/.singular/tarifs.json`, avec les prix relevés sur
console.anthropic.com (en dollars par million de jetons) et le crédit que tu as
acheté. À partir de là, chaque réponse dit ce qu'il te reste.

Le fichier affiché liste **tous** les modèles sur lesquels l'outil peut
dépenser — la conversation, l'analyse et la recherche d'offres n'utilisent pas
le même. Il n'en nommait qu'un, et il suffisait d'une recherche pour mettre
dans le compte un modèle sans tarif : le total refuse alors de répondre, parce
qu'un total qui oublie une dépense sert quand même à décider quand s'arrêter.
Le fichier est maintenant généré depuis les modèles réels, et un test refuse
qu'une faculté dépense sur un modèle qui n'y figure pas.

Si un modèle manque quand même — tu as changé `SINGULAR_OFFRES_MODELE`, par
exemple — le rapport le **nomme** au lieu de te renvoyer écrire des tarifs que
tu as déjà écrits, et il te dit ce qu'il te reste *au plus*.

Deux gardes, et elles ne comptent pas la même chose :

- **Soixante réponses par jour** depuis le téléphone. C'est large exprès : un
  garde-fou contre l'emballement — une poche, une soirée distraite — pas contre
  l'usage. Le clavier n'en a pas.
- **Le crédit restant**, dès que tes tarifs sont écrits. Quand il tombe à zéro,
  elle refuse *avant* d'appeler. Le service refuserait de toute façon, une
  requête plus tard et sans le dire aussi clairement. Si l'estimation te semble
  fausse, c'est `credit_usd` que tu corriges, pas le code.

  Cette garde se désarmait dès qu'un modèle n'avait pas de tarif : elle lisait
  le total exact, qui refuse de répondre dans ce cas, et ne refusait donc plus
  rien. Une garde qui s'éteint quand on se sert de l'outil est pire que pas de
  garde. Elle compte maintenant sur ce qu'elle sait — un chiffre qui surestime
  ce qui reste, donc qui refuse tard mais jamais trop tôt.

Le total des jetons ne repart jamais à zéro, lui. Sans ça, on peut respecter le
plafond tous les jours et vider son crédit sans l'avoir vu venir.

Les deux gardes lisent le même fichier, et deux choses peuvent l'écrire en même
temps : le serveur qui répond au téléphone, et la ligne de commande. Elles
lisaient toutes deux le total avant d'écrire chacune le sien. Mesuré sur huit
processus et quarante dépenses : **neuf plantages et vingt et une dépenses
perdues**. Un compte qui sous-estime fait refuser la garde du crédit trop tard,
et le plafond du jour pouvait être dépassé de la même façon. Un fichier verrou
sérialise désormais les écritures ; il est repris s'il traîne plus de cinq
secondes, pour qu'un processus tué ne condamne pas l'outil.

#### Pourquoi Sonnet et pas Opus

`parle` est la seule faculté dont le modèle par défaut est `claude-sonnet-5`.
`analyse` et `offres` sont des coups uniques ; une conversation, c'est vingt
appels dans la soirée, chacun portant tout ce qui précède. Sur un crédit de
cinq dollars, ce choix décide si la conversation dure une semaine ou un
après-midi.

Ce n'est pas un rabais : Sonnet 5 est un vrai modèle Claude, le même SDK, la
même clé. Pour revenir à Opus : `SINGULAR_PARLE_MODELE=claude-opus-5`.

Et le fil lui-même est mis en cache jusqu'au dernier tour enregistré. Sans ça
il est refacturé au plein tarif à chaque question, et le vingtième tour coûte
vingt fois le premier — c'est ce qui rend une conversation continue tenable.

### Ce que l'outil refuse, et comment il le dit

Les règles sont celles du journal : probabilité strictement entre 0 et 1,
heures positives, horizon d'au moins un jour, gain qui n'est pas un coût. Le
journal les fait respecter et lève en anglais — c'est son contrat de
bibliothèque.

Mais ce message-là te remontait. Au clavier tu lisais `probability must be
strictly between 0 and 1` ; sur ton téléphone, `expected_gain_eur cannot be
negative: a cost is not a gain`. Chaque surface s'était mise à valider de son
côté — le clavier en français, le formulaire par des attributs HTML, le serveur
pas du tout — et c'est celle qui ne validait pas qui te parlait anglais.

`singular/saisie.py` est le seul endroit où la règle est dite en français.
`test_saisie_au_clavier.py` vérifie que les **trois** surfaces acceptent
exactement ce que le journal accepte : une divergence te ferait perdre ta
saisie, ou passer une décision que le journal refuse juste après.

Ce que tu lis maintenant, des deux côtés :

| Tu tapes | Il répond |
|---|---|
| `75` pour la probabilité | `pas en pourcents - pour 75 %, ecris 0.75` |
| `1` | `une certitude ne peut pas avoir tort, une impossibilite non plus` |
| `-100` en gain | `un cout n'est pas un gain : laisse vide si tu ne sais pas` |
| `0` en horizon | `au moins un jour, sinon rien ne peut etre verifie` |

### `offres` — le premier agent

```bash
python3 -m singular offres --blanc          # montre ce qui partirait, n'envoie rien
python3 -m singular offres                  # cherche des offres BE dans la region
python3 -m singular offres "jusqu'a Albi"   # avec une precision
```

Il cherche sur le web, écarte, et propose cinq offres au maximum, chacune avec
ce qui correspond **et** ce qui coince. Puis il s'arrête. **Il ne postule
jamais, il n'écrit rien, il ne décide de rien** — et ce n'est pas une consigne
dans son instruction, qui se contournerait par une tournure de phrase : il
n'importe ni le journal, ni la frontière d'exécution, ni de quoi envoyer un
message. `tests/test_offres.py` ne s'en tient plus aux imports : il coupe le
module pour de bon et refait tout le parcours gratuit, et `test_sage_offres.py`
vérifie sur le journal lui-même qu'une recherche ne l'a pas touché.

Même conditions qu'`analyse` : clé requise, coupé sans elle, `--blanc` gratuit.
Il coûte plus cher qu'`analyse` — chaque recherche ramène des pages entières —
d'où un plafond de cinq recherches par appel, qui rend la facture prévisible.
Ce que la recherche a dépensé est compté dans le même total que la
conversation, au clavier comme au téléphone : sans ça, le solde affiché sur le
téléphone serait faux de tout ce qui a été cherché ailleurs.

#### Depuis le téléphone : le bouton 🔎

Le même agent, dans l'app, troisième rond en bas à droite. Il montre d'abord
**ce qui part de ton téléphone** — le même texte que `--blanc` au clavier —
puis cherche, et affiche les offres avec leurs liens cliquables.

Les gardes sont celles de la conversation, plus une : le verrou est **le même
objet**, parce que c'est le même porte-monnaie. Lancer une recherche pendant
qu'une réponse arrive dépenserait deux fois sur un crédit vérifié une seule
fois. Un double appui ne lance donc qu'une recherche, un crédit épuisé refuse
avant de chercher, et une faculté coupée le dit au lieu de ressembler à une
panne.

### Ce que `add` demande en plus depuis la v2 du journal

Deux questions facultatives, à la fin : **ce que la décision rapporte si elle
marche**, en euros, et **si tu peux revenir en arrière**. La constitution
demande de juger une décision sur « options, levier, coût, vitesse,
réversibilité » ; sans ces deux réponses, le journal ne connaissait que le coût
en heures.

Laisser le gain vide veut dire « non chiffré », **pas** « ne rapporte rien » :
le journal garde la différence, et c'est elle que la Notice reproche au-delà de
vingt heures **sur tes dix dernières décisions**. La fenêtre compte : le journal
ne se réécrit pas, donc un gain oublié le reste, et un total à vie ne redescend
jamais. Le constat portait sur ce total — quinze mois à chiffrer chaque décision
laissaient donc la même phrase tous les matins, au-dessus du même conseil sur le
prochain enregistrement. Il porte maintenant sur l'habitude en cours, la seule
chose que le prochain enregistrement peut changer. En ligne de commande :
`--gain 5000` et `--reversibility irreversible`.

Une décision irréversible dont l'échéance passe sans verdict devient la
seule observation CRITIQUE avec la chaîne rompue. C'est voulu : partout
ailleurs, le temps mal placé peut encore être réaffecté.

## Le même journal, en app

```bash
python3 -m singular sage          # ouvre http://127.0.0.1:8765/
python3 -m singular sage --lan    # joignable depuis ton téléphone, avec un jeton
```

`sage` sert le journal comme une application web, installable sur l'écran
d'accueil d'un iPhone (Safari → Partager → « Sur l'écran d'accueil »). Elle
affiche le rapport du jour plutôt que la liste brute : ce qui attend un verdict
et depuis combien de temps, l'écart entre ce que tu annonces et ce qui arrive,
les rangs de ta constitution restés vides.

`--lan` l'ouvre aux autres appareils du wifi et exige alors un jeton d'accès,
imprimé dans l'adresse au démarrage — le wifi d'une maison n'est pas un cercle
de confiance.

L'application iPhone **native** est dans `ios/` ; sa recette de compilation est
dans `ios/README.md`.

## Sur l'iPhone seul, sans Mac et sans rien installer

Depuis que `singular/__init__.py` résout ses noms à la demande, le cœur n'a
plus aucune dépendance : journal, chaîne d'intégrité, Notice, ligne de commande
et serveur du Sage tournent en bibliothèque standard pure. Donc dans **a-Shell**
(gratuit, App Store), qui embarque Python.

**Précise la branche.** Un `lg2 clone` sans elle prend la branche par défaut,
qui n'est pas toujours celle qui porte le travail. Le nom ci-dessous est celui
que `CLAUDE.md` désigne aujourd'hui ; `python3 tools/check_repo_state.py` dit
l'état réel du jour, et il faut le croire plutôt que cette ligne — c'est
exactement pour ça qu'il existe.

```sh
lg2 clone -b claude/decision-companion-rebuild-3k25h3 https://github.com/SLENDER66/SINGULAR
```

```sh
cd SINGULAR && python3 -m singular sage
```

Puis Safari sur `http://127.0.0.1:8765/`.

**Ce qui reste à vérifier, et que personne n'a encore testé :** iOS suspend les
applications passées à l'arrière-plan. Basculer d'a-Shell vers Safari peut
couper le serveur. Si la page ne charge pas, c'est ça — dis-le, il y a d'autres
chemins.

## Reprendre un journal venu d'ailleurs

Tu changes de machine, ou l'ancienne est hors de portée un moment. Tu écris en
attendant, et un jour tu récupères l'ancien fichier. Les deux histoires se
recollent alors en une seule :

```sh
python3 -m singular import /chemin/vers/ancien-journal.db
```

Les décisions de l'autre journal sont ajoutées **à la fin du tien**, dans leur
ordre d'origine. Les tiennes ne bougent pas : elles gardent exactement
l'empreinte qu'elles avaient. Seules les reprises sont resignées, parce qu'une
décision ne peut pas suivre deux décisions différentes — et l'empreinte qu'elles
portaient là-bas reste écrite à côté, comme preuve que rien n'a été réécrit.

Ce n'est pas la même chose que recoller deux fichiers. Insérer les lignes d'une
base dans l'autre donne bien toutes les entrées, et la chaîne rend **faux** :
`tests/test_deux_journaux.py` le mesure plutôt que de le supposer.

Trois refus, et aucun n'écrit quoi que ce soit :

- l'autre journal a été modifié après coup — le reprendre y blanchirait la
  modification ;
- le tien a déjà une chaîne rompue — on n'ajoute rien derrière ;
- une décision est déjà des deux côtés — elle compterait deux fois, et le
  journal mentirait sur ce que tu as décidé.

**Le sens n'a pas d'importance pour ce que tu vois.** Mesuré : reprendre le gros
journal dans le petit ou l'inverse donne le même rapport, la même Notice, la
même calibration, et la liste s'affiche dans l'ordre chronologique des deux
côtés. `tests/test_deux_journaux.py` le vérifie.

Fais donc le geste le plus simple : garde ton journal habituel là où il est, et
reprends l'autre dedans. Une seule commande, aucun fichier à renommer — et
renommer un journal, c'est le seul geste de cette page qui puisse effacer trois
mois de décisions.

La seule différence est une nuance de preuve. Les entrées reprises sont
resignées, donc c'est la chaîne d'**ici** qui se vérifie de bout en bout ; celle
d'où elles viennent ne se rejoue plus comme chaîne. Chaque entrée reprise garde
l'empreinte qu'elle portait là-bas, et la reprise refuse une source dont la
chaîne est cassée : ce qui entre a donc été prouvé intact au moment où il est
entré.

**Un journal par machine, et rien ne les synchronise.** `~/.singular/journal.db`
sur le Mac et sur le téléphone sont deux fichiers différents. Deux journaux
divergents donnent deux calibrations fausses, et rien ne le signale : un journal
neuf ressemble exactement à un journal qu'on n'a pas encore rempli. C'est pour
ça que « Journal vide » affiche désormais **le chemin** où il a regardé. Tiens-toi
à une seule machine : rien ne synchronise en continu. Si tu as quand même écrit
des deux côtés, ce n'est pas perdu — `python3 -m singular import` reprend l'un
dans l'autre, et la section ci-dessus dit ce que ça garde et ce que ça coûte.

## Le mettre devant tes yeux

Ajoute à ton `~/.zshrc` — c'est le fichier que le Terminal lit à chaque
ouverture de fenêtre :

```sh
alias sj='python3 -m singular'
python3 -m singular status 2>/dev/null
```

Pour l'ouvrir : `open -e ~/.zshrc`. Le fichier n'existe pas forcément encore ;
`open -e` le crée.

`zsh` est le shell du Mac depuis Catalina. Cette section a été écrite deux fois
de travers : d'abord pour `~/.bashrc`, puis pour le profil PowerShell quand le
PC Windows était la machine principale. C'est justement la section censée
mettre l'outil devant les yeux, donc celle où se tromper de machine coûte le
plus.

Chaque terminal que tu ouvres affichera alors :

```
SINGULAR · 3 à trancher · 42h sans verdict · calibration +35%
```

Un journal qu'il faut penser à ouvrir est un journal qu'on arrête d'ouvrir.

## Les règles qui font que ça marche

**La probabilité doit être entre 0.05 et 0.95.** La certitude est refusée :
elle ne peut pas avoir tort, donc elle n'apprend rien.

**Le résultat prédit doit être observable.** « le système sera plus clair » ne
peut pas être tranché. « au moins 2 réponses de gens qui déploient des agents »
peut l'être.

**Pour une candidature, le résultat c'est l'entretien, pas la réponse.** Un
refus est une réponse, pas ce que tu voulais. Te noter sur les réponses te
laisserait te sentir productif pendant que rien ne bouge.

**Abandonner est un résultat.** `abandon DEC-xxx "le contexte a changé"` est
honnête. Laisser une décision ouverte pour toujours ne l'est pas.

**Tu ne peux pas réécrire une prédiction.** Les entrées sont chaînées par hash ;
modifier ou supprimer une entrée casse la chaîne et `review` te le dit. Un
journal qu'on peut retoucher après coup n'apprend rien.

## Ce que `review` te dit

```
  OÙ VONT TES HEURES

  2 décisions   102h engagées
  0h ont produit le résultat attendu
  90h encore sans verdict (1 ouvertes, 0 en retard)

  CE QUE TA CONFIANCE VAUT

  tu prédis en moyenne 80%   il arrive 0%
  surconfiance de +80% - tu crois plus que ce qui arrive
  Brier moyen 0.640  (0 = parfait, 0.25 = pile ou face)

  PAR RANG DE LA CONSTITUTION

  rang             décisions   heures  ont marché  sans verdict
  stabilite                -        -           -             -
  revenus                  1      12h          0h            0h   0%
  capacites                -        -           -             -
  opportunites             -        -           -             -
  patrimoine               1      90h          0h           90h   -
  liberte                  -        -           -             -

  /!\ Aucune décision sur Stabilité - Ta constitution ouvre sur Stabilité → Revenus.
      Ce rang n’a reçu aucune décision, alors que 90h sont allées ailleurs.
```

La dernière ligne ne s'affiche que quand elle a de quoi se dire : il faut au
moins autant de décisions que la fondation a de rangs — une ligne ne peut pas
en occuper deux — et les heures qu'elle nomme sont celles réellement passées
hors fondation. Le lendemain d'une première décision, elle se tait.

Les deux chiffres qui comptent : **les heures sans verdict** et **l'écart de
calibration**. Le premier mesure l'activité qui ne s'est jamais transformée en
résultat. Le second mesure de combien tu te crois.

### Quand la Notice conclut sur ta calibration, et quand elle s'abstient

Il faut trois verdicts avant que la question ait un sens. Ensuite, dire « ce
n'est plus de la malchance » est une affirmation, et elle doit être vraie.

Le Sage calcule donc, exactement, à quelle fréquence des probabilités **justes**
produiraient un écart au moins aussi grand, et il te donne le nombre : « une
fois sur 6 », « une fois sur 117 ». En dessous d'une fois sur vingt, il conclut
et te conseille de baisser tes probabilités — **quel que soit l'écart**. Au-dessus,
il ne conclut pas : il montre l'écart s'il saute aux yeux (quinze points ou plus)
et te dit de le regarder sans le corriger, et il se tait s'il est à la fois petit
et incertain.

La preuve est la seule condition depuis le 9 septembre. Avant, il fallait aussi
quinze points d'écart, et le Sage se taisait donc sur ce qu'il pouvait démontrer :
deux cents verdicts annoncés à 60 % dont la moitié arrivent font dix points
d'écart que le hasard seul produirait une fois sur deux cents, et rien ne
s'affichait. Où placer ce plancher est une question sur ce qui vaut la peine
d'être corrigé, pas sur ce qui est établi : elle a été posée plutôt que déduite,
et la réponse était « dès que c'est prouvé ».

Ça compte, parce que la version d'avant affirmait « sur 3 verdicts, ce n'est
plus de la malchance » et enchaînait sur « baisse tes probabilités ». Sur trois
paris à 75 %, n'en gagner qu'un arrive **une fois sur six** par pur hasard :
l'outil conseillait de corriger un jugement que rien ne montrait faux. Corriger
un jugement juste, c'est le dérégler — sur la seule question pour laquelle ce
journal existe.

Le calcul tient compte de **chaque** probabilité, pas de leur moyenne. Deux
paris à 5 % et un à 95 %, tous perdus : la moyenne les ramènerait à 35 % et
effacerait ce qui compte, alors que c'est le pari sûr qui est tombé. Une fois
sur 21, donc : le Sage le dit.

## Le rituel

| Quand | Quoi | Durée |
|---|---|---|
| Avant toute décision qui coûte plus de 2h | `sj add` | 30 s |
| Chaque candidature | `sj apply "Boîte" "Poste"` | 5 s |
| Chaque matin | `sj due` | 10 s |
| Chaque dimanche | `sj review` | 2 min |
