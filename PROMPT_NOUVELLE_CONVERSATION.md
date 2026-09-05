# Prompt de reprise — à copier/coller dans une nouvelle conversation

Colle **uniquement le bloc entre les lignes**. Ne recolle jamais le mandat `CLAUDE.md` :
il est dans le dépôt et Claude le lit tout seul.

---

Dépôt : SLENDER66/SINGULAR (public). Branche de travail et branche par défaut :
`claude/singular-mandate-setup-d51s9t`. Le mandat complet est dans `CLAUDE.md` à la
racine : lis-le, applique-le, ne me le fais pas répéter.

État vérifié (tout est poussé sur la branche de travail, arbre propre) :
- 612 tests passent, audit de frontière propre, CI verte (Python 3.11 + 3.13).
- Frontière fail-closed : ValidatedTrajectoryDecision → attestation durable → capability
  (fingerprint d'artefact) → lease → effet externe → outcome ledger.
- LICENSE MIT en place. Dépôt nettoyé : 9 branches pour 8 commits distincts.
- 22 modules et 21 fichiers de test hors périmètre sont dans `attic/`.
- `route()` écrit désormais son verdict de gouvernance dans l'audit durable
  (`governance_route`, `governance_route_replayed`).
- Le registre d'amélioration déduit la criticité depuis la cible : plus de drapeau
  auto-déclaré, périmètre adaptatif en liste blanche, revérifié à l'activation.
- Les deux chemins d'effet externe exigent l'empreinte d'artefact et le registre durable,
  et l'attestation comme la capability sont relues juste avant l'appel du provider ; un refus
  tardif libère le lease en FAILED au lieu d'inventer une récupération.
- Un artefact peut déclarer sa configuration (`artifact_identity()`) : deux providers HTTP
  visant des endpoints différents ne sont plus le même artefact.
- L'approbation humaine n'est **pas** un canal d'autorisation via le pipeline validé :
  c'est délibéré (deux gardes explicites). La machinerie d'approbation dans
  `DurableExecutionEngine` est une défense time-of-use contre une gouvernance qui escalade
  après la frappe de la décision. Ne « répare » pas ça sans me demander.

Contexte personnel (ne me le redemande pas) :
- Débutant. PC sous Windows + téléphone. Explique les commandes pas à pas (PowerShell) :
  ne suppose ni Linux, ni Git configuré, ni Python installé.
- ~30 h/semaine. Objectif : SINGULAR utile puis rentable en 1–2 ans.
- Ne merge jamais dans `main` sans mon autorisation explicite.
- Économise mes tokens : droit au but, pas de récapitulatif long, pas de re-vérification de
  ce qui est écrit ci-dessus.

Travaille en autonomie :
1. Poursuis l'audit adversarial de la chaîne decision → capability → artefact → exécution.
   Pistes ouvertes repérées mais non traitées :
   - un artefact qui ne déclare pas `artifact_identity()` reste identifié par le seul
     bytecode de sa classe : sa configuration n'est pas couverte (opt-in assumé) ;
   - `ExecutionCapabilityRegistry.attach()` peut lier une partie des tokens puis échouer,
     laissant le registre sans magasin durable ;
   - `_persist_new_audit_events()` se cale sur la longueur du journal en mémoire : deux
     runtimes sur la même base ne peuvent pas écrire l'audit tous les deux (échec bruyant,
     donc fail-closed, mais un second processus ne peut rien auditer).

Méthode : inspecte → corrige → teste → commits atomiques → pousse → enchaîne.
Questions sous forme de questionnaire, seulement si une décision humaine est nécessaire.

---

## Ce que je dois faire moi-même sur GitHub

Rien pour l'instant. Le nettoyage des branches est fait : 39 branches en doublon
supprimées le 2026-09-05, il reste 9 branches pour 8 commits distincts, aucun travail
perdu.
