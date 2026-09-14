"""Quel refus de la frontiere peut-on retirer sans qu'aucun test ne rougisse ?

« Les tests passent » ne dit pas quels refus sont prouves. Cet outil le mesure :
il neutralise chaque refus des modules vises, un par un, relance une sous-suite
ciblee, et nomme ceux qui survivent. Un survivant est un refus qu'aucun test
n'atteint.

**Cinq formes, parce qu'il y en a cinq.**

1. Un `if ... raise` : sa condition devient fausse.
2. Un `return False` dans une fonction qui rend un booleen : il devient
   `return True`. La premiere version ne connaissait que la forme 1, et passait
   donc a cote de tous les predicats -- `verify`, `matches`, `authorised`,
   `same_origin` -- qui sont les refus les plus graves du depot et qui refusent
   sans lever.
3. **Une moitie** d'un garde compose. `if a or b: raise` neutralise en entier ne
   dit pas si `a` et `b` sont tous les deux prouves : on remplace donc une moitie
   a la fois par son element neutre -- `False` dans un `or`, `True` dans un `and`
   -- et l'autre continue de garder. C'est la forme la plus fine : elle nomme la
   moitie de condition que personne n'essaie.
4. **Une moitie d'un booleen rendu.** Les trois premieres ne savent voir que ce
   qui refuse. Elles ne trouvaient donc rien dans les modules qui **decident** :
   `global_control.py` n'avait pas un seul mutant, et c'est mesure, pas suppose.
   Ces modules ne levent rien, ils rendent un verdict que les autres lisent -- et
   un verdict faux est plus grave qu'un refus manquant.
   `GlobalDecisionReport.requires_human` est l'exemple : cinq raisons reliees par
   des `or`, cinq facons differentes d'exiger un humain. Si une seule n'est prouvee
   par aucun test, toute une categorie peut cesser d'en exiger un sans que rien ne
   rougisse.
5. **Une moitie d'un booleen rendu dans un dictionnaire.** La forme 4 ne voit un
   verdict que s'il est rendu tout nu, par une fonction annotee `-> bool`. Or ce
   depot construit ses verdicts les plus lus dans des dictionnaires :
   `calibration_verdict` rend `{"conclusive": ..., "montrable": ...}`,
   `calibration_progression` rend `{"corrige": ...}`, et la regle du depot est
   precisement que les interfaces les **lisent** sans jamais les recalculer.
   Ces booleens etaient donc entierement hors de portee de cet outil -- et
   c'etait la regle de calibration, celle qui s'est deja corrigee six fois, qui
   vivait dans l'angle mort. Le defaut que l'outil traque etait dans l'outil.
   Trouve le 14 septembre 2026, en verifiant a la main une condition que l'outil
   disait couverte et qu'il n'avait jamais touchee.

   **L'angle mort sur les imbrications est ferme, et il etait pire qu'annonce.**
   Cette place disait qu'une ligne portant plusieurs `BoolOp` imbriques etait
   ignoree, et demandait au prochain lecteur de mesurer `calibration_verdict
   ['montrable']` a la main. C'etait vrai de la forme 5 seule. Les formes 3 et 4
   affirmaient la meme prudence sans l'appliquer : elles ne regardaient que le
   `BoolOp` de tete -- le test d'un `if`, la valeur d'un `return` -- et ne voyaient
   donc jamais les imbriques. Elles ne sautaient rien : elles annoncaient une
   moitie et le transformateur, qui visait la ligne, en neutralisait une autre.

   Mesure le 14 septembre 2026 sur `GlobalDecisionReport.requires_human`, celui-la
   meme dont la forme 4 se reclame : trois de ses cinq raisons annoncees comme
   mesurees ne l'etaient pas, et une passe entiere de la frontiere a ete triee sur
   ces etiquettes. La clef porte desormais la colonne du `BoolOp`, l'etiquette
   porte le texte de l'operande, et les trois formes descendent dans les
   imbrications au lieu de les confondre ou de les sauter.
   `tests/test_l_outil_de_mesure.py` tient le temoin : deux `BoolOp` sur une meme
   ligne, et chacun doit recevoir exactement ce que son etiquette annonce.

**Un survivant du sous-ensemble n'est pas encore un survivant.** La sous-suite est
ciblee pour tenir en quelques secondes, donc elle ne couvre pas tout : le premier
refus que cet outil a denonce comme non prouve l'etait, par
`tests/test_outcome_ledger.py`, qui n'est pas dans la liste. Chaque survivant du
sous-ensemble est donc **reverifie contre la suite entiere** avant d'etre annonce,
et l'outil distingue les deux cas. Il ment alors dans le sens alarmant plutot que
dans le sens rassurant, ce qui est le bon sens pour un instrument de mesure.

Le sous-ensemble reste etroit expres, et c'est un arbitrage mesure : un faux
positif coute une passe de la suite entiere, et elargir le sous-ensemble aux
fichiers qui touchent ces modules coute quelques secondes **par mutant**, soit
autant. Elargir ne ferait donc pas gagner de temps -- ca rendrait seulement la
passe rapide plus lente. Ce qui rend l'outil juste est la confirmation, pas la
largeur du sous-ensemble.

**Le tri va plus vite avec ce principe, trouve le 14 septembre 2026 en triant
une soixantaine de survivants de la frontiere.** `verify()` reconstruit tout ce
que la decision porte en elle -- rapport, gouverneur, politique, contrat,
capacite, cible du fournisseur. Donc tout refus de la frontiere qui **relit un
champ de la decision** est une assurance : une decision qui le violerait aurait
une autre empreinte et serait refusee a la porte. Les refus qui comptent sont
ceux qui comparent la decision a l'**etat durable d'aujourd'hui** -- le contrat
relu en base, la gouvernance recalculee, la capacite reinscrite -- parce que
`verify()` ne peut rien savoir de ce qui a change depuis.

Les trois vrais trous de ce jour-la sont tous de la seconde famille, et tous sur
le chemin de la reconciliation : derive de gouvernance, contrat retrograde,
interdiction arrivee apres coup. Les huit refus de `validated_execution.py`
nommes le meme jour sont tous de la premiere.

**Un survivant confirme est une question, pas un defaut.** Cinq reponses
possibles, et il faut choisir la bonne avant d'ecrire une ligne :

1. *Le refus est atteignable et personne ne l'essaie.* C'est un trou. Ecris le
   test. La reconciliation etait dans ce cas : la substitution de fournisseur,
   d'operation et de charge etait testee a l'aller et pas au retour, alors que la
   reconciliation atteint le meme fournisseur et peut faire passer une execution
   a COMPLETED.

   `is_shared_memory_target` l'etait aussi, et sous la forme la plus sournoise :
   un test existait et couvrait **aucune** des deux moities. Ses trois cas
   passaient a l'identique avec l'une ou l'autre remplacee par `True`. Ce que la
   condition decide n'est pourtant pas cosmetique -- une base prise pour une base
   en memoire vit en RAM et s'ancre pour la duree du processus, donc le journal
   s'ecrirait et se relirait normalement sans que rien n'atteigne le disque.
   Corrige le 14 septembre 2026 : un `file:` qui n'est pas en memoire, et un
   chemin de disque qui contient les mots.
2. *Le refus ne peut pas se declencher parce qu'un controle anterieur le couvre.*
   La plupart des refus de `validated_execution.py` sont dans ce cas : une
   decision qui les violerait a une empreinte differente, donc `verify()` la
   refuse avant. Ce sont des assurances, pas des trous. Leur ecrire un test
   demanderait de desactiver `verify()`, donc de tester un chemin qui n'existe
   pas -- ce que la regle 18 du depot appelle un test suspect.

   Les deux `if ecrit.rowcount != 1` du journal -- dans `resolve()` et
   `abandon()` -- sont dans ce cas, et c'est ecrit ici pour que le prochain
   passage ne refasse pas le triage. `BEGIN IMMEDIATE` prend le verrou d'ecriture
   avant le SELECT, donc aucune autre connexion ne peut changer la ligne entre
   le SELECT et l'UPDATE, et le `AND status=OPEN` de l'UPDATE vise exactement la
   ligne qu'on vient de lire ouverte. Le refus est la pour le jour ou la course
   se rouvrirait par un autre chemin -- ce que son propre commentaire annonce.
   L'atteindre demanderait de defaire le verrou, donc de tester un chemin qui
   n'existe pas.

   La famille `action is None` de `singular/execution.py` -- aux trois portes,
   plus les deux liaisons contrat et capacite qui la suivent -- est dans ce cas
   aussi, et c'est ecrit ici pour qu'on ne refasse pas le triage. `verify()`
   reconstruit chacune de ces proprietes avant que l'execution commence :
   « global report and governor must target authorized actions », la boucle qui
   exige que chaque action autorisee porte l'identifiant du contrat, et le
   controle que l'action selectionnee porte la capacite validee. Une decision
   qui violerait l'un des trois est refusee a la porte.

   **La branche ESCALATE de `_validate_governance` est dans ce cas, et elle vaut
   pour cinq survivants d'un coup** -- `approval_id` vide, approbation non
   APPROVED, aux deux endroits, et la liaison d'identite de `_validate_approval_
   binding`. Ces refus peuvent bien se declencher, mais leur **succes** ne peut
   jamais produire une execution : `ValidatedTrajectoryDecision._validate` exige
   `governor.mode in {EXECUTE_REVERSIBLE, EXECUTE_AUTHORIZED}` -- « governor
   decision must explicitly authorize execution », tenu par
   `tests/test_global_verdict_human_review.py` -- donc aucune decision valide ne
   scelle un gouverneur ESCALATE. Et les deux portes validees comparent
   `governed.governor != decision.governor` juste apres avoir autorise. Si la
   gouvernance du jour escalade, les modes different et l'execution est refusee
   la, que la branche ait laisse passer ou non. Les neutraliser ne peut donc
   changer aucun resultat.

   Le controle voisin, lui, n'est pas une assurance : `_validate_approval_binding`
   compare le magasin natif au magasin **legacy**, et une divergence entre les
   deux ne serait vue par rien d'autre. Elle reste hors de portee tant que la
   branche ESCALATE l'est ; c'est une raison d'en retirer un jour le chemin
   legacy, pas d'ecrire un test qui desactiverait la porte pour y arriver.

   Meme chose pour `mode == Autonomy.BLOCK` : les trois facons de produire un
   BLOCK que le depot sait produire -- politique, red team, bus -- rendent toutes
   `can_prepare=False`, donc la moitie voisine refuse deja. `v32_governed_core`
   a bien un chemin qui rendrait BLOCK avec `can_prepare=True`, mais rien ne le
   nourrit ; la moitie est masquee, pas morte.

   Ce triage-la a ete **attaque avant d'etre ecrit**, parce qu'un raisonnement
   qui conclut « inatteignable » est exactement le genre de raisonnement qu'on
   aime trop. Six `resolve()` concurrents sur la meme entree : un passe, les cinq
   autres tombent sur le `status != OPEN` d'avant. Une ecriture brute par une
   autre connexion entre deux transactions : le `resolve()` suivant tombe encore
   sur ce meme controle. Les deux chemins atteignent le garde anterieur, jamais
   le `rowcount`.
3. *La moitie est morte.* Ni trou ni assurance : aucune entree ne peut la
   distinguer de sa voisine, donc elle ne decide jamais. `store is None` a cote de
   `not hasattr(store, "path")` -- `hasattr(None, "path")` est faux de toute
   facon. `rows is not None` apres un `SELECT COUNT(*)`, qui rend toujours une
   ligne. Celles-la se retirent : elles laissent croire que deux cas sont couverts
   quand un seul l'est, et elles reviennent dans chaque rapport. Trois trouvees le
   13 septembre 2026, dans trois modules differents.

   La troisieme a declenche la regle du troisieme passage :
   `tests/test_moitie_morte.py` refuse desormais la forme la plus commune de cette
   famille -- `X is None` a cote de `X != Y`, et sa symetrique sous un `and` --
   dans tout le Python du depot. Cet outil ne devrait donc plus la rencontrer ;
   s'il la nomme, c'est que le garde a ete contourne, pas que le triage est a
   refaire.
4. *Deux refus qui se couvrent l'un l'autre.* Ni trou, ni assurance, ni moitie
   morte : deux gardes sur le meme chemin dont **chacun suffit seul**. Cet outil
   mute un refus a la fois, donc il ne peut par construction en tuer aucun des
   deux, et il les nommera tous les deux a chaque passage.

   Les deux refus de l'effet ambigu en sont l'exemple, et c'est mesure :
   `effects.py` refuse de reexecuter un effet UNKNOWN au debut d'`execute`, puis
   une seconde fois quand la revendication echoue et qu'on relit l'etat.
   Neutraliser l'un ou l'autre laisse la suite verte ; neutraliser **les deux**
   la fait echouer. La garantie que le README annonce -- « on resout en demandant
   au fournisseur, jamais en reessayant » -- est donc bien tenue par un test ;
   c'est la paire qui porte, pas chaque ligne.

   Ne cherche pas a isoler l'un des deux : ici c'est impossible, la revendication
   ne peut pas reussir sur un effet UNKNOWN. Verifie que la suite echoue quand
   les deux tombent, ecris-le, et passe au suivant.

5. *Le refus ne peut pas se declencher parce que rien ne produit son entree.*
   Les quatre refus lies a l'approbation humaine sont dans ce cas : une decision
   validee ne peut pas porter ESCALATE, donc aucune execution escaladee n'atteint
   la frontiere. C'est ce que le README annonce -- « human approval is currently
   not an authorization channel » -- et cet outil le mesure au lieu de le croire.

Il ne tourne pas dans le CI, et **« une dizaine de minutes par groupe » etait
faux**. Ce que ca coute vraiment, mesure le 14 septembre 2026 : le prix est
domine par le nombre de survivants, parce que chacun est reverifie contre la
suite entiere -- une passe complete chacun. `genesis` : cinq minutes sans
survivant, treize avec treize. `matins` : dix a quinze. `frontiere` : **plus
d'une heure, sans avoir fini** -- c'est le groupe le plus gros, et il est celui
qu'on veut le plus.

Deux consequences operatoires, payees une heure pour les apprendre :

* ne l'enferme pas dans un `timeout` court. Une heure ne suffit pas pour
  `frontiere` ;
* ne le passe pas dans un tube qui tamponne, `| tail` en tete. S'il est coupe,
  tu ne recois rien du tout -- pas meme les survivants deja nommes. Ecris dans un
  fichier et lis-le au fur et a mesure.

C'est un instrument d'audit, a relancer quand on touche a ce qu'il mesure.

    python3 tools/gardes_sans_test.py              # les trois groupes
    python3 tools/gardes_sans_test.py frontiere    # decision, autorisation, effet
    python3 tools/gardes_sans_test.py matins       # journal, saisie, Scout, Notice, Sage
    python3 tools/gardes_sans_test.py genesis      # missions, capacites, banc differentiel

**Trois groupes, parce que la priorite du depot est celle de la section 0 du
mandat** : ce qui tourne sans jeton passe avant ce qui en consomme. Le moteur
qu'il lance chaque matin s'en sort mieux que la frontiere -- c'est la partie la
mieux testee du depot -- et il avait quand meme des refus sans temoin, dont deux
gardes qui refusaient l'infini tape au clavier.

Le premier defaut trouve en lancant cet outil apres l'avoir ecrit etait dans
l'outil : sa sous-suite nommait un fichier de tests renomme entre-temps, donc
pytest refusait de collecter et chaque refus paraissait prouve. Un instrument de
mesure qui se trompe dans le sens rassurant est pire qu'aucun -- d'ou le controle
d'entree : si la sous-suite ne passe pas sans mutant, il s'arrete.

**L'outil mesure une copie, jamais l'arbre depuis lequel on commite.** Il ecrit
un garde sabote dans le fichier qu'il mesure ; tant que ce fichier etait celui du
depot, deux choses fausses etaient possibles, et les deux sont arrivees le meme
jour. Un `git status` montrant un garde neutralise au moment de committer -- c'est
un hook de sortie qui l'a rattrape, pas moi. Et un processus tue avant son
`finally`, qui laisse ce garde en place : le caveat « si le processus est tue,
`git checkout -- singular/` remet tout » demandait au prochain lecteur de se
souvenir d'une reparation. Une copie jetable rend les deux impossibles.

La copie porte ce que le depot suit **et** ce qui n'est pas ignore : on mesure donc
les temoins qu'on vient d'ecrire, pas seulement ceux du dernier commit -- c'est
tout l'usage de l'outil. Et c'est mesure, pas suppose : le paquet est installe en
editable, donc un finder de site-packages pointe vers l'arbre d'origine, mais
`python -m pytest` met son repertoire courant en tete de `sys.path` et la copie
gagne. `tests/test_l_outil_de_mesure.py` le verifie en sabotant dans la copie.
"""
from __future__ import annotations

