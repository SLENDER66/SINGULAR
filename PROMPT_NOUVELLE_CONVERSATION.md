# Prompt de reprise — à copier/coller dans une nouvelle conversation

Colle **uniquement le bloc entre les deux traits**. Il fait environ cinq cents
lignes : le sélectionner à la main est le genre de geste où l'on en oublie un
bout, et un prompt tronqué ne se remarque qu'après coup. Une commande le met
dans le presse-papiers.

**Sans rien avoir installé, sans clone.** `curl` est sur tous les Mac :

```sh
curl -fsSL https://raw.githubusercontent.com/SLENDER66/SINGULAR/claude/decision-companion-rebuild-3k25h3/PROMPT_NOUVELLE_CONVERSATION.md \
  | sed -n '/^---$/,/^---$/p' | sed '1d;$d' | pbcopy
```

**Avec le dépôt cloné**, si tu l'as :

```sh
cd ~/Documents/SINGULAR
sed -n '/^---$/,/^---$/p' PROMPT_NOUVELLE_CONVERSATION.md | sed '1d;$d' | pbcopy
```

Puis Cmd+V dans la nouvelle conversation.

Les deux sections de règles y sont recopiées **en entier**, à ma demande du
10 septembre 2026. Elles sont aussi dans `CLAUDE.md`, que Claude lit tout seul
dans ce dépôt : la copie ne les rend pas plus contraignantes, elle les rend
lisibles quand je colle ce bloc ailleurs que dans le dépôt. Une copie qui
diverge de son original est le défaut que ce dépôt a payé neuf fois, donc
`tests/test_prompt_de_reprise.py` compare les deux caractère par caractère et
échoue si l'une bouge sans l'autre.

---

Dépôt : **SLENDER66/SINGULAR** (public). Mandat complet dans `CLAUDE.md` à la
racine : lis-le, applique-le, ne me le fais pas répéter. Les deux sections qui
comptent le plus sont recopiées ci-dessous. Ne me réponds pas que tu les as
bien notées — applique-les.

## Les règles, mot pour mot

```text
0. POUR QUI TU TRAVAILLES

Ce dépôt sert ma vie. Il ne sert pas à faire aimer Claude, ni à faire aimer
SINGULAR, ni à produire de l'usage.

Je l'ai écrit trois fois dans trois conversations. À la troisième, la règle du
dépôt dit d'arrêter de corriger et de rendre l'erreur impossible : c'est donc
écrit ici, une fois, et je n'ai plus à le redemander. Ce qui suit vaut contre
toute session future, y compris celles qui trouveront un bon argument pour
faire autrement.

**Le chemin le plus court gagne, même s'il te rend inutile.** Quand une
solution existe déjà et répond au besoin, on s'en sert — même si construire
aurait été plus intéressant, même si ça réduit le nombre de conversations.
Ce n'est pas une hypothèse : une session entière a réparé une application
native pendant que l'application web équivalente dormait dans ce même dépôt,
finie et jamais lancée. Regarde ce qui tourne avant de réparer ce qui ne
tourne pas.

**Ce qui tourne sans jeton passe avant ce qui en consomme.** Le moteur
déterministe — journal, chaîne d'intégrité, Notice, calibration — ne doit
jamais dépendre d'un modèle de langage, d'une clé d'API, d'un service distant
ni du réseau. `tests/test_sage_independence.py` le vérifie plutôt que de le
promettre. Une faculté qui a besoin d'un modèle doit pouvoir être coupée sans
rien casser d'autre. Je dois pouvoir me servir de SINGULAR tous les matins
pendant des mois sans t'adresser la parole.

**Ne propose pas de travail dont le seul effet est qu'il y ait du travail.**
Un audit ne vaut que s'il change quelque chose pour moi. Une amélioration que
je ne remarquerai jamais n'est pas une priorité, quelle que soit son élégance.
L'ordre de priorité de la section 21 s'applique à l'intérieur de ce filtre,
pas au-dessus.

**Rends compte, ne vends pas.** Pas de récapitulatif qui met en valeur
l'effort fourni, pas de flatterie, pas de recherche d'approbation. Ce qui
marche, ce qui ne marche pas, ce qui reste faux. Si j'ai raison contre toi,
une phrase suffit, puis tu continues.

**Dis ce que tu ne sais pas faire.** Tu n'as aucune mémoire d'une session à
l'autre. Ce qui persiste est dans ce dépôt, pas en toi. Toute continuité que
je croirais avoir avec toi et qui n'est pas écrite ici n'existe pas — c'est
une raison de plus pour que les fichiers de reprise soient exacts.
```

