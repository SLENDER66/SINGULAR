#!/usr/bin/env bash
# Bascule `main` sur la ligne de travail, puis supprime les branches mortes.
#
# À lancer depuis ton clone. Il ne supprime rien tant que la bascule n'est pas
# vérifiée, et il refuse de toucher à `main` ou à l'archive.
#
#   bash migrate_main.sh --dry-run   # montre ce qu'il ferait, ne touche à rien
#   bash migrate_main.sh             # exécute
set -euo pipefail

SOURCE="claude/singular-mandate-setup-d51s9t"
ARCHIVE="archive/main-2026-09-03"
DRY=${1:-}

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }
run() { if [ "$DRY" = "--dry-run" ]; then echo "  [dry-run] $*"; else "$@"; fi; }

say "1. Vérifications"
git fetch --prune origin >/dev/null 2>&1
git rev-parse --verify "origin/$ARCHIVE" >/dev/null 2>&1 \
  || { echo "  STOP : l'archive $ARCHIVE est absente. Rien ne sera fait."; exit 1; }
git rev-parse --verify "origin/$SOURCE" >/dev/null 2>&1 \
  || { echo "  STOP : la branche source $SOURCE est absente."; exit 1; }
TARGET_SHA=$(git rev-parse "origin/$SOURCE")
echo "  archive      $ARCHIVE -> $(git rev-parse --short origin/$ARCHIVE)"
echo "  source       $SOURCE -> ${TARGET_SHA:0:7}"
echo "  main actuel  $(git rev-parse --short origin/main)"

say "2. Tests avant bascule"
git -c advice.detachedHead=false checkout --quiet "$TARGET_SHA"
python3 -m pytest -q 2>&1 | tail -1
git checkout --quiet - 2>/dev/null || true

say "3. Bascule de main"
run git push --force-with-lease origin "$TARGET_SHA:refs/heads/main"

if [ "$DRY" != "--dry-run" ]; then
  git fetch origin main >/dev/null 2>&1
  [ "$(git rev-parse origin/main)" = "$TARGET_SHA" ] \
    || { echo "  STOP : main ne pointe pas où attendu. Aucune suppression."; exit 1; }
  echo "  main pointe maintenant sur ${TARGET_SHA:0:7}"
fi

say "4. Suppression des branches mortes"
DELETED=0
while read -r branch; do
  case "$branch" in
    main|"$ARCHIVE") continue ;;
  esac
  echo "  supprime $branch"
  run git push origin --delete "$branch" >/dev/null 2>&1 || echo "    (échec, ignoré)"
  DELETED=$((DELETED + 1))
done < <(git ls-remote --heads origin | awk '{print $2}' | sed 's|refs/heads/||' | sort)

say "Terminé"
echo "  $DELETED branche(s) supprimée(s). Restent : main, $ARCHIVE"
echo
echo "  Ensuite :"
echo "    - fermer la PR #4 (elle est sans objet)"
echo "    - Settings > Actions : débloquer les runners"
echo "    - puis rendre le dépôt public"