import ast
import pathlib
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager

RACINE = pathlib.Path(__file__).resolve().parent.parent

#: Les modules qui portent la frontiere : decision, autorisation, execution, effet.
CIBLES_FRONTIERE = (
    "singular/execution.py",
    "singular/validated_execution.py",
    "singular/validated_trajectory_decision.py",
    "singular/decision_attestation.py",
    "singular/execution_capability.py",
    "singular/effects.py",
    # Le cycle d'apprentissage et le grand livre des resultats n'avaient jamais
    # ete mesures. Ils ne franchissent pas la frontiere, mais ils decident ce qui
    # s'active -- candidat, artefact, evaluation, approbation, activation -- et la
    # section 13 du mandat demande explicitement de verifier que l'artefact active
    # est bien celui qui a ete evalue. Un refus sans temoin y a la meme valeur
    # qu'ailleurs.
    "singular/improvement_registry.py",
    "singular/outcome_ledger.py",
    # Le socle : le bail, la revendication, les transitions de mission et la
    # machine de recuperation. C'est lui qui tient l'exactement-une-fois dont tout
    # le reste depend, et il n'avait jamais vu un mutant non plus.
    "singular/durable.py",
    "singular/mission_runtime.py",
    # Le producteur. `validated_pipeline.py` est le seul chemin par lequel une
    # `ValidatedTrajectoryDecision` existe : tout ce que la frontiere accepte sort
    # d'ici. Il n'etait mesure par rien, et sa porte d'entree n'etait verifiee
    # qu'en marchant droit. Les deux autres portent le resultat d'une execution et
    # la reconciliation d'un effet ; `execution_boundary_audit.py` compte deja
    # `reconciled_execution.py` parmi les fichiers de frontiere.
    "singular/validated_pipeline.py",
    "singular/execution_result.py",
    "singular/reconciled_execution.py",
    # La porte globale. Elle ne refuse rien -- elle rend un verdict et deux
    # proprietes, `can_prepare` et `requires_human`, que tout le reste lit. Les
    # trois premieres formes n'y trouvaient aucun mutant ; la quatrieme en trouve
    # sept, un par raison d'autoriser ou d'exiger un humain.
    "singular/global_control.py",
    # Le gouverneur : la couche d'autorisation elle-meme, que `_validate`
    # reconstruit et croit. Elle n'avait jamais vu un mutant.
    "singular/autopilot.py",
)

