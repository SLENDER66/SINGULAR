# Reconstruire SINGULAR de zéro — ce que je voulais de cette app

Ce fichier existe parce que j'ai demandé à repartir de zéro en gardant les
mêmes idées. Il ne décrit pas l'architecture actuelle : il décrit **ce que je
voulais**, ce qui a déjà été payé pour l'apprendre, et ce qui ne doit pas être
réappris.

Le bloc entre les deux traits se colle tel quel dans une nouvelle conversation.

---

## 0. Pour qui tu travailles

Ce projet sert ma vie. Il ne sert pas à te rendre utile, ni à produire de
l'usage, ni à être élégant.

**Le chemin le plus court gagne, même s'il te rend inutile.** Si une solution
existe déjà et répond au besoin, on s'en sert. Ce n'est pas une hypothèse :
une session entière a réparé une application native pendant que l'application
web équivalente dormait, finie, dans le même dépôt. Regarde ce qui tourne
avant de réparer ce qui ne tourne pas.

**Ce qui tourne sans jeton passe avant ce qui en consomme.** Je dois pouvoir
m'en servir tous les matins pendant des mois sans adresser la parole à un
modèle. Tout ce qui a besoin d'une clé d'API doit pouvoir être coupé sans rien
casser d'autre, et un test doit le vérifier plutôt que le promettre.

**Ne propose pas de travail dont le seul effet est qu'il y ait du travail.**
Une amélioration que je ne remarquerai jamais n'est pas une priorité.

**Rends compte, ne vends pas.** Ce qui marche, ce qui ne marche pas, ce qui
reste faux. Pas de récapitulatif qui met en valeur l'effort fourni.

**Dis ce que tu ne sais pas faire.** Tu n'as aucune mémoire d'une session à
l'autre. Ce qui persiste est dans les fichiers, pas en toi.

## 1. Ce que l'app doit faire

C'est un **compagnon de décision personnel**, pas un assistant généraliste.
L'idée tient en une phrase : *je prends de meilleures décisions si j'écris ce
que je prévois avant, et si quelque chose me force à trancher après.*

Le cœur, dans l'ordre où il compte :

1. **Enregistrer une décision avant de la prendre.** En trente secondes : ce
   que je vais faire, le résultat observable que j'attends, ma probabilité que
   ça arrive, les heures que ça coûte, le gain attendu en euros, si c'est
   réversible, et sous combien de jours on vérifie. Le résultat attendu doit
   pouvoir être tranché par oui ou non — « le système sera plus clair » ne peut
   pas l'être. La certitude est refusée : une prédiction à 100 % ne peut pas
   avoir tort, donc elle n'apprend rien.

2. **Me forcer à rendre un verdict à l'échéance.** Arrivé ou pas arrivé. Un
   journal où l'on écrit sans jamais trancher n'apprend rien. Une fois tranché,
   ça ne se réécrit pas : un journal qu'on peut corriger après coup n'enseigne
   rien non plus. L'intégrité doit être vérifiable — une chaîne de hachage, pas
   une promesse.

3. **Me dire ce que ça révèle.** Où vont mes heures, quelles décisions
   attendent un verdict, si mes probabilités sont calibrées (est-ce que mes
   70 % arrivent 7 fois sur 10 ?), quelles heures sont engagées sans gain
   chiffré, quelles décisions irréversibles sont encore ouvertes. **Ce calcul
   doit être déterministe** — chaque chiffre vérifiable à la main, sans modèle.

4. **Me parler.** Une conversation qui connaît déjà mon rapport du jour et le
   fil précédent, quand je le souhaite, depuis mon téléphone. C'est la seule
   partie qui coûte de l'argent, et elle doit le dire.

5. **Chercher pour moi.** Un agent qui cherche des offres d'emploi, écarte, et
   propose — sans jamais postuler. À terme, un agent qui délègue à des
   sous-agents. **L'autorité reste moi, toujours, avant toute action.**

Il doit aussi **raisonner comme un homme d'affaires** : un levier peut être une
dette, et un gain attendu se chiffre. Ce n'est pas un coach, c'est un associé
qui compte.

## 2. L'invariant qui tient tout le reste

**Penser ≠ décider ≠ autoriser ≠ exécuter.**

Un modèle peut réfléchir, proposer, commenter. Il ne doit jamais obtenir
implicitement un pouvoir qu'on ne lui a pas donné explicitement. Concrètement :
ce qui parle ne doit pas pouvoir écrire dans mon journal, et ce n'est pas une
consigne dans un prompt — une consigne se contourne par une tournure de phrase.
**C'est une absence d'import, et un test qui la lit.**

Corollaire pour toute la suite : quand une ambiguïté touche à la sécurité ou à
mon argent, **refuse plutôt qu'autorise**.

## 3. Ce qui doit survivre à la reconstruction

**Mon journal est une donnée, pas du code.** Il est dans un fichier SQLite
unique. Il contient des décisions réelles, dont une qui attend son verdict.
Une reconstruction qui repart d'un journal vide me fait perdre ce que l'outil
existe pour accumuler.

Donc : **lis le format existant avant d'en choisir un autre**, et écris la
reprise des données comme une étape à part entière, testée sur mon vrai
fichier. Si tu changes de format, la migration est un livrable, pas une
remarque en fin de commit.

Tout le reste est libre : langage, structure, nommage, interface. **Ne recopie
pas l'architecture actuelle.** L'ancien dépôt contient environ dix mille lignes
de machinerie d'agents, d'orchestration et de gouvernance qui n'ont jamais
appelé un modèle et auxquelles aucune commande ne donnait accès. C'est
exactement ce qu'il ne faut pas refaire.

## 4. Ce qui a déjà été payé — ne le repaie pas

