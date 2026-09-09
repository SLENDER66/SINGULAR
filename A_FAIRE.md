# Ce que je dois faire moi-même

Le Sage tourne et je m'en sers. Ce qui reste tient en deux gestes par
semaine, un clic sur GitHub, plus une chose qui attend un Mac et ne bloque
rien.

---

## L'état du dépôt, en une commande plutôt qu'en une phrase

Ce fichier a déjà affirmé « la bonne branche est la branche par défaut » alors
que c'était faux, et rien ne pouvait le contredire : l'affirmation portait sur
l'état d'un serveur, pas sur le contenu du dépôt. Il ne l'affirme plus, il te
donne de quoi le voir :

```powershell
cd $HOME\Documents\SINGULAR; python tools/check_repo_state.py
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

Une session ne peut pas les supprimer : le proxy réseau des conteneurs refuse
l'opération, vérifié. Le geste est donc le tien — sur GitHub, onglet **Branches**,
icône corbeille — ou depuis ton PC : `git push origin --delete <nom>`.

Le tri a été fait le 7 septembre 2026, pour ne pas être refait. Ce tableau est
une **analyse**, pas un inventaire : il dit ce que chaque branche portait, pas
lesquelles existent aujourd'hui. Pour l'inventaire, une seule source —
`python tools/check_repo_state.py`, qui interroge le serveur. Trois des lignes
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

**Depuis le PC** (il ne répond alors que si le PC tourne et que je suis sur mon
wifi) :

```powershell
cd $HOME\Documents\SINGULAR; python -m singular sage --lan
```

Si l'app redemande la clé, un champ permet de la coller : l'adresse entière
affichée par PowerShell, ou le jeton seul. Ça arrivera de temps en temps :
une app installée sur l'écran d'accueil a son propre stockage, séparé de
Safari, et iOS le vide quand il veut. Ce n'est pas une panne.

**La partie après `?k=` est un secret.** Elle donne accès à ton journal depuis
n'importe quel appareil du wifi. Ne la colle jamais dans une conversation, un
message ou une capture d'écran — pas même ici. Si ça arrive, elle se change en
vingt secondes :

```powershell
del $HOME\.singular\sage_token; python -m singular sage --lan
```

L'ancienne clé cesse alors de fonctionner, et l'app en redemandera une neuve.

**Depuis le téléphone seul, sans PC.** Le cœur n'a plus aucune dépendance : il
tourne dans **a-Shell** sans rien installer. Une fois, dans a-Shell :

```
lg2 clone -b claude/decision-companion-rebuild-3k25h3 https://github.com/SLENDER66/SINGULAR
```

Puis, chaque matin :

```
cd SINGULAR && python -m singular sage
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
PC** : deux fichiers, aucune synchronisation. Tant qu'il n'y en a pas, s'en
tenir à une seule machine. C'est pour ça que « Journal vide » affiche le chemin
où il a regardé — **dans l'app comme au clavier**. Cette phrase n'était vraie
qu'au clavier : l'app, celle que tu ouvres le matin et celle qui peut pointer
le mauvais fichier, ne disait rien. Un journal vide et un mauvais journal
donnaient exactement le même écran.

**Sauvegarde.** Tout mon journal est dans un seul fichier :
`C:\Users\Utilisateur\.singular\journal.db`. Le copier de temps en temps sur
une clé ou dans un dossier synchronisé, c'est toute la sauvegarde nécessaire.
Rien ne part sur un serveur.

## Ce qui compte maintenant

1. **Ouvrir l'app le matin.** C'est le seul geste qui fait vivre le journal.
   Depuis le PC ou depuis le téléphone, mais **toujours le même des deux** tant
   que les deux journaux ne se parlent pas.
2. **Trancher le 20 septembre.** La carte passera en haut, « À trancher
   aujourd'hui ». Oui ou non. Un journal où l'on écrit sans jamais trancher
   n'apprend rien.