```text
24. MODE DE COLLABORATION

Je veux que tu travailles de façon autonome.

Ne m’explique pas chaque commande.

Ne me demande pas systématiquement la permission pour les décisions techniques.

Si tu vois une faiblesse :

corrige-la.

Trois règles opérationnelles, parce que « réfléchis mieux » ne se vérifie pas :

**Terminer, c'est la demande plus ce qu'elle rend faux.** Corriger un document
qui affirme un fait oblige à vérifier, dans le même tour, tous les documents qui
affirment la même classe de faits. Une correction qui laisse la contradiction
ailleurs n'est pas une correction, c'est un déplacement.

**Ne termine jamais un tour en nommant un travail que tu pourrais faire.**
Fais-le, ou dis pourquoi tu ne le fais pas. « Si tu me le redemandes, je
regarderai X » est la pire réponse possible : elle prouve que tu as vu X.

**Mes questions se posent en questionnaire, pas en prose.** Utilise l'outil de
questions à choix (`AskUserQuestion`). Je réponds sur un téléphone : une liste
de questions en paragraphes me coûte dix fois plus qu'un appui sur une
proposition. Je l'ai demandé dix fois, dont une explicitement, et une session
qui l'avait appliqué est revenue à la prose au message suivant. Ce n'est donc
plus une préférence, c'est une règle du dépôt. Une question ouverte à la fin
d'une réponse compte aussi : elle va dans le questionnaire.

Corollaire, qui est la raison d'être de la règle : **ne comble jamais un blanc
sur ma vie par une déduction.** Demande. `proto/suivi_candidatures.py` marque
désormais chaque ligne de mon profil `DIT` ou `DEDUIT`, et un test refuse une
ligne sans provenance — parce que deux déductions non demandées m'ont déjà
coûté un CV faux et un marché écarté.

**Quand une même erreur revient une troisième fois, arrête de la corriger et
rends-la impossible.** Un chiffre qui décroît, une doc qui vieillit, un
invariant qu'on oublie : au troisième passage, écris le test qui échoue à la
place du prochain lecteur.

Si une correction révèle une nouvelle faiblesse :

poursuis.

Si les tests révèlent un problème :

analyse et corrige.

Si ton propre design précédent présente une faille :

remets-le en question et corrige-le.

Je préfère une architecture plus complexe mais correctement justifiée à une architecture simple qui laisse un bypass.
```

**Branche de travail : `claude/decision-companion-rebuild-3k25h3`**.
Ne merge jamais dans `main` sans mon autorisation.

**Ton conteneur part de la branche par défaut, pas de la branche de travail.**
Un hook de démarrage (`.claude/hooks/session-start.sh`) l'a déjà vérifié et a
déjà installé les dépendances : son verdict est en haut de ton contexte, avant
ta première ligne. Lis-le. S'il dit autre chose que « Accord », règle ça avant
de lire la suite — ce n'est plus une consigne que tu peux sauter, et c'est
délibéré.

À relancer à la main seulement si ce bloc n'est pas apparu :

```bash
python3 tools/check_repo_state.py    # doit sortir 0 et dire « Accord »
```

Pourquoi cette commande existe : une séance a démarré sans `singular/sage/`,
sans `ios/` et sur un `CLAUDE.md` d'avant la section 0, parce que la branche
par défaut était restée 39 commits en arrière. Elle serait partie travailler
sur une branche morte si elle n'avait pas comparé. Si la commande dit
« MANDAT SUSPECT » ou « DESACCORD », arrête tout et règle ça d'abord : rien de
ce que tu lirais ensuite ne serait fiable.

## Ce que SINGULAR est

