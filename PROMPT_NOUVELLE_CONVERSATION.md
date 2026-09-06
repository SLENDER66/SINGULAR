# Prompt de reprise — à copier/coller dans une nouvelle conversation

Colle **uniquement le bloc entre les lignes**. Ne recolle jamais `CLAUDE.md` :
il est dans le dépôt et Claude le lit tout seul.

---

Dépôt : **SLENDER66/SINGULAR** (public). Mandat complet dans `CLAUDE.md` à la
racine : lis-le, applique-le, ne me le fais pas répéter.

**Branche de travail : `claude/remote-control-0pu0vh`**, en avance sur
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
```

## Ce qui se passe en ce moment — priorité absolue

**Ma sœur a mon Mac et compile à ma place, à distance.** Elle suit la section
« Si quelqu'un d'autre compile à ta place » de `ios/README.md` : Xcode, projet
`SingularSage`, `Cmd+U` puis `Cmd+R` dans le **simulateur**. Aucun compte Apple,
aucun euro — le simulateur n'en demande pas.

Elle ne peut pas installer sur mon iPhone (il n'est pas près du Mac ; seul
TestFlight le permettrait, donc 99 €/an, écarté pour l'instant).

**Quand je te donne son retour, traite-le dans cet ordre :**

1. **Erreurs de compilation Xcode** — le plus probable, ce Swift n'a jamais vu
   de compilateur. Corrige le fichier, ne réécris pas l'architecture pour une
   erreur de syntaxe.
2. **Tests rouges** — `NoticeVectorTests` compare le portage Swift au moteur
   Python via `ios/SingularSage/Resources/notice_vectors.json`. **Le moteur
   Python fait foi, c'est le Swift qui a tort.**
3. **Captures d'écran** — retours de design.
4. Une fois le build vert : enchaîne sur **Mémoire**.

**N'écris aucune faculté nouvelle avant que le build soit vert.**

## Contraintes — ne les redécouvre pas

- **Aucun compilateur Swift ici et impossible à installer** : la passerelle
  réseau refuse swift.org et les binaires GitHub. Vérifié, n'y passe pas de temps.
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

## Coût, pour ne pas le recalculer

Mon abonnement Claude **ne donne pas accès à l'API** — deux facturations
séparées. La faculté « Analyse » consommera ma propre clé : ~2,5 €/mois
(Sonnet 5), ~6 €/mois (Opus 5), ~22 €/mois en usage intense. Le moteur
déterministe (Notice, journal, calibration) tourne sans un token.

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
