# Prompt de reprise — à copier/coller dans une nouvelle conversation

Colle **uniquement le bloc entre les lignes**. Ne recolle jamais `CLAUDE.md` :
il est dans le dépôt et Claude le lit tout seul.

---

Dépôt : **SLENDER66/SINGULAR** (public). Mandat complet dans `CLAUDE.md` à la
racine : lis-le, applique-le, ne me le fais pas répéter.

Sa **section 0** dit pour qui tu travailles. Je l'avais écrit trois fois dans
trois conversations avant qu'elle existe ; elle est là pour que ce soit la
dernière. N'attends pas que je le redemande, et ne me réponds pas que tu l'as
bien noté — applique-le.

**Branche de travail : `claude/remote-control-feedback-ndpzle`**, en avance sur
`claude/singular-mandate-setup-d51s9t` (branche par défaut, pas à jour).
Ne merge jamais dans `main` sans mon autorisation.

## Ce que le projet est devenu

Plus seulement un audit d'architecture : **une application iPhone personnelle**
qui doit m'accompagner toute ma vie, façon « Grand Sage » de *Moi quand je me
réincarne en slime*. Il observe, analyse, conseille — **il ne décide jamais à ma
place**. C'est l'invariant que le dépôt protège déjà : penser ≠ décider ≠
autoriser ≠ exécuter. `tests/test_sage_isolation.py` interdit tout import de la
frontière d'exécution depuis `singular/sage/`.

**Facultés :** Notice (faite) → Mémoire → Analyse → Compétences.

## Vérifie l'état en 90 secondes

```bash
pip install -e '.[dev]'          # pytest n'est PAS installé dans un conteneur neuf
python -m pytest -q              # tout vert, zéro échec
python -c "from singular.execution_boundary_audit import ExecutionBoundaryAuditor; print(ExecutionBoundaryAuditor().audit().clean)"
python tools/generate_notice_vectors.py && git diff --stat   # doit ne rien changer
python tools/check_xcode_project.py   # le projet Xcode s'ouvre et est complet
```

## Ce qui se passe en ce moment

**Le Sage tourne sur mon PC Windows et je l'ouvre depuis mon iPhone.**
`python -m singular sage --lan` sert une app web installable sur l'écran
d'accueil, en bibliothèque standard seule, sans rien à installer. C'est le
chemin qui marche aujourd'hui. Sa limite : il faut que le PC tourne et que je
sois sur mon wifi.

L'app native Swift lève cette limite — hors ligne, partout — mais elle dépend
d'un Mac que je n'ai pas. **Ce n'est pas la priorité ; c'est une amélioration
qui attend.** Une session précédente l'avait traitée comme un blocage et a
passé son temps à réparer du Swift pendant que l'app web existait déjà,
inutilisée, dans le même dépôt. Ne refais pas ça : regarde ce qui tourne avant
de réparer ce qui ne tourne pas.

### L'app native, quand le Mac se libère

**Ma sœur a mon Mac et compile à ma place, à distance.** Elle suit la section
« Si quelqu'un d'autre compile à ta place » de `ios/README.md` : Xcode,
`git clone`, `open SINGULAR/ios/SingularSage.xcodeproj`, `Cmd+U` puis `Cmd+R`
dans le **simulateur**. Aucun compte Apple, aucun euro — le simulateur n'en
demande pas. Le projet Xcode est dans le dépôt : elle n'a plus rien à monter à
la main.