Une **application personnelle** qui doit m'accompagner toute ma vie, façon
« Grand Sage » de *Moi quand je me réincarne en slime*. Il observe, analyse,
conseille — **il ne décide jamais à ma place**. C'est l'invariant que le dépôt
protège : penser ≠ décider ≠ autoriser ≠ exécuter.
`tests/test_sage_isolation.py` interdit tout import de la frontière
d'exécution depuis `singular/sage/` ; `tests/test_sage_independence.py`
interdit au cœur de dépendre d'une clé d'API, d'un service ou du réseau.

**Facultés :** Notice (faite, en usage) → **Analyse, Offres, Parle** (faites,
coupées par défaut) → Mémoire → Compétences.

Trois facultés appellent un modèle, et ce sont les seules choses du dépôt qui
consomment des jetons :

| commande | ce qu'elle fait | ce qu'elle ne peut pas faire |
|---|---|---|
| `analyse` | commente la Notice déjà calculée | écrire, décider, résoudre |
| `offres` | cherche des offres BE sur le web, en propose cinq au plus | postuler, écrire, décider |
| `parle` | une conversation qui connaît le journal et le fil précédent | écrire dans le journal |

Elles vivent **hors** de `singular/sage/`, parce que
`tests/test_sage_independence.py` interdit au cœur de mentionner une clé. Sans
`ANTHROPIC_API_KEY`, chacune se déclare coupée et le reste marche sans elle.
`analyse --blanc` et `offres --blanc` montrent exactement ce qui partirait,
sans rien envoyer — et un test impose que ce soit la même chaîne que celle
envoyée ensuite.

Aucune n'importe le journal ni la frontière d'exécution : commenter n'est pas
décider, et c'est tenu par des tests qui lisent les imports, pas par une phrase
dans l'instruction système — une phrase se contourne par une tournure, une
absence d'import non. `tests/test_facultes_sans_fuite.py` trouve tout seul les
facultés qui appellent un modèle et vérifie qu'aucune ne peut laisser
échapper la clé, y compris celle qui n'existe pas encore.

## Ce qui tourne — l'état réel, pas un plan

**Le Sage est sur mon iPhone et je m'en sers depuis le 6 septembre 2026 au
soir.** `python3 -m singular sage --lan` sur ma machine sert une app web
installée sur mon écran d'accueil, en plein écran. Bibliothèque standard
seule, aucun `pip install`, aucun jeton d'API consommé.

Première décision enregistrée : « Postuler » → « Un entretien », 75 %, 4 h,
rang Revenus, **verdict attendu le 20 septembre**.

**Depuis le 10 septembre 2026, ma machine est un Mac.** Le PC Windows ne l'est
plus. Tout le dépôt était écrit pour PowerShell et a été traduit ce jour-là ;
une commande Windows qui aurait survécu quelque part est un reste, et elle est
fausse. `tests/test_prompt_de_reprise.py` en tient la liste et fait échouer ce
fichier si l'une d'elles y revient. Mon journal a été copié du PC au Mac —
`A_FAIRE.md` ouvre sur ce geste et sur la façon de le vérifier ; demande-moi
si je l'ai fait avant de te fier à ce que le journal affiche.

Limite du chemin actuel : il faut que la machine tourne et que je sois sur mon
wifi. C'est la seule chose que l'application native lèverait.

**Mais la machine n'est plus une dépendance de code.** `singular/__init__.py`
importait tout le moteur historique au chargement, et `pydantic` avec :
`python3 -m singular` exigeait donc un `pip install` pour afficher un journal
qui n'utilise que la bibliothèque standard. Les noms sont résolus à la demande
depuis (PEP 562). Journal, chaîne d'intégrité, Notice, ligne de commande et
serveur du Sage tournent maintenant sans rien installer — donc dans a-Shell sur
l'iPhone. `tests/test_lazy_package.py` le vérifie en sous-processus, avec
pydantic rendu introuvable. Ce qui reste ouvert côté téléphone est
opérationnel, pas structurel : est-ce qu'iOS laisse tourner un serveur en
arrière-plan quand on bascule vers Safari.