#: La sous-suite qui couvre ces modules. Ciblee exprès : la suite entiere est
#: trop longue, et il faut la relancer une fois par refus.
SOUS_SUITE_FRONTIERE = (
    "tests/test_validated_execution.py", "tests/test_validated_trajectory_decision.py",
    "tests/test_execution_bypass_resistance.py", "tests/test_validated_boundary_invariants.py",
    "tests/test_decision_execution_binding.py", "tests/test_validated_capability_binding.py",
    "tests/test_capability_durable_identity.py", "tests/test_capability_code_identity.py",
    "tests/test_capability_declared_identity.py", "tests/test_capability_registry_lifecycle.py",
    "tests/test_capability_field_separation.py", "tests/test_decision_attestation.py",
    "tests/test_adversarial.py", "tests/test_v47_adversarial_core.py",
    "tests/test_strict_execution_boundary_effects.py", "tests/test_effect_execution_boundary.py",
    "tests/test_execution_capability.py", "tests/test_effect_capability_time_of_use.py",
    "tests/test_effect_reconciliation_boundary.py", "tests/test_reconciliation_policy_drift.py",
    "tests/test_recovery_finalization.py", "tests/test_recovery_consistency.py",
    "tests/test_durable_execution.py", "tests/test_execution_boundary_audit.py",
    "tests/test_v34_execution.py", "tests/test_v39_effect_execution.py",
    "tests/test_v38_external_effects.py", "tests/test_v50_effect_races.py",
    "tests/test_validated_pipeline.py", "tests/test_validated_decision_service.py",
    "tests/test_approval_durability.py", "tests/test_no_raw_execution_call_sites.py",
    "tests/test_decision_serialization_guard.py", "tests/test_action_request_validation.py",
    "tests/test_refus_sans_temoin.py",
    # Ce qui couvre les deux modules d'apprentissage ajoutes aux cibles.
    "tests/test_improvement_registry.py", "tests/test_self_improvement.py",
    "tests/test_outcome_ledger.py", "tests/test_economic_learning_ledger.py",
    "tests/test_learning_review_queue.py", "tests/test_control_plane.py",
    # Et ce qui couvre le socle durable.
    "tests/test_v33_durable.py", "tests/test_v35_recovery.py",
    "tests/test_durable_audit.py", "tests/test_durable_integrity.py",
    "tests/test_durable_integrity_fail_closed.py", "tests/test_durable_integrity_lifecycle.py",
    "tests/test_durable_integrity_snapshot.py", "tests/test_audit_chain_growth.py",
    "tests/test_effect_recovery_integrity.py", "tests/test_recovery_completed_effect_routing.py",
    "tests/test_store_owns_its_transitions.py", "tests/test_governance_route_provenance.py",
    "tests/test_approval_immutability.py", "tests/test_ecriture_atomique.py",
    # Et ce qui couvre le producteur et les deux modules de resultat.
    "tests/test_global_verdict_human_review.py", "tests/test_validated_trajectory_decision.py",
    "tests/test_execution_result.py", "tests/test_reconciled_execution.py",
    # La porte globale et le gouverneur.
    "tests/test_global_control.py", "tests/test_autopilot.py", "tests/test_v33_governance.py",
    "tests/test_authority.py", "tests/test_commander_capacity.py",
)

