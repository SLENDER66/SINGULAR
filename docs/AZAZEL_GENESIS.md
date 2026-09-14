# AZAZEL Genesis — ce qui a été construit, et ce que ça prouve

**Statut : une cellule qui tourne, et des résultats positifs sur des cas
nommés.** Pas une architecture d'entreprise, pas une démonstration générale. La
différence est le sujet de ce document.

Lancer l'expérience :

```sh
python3 tools/genesis_experiment.py
```

Aucune clé, aucun modèle, aucun réseau. La suite de tests la rejoue en
entier à chaque commit, donc le CI aussi.

---

## 1. L'hypothèse, et comment elle peut être fausse

> Une expérience vérifiée devient une capacité réutilisable, et une capacité
> réutilisable rend une mission suivante objectivement meilleure.

Ce qui rendrait cette phrase fausse, et que le banc doit pouvoir dire :

* la capacité a **mémorisé** l'instance d'apprentissage au lieu d'apprendre ;
* la mission de contrôle s'améliore mais **aucune capacité n'a servi** ;
* le gain est payé par un **appel à un humain** ou par une **réponse fausse** ;
* le niveau de preuve **monte tout seul** en accumulant les succès et en
  oubliant les échecs.

Chacun de ces cas a son test dans `tests/test_genesis.py`, et chacun échoue
comme il doit. C'est le seul argument sérieux en faveur du chiffre positif.

---

## 2. Ce qui existait déjà, et qui n'a pas été réécrit

L'inspection d'abord, comme la directive l'exige. Le dépôt portait déjà
l'essentiel de la chaîne, et le réécrire aurait été le contraire du travail.

| Demandé par la directive | Ce qui existait | Décision |
|---|---|---|
| Identité d'artefact exécutable | `execution_capability.artifact_fingerprint` | **GARDÉ**, importé tel quel |
| Frontière d'exécution, autorisation durable | `validated_execution`, `decision_attestation` | **GARDÉ**, et Genesis n'y touche pas |
| Registre d'amélioration (candidat → évaluation → activation) | `improvement_registry` | **GARDÉ** |
| Télémétrie économique | `economic_learning`, `economic_learning_ledger` | **GARDÉ** |
| Trajectoire, mission, orchestration | `trajectory`, `mission_runtime`, `autopilot` | **GARDÉ, non employé** — voir ci-dessous |
| Prédiction vs réalité | `outcome_ledger`, et le journal lui-même | **GARDÉ** |
| Niveaux de preuve E0–E5 | rien | **AJOUTÉ** |
| Compte de réutilisation d'une capacité | rien | **AJOUTÉ** — dérivé des preuves, pas incrémenté |
| Banc différentiel baseline vs expérimenté | rien | **AJOUTÉ** |
| Missions ALPHA / BETA / GAMMA | rien | **AJOUTÉ** |
| World State universel, routage de modèles, calcul | rien | **REPORTÉ** — aucune hypothèse à tester aujourd'hui |

**Pourquoi Genesis a sa propre `Trajectoire` alors que le dépôt en a une.** La
directive interdit de dupliquer ce qui existe, et cette ligne du tableau mérite
sa justification plutôt qu'un mot. `singular/trajectory.py` n'est pas une trace
d'exécution : c'est l'optimisation multi-objectifs d'une décision — vision,
poids, arbitrages. `mission_runtime.py`, lui, est bien une exécution de mission,
mais **gouvernée** : il est relié à la frontière, et la section 5 interdit à
Genesis de l'importer. Reprendre l'un aurait mélangé deux notions ; reprendre
l'autre aurait donné à Genesis un chemin vers l'exécution. Ce qui est réellement
partagé — l'identité d'artefact — l'est pour de bon.

`JARVIS` n'apparaît dans aucun fichier suivi du dépôt. Seuls des noms de
branches en gardent la trace. La migration demandée par la directive était donc
déjà faite ; c'est vérifié, pas supposé.

---

## 3. Ce qui a été ajouté

`singular/genesis/`, cinq modules, rien qui exécute.

**`mission.py`** — une mission, sa trajectoire, son juge. Trois choix de forme :
le juge est séparé du solveur et recalcule depuis la source ; la trajectoire
s'écrit pendant, pas après ; un solveur qui lève rate au lieu d'interrompre.

**`lecteurs.py`** — quatre lecteurs sur des formats réels du dépôt (JSON, TOML,
titres de changelog, CSV). Chacun **refuse** ce qui n'est pas de son format,
ce qui rend le tâtonnement observable.

**`capability.py`** — le registre et l'échelle de preuve.

| | |
|---|---|
| E0 | inscrite, jamais vérifiée |
| E1 | vérifiée une fois |
| E2 | vérifiée sur deux instances distinctes |
| E3 | sur trois, sans aucun échec |
| E4 | en plus, sur une instance abîmée |
| E5 | en plus, dans deux domaines distincts |

