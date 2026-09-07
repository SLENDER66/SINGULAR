# Le journal — mode d'emploi

Ta constitution dit : *maximiser le progrès réel, sans confondre activité et
résultat.* Cet outil est ce qui la fait respecter. Il ne fait qu'une chose :
il t'oblige à écrire ce que tu attends **avant** d'agir, puis il revient te
demander ce qui s'est passé.

## Installation

```bash
cd ~/SINGULAR && pip install -e '.[dev]'
```

La base vit dans `~/.singular/journal.db`.

## Les cinq commandes

```bash
python -m singular apply "Anthropic" "Ingénieur agents"   # une candidature, 5 s
python -m singular add                                    # une décision, 30 s
python -m singular due                                    # ce qui attend un verdict
python -m singular resolve DEC-xxxxxxx --yes|--no         # ce qui s'est passé
python -m singular review                                 # où vont tes heures
```

Plus `list`, `abandon DEC-xxx "raison"`, `export` (CSV), `status` (une ligne).

### `analyse` — la seule commande qui coûte de l'argent

```bash
python -m singular analyse --blanc     # montre ce qui partirait, n'envoie rien
python -m singular analyse             # fait commenter la Notice par un modele
```

**`--blanc` ne coûte rien et ne demande rien.** Pas de SDK, pas de clé, pas de
PC : il assemble le rapport en texte et n'appelle personne. Colle le bloc dans
l'app Claude — c'est le même pont que le `6` du prototype, pour le journal.
C'est aujourd'hui le seul chemin qui marche depuis un téléphone seul, et un
test l'impose plutôt que d'en dépendre par chance.

Sans `--blanc`, elle est **coupée par défaut** : sans `ANTHROPIC_API_KEY` dans
l'environnement, elle le dit et affiche la Notice calculée sans elle. Tout le reste de SINGULAR
— journal, chaîne d'intégrité, Notice, calibration — n'a jamais besoin d'elle,
et `tests/test_sage_independence.py` le vérifie plutôt que de le promettre.

Pour l'allumer : `pip install -e '.[analyse]'`, puis une clé depuis
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
python -m singular parle                     # une conversation, tu tapes, elle répond
python -m singular parle "je fais quoi ?"    # une seule question, une seule réponse
python -m singular parle --oubli             # efface le fil, garde le journal
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
serveur tourne sur le PC, donc ça marche aux mêmes conditions que le reste de
l'app — PC allumé, même wifi.

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

`SINGULAR_PARLE_PLAFOND` n'existe pas : le plafond est dans le code, à vingt.
Le changer est un geste délibéré, pas une variable d'environnement qu'on
oublie à 200.

### `offres` — le premier agent

```bash
python -m singular offres --blanc          # montre ce qui partirait, n'envoie rien
python -m singular offres                  # cherche des offres BE dans la region
python -m singular offres "jusqu'a Albi"   # avec une precision
```

Il cherche sur le web, écarte, et propose cinq offres au maximum, chacune avec
ce qui correspond **et** ce qui coince. Puis il s'arrête. **Il ne postule
jamais, il n'écrit rien, il ne décide de rien** — et ce n'est pas une consigne
dans son instruction, qui se contournerait par une tournure de phrase : il
n'importe ni le journal, ni la frontière d'exécution, ni de quoi envoyer un
message. `tests/test_offres.py` le vérifie sur les imports.

Même conditions qu'`analyse` : clé requise, coupé sans elle, `--blanc` gratuit.
Il coûte plus cher qu'`analyse` — chaque recherche ramène des pages entières —
d'où un plafond de cinq recherches par appel, qui rend la facture prévisible.

### Ce que `add` demande en plus depuis la v2 du journal

Deux questions facultatives, à la fin : **ce que la décision rapporte si elle
marche**, en euros, et **si tu peux revenir en arrière**. La constitution
demande de juger une décision sur « options, levier, coût, vitesse,
réversibilité » ; sans ces deux réponses, le journal ne connaissait que le coût
en heures.

Laisser le gain vide veut dire « non chiffré », **pas** « ne rapporte rien » :
le journal garde la différence, et c'est elle que la Notice reproche au-delà de
vingt heures. En ligne de commande : `--gain 5000` et
`--reversibility irreversible`.

Une décision irréversible dont l'échéance passe sans verdict devient la
seule observation CRITIQUE avec la chaîne rompue. C'est voulu : partout
ailleurs, le temps mal placé peut encore être réaffecté.

## Le même journal, en app

```bash
python -m singular sage          # ouvre http://127.0.0.1:8765/
python -m singular sage --lan    # joignable depuis ton téléphone, avec un jeton
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

## Sur l'iPhone seul, sans PC et sans rien installer

Depuis que `singular/__init__.py` résout ses noms à la demande, le cœur n'a
plus aucune dépendance : journal, chaîne d'intégrité, Notice, ligne de commande
et serveur du Sage tournent en bibliothèque standard pure. Donc dans **a-Shell**
(gratuit, App Store), qui embarque Python.

**Précise la branche.** Un `lg2 clone` sans elle prend la branche par défaut,
qui n'est pas toujours celle qui porte le travail. Le nom ci-dessous est celui
que `CLAUDE.md` désigne aujourd'hui ; `python tools/check_repo_state.py` dit
l'état réel du jour, et il faut le croire plutôt que cette ligne — c'est
exactement pour ça qu'il existe.

```
lg2 clone -b claude/remote-control-feedback-ndpzle https://github.com/SLENDER66/SINGULAR
```

```
cd SINGULAR && python -m singular sage
```

Puis Safari sur `http://127.0.0.1:8765/`.

**Ce qui reste à vérifier, et que personne n'a encore testé :** iOS suspend les
applications passées à l'arrière-plan. Basculer d'a-Shell vers Safari peut
couper le serveur. Si la page ne charge pas, c'est ça — dis-le, il y a d'autres
chemins.

**Un journal par machine, et ils ne se parlent pas.** `~/.singular/journal.db`
sur le PC et sur le téléphone sont deux fichiers différents. Deux journaux
divergents donnent deux calibrations fausses, et rien ne le signale : un journal
neuf ressemble exactement à un journal qu'on n'a pas encore rempli. C'est pour
ça que « Journal vide » affiche désormais **le chemin** où il a regardé. Tiens-toi
à une seule machine tant qu'il n'y a pas de synchronisation.

## Le mettre devant tes yeux

Ajoute à ton `~/.bashrc` ou `~/.zshrc` :

```bash
alias sj='python -m singular'
python -m singular status 2>/dev/null
```

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
  tu prédis en moyenne 85%   il arrive 0%
  surconfiance de +85% — tu crois plus que ce qui arrive
  Brier moyen 0.723  (0 = parfait, 0.25 = pile ou face)

  PAR RANG DE LA CONSTITUTION
  rang             décisions   heures  ont marché  sans verdict
  stabilite                —        —           —             —
  revenus                  1      12h          0h           12h   —
  patrimoine               1      90h          0h            0h   0%

  ⚠ Aucune décision sur stabilite — les deux premiers rangs de ta hiérarchie.
```

Les deux chiffres qui comptent : **les heures sans verdict** et **l'écart de
calibration**. Le premier mesure l'activité qui ne s'est jamais transformée en
résultat. Le second mesure de combien tu te crois.

## Le rituel

| Quand | Quoi | Durée |
|---|---|---|
| Avant toute décision qui coûte plus de 2h | `sj add` | 30 s |
| Chaque candidature | `sj apply "Boîte" "Poste"` | 5 s |
| Chaque matin | `sj due` | 10 s |
| Chaque dimanche | `sj review` | 2 min |
