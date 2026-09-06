# Le Sage sur ton iPhone — recette complète

Tout le code est écrit. Il reste à le compiler, ce que seul ton Mac peut faire.
Compte **une heure la première fois**, dont quarante minutes de téléchargement
pendant lesquelles tu n'as rien à faire.

> **Important.** Je n'ai pas pu compiler ce code : l'environnement où je
> travaille n'a pas de compilateur Swift et le réseau y interdit son
> installation. C'est pour ça que la première chose que tu feras est de lancer
> les tests. Ils comparent ce port aux **vecteurs de référence** produits par le
> moteur Python du dépôt, lui-même couvert par sa propre suite. S'ils passent, le cœur
> de l'app est prouvé équivalent à l'original. S'ils échouent, ils te disent
> quelle phrase diverge et de quoi — envoie-moi le message, je corrige.

---

## 1. Installer Xcode  (40 min, dont 39 d'attente)

App Store sur le Mac → cherche **Xcode** → Installer. C'est gros (~10 Go, prévois
40 Go de libre). Lance-le une fois l'installation finie, accepte la licence,
laisse-le installer ses composants.

## 2. Récupérer le code

Ouvre **Terminal** (Cmd+Espace, tape « Terminal ») et colle :

```bash
cd ~/Documents
git clone https://github.com/SLENDER66/SINGULAR.git
open SINGULAR/ios
```

Une fenêtre s'ouvre sur le dossier `ios`. Laisse-la ouverte, tu vas y glisser des
fichiers.

## 3. Créer le projet

Dans Xcode : **File → New → Project…**

| Champ | Valeur |
|---|---|
| Modèle | **iOS** → **App** |
| Product Name | `SingularSage` — exactement, les tests en dépendent |
| Team | laisse vide pour l'instant |
| Organization Identifier | `com.thomas` (ou ce que tu veux, sans espace) |
| Interface | **SwiftUI** |
| Language | **Swift** |
| Storage | **None** |
| Include Tests | **coché** |

**Next**, enregistre-le dans `~/Documents` (pas dans le dossier SINGULAR).

## 4. Mettre les fichiers dedans

Dans Xcode, à gauche, tu vois un dossier bleu `SingularSage`.

1. Depuis la fenêtre du Finder ouverte à l'étape 2, glisse les dossiers
   **`Core`** et **`App`** sur le dossier jaune `SingularSage` de Xcode.
   Dans la boîte qui s'ouvre : **coche « Copy items if needed »**, choisis
   **« Create groups »**, et sous *Add to targets* coche **SingularSage**.
2. Xcode a créé un fichier `SingularSageApp.swift` de son côté et tu viens d'en
   apporter un autre du même nom. **Supprime celui que Xcode a créé** (clic
   droit → Delete → *Move to Trash*) ; garde le mien.
   Fais pareil avec `ContentView.swift`, qui ne sert plus.
3. Glisse le contenu de **`Tests`** (les deux fichiers `.swift`) sur le dossier
   `SingularSageTests`. Cette fois, sous *Add to targets*, coche
   **SingularSageTests** et **décoche SingularSage**.
4. Glisse **`Resources/notice_vectors.json`** au même endroit, dans
   `SingularSageTests`, en cochant **SingularSageTests** uniquement.
   Sans ce fichier, les tests ne peuvent rien vérifier — et ils te le diront
   plutôt que de passer au vert en silence.

## 5. Lancer les tests  ← fais ça avant tout le reste

**Cmd + U**.

- Tout est vert → le port dit exactement ce que dit le moteur de référence.
  Continue.
- Du rouge → clique sur l'erreur, tu verras `attendu ... obtenu ...`.
  Envoie-moi le texte, c'est fait pour ça.

## 6. Se signer avec ton Apple ID  (gratuit)

Clique sur le projet `SingularSage` tout en haut à gauche → onglet
**Signing & Capabilities**.

1. **Team** → *Add an Account…* → connecte-toi avec ton Apple ID → ferme.
2. Reviens sur **Team** et choisis **« Ton Nom (Personal Team) »**.
3. Si Xcode râle sur le *Bundle Identifier*, change-le pour quelque chose
   d'unique : `com.thomas.singularsage.2026`.

## 7. Installer sur ton iPhone

