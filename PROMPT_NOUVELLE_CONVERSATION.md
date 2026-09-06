# Prompt de reprise — à copier/coller dans une nouvelle conversation

Colle **uniquement le bloc entre les deux traits**. Ne recolle jamais
`CLAUDE.md` : il est dans le dépôt et Claude le lit tout seul.

---

Dépôt : **SLENDER66/SINGULAR** (public). Mandat complet dans `CLAUDE.md` à la
racine : lis-le, applique-le, ne me le fais pas répéter.

Sa **section 0** dit pour qui tu travailles. Je l'avais écrit trois fois dans
trois conversations avant qu'elle existe ; elle est là pour que ce soit la
dernière. Ne me réponds pas que tu l'as bien noté — applique-la.

**Branche de travail : `claude/remote-control-feedback-ndpzle`**, en avance sur
`claude/singular-mandate-setup-d51s9t` (branche par défaut, pas à jour).
Ne merge jamais dans `main` sans mon autorisation.

**Ton conteneur part de la branche par défaut, donc en retard.** Une séance a
démarré ainsi sans `singular/sage/`, sans `ios/`, et sur un `CLAUDE.md` d'avant
la section 0 — et aurait travaillé sur une branche morte si elle n'avait pas
comparé. `python tools/check_repo_state.py` le dit en une commande. Fais-le
avant de lire quoi que ce soit d'autre.

## Ce que SINGULAR est

Une **application personnelle** qui doit m'accompagner toute ma vie, façon
« Grand Sage » de *Moi quand je me réincarne en slime*. Il observe, analyse,
conseille — **il ne décide jamais à ma place**. C'est l'invariant que le dépôt
protège : penser ≠ décider ≠ autoriser ≠ exécuter.
`tests/test_sage_isolation.py` interdit tout import de la frontière
d'exécution depuis `singular/sage/` ; `tests/test_sage_independence.py`
interdit au cœur de dépendre d'une clé d'API, d'un service ou du réseau.

**Facultés :** Notice (faite, en usage) → Mémoire → Analyse → Compétences.

## Ce qui tourne — l'état réel, pas un plan

**Le Sage est sur mon iPhone et je m'en sers depuis le 6 septembre 2026 au
soir.** `python -m singular sage --lan` sur mon PC Windows sert une app web
installée sur mon écran d'accueil, en plein écran. Bibliothèque standard
seule, aucun `pip install`, aucun jeton d'API consommé.

Première décision enregistrée : « Postuler » → « Un entretien », 75 %, 4 h,
rang Revenus, **verdict attendu le 20 septembre**.

Limite du chemin actuel : il faut que le PC tourne et que je sois sur mon
wifi. C'est la seule chose que l'application native lèverait.

**L'application native Swift n'est pas la priorité et ne bloque rien.** Le
port existe, `ios/SingularSage.xcodeproj` est livré, mais il n'a jamais été
compilé — je n'ai pas de Mac. Une session précédente a passé son temps à le
réparer pendant que l'app web dormait, finie, dans le même dépôt. Ne refais
pas ça : **regarde ce qui tourne avant de réparer ce qui ne tourne pas.**

## Vérifie l'état en 90 secondes

```bash
python tools/check_repo_state.py  # AVANT tout : sur quelle branche ce conteneur est-il parti ?
pip install -e '.[dev]'          # pytest n'est PAS installé dans un conteneur neuf
python -m pytest -q              # tout vert, zéro échec
python -c "from singular.execution_boundary_audit import ExecutionBoundaryAuditor; print(ExecutionBoundaryAuditor().audit().clean)"
python tools/generate_notice_vectors.py && git diff --stat   # doit ne rien changer
python tools/check_xcode_project.py                          # le projet Xcode tient
```

## Contraintes — ne les redécouvre pas

- **Je suis sur Windows, en français.** Toute sortie console doit tenir dans
  **cp850** : ni flèche, ni tiret cadratin, ni points de suspension
  typographiques. Les accents passent. `tests/test_windows_console.py` le
  vérifie, et la sortie tolère l'irreprésentable pour que mes propres mots ne
  fassent jamais échouer une commande.
- **PowerShell fusionne les lignes collées.** Donne-moi **une seule ligne à la
  fois**, et dis-moi d'appuyer sur Échap avant de coller. Trois allers-retours
  ont été perdus là-dessus.
- **`core.autocrlf`** recrée sans fin une modification locale et bloque
  `git checkout`. Réglé chez moi à `false`.
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

## Ce qui décide de la suite

Pas un compilateur, pas une liste de facultés : **une semaine d'usage.**
N'écris pas « Mémoire » avant que je t'aie dit ce qui me manque en m'en
servant. Construire pour un usage que personne n'a observé est exactement ce
que la section 0 interdit.

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
   `tests/test_notice_rounding_port.py`, et la correspondance du JSON des
   vecteurs avec les structures Swift par `tests/test_notice_vector_schema.py`.

## Coût, pour ne pas le recalculer

Mon abonnement Claude **ne donne pas accès à l'API** — deux facturations
séparées. La faculté « Analyse » consommera ma propre clé : ~2,5 €/mois
(Sonnet 5), ~6 €/mois (Opus 5), ~22 €/mois en usage intense. Le moteur
déterministe tourne sans un jeton, et doit continuer : quand « Analyse »
arrivera, elle vivra derrière une frontière qu'on peut couper — clé révoquée,
service fermé, réseau absent — sans emporter le reste.

## Contexte personnel (ne me le redemande pas)

Débutant. iPhone + PC Windows ; le Mac est chez ma sœur et n'est pas requis.
Explique les commandes pas à pas, **une ligne à la fois**. ~30 h/semaine.
**Parle-moi en français.** Droit au but, pas de long récapitulatif, pas de
flatterie.

## Méthode

Inspecte → corrige → teste → commits atomiques → pousse → vérifie le CI réel →
enchaîne. Les trois règles opérationnelles sont dans `CLAUDE.md` §24 :
terminer c'est la demande **plus ce qu'elle rend faux** ; ne jamais finir un
tour en nommant un travail qu'on pourrait faire ; à la troisième occurrence
d'une même erreur, écrire le test au lieu de corriger.

---

## Ce que je dois faire moi-même

Voir `A_FAIRE.md`. En résumé : ouvrir l'app le matin, et **trancher le
20 septembre**. Le reste attend ce que l'usage montrera.
