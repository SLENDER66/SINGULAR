# Ce qu'il te reste à faire — 3 clics

Tout le reste est fait. Ces trois actions demandent des droits que je n'ai pas.

---

## 1. Faire de la bonne branche la branche principale  (2 min)

`main` contient l'ancienne version du projet : 40 modules, 37 fichiers de test,
**un test qui échoue**. La branche `claude/singular-mandate-setup-d51s9t`
contient 101 modules, 122 fichiers de test, **664 tests verts**, et tous les
fichiers de `main` sans exception.

Les deux n'ont aucun ancêtre commun, donc on ne peut pas les fusionner. On change
juste laquelle est la principale. **Rien n'est supprimé.**

1. Va sur <https://github.com/SLENDER66/SINGULAR/settings>
2. Section **Default branch**, clique sur l'icône ⇄ (deux flèches)
3. Choisis `claude/singular-mandate-setup-d51s9t`
4. **Update** → confirme

C'est réversible : tu peux revenir à `main` par le même chemin.

### Ensuite, pour que ça s'appelle vraiment `main` (optionnel, 1 min)

Une fois l'étape ci-dessus faite :

5. Toujours dans Settings → **Branches** → à côté de l'ancienne `main`, la
   corbeille 🗑 (elle est sauvegardée dans `archive/main-2026-09-03`)
6. Puis à côté de `claude/singular-mandate-setup-d51s9t`, le crayon ✏ →
   renomme-la en `main`

---

## 2. Rendre le dépôt public  (30 s) — et ça répare le CI

**J'avais l'ordre à l'envers.** J'ai regardé la facturation Actions :

```
run #1025 : 3 jobs, 0 milliseconde facturée, 4 secondes au total
```

Zéro milliseconde. Aucun runner n'a jamais démarré. Tu as **1025 runs** sur un
dépôt privé, dont le quota gratuit est de 2000 minutes par mois. Tu les as
épuisées.

**Les dépôts publics ont GitHub Actions gratuit et illimité.** Passer en public
ne casse pas le CI : ça le répare.

1. <https://github.com/SLENDER66/SINGULAR/settings>
2. Tout en bas, **Danger Zone** → **Change repository visibility**
3. **Make public** → tape le nom du dépôt pour confirmer

Pour vérifier mon diagnostic avant : <https://github.com/settings/billing>,
section Actions. Tu devrais voir tes minutes à zéro.

*Fais l'étape 1 avant celle-ci*, pour que les visiteurs tombent sur la bonne
version.

---

## 3. Nettoyer les 46 branches mortes  (1 min)

À faire seulement après l'étape 1, depuis ton terminal :

```bash
cd ~/SINGULAR
git pull
bash migrate_main.sh --dry-run    # montre tout, ne touche à rien
bash migrate_main.sh              # exécute
```

Si tu ne veux pas toucher au terminal, ce n'est pas grave : 46 branches
inutilisées ne cassent rien, c'est juste moins lisible pour un visiteur.

---

## Fait, tu n'as rien à faire

- ✅ PR #4 fermée, avec un commentaire qui explique ce qui a été intégré
- ✅ `archive/main-2026-09-03` créée — l'ancien `main` est sauvegardé
- ✅ Matrice CI réduite de 3 à 2 versions de Python (un tiers de minutes en moins)
- ✅ 664 tests verts, audit de frontière propre
- ✅ Le journal, le provider HTTP réel, le README, `USAGE.md`

---

## Et pendant ce temps

```bash
cd ~/SINGULAR && pip install -e '.[dev]'
python -m singular apply "Nom de la boîte" "Le poste"
```

L'outil est vide. Les deux rangs que ta constitution met en premier —
Stabilité et Revenus — n'ont aucune décision enregistrée. C'est la seule chose
de cette page qui change quelque chose pour toi cette semaine.
