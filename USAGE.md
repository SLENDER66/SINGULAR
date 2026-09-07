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

Elle est **coupée par défaut** : sans `ANTHROPIC_API_KEY` dans l'environnement,
elle le dit et affiche la Notice calculée sans elle. Tout le reste de SINGULAR
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