Deux règles font tout le travail. **Un seul échec plafonne à E2** : « observée »
et « répétée » sont des faits qu'un échec ne défait pas, « vérifiée », « robuste »
et « prouvée » sont des affirmations de fiabilité qu'un échec réfute. Et
**réinscrire un autre artefact sous un nom déjà prouvé remet les preuves à
zéro** : elles avaient été gagnées par l'ancien code. C'est ce qui empêche
« candidat X, évalué, approuvé » d'activer autre chose que X.

Le niveau est **recalculé à chaque lecture** depuis les preuves. Il n'y a aucun
champ où l'écrire, donc aucun moyen de le poser sans l'avoir gagné.

**`bench.py`** — la même mission deux fois, un seul changement entre les deux :
le registre. Verdicts `AMELIORATION`, `AUCUNE`, `REFUTE`. Les trois refus sont
au cœur du fichier et documentés là-bas.

**`missions.py`** — ALPHA lit deux formats et synthétise ; BETA affronte une
source tronquée et une source absente, et ne comble aucun trou ; GAMMA détecte
un format que rien ne sait lire, construit un lecteur, l'éprouve sur un contrôle
mis de côté, et ne l'inscrit que s'il tient. Puis deux missions qui éprouvent la
capacité acquise ailleurs que là où elle est née : DELTA sur
`.github/workflows/ci.yml`, le workflow réel du dépôt, et EPSILON sur
`pyproject.toml`, qu'elle **ne sait pas lire**.

---

## 4. Le résultat mesuré

Sur la mission de contrôle — une instance jamais vue du format appris :

| axe | sans registre | avec registre |
|---|---|---|
| vérifiée | non | **oui** |
| coût | 5.0 | **1.0** |
| erreurs | 5 | **0** |
| récupérations | 0 | 0 |
| appels à un humain | 0 | 0 |

Verdict : `AMELIORATION`, capacité employée `lecteur:cle_valeur`, naissance
constatée.

### L'échelle, et sa chute

Monter jusqu'à E5 dans un script ne prouve rien : quand on a les instances sous
la main, une échelle se gravit. Ce qu'elle vaut se lit à ce qu'elle refuse.
L'expérience se termine donc sur un échec réel, et il faut voir le niveau
retomber.

| emploi | ce que c'est | tenu ? | niveau après |
|---|---|---|---|
| `ci` | `.github/workflows/ci.yml`, deuxième domaine | oui | E3 |
| `abimee` | un relevé arraché — lignes sans paire, commentaires, blanc | oui | **E5** |
| `pyproject` | `cle = "valeur"` : ce lecteur ne sait pas | **non** | **E2** |

Le lecteur avait été appris sur un relevé écrit à la main. Il répond sur le
workflow du CI sans avoir rien réappris : c'est ce qui sépare « généralisation »
du mot « généralisation ». Et il échoue pour de bon sur du TOML, ce qui ramène
le niveau au plafond d'après échec.

### La composition : deux capacités valent-elles mieux qu'une ?

C'est l'hypothèse stratégique de la directive — `CAPACITÉ A + CAPACITÉ B →
CAPACITÉ COMPOSITE` — et elle dit de ne jamais la supposer automatique.

Un second cycle d'acquisition tourne sur `pytest.ini`, qui n'est lisible par
**aucun** des quatre lecteurs du dépôt ni par le premier lecteur appris. Le bac
à sable essaie `': '`, le refuse, retient `'='`. Deux artefacts distincts, deux
noms distincts.

ZETA demande alors une valeur à `.github/workflows/ci.yml` et une autre à
`pytest.ini`. La ligne de base du banc est ici **une capacité**, pas zéro : mesurer
deux contre rien aurait mesuré l'acquisition, pas la composition.

| registre | vérifiée | coût | erreurs |
|---|---|---|---|
| rien | non | 10 | 10 |
| une capacité | **non** | 7 | 6 |
| les deux | **oui** | 3 | 1 |

Verdict `AMELIORATION`, les deux capacités employées. Le surcoût d'essayer deux
lecteurs au lieu d'un est payé — mais c'est un fait mesuré sur ces fichiers-là,
pas une règle : sur un registre plus fourni, chaque lecture essaierait davantage
de lecteurs avant de tomber sur le bon.

Et ce qui est composé reste modeste : le composite est la **sélection** parmi
les lecteurs appris, pas une capacité nouvelle qu'aucun des deux ne portait.