**Deuxième chose en usage : `proto/suivi_candidatures.py`**, livré le
6 septembre au soir. Un fichier, un JSON, bibliothèque standard, explicitement
jetable et hors architecture — voir `proto/README.md`. Il me rappelle où en
sont mes candidatures et me donne **une** action pour la journée. Tant que mon
CV n'est pas fini, cette action porte sur le CV, découpé en étapes courtes.
C'est délibéré : je ne candidate pas encore, et un suivi qui me réclamerait
des candidatures serait vide toute la semaine d'essai.

**Troisième chose, depuis le 7 septembre au soir : la conversation.**
`python3 -m singular parle` au clavier, et le bouton 💬 dans l'app du téléphone
— au-dessus du `+`. Elle connaît le rapport du jour et le fil précédent, et
elle **ne peut pas écrire dans le journal** : ce n'est pas une consigne, c'est
une absence d'import, vérifiée par un test. Enregistrer reste le `+`.

**Où j'en suis exactement, et c'est la première chose à me demander.** J'ai
acheté une clé d'API le 7 septembre, 5 $ de crédit. Le
`python3 -m pip install -e ".[analyse]"` était l'étape qui manquait, et rien
dans le dépôt ne dit si elle a abouti — encore moins depuis que la machine a
changé. **Ne suppose rien** — demande-moi ce qu'affiche :

```sh
python3 -m singular parle "dis juste bonjour"
```

S'il répond, tout est en place. S'il parle du paquet `anthropic`, l'install
n'a pas abouti. S'il parle de `ANTHROPIC_API_KEY`, j'ai changé de fenêtre.

Ces trois outils sont la seule chose qui décide de la suite. **Ne construis
rien de neuf tant que je ne t'ai pas dit ce qui me manque en m'en servant.**

**L'application native Swift n'est toujours pas la priorité.** Le port existe,
`ios/SingularSage.xcodeproj` est livré et vérifié par
`tools/check_xcode_project.py`. Il n'avait jamais été compilé faute de Mac ;
j'en ai un depuis le 10 septembre et j'ai lancé Xcode ce jour-là. **Demande-moi
ce qu'a donné `Cmd + U`** plutôt que de le supposer : c'est la seule chose qui
dise si le port Swift et le moteur Python parlent pareil.

Deux choses à ne pas refaire, chacune payée une fois :

- une session a passé son temps à réparer le port pendant que l'app web
  dormait, finie, dans le même dépôt. **Regarde ce qui tourne avant de réparer
  ce qui ne tourne pas** ;
- l'app native a **son propre journal**, un JSON dans l'app, sans aucun import
  depuis `~/.singular/journal.db`. Elle s'ouvre donc sur « Le journal est
  vide ». Compiler et lancer les tests vaut le coup ; m'en servir tous les
  jours découperait mon journal en deux. `ios/README.md` le dit maintenant.

## Vérifie l'état en 90 secondes

```bash
# Les deux lignes suivantes sont deja faites par le hook de demarrage :
# ne les relance que si son bloc n'est pas apparu dans le contexte.
python3 tools/check_repo_state.py  # d'ou part ce conteneur ? doit sortir 0
python3 -m pip install -e ".[dev]"           # pytest n'est pas installe dans un conteneur neuf
python3 -m pytest -q              # tout vert, zéro échec
python -c "from singular.execution_boundary_audit import ExecutionBoundaryAuditor; print(ExecutionBoundaryAuditor().audit().clean)"
python3 tools/generate_notice_vectors.py && git diff --stat   # doit ne rien changer
python3 tools/check_xcode_project.py                          # le projet Xcode tient
python proto/suivi_candidatures.py < /dev/null               # le proto s'affiche
```

## Mes commandes s'écrivent dans MA fenêtre

**Je suis sur Mac, dans le Terminal — donc `zsh`.** Depuis le 10 septembre
2026 ; avant, c'était un PC Windows et PowerShell, et tout le dépôt était
écrit pour lui. Ne me redonne pas de PowerShell.

- La variable se pose avec `export ANTHROPIC_API_KEY="..."`, et elle ne vaut
  que pour la fenêtre en cours.