#: Le moteur deterministe : ce qu'il lance chaque matin, sans jeton ni reseau.
CIBLES_MATINS = (
    "singular/journal.py",
    "singular/saisie.py",
    "singular/collecte.py",
    "singular/sage/notice.py",
    "singular/sage/server.py",
    "singular/fichiers.py",
    "singular/sqlite_support.py",
    "proto/suivi_candidatures.py",
)

SOUS_SUITE_MATINS = (
    "tests/test_journal.py", "tests/test_journal_business_fields.py",
    "tests/test_journal_concurrence.py", "tests/test_deux_journaux.py",
    "tests/test_le_journal_ecrit_seul.py", "tests/test_saisie_au_clavier.py",
    "tests/test_collecte.py", "tests/test_sage_notice.py", "tests/test_notice_business.py",
    "tests/test_sage_server.py", "tests/test_sage_web_client.py", "tests/test_sage_isolation.py",
    "tests/test_sage_independence.py", "tests/test_ecriture_atomique.py",
    "tests/test_sqlite_location.py", "tests/test_review_se_lit.py",
    "tests/test_reproche_premature.py", "tests/test_proto_suivi.py",
    "tests/test_etat_en_francais.py", "tests/test_notice_vectors.py",
    "tests/test_une_seule_regle_par_phrase.py", "tests/test_commandes_de_sa_fenetre.py",
    "tests/test_messages_recopies.py", "tests/test_windows_console.py",
    # La calibration datee. Sans elle, l'outil annoncait « sous-suite trop
    # etroite » sur les conditions de `corrige` : elles etaient couvertes, mais
    # par un fichier que la passe rapide ne lancait pas, donc chacune coutait une
    # passe complete pour rien.
    "tests/test_calibration_datee.py",
)