**Ce que ça ne dit pas.** Deux capacités, deux domaines proches, cinq instances,
et un lecteur qui ne comprend pas YAML — il lit les paires `clé: valeur` qu'il
trouve, à plat. L'hypothèse tient sur ces cas ; elle n'est pas démontrée en
général, et la directive interdit de confondre les deux.

---

## 5. Séparation et permissions

Le mandat pose `INTELLIGENCE ≠ DECISION ≠ AUTHORIZATION ≠ EXECUTION` avant tout
le reste. Un paquet qui planifie des missions et construit des capacités est
précisément ce qui obtient un pouvoir d'exécution sans qu'on le lui ait donné :
il suffit d'un import, un jour, pour une bonne raison.

`tests/test_genesis_isolation.py` le refuse :

* aucun import de ce qui peut exécuter — la liste est écrite, pas devinée ;
* **une exception nommée** : `artifact_fingerprint`, fonction pure, parce que
  réécrire une deuxième empreinte d'artefact à côté de celle que la frontière
  utilise serait la garantie qu'elles divergent ;
* aucune bibliothèque qui parle à un service ou à un modèle ;
* aucun appel qui écrit, supprime ou lance un processus ;
* et la preuve par l'acte : les trois missions tournent avec les sockets
  retirées, avec un témoin qui vérifie que le garde attraperait vraiment une
  connexion.

Genesis n'a donc aucun niveau d'autonomie au sens de la directive. Elle est en
L0 : elle observe et rend un rapport.

---

## 6. Kill / rollback

Le paquet entier est supprimable sans rien casser d'autre : rien dans
`singular/` n'importe `singular.genesis`. C'est vérifiable en une commande
(`grep -r "genesis" singular/ --include='*.py' | grep -v '^singular/genesis/'`)
et c'est la forme la plus simple du protocole d'arrêt que la directive demande.

Une capacité, elle, meurt proprement en réinscrivant son nom : la version
s'incrémente et les preuves repartent à zéro.

---

## 7. Limites connues

* **Le registre est en mémoire.** Rien ne survit à un redémarrage. Le jour où
  Genesis devra persister, ce sera `DurableCapabilityStore` qui portera ça — pas
  une deuxième table inventée à côté.
* **Deux domaines, et ils sont proches.** Un relevé écrit à la main et un
  workflow YAML partagent la forme `clé: valeur` ; ce sont deux domaines au sens
  de l'échelle, pas deux mondes. E5 est atteint, et il ne veut dire que les
  critères de la table ci-dessus.
* **La capacité n'est pas un analyseur YAML.** Elle lit des paires à plat :
  l'imbrication est perdue, une entrée de liste garde son tiret. C'est assez
  pour la question posée, et c'est écrit pour qu'on ne lui prête pas mieux.
* **Le solveur est déterministe.** Aucun modèle n'intervient. C'est ce qui rend
  l'expérience rejouable et gratuite ; c'est aussi ce qui limite la difficulté
  des missions à ce qu'un programme sans intelligence peut faire.
* **Le coût est un compte de pas**, pas des euros ni des jetons. Il mesure ce
  que l'expérience fait varier ; il ne se compare à aucun prix réel.
* **Le coût de la composition grandit avec le registre.** Chaque lecture essaie
  les lecteurs appris jusqu'à ce qu'un réponde. À deux, c'est gagnant ; à vingt,
  la question se reposera, et rien ici ne la traite.
* **`SEPARATEURS_ESSAYES` est une liste courte.** Un format clé/valeur avec un
  séparateur absent de la liste ne serait pas appris, et GAMMA échouerait — ce
  qui serait un vrai résultat négatif, pas un plantage.

---

## 8. La prochaine action justifiée

Dans l'ordre où elle se justifie techniquement, sans que rien ici ne soit
promis :

1. **Un domaine réellement éloigné** — pas une deuxième variante de
   `clé: valeur`. Tant que les deux domaines se ressemblent, E5 mesure la forme
   du texte et pas la portée de la capacité.
2. **Un composite qui fasse plus que choisir** — deux capacités dont la
   combinaison produit ce qu'aucune ne porte. Celui d'ici sélectionne ; c'est un
   compounding réel mais faible.
3. **Un deuxième registre expérimenté**, pour comparer deux versions de Genesis
   entre elles — « AZAZEL doit battre AZAZEL » — plutôt que Genesis contre rien.
4. **La persistance**, seulement quand une expérience durera plus d'un processus.

Le premier point de cette liste disait « un deuxième domaine » ; il est fait, et
ce qu'il a appris est qu'un deuxième domaine trop proche déplace la question
plutôt qu'il ne la règle.

Ce qui n'est pas justifié aujourd'hui : le routage de modèles, le World State
universel, la doctrine de calcul. Aucun ne teste une hypothèse que nous ayons.
La directive dit de ne pas construire dans ce cas ; c'est ce qui est fait.