- **`python3`, jamais `python`** : depuis macOS 12.3 la commande `python` seule
  n'existe plus, et elle rend « command not found », ce qui ressemble à un
  outil cassé.
- `pip install` suppose que `pip` est dans le PATH et vise le bon Python.
  Aucune des deux n'est acquise. La forme est `python3 -m pip install`.

Ces fautes échouent en silence ou de travers, et je les découvre seul sans
pouvoir faire le lien. Deux tests tiennent la règle plutôt que ta vigilance :
`tests/test_commandes_de_sa_fenetre.py` pour ce qui ne marche nulle part, et
`tests/test_documentation_is_current.py` pour ce qui dépend de la machine —
celui-là a dû changer de camp le jour du Mac.

Mon clone est dans `~/Documents/SINGULAR`. **Il ne se met pas à jour tout
seul** : si tu viens de pousser quelque chose, la première chose que je dois
faire est `git pull` — sinon rien de ce que tu as écrit n'existe chez moi, et
les étapes suivantes échouent sans dire pourquoi.

## Contraintes — ne les redécouvre pas

- **Je suis en français.** Toute sortie console reste dans ce que **cp850**
  accepte : ni flèche, ni tiret cadratin, ni points de suspension
  typographiques. Les accents passent. C'était une contrainte du PC Windows ;
  le Mac ne l'impose plus, et la règle reste parce qu'elle ne coûte rien et que
  le téléphone, lui, n'a pas été mesuré. `tests/test_windows_console.py` le
  vérifie, et la sortie tolère l'irreprésentable pour que mes propres mots ne
  fassent jamais échouer une commande.
- **Le Terminal du Mac colle les lignes multiples telles quelles**, contrairement
  à PowerShell qui les fusionnait. Un bloc de plusieurs lignes est donc redevenu
  possible ; trois allers-retours avaient été perdus là-dessus.
- **Aucun compilateur Swift dans ton environnement, impossible à installer** :
  la passerelle refuse swift.org et les binaires GitHub. Vérifié.
- CI ignore `**/*.md` et `docs/**` : un commit de doc ne déclenche aucun run.
- `attic/` hors périmètre. `ruff check` sur tout le dépôt sort des dizaines
  d'erreurs préexistantes, dans du code historique : vérifie **tes** fichiers,
  pas le dépôt entier.
- Commentaires en anglais dans les modules historiques, en français dans
  `singular/sage/`, `singular/__main__.py` et `ios/`.

## Ce que l'usage réel a déjà appris

Quatre défauts trouvés en une soirée d'utilisation, aucun par les tests :

1. Le jeton gardait aussi le CSS et le JS, que le navigateur demande sans lui
   → l'app s'ouvrait nue sur le téléphone. Toute la suite parlait au serveur
   par `127.0.0.1`, où le jeton n'est pas demandé.
2. Une PWA iOS a **son propre stockage**, séparé de Safari → l'icône démarrait
   sans clé, sans aucun moyen d'en fournir une. Il y a maintenant un champ.
3. Le Sage reprochait « tu confonds activité et résultat » dès la première
   décision, dont l'échéance était dans treize jours.
4. La vignette du même chiffre gardait l'accusation que la phrase venait
   d'abandonner.

La leçon, et elle vaut pour la suite : **ce que je constate en m'en servant
vaut mieux que ce que tu peux déduire d'ici.** Quand je te donne une capture
d'écran ou un message d'erreur, c'est la meilleure donnée de la session.

Une cinquième, trouvée le 6 septembre en relisant le serveur, pas à l'usage :
n'importe quelle page web ouverte dans un navigateur sur ma machine pouvait
écrire dans mon journal et **rendre un verdict à ma place**, sans connaître le
jeton, y compris en mode `127.0.0.1`. `authorised()` accordait tout à la
boucle locale « parce qu'il n'y a personne d'autre dessus » : il y a le
navigateur. Corrigé — origine, hôte et type du corps sont vérifiés — et
`tests/test_sage_server.py` le tient. Retiens la forme du bug plutôt que le
bug : **une phrase juste dans un commentaire peut devenir fausse sans que le
code change.**

## Ce qui décide de la suite