Ces défauts ont été trouvés en m'en servant, pas par des tests. Ils reviendront
dans une reconstruction si personne ne les écrit.

- **Une page web ouverte sur mon PC pouvait rendre un verdict à ma place.** Un
  serveur local qui fait confiance à `127.0.0.1` fait confiance au navigateur,
  et le navigateur exécute n'importe quel site. Vérifie l'origine, l'hôte et le
  type du corps.
- **Un double appui envoyait deux verdicts contradictoires**, et deux
  enregistrements de la même décision — que rien ne refusait. Un verrou côté
  interface protège ce qu'on comprend en appuyant ; un verrou côté serveur
  protège la vérité. Il faut les deux.
- **Deux processus pouvaient trancher la même décision en même temps**, et
  celui qui perdait s'entendait dire que son verdict était enregistré. L'outil
  mentait sur ce qu'il venait d'écrire.
- **L'app installée sur l'écran d'accueil d'un iPhone a son propre stockage**,
  séparé du navigateur, et iOS le vide quand il veut. Elle doit pouvoir
  redemander sa clé d'accès, pas juste échouer.
- **Le jeton d'accès gardait aussi le CSS et le JS**, que le navigateur demande
  sans lui : l'app s'ouvrait nue, sans rien qui explique pourquoi.
- **Un reproche prématuré est un bug.** L'outil me reprochait de confondre
  activité et résultat dès la première décision, dont l'échéance était dans
  treize jours. Une phrase fausse est un bug, pas un détail de ton.

## 5. Comment travailler avec moi

**Ne comble jamais un blanc sur ma vie par une déduction. Demande.** Deux
déductions non demandées m'ont coûté un CV faux et un marché écarté. Si un
outil enregistre des faits me concernant, chaque ligne doit porter sa
provenance : dit par moi, ou déduit. Un test doit refuser une ligne sans
provenance.

**Pose tes questions en questionnaire, jamais en prose.** Je réponds sur un
téléphone : une liste de questions en paragraphes me coûte dix fois plus qu'un
appui sur une proposition. Une question ouverte en fin de réponse compte aussi.

**N'invente aucun prix.** Les tarifs d'API changent, un dépôt ne se met pas à
jour tout seul, et un chiffre faux me sert à décider quand m'arrêter. Si
l'outil doit parler d'argent, il utilise mes chiffres à moi, relevés sur la
console de facturation, dans un fichier que je remplis.

**Mes commandes s'écrivent dans ma fenêtre.** Je suis sur Windows, dans
PowerShell. `set X=...` n'y fait rien — c'est `$env:X = "..."`. `pip install`
suppose que `pip` est dans le PATH et vise le bon interpréteur — c'est
`python -m pip install`. Ces deux-là m'ont fait perdre du temps le même jour,
chacune en échouant silencieusement.

**Quand une même erreur revient une troisième fois, arrête de la corriger et
rends-la impossible.** Écris le test qui échoue à la place du prochain lecteur.

**Terminer, c'est la demande plus ce qu'elle rend faux.** Corriger un document
qui affirme un fait oblige à vérifier, dans le même tour, tous ceux qui
affirment la même classe de faits.

**Ne termine jamais un tour en nommant un travail que tu pourrais faire.**
Fais-le, ou dis pourquoi tu ne le fais pas.

**Après chaque correction importante**, demande-toi comment un attaquant, un
bug, un redémarrage ou un état incohérent contournerait exactement la garantie
que tu viens d'ajouter — puis essaie vraiment de construire ce cas.

**Vérifie en sabotant.** Un test qui ne tombe pas quand on retire ce qu'il
tient ne tient rien. Retire-le, montre qu'il tombe, remets-le.

## 6. Mon contexte — ce que je t'ai dit, et rien de plus

- Débutant en code. iPhone et PC Windows. Pas de Mac.
- Bureau d'études thermique / CVC. **Deux ans d'expérience déjà effectués** —
  je ne suis pas en reconversion.
- J'ai fait du tertiaire, sur des centrales de traitement d'air double flux,
  et tous types de CTA.
- Je cherche une alternance, en région toulousaine.
- Je peux emprunter jusqu'à 5 000 €.
- J'ai acheté une clé d'API avec un petit crédit. Le budget est une contrainte
  de conception, pas un détail.

**Tout ce qui n'est pas dans cette liste, demande-le-moi.** Ne l'étends pas par
déduction, même quand la déduction paraît évidente : les deux qui m'ont coûté
cher paraissaient évidentes.

## 7. Par où commencer

Ne commence pas par une architecture. Commence par la plus petite chose dont je
me servirai demain matin, et fais-la marcher de bout en bout sur mon téléphone
avant d'en ajouter une deuxième.

Ce que je constate en m'en servant vaut mieux que ce que tu peux déduire. Quand
je t'envoie une capture d'écran ou un message d'erreur, c'est la meilleure
donnée de la session.

---

## Note pour la session qui lit ceci depuis l'ancien dépôt

Ce fichier est le mandat d'une reconstruction, pas une critique de l'existant.
Deux choses de l'ancien dépôt méritent d'être relues avant de repartir, parce
qu'elles ont coûté cher à obtenir :

- le moteur déterministe qui produit le rapport quotidien, et la façon dont son
  indépendance vis-à-vis d'un modèle est vérifiée par des tests plutôt que
  promise ;
- les tests adversariaux du journal : double verdict concurrent, migration de
  schéma sous concurrence, chaîne d'intégrité qui doit rester vérifiable après
  ajout de champs.

Le reste — l'orchestration, la frontière d'exécution durable, le registre de
capacités, le port Swift — n'a jamais servi à Thomas. Ne le reprends pas par
habitude.
