# Prototype jetable — suivi de candidatures

Un fichier, `suivi_candidatures.py`. Bibliothèque standard seule, aucun
`pip install`, aucune clé d'API, aucun réseau. Rien ici n'appartient à
l'architecture de SINGULAR : pas de couches, pas de frontière d'exécution.
C'est fait pour être supprimé si une semaine d'usage ne prouve pas que ça sert.

## Sur l'iPhone — sans PC, sans serveur, sans wifi particulier

C'est le chemin principal : contrairement au Sage, ce script n'a besoin de rien
d'autre que du téléphone. Installe **a-Shell** (gratuit, App Store) : un
terminal avec Python 3 intégré, tout tourne en local.

Une seule fois, dans a-Shell — le script est un fichier autonome, inutile de
cloner le dépôt :

```
curl -O https://raw.githubusercontent.com/SLENDER66/SINGULAR/claude/remote-control-feedback-ndpzle/proto/suivi_candidatures.py
```

Puis chaque matin, une seule ligne :

```
python suivi_candidatures.py
```

Il affiche où tu en es, puis **une** action pour aujourd'hui. Puis un menu à un
chiffre : `1` ajouter, `2` changer un statut, `3` noter, `4` le CV, `5` tout
voir, `6` préparer une question pour Claude, `0` quitter.

Tes données restent sur le téléphone, dans `~/.singular/candidatures.json`.
Pour les relire ou les sauvegarder : `cat ~/.singular/candidatures.json`.

Pour n'avoir qu'un geste : ouvre l'app **Raccourcis**, crée un raccourci qui
ouvre a-Shell, et pose-le sur ton écran d'accueil.

Pour reprendre une version plus récente du script, relance la même commande
`curl` : elle écrase le fichier, jamais tes données.

**Ce que je n'ai pas pu vérifier d'ici :** ni App Store, ni iPhone. Le
téléchargement par `curl` et l'exécution du fichier seul sont testés dans mon
environnement, mais qu'a-Shell fournisse bien `curl` et `python` ne l'est pas.
Si l'une des deux lignes ne passe pas, envoie-moi le message d'erreur.

## Sur le PC — si tu y as accès

Appuie sur **Échap** avant de coller (PowerShell fusionne les lignes collées).

```powershell
cd $HOME\Documents\SINGULAR; python proto\suivi_candidatures.py
```

Tes données vont alors dans `C:\Users\Utilisateur\.singular\candidatures.json`,
le même dossier que `journal.db`.

**Les deux copies ne se parlent pas.** Le fichier du téléphone et celui du PC
sont deux fichiers séparés : tiens-toi à un seul des deux, sinon tu auras deux
suivis divergents. Tant que le PC n'est pas accessible, c'est le téléphone.

## Le Sage, lui, a besoin du PC

`python -m singular sage --lan` sert l'app web depuis le PC : sans PC allumé et
sans le même wifi, le Sage n'est pas joignable. Ce prototype-ci ne dépend pas
de lui et fonctionne seul.

## Ce que fait l'action du jour, et dans quel ordre

L'ordre est tout l'intérêt du script. Il ne donne jamais deux choses à faire.

1. **Un entretien décroché** — tout le reste attend.
2. **Une candidature préparée mais pas envoyée** depuis 2 jours.
3. **Une candidature sans réponse** depuis 10 jours : relancer.
4. **Une relance sans réponse** depuis 14 jours : classer sans suite.
5. **Le CV pas fini** : l'étape suivante.
6. **Rien ajouté depuis 7 jours** : en ajouter une.

Le CV passe avant les nouvelles candidatures, et c'est délibéré : tu ne
candidates pas encore. Un outil qui te réclamerait des candidatures cette
semaine serait vide et agaçant, et ne t'aurait rien appris — c'est exactement
le reproche que le Sage t'a fait à tort le premier soir.

Les huit étapes du CV sont pré-remplies pour un profil qui **a déjà 2 ans de
bureau d'études** derrière lui, plus 5 ans de terrain Armée (chambre froide,
groupe électrogène, brûleur). Elles ont d'abord été écrites pour une
reconversion depuis le terrain : c'était faux, et le tableau de bord a propagé
l'erreur deux jours. Elles sont dans le fichier, en haut, avec le profil :
change-les si elles ne correspondent plus.

Tant qu'aucune étape n'est cochée, un changement de cette liste se propage
automatiquement à ton fichier de données. Dès que tu en coches une, ta liste
est figée : le travail déjà fait passe avant une liste à jour.

## Les délais

En haut du fichier, six lignes en majuscules. `JOURS_AVANT_RELANCE = 10` et les
autres. Si dix jours te semblent trop courts, change le chiffre.

## Le `6` : parler à Claude sans payer d'API

Ce script ne contient aucune IA et n'en contiendra pas. Le `6` fait autre
chose : il assemble un bloc de texte — qui tu es, où en sont tes candidatures,
ce qu'il reste à faire sur ton CV, ta question — que tu copies dans l'app
Claude, déjà installée et déjà comprise dans ton abonnement.

Ce n'est pas un pis-aller. Claude oublie tout d'une conversation à l'autre ;
ce fichier, non. Le seul travail que ferait une faculté « Analyse » branchée
sur l'API, c'est exactement ce transport-là — en coûtant 2,5 à 6 € par mois et
en demandant une clé d'API à saisir sur un téléphone.

Rien ne part de ton téléphone quand tu tapes `6` : le bloc s'affiche, c'est
tout. `tests/test_proto_suivi.py` vérifie cette phrase sur le code plutôt que
de la promettre — il refuse tout import capable d'ouvrir une connexion.

## Ce qu'il ne fait pas

Pas de mails, pas de rappels automatiques, pas de scraping d'annonces, pas de
modèle de langage. Si l'un de ces manques te gêne au bout d'une semaine, c'est
une information : c'est ça qu'on construira, et pas autre chose.