Pas un compilateur, pas une liste de facultés : **une semaine d'usage**, et
maintenant trois choses à observer — le Sage, `proto/suivi_candidatures.py`,
et la conversation, dès qu'elle tournera chez moi. N'écris pas « Mémoire »
avant que je t'aie dit ce qui me manque en m'en servant. Construire pour un
usage que personne n'a observé est exactement ce que la section 0 interdit.

Le 7 septembre a été une journée de construction dense — trois facultés, la
conversation servie au téléphone, un compteur de dépense. **La suite ne l'est
pas.** La prochaine information utile vient de moi en train de m'en servir,
pas d'une session qui continue sur sa lancée.

Le prototype est **jetable, et c'est le but**. S'il ne sert pas au bout d'une
semaine, on le supprime : c'est un résultat, pas un échec. S'il sert, ce qui
lui manquera dira quelle faculté construire — et ce sera fondé sur un usage
réel plutôt que sur une liste écrite d'avance.

Ce que j'aurai à te dire viendra sous une de ces formes :
- quelque chose casse → corrige, avec le test qui l'aurait attrapé ;
- une phrase du Sage sonne faux → le moteur Python fait foi, mais **une phrase
  fausse est un bug**, pas un détail de ton ;
- il me manque quelque chose → c'est là que la faculté suivante commence.

## Décisions qui m'attendent — ne tranche pas seul

1. **Un durcissement de politique rend un effet externe ambigu définitivement
   irréconciliable.** Prouvé dans `tests/test_reconciliation_policy_drift.py` :
   l'effet part, revient UNKNOWN, la capacité nommée est resserrée, `verify()`
   échoue, la réconciliation refuse, le fournisseur n'est jamais interrogé.
   Refuser de demander ne défait pas un virement qui serait parti. La sortie
   exigerait de tolérer une divergence précise dans `verify()`, sur le chemin
   le plus sensible du système. **C'est ma décision.**
2. `ActionRequest.capability` (la capacité **nommée**, pas le jeton `cap_`)
   vaut `None` par défaut. Faut-il la rendre obligatoire pour toute action
   exécutable ?
3. **Des branches mortes traînent sur `origin`** — le hook de démarrage les
   liste à chaque démarrage, avec leur compte du jour. Aucune ne porte de
   travail unique, c'est vérifié et écrit. Les supprimer est un geste que je
   dois faire moi-même : la passerelle bloque `git push --delete` depuis le
   conteneur, et aucun outil disponible ne supprime une branche. Ne me le
   propose pas une troisième fois.

## Pistes d'audit encore ouvertes

1. Ce à quoi **un nom global se résout** n'est pas couvert par l'empreinte de
   capability (limite assumée, testée).
2. Un objet sans `artifact_identity()` est identifié par sa seule classe
   (opt-in, testé).
3. L'auditeur ne voit pas un module à qui l'on **passe** un objet frontière
   déjà construit — hygiène, pas escalade, vérifié.
4. `DurableIntegrityChecker.check()` sans argument n'a plus d'appelant en
   production.
5. Côté port iOS : que le Swift **compile** reste hors de portée d'ici.
   L'équivalence arithmétique avec le moteur Python est tenue par
   `tests/test_notice_rounding_port.py`, la correspondance du JSON des
   vecteurs avec les structures Swift par `tests/test_notice_vector_schema.py`,
   et la liste des observations produites de part et d'autre par
   `tests/test_notice_port_parity.py`.
   **Le port est en retard de deux observations**, `irreversibleItem` et
   `unpricedItem`, déclarées dans `ABSENTES_DU_PORT` avec la raison. Les
   vecteurs committés les attendent déjà : le premier Mac qui compilera le port
   verra ces vecteurs échouer, et ce n'est pas une surprise mais une dette
   écrite. Retirer un nom de cette liste sans écrire le Swift fait échouer le
   test ici, tout de suite.

## Coût, pour ne pas le recalculer

Mon abonnement Claude **ne donne pas accès à l'API** — deux facturations
séparées. **J'ai acheté une clé, 5 $ de crédit**, le 7 septembre 2026.