#: L'experience Genesis. Elle ne tourne pas les matins et ne touche pas la
#: frontiere, donc elle n'a sa place dans aucun des deux groupes -- et elle a
#: quand meme besoin d'etre mesuree ici, plus qu'eux : tout ce qu'elle affirme
#: repose sur ce qu'elle refuse. Un banc differentiel dont un refus n'a pas de
#: temoin ne mesure plus que sa propre complaisance, et son chiffre positif ne
#: vaut plus rien.
CIBLES_GENESIS = (
    "singular/genesis/bench.py",
    "singular/genesis/capability.py",
    "singular/genesis/mission.py",
    "singular/genesis/missions.py",
    "singular/genesis/lecteurs.py",
)

SOUS_SUITE_GENESIS = (
    "tests/test_genesis.py", "tests/test_genesis_isolation.py",
)

GROUPES = {
    "frontiere": (CIBLES_FRONTIERE, SOUS_SUITE_FRONTIERE),
    "matins": (CIBLES_MATINS, SOUS_SUITE_MATINS),
    "genesis": (CIBLES_GENESIS, SOUS_SUITE_GENESIS),
}

#: Les exceptions qui disent « refuse ». Une `KeyError` ou une `AttributeError`
#: n'est pas un refus, c'est un accident -- on ne les mute pas.
REFUS = frozenset({"PermissionError", "ValueError", "RuntimeError", "TypeError"})


class RendUneMoitieFausse(ast.NodeTransformer):
    """Neutralise **une** moitie d'un garde compose, en laissant l'autre garder.

    L'element neutre depend de l'operateur : `a or False` vaut `a`, `a and True`
    vaut `a`. Remplacer par la mauvaise constante ferait un mutant qui ne mesure
    rien -- `a or True` refuse toujours, `a and False` ne refuse jamais.

    **La clef porte la colonne, pas seulement la ligne.** Une ligne peut porter
    plusieurs `BoolOp` -- `a or b or (c and d)` en porte deux -- et `generic_visit`
    visite les enfants avant leur parent : viser « la ligne 45 » mutait donc le
    `and` imbrique en croyant muter le `or` exterieur. Le rapport nommait une
    moitie et en neutralisait une autre, et les deux premieres moities du `or`
    n'etaient jamais mutees du tout. Mesure sur
    `GlobalDecisionReport.requires_human`, l'exemple meme dont cet outil se
    reclame : trois de ses cinq raisons annoncees comme mesurees ne l'etaient pas.
    La colonne distingue deux `BoolOp` d'une meme ligne ; l'etiquette porte en
    plus le texte de l'operande, pour qu'un mauvais ciblage se voie.
    """

    def __init__(self, clef: tuple[int, int, int]) -> None:
        self.ligne, self.colonne, self.index = clef
        self.touche = False

    def visit_BoolOp(self, node: ast.BoolOp) -> ast.BoolOp:
        self.generic_visit(node)
        vise = node.lineno == self.ligne and node.col_offset == self.colonne
        if vise and self.index < len(node.values) and not self.touche:
            neutre = isinstance(node.op, ast.And)
            node.values[self.index] = ast.Constant(value=neutre)
            self.touche = True
        return node