Elle ne peut pas installer sur mon iPhone (il n'est pas près du Mac ; seul
TestFlight le permettrait, donc 99 €/an, écarté pour l'instant).

**Quand je te donne son retour, traite-le dans cet ordre :**

1. **Erreurs de compilation Xcode** — le plus probable, ce Swift n'a jamais vu
   de compilateur. Corrige le fichier, ne réécris pas l'architecture pour une
   erreur de syntaxe.
   Déjà écartés sans elle, ne les recherche pas : le mode Swift 6 (les vues
   touchent le journal `@MainActor`, le formateur ISO8601 est une globale non
   `Sendable`) et le montage manuel du projet. Le projet fixe `SWIFT_VERSION`
   et `IPHONEOS_DEPLOYMENT_TARGET`, donc sa version d'Xcode ne décide plus.
   **Si Xcode dit « the project is damaged »**, c'est la seule panne que
   `tools/check_xcode_project.py` ne peut pas voir : l'annexe « Si le projet ne
   s'ouvre pas » du README lui donne le montage manuel en repli.
2. **Tests rouges** — `NoticeVectorTests` compare le portage Swift au moteur
   Python via `ios/SingularSage/Resources/notice_vectors.json`. **Le moteur
   Python fait foi, c'est le Swift qui a tort.**
   Douze cas, dont deux qui existent pour une raison précise :
   `arrondi_sur_une_moitie` (multiplier avant d'arrondir se trompe d'un point,
   corrigé) et `chaine_rompue` (l'observation la plus grave, et l'ordre de deux
   observations de même gravité).
3. **Captures d'écran** — retours de design.
4. Une fois le build vert : c'est fini pour l'app native.

Le build Swift ne bloque plus rien : le Sage est déjà sur mon téléphone par
le web. Ce qui décide de la suite, ce n'est plus un compilateur — c'est ce que
l'usage quotidien me montre.

## Contraintes — ne les redécouvre pas

- **Aucun compilateur Swift ici et impossible à installer** : la passerelle
  réseau refuse swift.org et les binaires GitHub. Vérifié, n'y passe pas de temps.
- **Je suis sur Windows.** Toute sortie console doit tenir dans cp850 : ni
  flèche, ni tiret cadratin, ni points de suspension typographiques. Les
  accents passent. `tests/test_windows_console.py` le vérifie.
- CI ignore `**/*.md` et `docs/**` : un commit de doc ne déclenche aucun run.
- `attic/` hors périmètre. `ruff check` sur tout le dépôt sort ~91 erreurs
  préexistantes : vérifie **tes** fichiers, pas le dépôt entier.
- Commentaires en anglais dans les modules historiques, en français dans
  `singular/sage/` et `ios/`. Suis le fichier que tu touches.

## Décisions qui m'attendent — ne tranche pas seul

1. **Un durcissement de politique rend un effet externe ambigu définitivement
   irréconciliable.** Prouvé de bout en bout dans
   `tests/test_reconciliation_policy_drift.py` : l'effet part, revient UNKNOWN,
   la capacité nommée est resserrée, `verify()` échoue, la réconciliation
   refuse, le fournisseur n'est jamais interrogé. Refuser de demander ne défait
   pas un virement qui serait parti. La sortie exigerait de séparer « décision
   encore exécutable » de « décision authentique désignant cet effet », donc de
   tolérer une divergence précise dans `verify()`, sur le chemin le plus
   sensible du système. **Échanger un refus contre une autorisation
   conditionnelle sur la frontière d'exécution est ma décision.**
2. `ActionRequest.capability` (la capacité **nommée**, pas le jeton `cap_`) vaut
   `None` par défaut. Faut-il la rendre obligatoire pour toute action exécutable ?

## Pistes d'audit encore ouvertes

1. Ce à quoi **un nom global se résout** n'est pas couvert par l'empreinte de
   capability (limite assumée, testée).
2. Un objet sans `artifact_identity()` est identifié par sa seule classe (opt-in,
   testé).
3. L'auditeur ne voit pas un module à qui l'on **passe** un objet frontière déjà
   construit — hygiène, pas escalade, vérifié.
4. `DurableIntegrityChecker.check()` sans argument n'a plus d'appelant en
   production depuis que la frontière est bornée à la mission.
5. Côté port iOS, ce qui reste hors de portée d'ici : que le Swift **compile**,
   et qu'il emploie bien les formules vérifiées. L'équivalence de l'arithmétique
   entre les deux moteurs est, elle, tenue par
   `tests/test_notice_rounding_port.py`, qui tourne dans le CI.

## Coût, pour ne pas le recalculer

Mon abonnement Claude **ne donne pas accès à l'API** — deux facturations
séparées. La faculté « Analyse » consommera ma propre clé : ~2,5 €/mois
(Sonnet 5), ~6 €/mois (Opus 5), ~22 €/mois en usage intense. Le moteur
déterministe (Notice, journal, calibration) tourne sans un token.

Ce n'est pas qu'une question d'argent : quand « Analyse » arrivera, elle devra
vivre derrière une frontière qu'on peut couper — clé révoquée, service fermé,
réseau absent — sans emporter le reste. `tests/test_sage_independence.py`
interdit déjà au cœur d'importer un client de service ou de lire une clé, et
construit une Notice complète avec les sockets retirés.

## Contexte personnel (ne me le redemande pas)

Débutant. iPhone ; le Mac est chez ma sœur pour l'instant. Explique les
commandes pas à pas. ~30 h/semaine. Objectif : SINGULAR utile puis rentable en
1–2 ans. **Parle-moi en français.** Droit au but, pas de long récapitulatif.

## Méthode

Inspecte → corrige → teste → commits atomiques → pousse → enchaîne. Les trois
règles opérationnelles sont dans `CLAUDE.md` et je te demanderai de les tenir :
terminer c'est la demande **plus ce qu'elle rend faux** ; ne jamais finir un
tour en nommant un travail qu'on pourrait faire ; à la troisième occurrence
d'une même erreur, écrire le test au lieu de corriger une fois de plus.

---

## Ce que je dois faire moi-même

Voir `A_FAIRE.md`. Rien sur GitHub ; tout est entre les mains de ma sœur et du
Mac.