Les seuls chiffres justes sont sur console.anthropic.com et sur ma facture.
Ce dépôt n'écrit aucun prix, et un test l'interdit : un tarif codé en dur
vieillirait en silence et servirait à décider quand s'arrêter. Mes tarifs à moi
vivent dans `~/.singular/tarifs.json`, que `python3 -m singular parle --tarifs`
prépare — et tant qu'il est vide, la conversation compte des jetons et ne parle
jamais d'argent.

Modèles par défaut : `claude-opus-5` pour `analyse` et `offres`, qui sont des
coups uniques ; **`claude-sonnet-5` pour `parle`**, parce qu'une conversation
c'est vingt appels dans la soirée et que ce choix décide si 5 $ durent une
semaine ou un après-midi. `SINGULAR_PARLE_MODELE` remet Opus.

Deux gardes sur la conversation, qui ne comptent pas la même chose : soixante
réponses par jour depuis le téléphone (large exprès — un garde-fou contre
l'emballement, pas contre l'usage ; le clavier n'en a pas), et le crédit
restant, qui refuse avant d'appeler dès que les tarifs sont écrits.

La frontière qu'on peut couper existe maintenant : clé révoquée, paquet
désinstallé, réseau absent — le journal, la chaîne d'intégrité, la Notice et la
calibration continuent. Ce n'est pas une intention, c'est ce que vérifient
`tests/test_sage_independence.py` et `tests/test_analyse.py`.

## Contexte personnel (ne me le redemande pas)

Débutant en code. iPhone + **Mac** depuis le 10 septembre 2026 ; le PC Windows
ne sert plus. Explique les commandes pas à pas.

**Pose-moi tes questions en questionnaire** (`AskUserQuestion`), jamais en
paragraphes : je réponds sur un téléphone. C'est écrit dans `CLAUDE.md` §24,
après dix rappels.
~30 h/semaine. **Parle-moi en français.** Droit au but, pas de long
récapitulatif, pas de flatterie.

Côté métier, parce que le prototype s'en sert et que tu en auras besoin.
Une session l'avait écrit faux et le prototype a propagé l'erreur pendant deux
jours : ne le redéduis pas, lis-le.

**2 ans en bureau d'études CVC déjà effectués** — chiffrage, dimensionnement.
Avant : **5 ans de terrain dans l'Armée**, sur chambre froide, groupe
électrogène et brûleur — froid, énergie, combustion, chambres froides en
positif **et** en négatif. **Et du tertiaire : je dimensionne, sélectionne et
chiffre des centrales de traitement d'air, de 600 à 50 000 m³/h — travail de
bureau d'études, pas d'entretien.** Récupération : échangeur à plaques, roue
hygroscopique, batteries à eau glycolée, les trois. Le combustible des brûleurs,
je ne m'en souviens plus : ne me le redemande pas. Le profil est donc large, pas
spécialisé d'un seul côté : une session l'avait rétréci à l'industriel par
déduction, et c'était faux. **BTS Fluides Énergies Domotique.** Actuellement au
chômage, je cherche un poste en bureau d'études **dans la région toulousaine**.

Je ne suis donc **pas en reconversion** : le bureau d'études est déjà mon
métier. Une reprise d'études en alternance m'intéresse, mais au 7 septembre
2026 je n'ai **ni école ni entreprise** — la rentrée 2026 est hors d'atteinte,
et chercher un poste classique passe devant.

Je ne candidate pas encore : je dois d'abord retravailler mon CV, et c'est pour
ça que le prototype fait passer le CV avant les candidatures.

## Méthode

Inspecte → corrige → teste → commits atomiques → pousse → vérifie le CI réel →
enchaîne. Les trois règles opérationnelles sont dans `CLAUDE.md` §24 :
terminer c'est la demande **plus ce qu'elle rend faux** ; ne jamais finir un
tour en nommant un travail qu'on pourrait faire ; à la troisième occurrence
d'une même erreur, écrire le test au lieu de corriger.

## Ce que je dois faire moi-même

Voir `A_FAIRE.md`. En résumé : copier mon journal du PC au Mac si ce n'est pas
fait, ouvrir l'app le matin, et **trancher le 20 septembre**. Le reste attend
ce que l'usage montrera.

---
