# Ce que je dois faire moi-même

Le Sage tourne et je m'en sers. Ce qui reste tient en deux gestes par
semaine, un clic sur GitHub, plus une chose qui attend un Mac et ne bloque
rien.

---

## Un clic sur GitHub, qui compte plus qu'il n'en a l'air

La branche par défaut du dépôt est restée en arrière. Ce n'est pas cosmétique :
chaque nouvelle conversation démarre depuis elle, donc sur un dépôt **sans le
Sage, sans `ios/`, et sur un `CLAUDE.md` d'avant la section 0** — celle qui
existe précisément pour ne plus jamais avoir à être réécrite. Ce n'est pas une
hypothèse : c'est arrivé le 6 septembre au soir, à la séance qui écrit ces
lignes.

Sur GitHub : **Settings > General > Default branch**, basculer sur la branche
que `CLAUDE.md` nomme comme branche de travail. Aucun commit n'est perdu.

La version précédente de ce fichier affirmait que c'était fait. Elle avait
tort, et rien ne pouvait la contredire : l'affirmation portait sur l'état d'un
serveur, pas sur le contenu du dépôt. D'où une commande plutôt qu'une phrase,
qui dit l'état réel et ne conclut jamais qu'elle n'a pas pu vérifier :

```powershell
cd $HOME\Documents\SINGULAR; python tools/check_repo_state.py
```

Elle liste aussi les branches qui traînent — dont celles que `CLAUDE.md`
déclare mortes, encore présentes. Les supprimer est ton choix ; ce fichier ne
prétendra plus qu'elles le sont.

---

## Fait — le Sage est sur mon écran d'accueil

Depuis le 6 septembre 2026 au soir. Première décision enregistrée :
« Postuler » → « Un entretien », 75 %, 4 h, Revenus, **verdict le 20 septembre**.

**Pour le relancer** (il ne répond que si le PC tourne et que je suis sur mon
wifi) :

```powershell
cd $HOME\Documents\SINGULAR; python -m singular sage --lan
```

Si l'app redemande la clé, un champ permet de la coller : l'adresse entière
affichée par PowerShell, ou le jeton seul.

**Sauvegarde.** Tout mon journal est dans un seul fichier :
`C:\Users\Utilisateur\.singular\journal.db`. Le copier de temps en temps sur
une clé ou dans un dossier synchronisé, c'est toute la sauvegarde nécessaire.
Rien ne part sur un serveur.

## Ce qui compte maintenant

1. **Ouvrir l'app le matin.** C'est le seul geste qui fait vivre le journal.
2. **Trancher le 20 septembre.** La carte passera en haut, « À trancher
   aujourd'hui ». Oui ou non. Un journal où l'on écrit sans jamais trancher
   n'apprend rien.
3. **Noter ce qui manque** — au fil de l'eau, pour la prochaine session :
   - Est-ce que je l'ouvre sans y penser, ou faut-il que j'y pense ?
   - Enregistrer une décision fait-il vraiment trente secondes ?
   - Les phrases sonnent-elles juste, ou me reproche-t-il des choses sans
     importance ?
   - Qu'ai-je cherché sans le trouver ?

C'est ça qui décidera de la faculté suivante — pas une liste écrite d'avance.

---

## En attente d'un Mac — l'app native, hors ligne et partout

### Compiler l'app iPhone  (≈ 1 h, dont 40 min de téléchargement)

Suis **`ios/README.md`**. Cinq étapes, écrites pour quelqu'un qui n'a jamais
ouvert Xcode. Le projet Xcode est maintenant dans le dépôt : il n'y a plus rien
à créer ni à glisser, les deux étapes qui se trompaient le plus facilement.

L'ordre compte :

1. Installer Xcode depuis l'App Store.
2. `git clone` du dépôt, puis `open SINGULAR/ios/SingularSage.xcodeproj`.
   Si Xcode propose de « mettre à jour vers les réglages recommandés » :
   **refuse**. Ce sont les réglages que le projet fixe exprès.
3. **`Cmd + U` avant tout le reste.** Les tests comparent le portage Swift au
   moteur Python. Vert : le cœur de l'app est prouvé fidèle. Rouge : envoie-moi
   le message d'erreur.
4. Se signer avec l'Apple ID (gratuit).
5. `Cmd + R` avec l'iPhone branché.

Si Xcode refuse d'ouvrir le projet (« the project is damaged »), l'annexe
« Si le projet ne s'ouvre pas » du README donne le montage à la main. Envoie-moi
le message dans ce cas : c'est la seule panne que je ne peux pas voir d'ici.

### Pendant la semaine d'essai

Le certificat gratuit dure **7 jours**. Au 8ᵉ jour l'app ne s'ouvre plus :
rebranche l'iPhone, `Cmd + R`, une minute.

**Ne supprime jamais l'app pour régler ça.** Le rebuild garde tes décisions,
la désinstallation les efface.

Note au fil de l'eau :

- Est-ce que tu l'ouvres le matin sans y penser ?
- Enregistrer une décision fait-il vraiment trente secondes ?
- Les phrases du Sage sonnent-elles juste, ou te reproche-t-il des choses sans
  importance ?
- Qu'as-tu cherché sans le trouver ?
- La notification de 8 h : bonne heure, bon texte ?

### Ensuite

Quand la réinstallation hebdomadaire te gênera :
[developer.apple.com/programs](https://developer.apple.com/programs/), 99 €/an,
et le certificat passe à un an. Tes données sont conservées.