class RendLeRefusVrai(ast.NodeTransformer):
    """`return False` -> `return True` : le refus cesse de refuser, sans rien lever.

    C'est la forme fail-open : la fonction repond « oui » la ou elle repondait
    « non », et l'appelant qui s'y fiait laisse passer. Aucune exception, aucune
    trace -- le seul temoin possible est un test qui attendait `False`.
    """

    def __init__(self, ligne: int) -> None:
        self.ligne = ligne
        self.touche = False

    def visit_Return(self, node: ast.Return) -> ast.Return:
        if (node.lineno == self.ligne and isinstance(node.value, ast.Constant)
                and node.value.value is False):
            node.value = ast.Constant(value=True)
            self.touche = True
        return node


class RendLaConditionFausse(ast.NodeTransformer):
    def __init__(self, ligne: int) -> None:
        self.ligne = ligne
        self.touche = False

    def visit_If(self, node: ast.If) -> ast.If:
        self.generic_visit(node)
        if node.test.lineno == self.ligne and not node.orelse:
            node.test = ast.Constant(value=False)
            self.touche = True
        return node


def refus_d_un_fichier(arbre: ast.AST) -> list[tuple[int, str]]:
    """Les `if <condition>: raise <refus>` d'un module, par ligne de condition."""
    trouves = []
    for noeud in ast.walk(arbre):
        if not isinstance(noeud, ast.If) or noeud.orelse:
            continue
        if len(noeud.body) != 1 or not isinstance(noeud.body[0], ast.Raise):
            continue
        leve = noeud.body[0].exc
        nom = ""
        if isinstance(leve, ast.Call):
            nom = getattr(leve.func, "id", "") or getattr(leve.func, "attr", "")
        if nom in REFUS:
            trouves.append((noeud.test.lineno, nom))
    return trouves


def refus_booleens_d_un_fichier(arbre: ast.AST) -> list[tuple[int, str]]:
    """Les `return False` des fonctions annotees `-> bool`, par ligne.

    L'annotation est le critere, et c'est deliberement etroit : une fonction qui
    declare rendre un booleen declare etre un predicat. Une qui rend `False` sans
    l'annoncer peut rendre autre chose ailleurs, et muter son refus ne dirait pas
    la meme chose.
    """
    trouves = []
    for noeud in ast.walk(arbre):
        if not isinstance(noeud, ast.FunctionDef):
            continue
        if not (isinstance(noeud.returns, ast.Name) and noeud.returns.id == "bool"):
            continue
        for interne in ast.walk(noeud):
            if (isinstance(interne, ast.Return) and isinstance(interne.value, ast.Constant)
                    and interne.value.value is False):
                trouves.append((interne.lineno, f"return False ({noeud.name})"))
    return trouves


def _operande(valeur: ast.expr) -> str:
    """Le texte de la moitie neutralisee, pour que l'etiquette ne puisse pas mentir.

    Une etiquette qui ne dit que « moitie 2 » oblige a recompter les operandes a
    la main, et un mauvais ciblage passe alors inapercu -- c'est exactement ce qui
    est arrive. Le texte de l'operande rend la verification immediate.
    """
    texte = ast.unparse(valeur).replace("\n", " ")
    return texte if len(texte) <= 60 else texte[:57] + "..."


def _boolops(racine: ast.expr) -> list[ast.BoolOp]:
    """Tous les `BoolOp` d'une expression, imbriques compris, du plus externe au plus interne."""
    return [noeud for noeud in ast.walk(racine) if isinstance(noeud, ast.BoolOp)]


def moities_d_un_fichier(arbre: ast.AST) -> list[tuple[tuple[int, int, int], str]]:
    """Chaque moitie d'un garde compose, par (ligne, colonne, rang de la moitie).

    La clef portait autrefois la seule ligne, et sautait les lignes ambigues. Les
    deux choix etaient faux : une ligne peut porter plusieurs `BoolOp` imbriques,
    que cette forme ne voyait meme pas -- elle ne regardait que le `BoolOp` de tete
    -- donc elle ne sautait rien et laissait le transformateur muter l'imbrique a la
    place de celui qu'elle annoncait. La colonne les distingue, et l'imbrique
    devient mesurable au lieu d'etre confondu ou saute.
    """
    trouves = []
    for noeud in ast.walk(arbre):
        if not isinstance(noeud, ast.If) or noeud.orelse or len(noeud.body) != 1:
            continue
        if not isinstance(noeud.body[0], ast.Raise):
            continue
        leve = noeud.body[0].exc
        nom = ""
        if isinstance(leve, ast.Call):
            nom = getattr(leve.func, "id", "") or getattr(leve.func, "attr", "")
        if nom not in REFUS or not isinstance(noeud.test, ast.BoolOp):
            continue
        for boolop in _boolops(noeud.test):
            operateur = "and" if isinstance(boolop.op, ast.And) else "or"
            for index, valeur in enumerate(boolop.values):
                trouves.append(((boolop.lineno, boolop.col_offset, index),
                                f"moitie {index + 1} du {operateur} :: {_operande(valeur)}"))
    return sorted(trouves)


