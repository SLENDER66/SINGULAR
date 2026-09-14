# AZAZEL Genesis — ce qui a été construit, et ce que ça prouve

**Statut : une cellule qui tourne, et un résultat positif sur un cas.** Pas une
architecture d'entreprise, pas une démonstration de compounding. La différence
est le sujet de ce document.

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
| Trajectoire, mission, orchestration | `trajectory`, `mission_runtime`, `autopilot` | **GARDÉ** |
| Prédiction vs réalité | `outcome_ledger`, et le journal lui-même | **GARDÉ** |
| Niveaux de preuve E0–E5 | rien | **AJOUTÉ** |
| Compte de réutilisation d'une capacité | rien | **AJOUTÉ** |
| Banc différentiel baseline vs expérimenté | rien | **AJOUTÉ** |
| Missions ALPHA / BETA / GAMMA | rien | **AJOUTÉ** |
| World State universel, routage de modèles, calcul | rien | **REPORTÉ** — aucune hypothèse à tester aujourd'hui |

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
mis de côté, et ne l'inscrit que s'il tient.

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

**Ce que ça ne dit pas.** Une capacité, un domaine, deux instances. Le niveau de
preuve de cette capacité est E1 à la fin de l'expérience, et l'échelle refuse de
le monter davantage : elle dit exactement ce qui a été montré. L'hypothèse tient
sur ce cas ; le compounding n'est pas démontré, et la directive interdit de
confondre les deux.

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
* **Un seul domaine.** E5 demande deux domaines distincts ; l'expérience n'en
  fournit qu'un. Le barreau existe et n'est pas atteint : c'est un fait affiché,
  pas une case cochée.
* **Le solveur est déterministe.** Aucun modèle n'intervient. C'est ce qui rend
  l'expérience rejouable et gratuite ; c'est aussi ce qui limite la difficulté
  des missions à ce qu'un programme sans intelligence peut faire.
* **Le coût est un compte de pas**, pas des euros ni des jetons. Il mesure ce
  que l'expérience fait varier ; il ne se compare à aucun prix réel.
* **`SEPARATEURS_ESSAYES` est une liste courte.** Un format clé/valeur avec un
  séparateur absent de la liste ne serait pas appris, et GAMMA échouerait — ce
  qui serait un vrai résultat négatif, pas un plantage.

---

## 8. La prochaine action justifiée

Dans l'ordre où elle se justifie techniquement, sans que rien ici ne soit
promis :

1. **Un deuxième domaine**, pour que E5 soit atteignable et que
   « généralisation » cesse d'être un mot. C'est la seule addition qui change ce
   que le banc peut démontrer.
2. **Un deuxième registre expérimenté**, pour comparer deux versions de Genesis
   entre elles — « AZAZEL doit battre AZAZEL » — plutôt que Genesis contre rien.
3. **La persistance**, seulement quand une expérience durera plus d'un processus.

Ce qui n'est pas justifié aujourd'hui : le routage de modèles, le World State
universel, la doctrine de calcul. Aucun ne teste une hypothèse que nous ayons.
La directive dit de ne pas construire dans ce cas ; c'est ce qui est fait.
