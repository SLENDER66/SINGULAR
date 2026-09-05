# Prompt de reprise — à copier/coller dans une nouvelle conversation

Colle **uniquement le bloc entre les lignes**. Ne recolle jamais le mandat `CLAUDE.md` :
il est dans le dépôt et Claude le lit tout seul.

---

Dépôt : SLENDER66/SINGULAR (public). Branche de travail et branche par défaut :
`claude/singular-mandate-setup-d51s9t`. Le mandat complet est dans `CLAUDE.md` à la
racine : lis-le, applique-le, ne me le fais pas répéter.

État vérifié (tout est poussé sur la branche de travail, arbre propre) :
- 585 tests passent, audit de frontière propre, CI verte (Python 3.11 + 3.13).
- Frontière fail-closed : ValidatedTrajectoryDecision → attestation durable → capability
  (fingerprint d'artefact) → lease → effet externe → outcome ledger.
- LICENSE MIT en place. Dépôt nettoyé : 9 branches pour 8 commits distincts.
- 22 modules et 21 fichiers de test hors périmètre sont dans `attic/`.
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

Travaille en autonomie, dans cet ordre :
1. `route()` (singular/mission_runtime.py) n'écrit aucun événement d'audit sur son chemin
   normal — trou de provenance.
2. `ImprovementCandidate.safety_critical` (singular/improvement_registry.py) est un drapeau
   auto-déclaré : un candidat peut se déclarer non critique et échapper aux contrôles.
3. Poursuis l'audit adversarial de la chaîne decision → capability → artefact → exécution.

Méthode : inspecte → corrige → teste → commits atomiques → pousse → enchaîne.
Questions sous forme de questionnaire, seulement si une décision humaine est nécessaire.

---

## Ce que je dois faire moi-même sur GitHub

Rien pour l'instant. Le nettoyage des branches est fait : 39 branches en doublon
supprimées le 2026-09-05, il reste 9 branches pour 8 commits distincts, aucun travail
perdu.