def moities_rendues_d_un_fichier(arbre: ast.AST) -> list[tuple[tuple[int, int], str]]:
    """Chaque moitie d'un booleen **rendu** par un predicat, par (ligne, rang).

    Les trois premieres formes ne savent voir que ce qui refuse : un `raise`, un
    `return False`. Elles ne trouvent donc rien dans les modules qui **decident** --
    `global_control.py`, `security.py`, `v32_governed_core.py` n'ont pas un seul
    garde mutable, et c'est mesure, pas suppose. Ces modules ne refusent pas : ils
    rendent un verdict que les autres lisent, et un verdict faux est plus grave
    qu'un refus manquant.

    `GlobalDecisionReport.requires_human` en est l'exemple exact : cinq raisons
    reliees par des `or`, chacune une facon differente d'exiger un humain. Si une
    seule n'est prouvee par aucun test, toute une categorie peut cesser d'exiger un
    humain sans que rien ne rougisse.

    Le critere est le meme que pour la forme 2, et pour la meme raison : une
    fonction annotee `-> bool` declare etre un predicat. Une propriete compte, c'est
    une fonction annotee comme les autres.
    """
    trouves = []
    for noeud in ast.walk(arbre):
        if not isinstance(noeud, ast.FunctionDef):
            continue
        if not (isinstance(noeud.returns, ast.Name) and noeud.returns.id == "bool"):
            continue
        for interne in ast.walk(noeud):
            if not (isinstance(interne, ast.Return) and isinstance(interne.value, ast.BoolOp)):
                continue
            for boolop in _boolops(interne.value):
                operateur = "and" if isinstance(boolop.op, ast.And) else "or"
                for index, valeur in enumerate(boolop.values):
                    trouves.append(((boolop.lineno, boolop.col_offset, index),
                                    f"moitie {index + 1} du {operateur} rendu ({noeud.name})"
                                    f" :: {_operande(valeur)}"))
    return sorted(trouves)


def moities_d_un_verdict_en_dictionnaire(arbre: ast.AST) -> list[tuple[tuple[int, int], str]]:
    """Forme 5 : une moitie d'un booleen rendu **dans un dictionnaire**.

    Les quatre premieres formes ne voient un verdict que s'il est rendu tout nu,
    par une fonction annotee `-> bool`. Or ce depot construit ses verdicts les
    plus lus dans des dictionnaires : `calibration_verdict` rend
    `{"conclusive": ..., "montrable": ...}`, `calibration_progression` rend
    `{"corrige": ...}`, et toutes les interfaces les lisent sans jamais les
    recalculer -- c'est meme la regle du depot qu'elles ne les recalculent pas.

    Ces booleens-la etaient donc **entierement hors de portee de cet outil**, et
    c'est la regle de calibration, celle qui s'est deja corrigee six fois, qui
    vivait dans l'angle mort. Le defaut que l'outil traque etait dans l'outil.

    Cette forme etait la seule a voir les imbrications, et elle les sautait :
    l'etiquette aurait ete ambigue, parce que le transformateur visait une ligne et
    visite les enfants avant leur parent. La clef porte maintenant la colonne, donc
    l'ambiguite n'existe plus et rien n'est saute -- `calibration_verdict
    ['montrable']`, un `and` dans un `or`, redevient mesurable.
    """
    trouves = []
    for noeud in ast.walk(arbre):
        if not isinstance(noeud, ast.FunctionDef):
            continue
        for interne in ast.walk(noeud):
            if not (isinstance(interne, ast.Return) and isinstance(interne.value, ast.Dict)):
                continue
            for clef, valeur in zip(interne.value.keys, interne.value.values, strict=False):
                etiquette = clef.value if isinstance(clef, ast.Constant) else "?"
                for boolop in _boolops(valeur):
                    operateur = "and" if isinstance(boolop.op, ast.And) else "or"
                    for index, operande in enumerate(boolop.values):
                        trouves.append((
                            (boolop.lineno, boolop.col_offset, index),
                            f"moitie {index + 1} du {operateur} en dictionnaire "
                            f"({noeud.name}[{etiquette!r}]) :: {_operande(operande)}"))
    return sorted(trouves)


#: Chaque forme de refus : ce qui la trouve, ce qui la neutralise.
FORMES = (
    (refus_d_un_fichier, RendLaConditionFausse),
    (refus_booleens_d_un_fichier, RendLeRefusVrai),
    (moities_d_un_fichier, RendUneMoitieFausse),
    (moities_rendues_d_un_fichier, RendUneMoitieFausse),
    (moities_d_un_verdict_en_dictionnaire, RendUneMoitieFausse),
)


def fichiers_a_copier(racine: pathlib.Path = RACINE) -> tuple[str, ...]:
    """Ce que le depot suit, plus ce qui n'est ni suivi ni ignore.

    Les deux, parce qu'un audit lance avant de committer doit mesurer les temoins
    qu'on vient d'ecrire. Ce que `.gitignore` couvre est laisse dehors : bases
    SQLite de travail, caches, environnements.
    """
    acheve = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        capture_output=True, text=True, cwd=racine, check=True,
    )
    return tuple(nom for nom in acheve.stdout.split("\0") if nom)


