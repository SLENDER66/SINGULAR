# Ce que je dois faire moi-même

Rien sur GitHub. Les trois actions de la version précédente de ce fichier sont
faites : le dépôt est public, la bonne branche est la branche par défaut, les
branches mortes sont supprimées.

Il reste une chose, et elle attend le Mac.

---

## Compiler l'app iPhone  (≈ 1 h, dont 40 min de téléchargement)

Suis **`ios/README.md`**. Sept étapes, écrites pour quelqu'un qui n'a jamais
ouvert Xcode.

L'ordre compte :

1. Installer Xcode depuis l'App Store.
2. `git clone` du dépôt.
3. Créer le projet — **Product Name exactement `SingularSage`**.
4. Y glisser `Core/`, `App/`, `Tests/` et `Resources/notice_vectors.json`.
5. **`Cmd + U` avant tout le reste.** Les tests comparent le portage Swift au
   moteur Python. Vert : le cœur de l'app est prouvé fidèle. Rouge : envoie-moi
   le message d'erreur.
6. Se signer avec l'Apple ID (gratuit).
7. `Cmd + R` avec l'iPhone branché.

## Pendant la semaine d'essai

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

## Ensuite

Quand la réinstallation hebdomadaire te gênera :
[developer.apple.com/programs](https://developer.apple.com/programs/), 99 €/an,
et le certificat passe à un an. Tes données sont conservées.
