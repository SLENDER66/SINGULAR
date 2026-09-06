# Prototype jetable — suivi de candidatures

Un fichier, `suivi_candidatures.py`. Bibliothèque standard seule, aucun
`pip install`, aucune clé d'API, aucun réseau. Rien ici n'appartient à
l'architecture de SINGULAR : pas de couches, pas de frontière d'exécution.
C'est fait pour être supprimé si une semaine d'usage ne prouve pas que ça sert.

## Sur le PC — une ligne, à coller telle quelle

Appuie sur **Échap** avant de coller (PowerShell fusionne les lignes collées).

```powershell
cd $HOME\Documents\SINGULAR; python proto\suivi_candidatures.py
```

Il affiche où tu en es, puis **une** action pour aujourd'hui. Puis un menu à un
chiffre : `1` ajouter, `2` changer un statut, `3` noter, `4` le CV, `5` tout
voir, `0` quitter.

Tes données vont dans `C:\Users\Utilisateur\.singular\candidatures.json` —
le même dossier que `journal.db`, donc la sauvegarde que tu fais déjà les
couvre toutes les deux.

## Sur l'iPhone

Le plus court chemin, et il ne demande ni PC allumé ni serveur : **a-Shell**,
gratuit sur l'App Store. C'est un terminal avec Python intégré, tout tourne sur
le téléphone, hors ligne.

Une fois installé, dans a-Shell :

```
lg2 clone https://github.com/SLENDER66/SINGULAR
```

Puis, chaque matin :

```
cd SINGULAR && python proto/suivi_candidatures.py
```

Pour n'avoir qu'un geste : ouvre l'app **Raccourcis**, crée un raccourci qui
ouvre a-Shell, et pose-le sur ton écran d'accueil à côté du Sage.

**Ce que je n'ai pas pu vérifier d'ici :** je n'ai pas accès à l'App Store ni à
un iPhone depuis cet environnement. a-Shell embarque bien Python 3 et `lg2`
(son git), mais si l'une de ces deux commandes ne passe pas chez toi, envoie-moi
le message d'erreur — c'est le genre de panne qui se corrige en une fois.

Le repli, si a-Shell te déplaît : le script tourne sur le PC, et le fichier
JSON est lisible tel quel. Rien ne t'y enferme.

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

Les huit étapes du CV sont pré-remplies pour le passage terrain vers bureau
d'études. Elles sont dans le fichier, en haut : change-les si elles ne
correspondent pas à ce que tu as à faire.

## Les délais

En haut du fichier, six lignes en majuscules. `JOURS_AVANT_RELANCE = 10` et les
autres. Si dix jours te semblent trop courts, change le chiffre.

## Ce qu'il ne fait pas

Pas de mails, pas de rappels automatiques, pas de scraping d'annonces, pas de
modèle de langage. Si l'un de ces manques te gêne au bout d'une semaine, c'est
une information : c'est ça qu'on construira, et pas autre chose.