@contextmanager
def copie_a_mesurer(racine: pathlib.Path = RACINE) -> Iterator[pathlib.Path]:
    """Un depot jetable, identique a celui-ci, ou l'on peut saboter sans rien risquer."""
    with tempfile.TemporaryDirectory(prefix="gardes-") as dossier:
        copie = pathlib.Path(dossier) / "depot"
        for relatif in fichiers_a_copier(racine):
            source = racine / relatif
            if not source.is_file():
                continue
            cible = copie / relatif
            cible.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, cible)
        yield copie


def _la_sous_suite_passe(sous_suite: tuple[str, ...], racine: pathlib.Path = RACINE) -> bool:
    acheve = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider",
         "-p", "no:randomly", *sous_suite],
        capture_output=True, text=True, cwd=racine, check=False,
    )
    return acheve.returncode == 0


def _la_suite_entiere_passe(racine: pathlib.Path = RACINE) -> bool:
    """Le juge de derniere instance. Lent -- on ne l'appelle que sur un survivant."""
    acheve = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", "-p", "no:randomly"],
        capture_output=True, text=True, cwd=racine, check=False,
    )
    return acheve.returncode == 0


#: Les racines dont la suite entiere a deja ete jugee utilisable, pour ne pas
#: payer deux fois la meme passe quand on demande les deux groupes.
_JUGES_VERIFIES: set[pathlib.Path] = set()


def _le_juge_est_utilisable(racine: pathlib.Path = RACINE) -> bool:
    """La suite entiere doit passer SANS mutant, sinon rien ne peut etre confirme.

    Le controle d'entree ne portait que sur la sous-suite, et ca ne suffit pas :
    si la suite entiere est deja rouge, chaque survivant du sous-ensemble est
    annonce comme un faux positif et l'outil devient aveugle dans le sens
    rassurant -- il dit « rien a signaler » en ne mesurant plus rien.

    C'est arrive le jour meme ou la copie jetable a ete introduite : les tests de
    l'outil appellent `git ls-files`, la copie n'est pas un depot git, donc les
    trois tests de la copie echouaient **dans la copie**. Une passe entiere de
    soixante-douze mutants a ete rendue sans valeur, et rien ne le disait. Ce
    controle le dit maintenant, et refuse de mesurer.
    """
    if racine in _JUGES_VERIFIES:
        return True
    if not _la_suite_entiere_passe(racine):
        return False
    _JUGES_VERIFIES.add(racine)
    return True


def _un_groupe(nom: str, racine: pathlib.Path = RACINE) -> int:
    """Les refus survivants d'un groupe. Rend leur nombre, ou -1 si rien n'a pu etre mesure."""
    cibles, sous_suite = GROUPES[nom]
    print(f"--- {nom} ---", flush=True)
    if not _la_sous_suite_passe(sous_suite, racine):
        print(f"la sous-suite de « {nom} » echoue deja sans mutant : rien a mesurer",
              file=sys.stderr)
        return -1
    if not _le_juge_est_utilisable(racine):
        print("la suite entiere echoue deja sans mutant : aucun survivant ne pourrait "
              "etre confirme, donc rien n'est mesure", file=sys.stderr)
        return -1
    survivants = 0
    total = 0
    for cible in cibles:
        chemin = racine / cible
        original = chemin.read_text(encoding="utf-8")
        lignes = original.split("\n")
        try:
            trouves = [(clef, refus, transformateur)
                       for collecteur, transformateur in FORMES
                       for clef, refus in collecteur(ast.parse(original))]
            for clef, refus, transformateur in trouves:
                total += 1
                ligne = clef[0] if isinstance(clef, tuple) else clef
                mutant = transformateur(clef)
                arbre = mutant.visit(ast.parse(original))
                if not mutant.touche:
                    continue
                ast.fix_missing_locations(arbre)
                chemin.write_text(ast.unparse(arbre), encoding="utf-8")
                if _la_sous_suite_passe(sous_suite, racine):
                    ou = f"{cible}:{ligne}  {refus}  {lignes[ligne - 1].strip()[:90]}"
                    if _la_suite_entiere_passe(racine):
                        survivants += 1
                        print(f"SURVIT  {ou}", flush=True)
                    else:
                        print(f"(sous-suite trop etroite)  {ou}", flush=True)
                chemin.write_text(original, encoding="utf-8")
        finally:
            chemin.write_text(original, encoding="utf-8")
    print(f"\n{nom} : {survivants} refus survivant(s) sur {total} mutes\n")
    return survivants


def main(arguments: list[str] | None = None) -> int:
    demandes = arguments if arguments else list(GROUPES)
    inconnus = [nom for nom in demandes if nom not in GROUPES]
    if inconnus:
        # « Les deux » etait ecrit en toutes lettres a cote d'une liste qui en
        # contient trois. Le message se compte lui-meme maintenant.
        print(f"groupe inconnu : {', '.join(inconnus)}. Les {len(GROUPES)} : "
              f"{', '.join(GROUPES)}.",
              file=sys.stderr)
        return 2
    with copie_a_mesurer() as copie:
        print(f"mesure dans une copie jetable : {copie}", flush=True)
        return 2 if any(_un_groupe(nom, copie) < 0 for nom in demandes) else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
