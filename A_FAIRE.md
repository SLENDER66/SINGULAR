# Ce que je dois faire moi-même

Rien sur GitHub. Les trois actions de la version précédente de ce fichier sont
faites : le dépôt est public, la bonne branche est la branche par défaut, les
branches mortes sont supprimées.

Il reste deux choses. **La première n'attend rien ni personne** — ni le Mac,
ni ta sœur, ni un euro. Ce fichier disait le contraire, et c'est ce qui a fait
passer l'app native avant elle.

---

## 1. Mettre le Sage sur ton écran d'accueil, ce soir  (10 min)

Sur ton PC Windows.

**Une seule fois — installer Python.**
[python.org/downloads](https://www.python.org/downloads/) → le gros bouton
jaune. Dans l'installateur, **coche « Add python.exe to PATH »** en bas de la
première fenêtre. C'est la seule case qui compte ; l'oublier est l'erreur que
tout le monde fait.

**Récupérer le code.** Ouvre PowerShell (touche Windows, tape `powershell`) :

```powershell
cd $HOME\Documents
git clone https://github.com/SLENDER66/SINGULAR.git
cd SINGULAR
```

Si `git` n'existe pas : va sur la page GitHub du dépôt, bouton vert **Code** →
**Download ZIP**, décompresse dans `Documents`, puis
`cd $HOME\Documents\SINGULAR-<nom-de-la-branche>`.

**Lancer le Sage.** Ton iPhone et le PC doivent être sur le même wifi.

```powershell
python -m singular sage --lan
```

Windows demandera d'autoriser Python sur le réseau : **accepte** pour les
réseaux privés. Sans ça, le téléphone ne verra rien.

Le programme affiche une adresse du genre `http://192.168.1.24:8765/?k=...`.

**Sur l'iPhone.** Ouvre cette adresse dans **Safari** — le jeton `?k=` en fait
partie, recopie-la en entier. Puis bouton **Partager** (le carré avec la
flèche) → **Sur l'écran d'accueil**.

Tu as une icône. Plein écran, pas de barre de navigateur. C'est le Sage.

**Ce que ça vaut, et ce que ça ne vaut pas.** L'app marche tant que le PC
tourne et que tu es sur ton wifi. Dehors, ou PC éteint, elle ne répond pas.
C'est la limite, et c'est ce que l'app native lèvera. En attendant, tu as le
Sage aujourd'hui au lieu de l'avoir peut-être.

Aucune dépendance à installer : le serveur n'utilise que ce qui vient avec
Python.

---

## 2. L'app native, quand le Mac sera disponible

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
