# Ce que je dois faire moi-même

Le Sage tourne et je m'en sers. Ce qui reste tient en deux gestes par semaine
et un clic sur GitHub.

**Les commandes de ce fichier sont celles du Terminal du Mac (zsh).** Elles
étaient en PowerShell : le PC Windows était la machine principale jusqu'à
cette date.

---

## D'abord : ton journal est sur le PC, pas sur le Mac

Le 10 septembre 2026, le Mac remplace le PC. Le code se reprend d'un `git
clone` ; **ton journal, non**. Il vit dans `~/.singular/` et il est
irremplaçable : trois mois de prédictions chaînées, qu'aucune session ne peut
reconstruire.

### Si tu n'as pas accès au PC

C'est le cas au 10 septembre 2026. Trois choses sont vraies, et c'est la
troisième qui change ta journée.

**Rien n'est perdu.** Le fichier est sur le disque du PC et n'en bouge pas. Ne
pas pouvoir l'atteindre n'est pas la même chose que l'avoir perdu.

**Regarde d'abord le téléphone.** Si tu as lancé SINGULAR dans a-Shell, il y a
un journal là aussi, et il est peut-être suffisant. Dans a-Shell :

```sh
python3 -c "import sqlite3, os; c=os.path.expanduser('~/.singular/journal.db'); \
print(sqlite3.connect(c).execute('select count(*) from journal_entries').fetchone()[0], 'décisions') if os.path.exists(c) else print('aucun journal ici')"
```

**Écris tes décisions sur le Mac, dès aujourd'hui.** Cette page disait le
contraire, et te promettait d'avoir un jour à sacrifier l'un des deux journaux.
C'était faux depuis que `import` existe. Tu ne sacrifieras rien : les deux
histoires tiennent dans la même.

```sh
python3 -m singular import ~/journal-du-pc.db
```

C'est mesuré, pas supposé : deux journaux de trois et deux décisions donnent
un journal de cinq, la chaîne se vérifie de bout en bout, et le fichier
d'origine n'est pas touché. Relancer la commande refuse, en disant que ces
décisions sont déjà là.

Recopier les **lignes** d'une base dans l'autre, ça, ça casse la chaîne : chaque
empreinte signe la précédente, donc une entrée insérée au milieu rompt tout ce
qui suit. C'est pour ça que la reprise resigne ce qu'elle écrit au lieu de le
recopier. Chaque décision reprise garde en plus l'empreinte qu'elle portait
là-bas, et une source dont la chaîne est cassée est refusée avant d'entrer.

Le vrai risque n'est donc pas de perdre une histoire, c'est d'en écraser une :
**ne copie jamais le `journal.db` du PC par-dessus celui du Mac.** Les étapes
ci-dessous le posent à côté, sous un autre nom, et le reprennent.

### Ce qu'il y a dans ce dossier

Quatre fichiers comptent, et un ne doit pas être copié.

| fichier | ce que c'est | si tu le perds |
|---|---|---|
| `journal.db` | toutes tes décisions et leurs verdicts | **irremplaçable** |
| `candidatures.json` | le suivi de tes candidatures | **irremplaçable** |
| `tarifs.json` | les prix que tu as relevés toi-même | à retaper, une fois |
| `parle_quota.json` | ce que tu as déjà dépensé en jetons | le compteur repart à zéro |
| `sage_token` | la clé d'accès de l'app depuis le téléphone | **ne le copie pas** |

Le jeton ne se copie pas exprès : une machine neuve mérite une clé neuve, et
elle se recrée toute seule au premier démarrage du Sage.

### Étape 1 — sur le PC, trouver le dossier

Ouvre l'Explorateur de fichiers, clique dans la barre d'adresse tout en haut,
efface ce qu'il y a, et colle exactement ceci :

```text
%USERPROFILE%\.singular
```

Entrée. Tu dois voir les fichiers du tableau ci-dessus. Sélectionne-les tous
(Ctrl+A), copie (Ctrl+C), et colle sur une clé USB.

Un dossier dont le nom commence par un point n'est pas caché sous Windows : il
s'affiche normalement. C'est sur le Mac que ça change, et c'est l'étape 3.

### Étape 2 — de la clé au Mac

Branche la clé sur le Mac. Elle apparaît dans le Finder, dans la colonne de
gauche.

### Étape 3 — sur le Mac, ouvrir le dossier de destination

**Sur le Mac, un dossier dont le nom commence par un point est caché** : tu ne
le verras pas en cliquant dans le Finder. C'est une convention Unix, pas une
protection.

Deux façons d'y aller :

- dans le Finder, **Cmd + Maj + G**, puis tape `~/.singular` et Entrée ;
- ou, si le dossier n'existe pas encore, ouvre le Terminal et tape
  `mkdir -p ~/.singular` avant de refaire Cmd + Maj + G.

Puis glisse les quatre fichiers de la clé dans cette fenêtre.

**Ou tout par le Terminal**, si tu préfères une seule commande. Remplace
`TA_CLE` par le nom de ta clé — le Terminal le complète si tu tapes
`/Volumes/` puis Tab :

```sh
mkdir -p ~/.singular
cp /Volumes/TA_CLE/journal.db        ~/journal-du-pc.db
cp /Volumes/TA_CLE/candidatures.json ~/.singular/
cp /Volumes/TA_CLE/tarifs.json       ~/.singular/
cp /Volumes/TA_CLE/parle_quota.json  ~/.singular/
```

**Le journal, lui, ne va pas dans `~/.singular/`** : il se pose à côté, et
l'étape 4 le reprend. S'il allait à sa place, il écraserait ce que tu as écrit
sur le Mac entre-temps, et c'est le seul geste de cette page qui puisse effacer
des mois de décisions.

Les trois autres fichiers s'écrasent sans dommage tant que tu ne t'en es pas
servi sur le Mac : `tarifs.json` se retape, `parle_quota.json` est un compteur.
`candidatures.json` est irremplaçable comme le journal — si tu as suivi des
candidatures sur le Mac aussi, pose-le à côté également et garde les deux.

### Étape 4 — vérifier que tout est arrivé

**Avant de faire quoi que ce soit d'autre.** Cette commande ne demande ni
clone ni installation — le `python3` du Mac suffit. Colle-la dans le Terminal :

```sh
python3 -c "import sqlite3; b=sqlite3.connect('$HOME/.singular/journal.db'); \
print(b.execute('select count(*) from journal_entries').fetchone()[0], 'décisions')"
```

Le nombre doit être celui que tu attends. Zéro ou une erreur veut dire que le
fichier n'est pas arrivé, ou pas en entier.

Une fois SINGULAR installé sur le Mac, la vraie vérification est celle-là :

```sh
python3 -m singular review
```

Il doit afficher tes décisions, et **la chaîne doit être intacte** — si elle
était rompue, la Notice le dirait en tête, en rouge. Le déplacement lui-même ne
la casse pas : les empreintes signent le contenu des entrées, pas leur chemin.
C'est mesuré, pas supposé — une base copiée dans un autre dossier se vérifie
encore, et une décision écrite après la copie se chaîne derrière les
précédentes.

**Le PC ne sert qu'à ça.** Ce dossier est la seule chose qui n'existe qu'ici :
le code se reclone depuis GitHub, et tout le reste se recrée. Une fois la copie
faite et vérifiée, tu n'as plus besoin d'y retourner.

Ce qu'on **ne** copie pas : `sage_token`. Une machine neuve mérite un jeton
neuf, et il se recrée tout seul au premier `--lan`.

Ce qu'on ne copie pas non plus, mais pour une autre raison : `conversation.json`
est le fil de la faculté « parle ». Le perdre ne coûte rien — le journal, lui,
ne se reconstruit pas.

### Étape 5 — reprendre le journal du PC dans celui du Mac

```sh
python3 -m singular import ~/journal-du-pc.db
python3 -m singular review
```

La première commande dit combien de décisions sont entrées et si la chaîne
tient. La seconde te montre le tout, dans l'ordre chronologique, les deux
histoires mêlées.

Une fois que `review` affiche le compte attendu, le fichier `~/journal-du-pc.db`
ne sert plus à rien. Garde-le quand même quelque part : il ne coûte rien, et
c'est ta seule copie de sauvegarde.

---

## L'état du dépôt, en une commande plutôt qu'en une phrase

Ce fichier a déjà affirmé « la bonne branche est la branche par défaut » alors
que c'était faux, et rien ne pouvait le contredire : l'affirmation portait sur
l'état d'un serveur, pas sur le contenu du dépôt. Il ne l'affirme plus, il te
donne de quoi le voir :

```sh
cd ~/Documents/SINGULAR && python3 tools/check_repo_state.py
```

Ce que ça a coûté, pour que personne ne le refasse : la branche par défaut
était restée 39 commits en arrière, et chaque nouvelle conversation démarre
depuis elle. La séance du 6 septembre au soir a donc commencé **sans le Sage,
sans `ios/`, et sur un `CLAUDE.md` d'avant la section 0** — celle qui existe
précisément pour ne plus avoir à être réécrite. Elle serait partie travailler
sur une branche morte si elle n'avait pas comparé.

Les deux branches ont été rattrapées le soir même, en avance rapide, sans rien
perdre. La commande ci-dessus le dira si ça se défait.

**Ce qui reste et qui n'appartient qu'à toi :** des branches traînent encore sur
GitHub. La commande ci-dessus les liste. Depuis le 8 septembre,
`claude/remote-control-feedback-ndpzle` en fait partie : elle a été mise au
même commit que la branche par défaut, donc elle ne porte plus rien qui lui
soit propre. Les supprimer ou les garder est ton
choix ; ce fichier ne prétendra pas qu'elles sont supprimées.

Le 9 septembre tu as autorisé la suppression de
`claude/remote-control-feedback-ndpzle`, et la session a essayé : refusée, une
deuxième fois, par le proxy réseau du conteneur — `HTTP 403` sur le `git push
origin --delete`. L'API GitHub disponible ici n'offre aucun outil de
suppression de branche. Ce qu'une session **peut** faire a été fait : plus
personne ne pousse dessus, et plus aucun document ne dit de la cloner. Elle est
donc figée, et sa suppression t'attend.

Une session ne peut pas les supprimer : le proxy réseau des conteneurs refuse
l'opération, vérifié deux fois. Le geste est donc le tien — sur GitHub, onglet
**Branches**, icône corbeille — ou depuis le Terminal :
`git push origin --delete claude/remote-control-feedback-ndpzle`.

Le tri a été fait le 7 septembre 2026, pour ne pas être refait. Ce tableau est
une **analyse**, pas un inventaire : il dit ce que chaque branche portait, pas
lesquelles existent aujourd'hui. Pour l'inventaire, une seule source —
`python3 tools/check_repo_state.py`, qui interroge le serveur. Trois des lignes
d'origine nommaient des branches que tu as depuis supprimées ; les recopier
ici une deuxième fois ne ferait que recommencer.

| Branche | Commits qu'elle est seule à porter |
|---|---|
| `claude/singular-startup-hook-czr3hp` | aucun |
| `archive/main-2026-09-03` | 191 — et c'est **exactement le même commit que `main`** |
| `v51-final` | 132 — **rien d'unique, supprimable** |
| `feat/global-coherence-integration` | 260 — **rien d'unique, supprimable** |
| `feat/economic-control-plane` | 356 — **rien d'unique, supprimable** |
| `feat/human-trajectory-engine` | 380 — **rien d'unique, supprimable** |
| `feat/decision-lifecycle-hardening` | 426 — **rien d'unique, supprimable** |
| `feat/validated-execution-boundary` | 608 — **rien d'unique, supprimable** |

**Toutes les branches `feat/*` et `v51-final` ont été examinées le 7 septembre,
définition par définition, `attic/` compris.** Aucune ne porte quoi que ce soit
que la branche de travail n'ait, sous une forme meilleure.

La méthode, si tu veux la refaire : comparer les définitions publiques
(fonctions et classes) plutôt que les fichiers ou les commits. Le compte de
commits est trompeur — ces branches datent du 3 septembre et leur « retard »
est ce que le travail a en plus, pas l'inverse.

Ce que l'examen a trouvé, et pourquoi ce n'est pas une perte :

- les modules `capital_allocation`, `v2_empire`, `v2_1_control`,
  `cashflow_engine`, `openai_runtime` sont **dans `attic/`** sur le travail,
  pas disparus. Les oublier dans la comparaison fait croire à 250 définitions
  perdues ;
- `begin_execution` et `finish_execution` sont les versions **non atomiques**
  de méthodes que le travail ne garde qu'en version atomique. Retrait
  volontaire d'une API dangereuse ;
- la quarantaine de tests « uniques » testent précisément cette API brute.
  Le travail les a remplacés par quatre tests qui vérifient qu'elle **reste
  désactivée** — `test_raw_execution_api_is_disabled`,
  `test_raw_recovery_takeover_path_is_closed`. Tester qu'un chemin dangereux
  n'existe plus vaut mieux que tester qu'il se comporte bien ;
- `feat/validated-execution-boundary` ne laissait que trois greffons de
  140 lignes, repliés depuis dans les classes. Une phrase de docstring
  manquait vraiment : récupérée dans `singular/effects.py`.

`archive/main-2026-09-03` n'a pas été examinée : elle est le même commit que
`main`, et `main` ne se touche pas sans ta décision. Les autres portent du code que la branche de
travail n'a pas — vieux, probablement superseded, mais je ne peux pas le
prouver, et une suppression ne se défait pas facilement. Ne les efface que si
tu sais ce qu'elles contenaient.

---

## Fait — le Sage est sur mon écran d'accueil

Depuis le 6 septembre 2026 au soir. Première décision enregistrée :
« Postuler » → « Un entretien », 75 %, 4 h, Revenus, **verdict le 20 septembre**.

**Depuis le Mac** (il ne répond alors que si le Mac tourne et que je suis sur mon
wifi) :

```sh
cd ~/Documents/SINGULAR && python3 -m singular sage --lan
```

Si l'app redemande la clé, un champ permet de la coller : l'adresse entière
affichée par le Terminal, ou le jeton seul. Ça arrivera de temps en temps :
une app installée sur l'écran d'accueil a son propre stockage, séparé de
Safari, et iOS le vide quand il veut. Ce n'est pas une panne.

**La partie après `?k=` est un secret.** Elle donne accès à ton journal depuis
n'importe quel appareil du wifi. Ne la colle jamais dans une conversation, un
message ou une capture d'écran — pas même ici. Si ça arrive, elle se change en
vingt secondes :

```sh
rm ~/.singular/sage_token && python3 -m singular sage --lan
```

L'ancienne clé cesse alors de fonctionner, et l'app en redemandera une neuve.

**Depuis le téléphone seul, sans Mac.** Le cœur n'a plus aucune dépendance : il
tourne dans **a-Shell** sans rien installer. Une fois, dans a-Shell :

```sh
lg2 clone -b claude/decision-companion-rebuild-3k25h3 https://github.com/SLENDER66/SINGULAR
```

Puis, chaque matin :

```sh
cd SINGULAR && python3 -m singular sage
```

Et Safari sur `http://127.0.0.1:8765/`. Pas de jeton : rien ne sort du
téléphone.

La branche nommée ci-dessus est celle que `CLAUDE.md` déclare comme branche de
travail. Ce n'est pas une coïncidence à maintenir à la main :
`test_documentation_is_current.py` refuse que les deux se séparent. Une
commande de clonage qui nomme une branche périmée ne casse rien — elle rend
simplement l'ancienne version, avec les défauts qu'on croyait corrigés, et on
ne s'en aperçoit qu'en cherchant pourquoi le bouton promis n'est pas là.

**Ce qui ne marche pas depuis le téléphone seul :** les boutons 💬 et 🔎. Ils
ont besoin du paquet `anthropic`, qui ne fait pas partie du cœur — c'est
précisément ce qui permet au reste de tourner sans rien installer. Le journal,
le rapport, les verdicts et la Notice marchent ; les deux facultés qui
appellent un modèle se déclarent coupées et le disent.

Deux réserves, non vérifiées d'ici. iOS suspend les applications passées à
l'arrière-plan : basculer vers Safari peut couper le serveur — si la page ne
charge pas, c'est ça, dis-le. Et **le journal du téléphone n'est pas celui du
Mac** : deux fichiers, aucune synchronisation. Tant qu'il n'y en a pas, s'en
tenir à une seule machine. C'est pour ça que « Journal vide » affiche le chemin
où il a regardé — **dans l'app comme au clavier**. Cette phrase n'était vraie
qu'au clavier : l'app, celle que tu ouvres le matin et celle qui peut pointer
le mauvais fichier, ne disait rien. Un journal vide et un mauvais journal
donnaient exactement le même écran.

**Sauvegarde.** Tout mon journal est dans un seul fichier :
`~/.singular/journal.db`. Le copier de temps en temps sur une clé ou dans un
dossier synchronisé, c'est toute la sauvegarde nécessaire. Rien ne part sur un
serveur, et le fichier se relit tel quel sur n'importe quelle machine — c'est
ce qui a permis de passer du PC au Mac sans rien perdre.

## Ce qui compte maintenant

1. **Ouvrir l'app le matin.** C'est le seul geste qui fait vivre le journal.
   Depuis le Mac ou depuis le téléphone : tiens-t'en de préférence au même des
   deux, parce que deux journaux qui divergent donnent deux calibrations
   fausses et que rien ne le signale. Mais si ça arrive, ce n'est plus perdu :
   `python3 -m singular import <l'autre journal>` les réunit.
2. **Trancher le 20 septembre.** La carte passera en haut, « À trancher
   aujourd'hui ». Oui ou non. Un journal où l'on écrit sans jamais trancher
   n'apprend rien.
3. **Quand une question se pose sur mon journal**, sans clé d'API et sans Mac :

   ```
   python3 -m singular analyse --blanc
   ```

   Il affiche le rapport en texte, sans rien envoyer. Je colle le bloc dans
   l'app Claude. C'est gratuit et ça marche depuis le téléphone.

4. **Le bouton 💬 dans l'app** — une conversation qui connaît déjà le rapport
   du jour et ce qu'on s'est dit la dernière fois. Elle ne peut pas écrire dans
   le journal : enregistrer reste le `+`.

   **Rien de tout ça n'est encore sur mon Mac.** Le clone est neuf, et
   c'est la première chose à faire — sinon il n'y a ni bouton, ni commande
   `parle`, et les étapes suivantes échouent sans dire pourquoi.

   J'ai la clé et 5 $ de crédit. Une seule fois, dans le Terminal, dans
   l'ordre :

   ```sh
   cd ~/Documents/SINGULAR
   git fetch origin
   git checkout claude/decision-companion-rebuild-3k25h3
   git pull
   python3 -m pip install -e ".[analyse]"
   ```

   **`git pull` seul ne suffit pas**, et c'est le piège : il met à jour la
   branche sur laquelle tu es, pas celle qui porte le travail. Ton clone est
   resté sur celle d'une séance précédente. La commande ne dit rien, ne se
   plaint de rien, et rend simplement l'ancienne version — on ne s'en aperçoit
   qu'en cherchant pourquoi le bouton annoncé n'est pas là. D'où le `checkout`
   au-dessus, et la branche nommée est celle que `CLAUDE.md` déclare : un test
   refuse que les deux se séparent.

   Pour vérifier d'un coup que tu es au bon endroit, avant tout le reste :

   ```sh
   python3 tools/check_repo_state.py
   ```

   `python3 -m pip` et pas `pip` seul : `pip` peut viser un autre Python que
   celui qui lance SINGULAR. Et `python3`, jamais `python` : depuis macOS 12.3
   la commande `python` n'existe plus, seul `python3` est là.

   Puis, **dans cette même fenêtre**, poser la clé et vérifier tout de suite
   qu'elle est vue :

   ```sh
   export ANTHROPIC_API_KEY="sk-ant-..."
   python3 -m singular parle "dis juste bonjour"
   ```

   S'il répond, c'est bon. S'il dit « aucune clé dans ANTHROPIC_API_KEY »,
   c'est que la ligne du dessus n'a pas pris. `export` ne vaut que pour la
   fenêtre en cours : dans une nouvelle fenêtre de Terminal, il faut la
   reposer, ou l'écrire dans `~/.zshrc`.

   Enfin, dire à SINGULAR ce que je paie. **Il ne connaît aucun prix**, et
   c'est voulu : un tarif écrit dans le code vieillirait en silence et me
   servirait à décider quand m'arrêter.

   ```sh
   python3 -m singular parle --tarifs
   ```

   Il affiche un petit fichier à coller dans `~/.singular/tarifs.json`, avec
   les prix relevés sur
   console.anthropic.com et mes 5 $. Sans ça il compte des jetons ; avec, il
   me dit ce qu'il me reste sous chaque réponse.

   **Ensuite, chaque fois**, la clé doit être posée dans la fenêtre **avant**
   de lancer le serveur — un serveur déjà démarré ne la verra jamais :

   ```sh
   cd ~/Documents/SINGULAR
   export ANTHROPIC_API_KEY="sk-ant-..."
   python3 -m singular sage --lan
   ```

   Le démarrage écrit maintenant « conversation allumée » ou « conversation
   coupée » : je le lis avant de prendre le téléphone, pas après. **Et s'il
   n'écrit ni l'une ni l'autre, c'est que le `git pull` n'a pas eu lieu** —
   cette ligne n'existe que dans la nouvelle version.

   Soixante réponses par jour depuis le téléphone, aucune limite au clavier,
   et un refus net quand le crédit est épuisé. Le modèle est
   `claude-sonnet-5`, choisi pour que 5 $ durent ; `SINGULAR_PARLE_MODELE`
   remet Opus.

   Le reste — le journal, le rapport, les verdicts — n'a jamais besoin de
   cette clé. Si je la révoque demain, rien d'autre ne bouge.

5. **Le bouton 🔎 dans l'app** — le troisième rond, au-dessus de 💬. Il
   cherche des offres de bureau d'études CVC en région toulousaine, il écarte,
   il propose — **il ne postule jamais**. Avant de chercher, il te montre ce
   qui part de ton téléphone : c'est ton profil, celui que tu as dicté, et si
   une ligne est fausse dis-le-moi plutôt que de laisser chercher dessus.

   Même clé et même crédit que 💬, et il coûte nettement plus : une recherche
   ramène des pages entières. Le compteur est commun aux deux — c'est le même
   porte-monnaie.

6. **Noter ce qui manque** — au fil de l'eau, pour la prochaine session :
   - Est-ce que je l'ouvre sans y penser, ou faut-il que j'y pense ?
   - Enregistrer une décision fait-il vraiment trente secondes ?
   - Les phrases sonnent-elles juste, ou me reproche-t-il des choses sans
     importance ?
   - Qu'ai-je cherché sans le trouver ?

C'est ça qui décidera de la faculté suivante — pas une liste écrite d'avance.

---

## L'app native — mise de côté le 10 septembre 2026

**Je l'ai écartée moi-même**, en questionnaire, le jour où le Mac est arrivé.
L'App Store a refusé Xcode — pas compatible avec cette machine — et la question
posée était : on cherche une version plus ancienne, ou on laisse tomber ?

J'ai laissé tomber, et c'est ce que la section 0 du mandat recommande. L'app
web sur mon iPhone fait déjà tout. La seule chose que l'app native ajouterait
est de marcher Mac éteint, et une séance entière a déjà été perdue à réparer ce
port pendant que l'app web dormait, finie, dans le même dépôt.

Ce qui suit reste écrit pour le jour où la question se reposerait. **Ce n'est
pas une tâche en attente : c'est une porte fermée dont on garde la clé.**

Une chose a été mesurée ce jour-là et vaut d'être notée : **le projet exige
iOS 17 alors que le code n'a besoin que d'iOS 16.** Le plancher réel est
`NavigationStack` ; rien dans les sources n'utilise d'API iOS 17. Abaisser la
cible élargirait les iPhone compatibles et permettrait à un Xcode plus ancien
de construire le projet. Ça n'a pas été fait, faute d'objet.

### Si la question se repose : compiler l'app iPhone  (≈ 1 h, dont 40 min de téléchargement)

Suis **`ios/README.md`**. Cinq étapes, écrites pour quelqu'un qui n'a jamais
ouvert Xcode. Le projet Xcode est maintenant dans le dépôt : il n'y a plus rien
à créer ni à glisser, les deux étapes qui se trompaient le plus facilement.

L'ordre compte :

1. Installer Xcode depuis l'App Store.
2. Cloner **en précisant la branche** — `git clone -b claude/decision-companion-rebuild-3k25h3 …` — puis
   `open SINGULAR/ios/SingularSage.xcodeproj`. Sans `-b`, tu prends la branche
   par défaut, qui n'est pas toujours celle qui porte le travail.
   Si Xcode propose de « mettre à jour vers les réglages recommandés » :
   **refuse**. Ce sont les réglages que le projet fixe exprès.
3. **`Cmd + U` avant tout le reste.** Les tests comparent le portage Swift au
   moteur Python. Vert : le cœur de l'app est prouvé fidèle. Rouge : envoie-moi
   le message d'erreur.
4. Se signer avec l'Apple ID (gratuit).
5. `Cmd + R` avec l'iPhone branché.

Si Xcode refuse d'ouvrir le projet (« the project is damaged »), l'annexe
« Si le projet ne s'ouvre pas » du README donne le montage à la main. Envoie-moi
le message dans ce cas : c'est la seule panne que je ne peux pas voir d'ici.

### Pendant la semaine d'essai

Le certificat gratuit dure **7 jours**. Au 8ᵉ jour l'app ne s'ouvre plus :
rebranche l'iPhone, `Cmd + R`, une minute.

**Ne supprime jamais l'app pour régler ça.** Le rebuild garde tes décisions,
la désinstallation les efface.

Note au fil de l'eau :

- Est-ce que tu l'ouvres le matin sans y penser ?
- Enregistrer une décision fait-il vraiment trente secondes ?
- Les phrases du Sage sonnent-elles juste, ou te reproche-t-il des choses sans
  importance ?
- Qu'as-tu cherché sans le trouver ?
- La notification de 8 h : bonne heure, bon texte ?

### Ensuite

Quand la réinstallation hebdomadaire te gênera :
[developer.apple.com/programs](https://developer.apple.com/programs/), 99 €/an,
et le certificat passe à un an. Tes données sont conservées.