1. Branche l'iPhone au Mac. Sur le téléphone : **Se fier** à cet ordinateur.
2. En haut de Xcode, à côté du bouton ▶, choisis ton iPhone dans la liste.
3. **Cmd + R**.
4. Au premier lancement l'iPhone refuse l'app. Va dans **Réglages → Général →
   VPN et gestion de l'appareil → ton Apple ID → Faire confiance**.
5. Relance l'app depuis l'écran d'accueil.

C'est fini. L'icône est là, l'app fonctionne hors ligne, la notification de 8 h
se planifie toute seule à la première ouverture.

---

## Si quelqu'un d'autre compile à ta place

Le dépôt est public : la personne qui a le Mac n'a besoin de rien d'autre que
son adresse. Elle n'a **aucun compte Apple à créer** et **aucun euro à
dépenser** pour tout ce qui suit.

### Ce qu'elle fait — 1 h, dont 40 min d'attente

1. Étapes **1 à 4** ci-dessus : installer Xcode, `git clone`, créer le projet
   `SingularSage`, y glisser les fichiers.
2. **`Cmd + U`** — les tests. C'est le but de l'opération.
3. En haut de Xcode, choisir **n'importe quel iPhone de la liste des
   simulateurs** (pas un appareil réel), puis **`Cmd + R`**. L'app démarre dans
   un iPhone à l'écran, entièrement fonctionnelle.

Le simulateur ne demande ni Apple ID, ni certificat, ni signature. Les étapes 6
et 7 du haut de page ne la concernent pas.

### Ce qu'elle renvoie

- **Le résultat de `Cmd + U`.** Vert, ou le texte exact de chaque échec.
- **Si ça ne compile pas** : le message d'erreur et le nom du fichier. C'est
  attendu — ce code n'a jamais vu de compilateur.
- **Deux ou trois captures d'écran** de l'app dans le simulateur : l'écran
  d'accueil, l'ajout d'une décision, le verdict.

Elle n'a rien à comprendre au projet. Copier l'erreur suffit.

### Ce que ça ne donne pas

L'app **sur ton iPhone**. Xcode installe sur un appareil branché en câble ou
appairé sur le même réseau local ; ton téléphone n'est pas là-bas. Le seul
chemin à distance est TestFlight, qui demande le compte à 99 €/an : elle
téléverse une version, tu l'installes depuis n'importe où.

Autrement dit, sa contribution valide **que l'app fonctionne et à quoi elle
ressemble**. La mettre dans ta poche demande soit le téléphone à côté du Mac,
soit les 99 €.

## Ce que la version gratuite change

**Rien dans l'app.** Une seule différence : le certificat gratuit dure **7 jours**.
Passé ce délai l'app ne s'ouvre plus, et il faut rebrancher l'iPhone et refaire
**Cmd + R** — une minute.

Les notifications fonctionnent : celle du matin est *locale*, planifiée par
l'app sur le téléphone. Seules les notifications poussées depuis un serveur
demandent le compte payant, et cette app n'a pas de serveur.

Quand la semaine te gênera : [developer.apple.com/programs](https://developer.apple.com/programs/),
99 €/an, et le certificat passe à un an.

---

## Ce qu'il y a dans chaque fichier

| Fichier | Ce qu'il fait |
|---|---|
| `Core/Tier.swift` | La hiérarchie de ta constitution |
| `Core/Entry.swift` | Une décision, et depuis quand elle attend |
| `Core/Journal.swift` | Le stockage et la chaîne de hachage |
| `Core/Notice.swift` | **Le moteur d'observation** — le port du Python |
| `App/BriefView.swift` | L'écran du matin |
| `App/AddDecisionView.swift` | Enregistrer une décision, en trente secondes |
| `App/ResolveSheet.swift` | Trancher : arrivé, pas arrivé, ou abandonné |
| `App/DailyNotice.swift` | Le rappel de 8 h |
| `Tests/NoticeVectorTests.swift` | La comparaison avec le moteur de référence |
| `Tests/JournalTests.swift` | La chaîne, les refus, les comptes |

Le journal vit dans un fichier JSON dans l'app. Il ne part sur aucun serveur, et
la sauvegarde iCloud de ton iPhone l'emporte avec elle.

## Quand la règle change côté Python

Le moteur Python reste la référence. Après toute modification de
`singular/sage/notice.py` :

```bash
python tools/generate_notice_vectors.py
```

Remplace ensuite `notice_vectors.json` dans Xcode, relance **Cmd + U**, et le
test te dira exactement ce qu'il reste à porter.
