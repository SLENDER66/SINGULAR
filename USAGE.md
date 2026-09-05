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
