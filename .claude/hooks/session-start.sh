#!/bin/bash
# Ce que toute session doit savoir avant sa premiere ligne.
#
# Deux choses etaient ecrites dans les fichiers de reprise et sautees une fois
# sur deux, parce qu'une consigne se lit ou ne se lit pas :
#
#   1. pytest n'est pas installe dans un conteneur neuf. Une session qui lance
#      la suite sans installer croit le depot casse.
#   2. le conteneur part de la branche par defaut. Elle a ete laissee 39
#      commits en arriere une fois, et la seance a demarre sans singular/sage/,
#      sans ios/ et sur un mandat perime -- elle serait partie travailler sur
#      une branche morte.
#
# Le hook les fait au lieu de les demander. Son verdict arrive dans le contexte
# de la session : il ne peut plus etre saute.
set -uo pipefail

cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0

echo "=== SINGULAR : etat verifie au demarrage ==="

# Les dependances. Idempotent, et le conteneur garde le resultat en cache.
if python -m pip install -e '.[dev]' --quiet > /tmp/pip-singular.log 2>&1; then
    echo "dependances installees (pytest, ruff, mypy)"
else
    echo "ATTENTION : l'installation a echoue, pytest ne tournera pas. Detail :"
    tail -5 /tmp/pip-singular.log
fi

# L'etat du depot distant. Un echec ici n'empeche pas la session de demarrer,
# mais il doit etre lu : c'est la seule chose qui dise si le code sous les yeux
# est bien celui du travail.
echo
if python tools/check_repo_state.py; then
    :
else
    echo
    echo "  ^^ NE COMMENCE RIEN AVANT D'AVOIR REGLE CA."
    echo "  Le bloc ci-dessus dit lequel des cas c'est -- code en retard,"
    echo "  mandat suspect, travail echoue sur une branche hors mandat, ou"
    echo "  comparaison impossible. Lis-le : il nomme le probleme et le geste."
    echo "  Tant qu'il n'est pas regle, ce que tu lirais ensuite, mandat"
    echo "  compris, peut venir d'ailleurs -- ou n'aller nulle part."
fi
echo
echo "=== fin de la verification ==="