3. **Quand une question se pose sur mon journal**, sans clé d'API et sans PC :

   ```
   python -m singular analyse --blanc
   ```

   Il affiche le rapport en texte, sans rien envoyer. Je colle le bloc dans
   l'app Claude. C'est gratuit et ça marche depuis le téléphone.

4. **Le bouton 💬 dans l'app** — une conversation qui connaît déjà le rapport
   du jour et ce qu'on s'est dit la dernière fois. Elle ne peut pas écrire dans
   le journal : enregistrer reste le `+`.

   **Rien de tout ça n'est encore sur mon PC.** Mon clone date d'avant, et
   c'est la première chose à faire — sinon il n'y a ni bouton, ni commande
   `parle`, et les étapes suivantes échouent sans dire pourquoi.

   J'ai la clé et 5 $ de crédit. Une seule fois, dans PowerShell, dans
   l'ordre :

   ```powershell
   cd $HOME\Documents\SINGULAR
   git fetch origin
   git checkout claude/decision-companion-rebuild-3k25h3
   git pull
   python -m pip install -e ".[analyse]"
   ```

   **`git pull` seul ne suffit pas**, et c'est le piège : il met à jour la
   branche sur laquelle tu es, pas celle qui porte le travail. Ton clone est
   resté sur celle d'une séance précédente. La commande ne dit rien, ne se
   plaint de rien, et rend simplement l'ancienne version — on ne s'en aperçoit
   qu'en cherchant pourquoi le bouton annoncé n'est pas là. D'où le `checkout`
   au-dessus, et la branche nommée est celle que `CLAUDE.md` déclare : un test
   refuse que les deux se séparent.

   Pour vérifier d'un coup que tu es au bon endroit, avant tout le reste :

   ```powershell
   python tools/check_repo_state.py
   ```

   `python -m pip` et pas `pip` seul : sur Windows, `pip` n'est pas toujours
   dans le PATH, et il peut installer pour un autre Python que celui qui lance
   SINGULAR.

   Puis, **dans cette même fenêtre**, poser la clé et vérifier tout de suite
   qu'elle est vue :

   ```powershell
   $env:ANTHROPIC_API_KEY = "sk-ant-..."
   python -m singular parle "dis juste bonjour"
   ```

   S'il répond, c'est bon. S'il dit « aucune clé dans ANTHROPIC_API_KEY »,
   c'est que la ligne du dessus n'a pas pris — en `cmd` la commande s'écrit
   `set ANTHROPIC_API_KEY=sk-ant-...`, ce n'est pas la même.

   Enfin, dire à SINGULAR ce que je paie. **Il ne connaît aucun prix**, et
   c'est voulu : un tarif écrit dans le code vieillirait en silence et me
   servirait à décider quand m'arrêter.

   ```powershell
   python -m singular parle --tarifs
   ```

   Il affiche un petit fichier à coller dans
   `C:\Users\Utilisateur\.singular\tarifs.json`, avec les prix relevés sur
   console.anthropic.com et mes 5 $. Sans ça il compte des jetons ; avec, il
   me dit ce qu'il me reste sous chaque réponse.

   **Ensuite, chaque fois**, la clé doit être posée dans la fenêtre **avant**
   de lancer le serveur — un serveur déjà démarré ne la verra jamais :

   ```powershell
   cd $HOME\Documents\SINGULAR
   $env:ANTHROPIC_API_KEY = "sk-ant-..."
   python -m singular sage --lan
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

## En attente d'un Mac — l'app native, hors ligne et partout

### Compiler l'app iPhone  (≈ 1 h, dont 40 min de téléchargement)

Suis **`ios/README.md`**. Cinq étapes, écrites pour quelqu'un qui n'a jamais
ouvert Xcode. Le projet Xcode est maintenant dans le dépôt : il n'y a plus rien
à créer ni à glisser, les deux étapes qui se trompaient le plus facilement.

L'ordre compte :

1. Installer Xcode depuis l'App Store.
2. `git clone` du dépôt, puis `open SINGULAR/ios/SingularSage.xcodeproj`.
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
