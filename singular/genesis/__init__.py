"""AZAZEL Genesis : la plus petite chose capable de contredire l'hypothèse.

L'hypothèse est qu'une expérience vérifiée devient une capacité réutilisable, et
qu'une capacité réutilisable rend une mission suivante objectivement meilleure.
Ce paquet ne cherche pas à la confirmer : il la mesure, et il sait dire non.

Il ne touche à rien. Pas de modèle, pas de clé, pas de réseau, pas d'écriture,
et aucun chemin vers la frontière d'exécution du dépôt --
`tests/test_genesis_isolation.py` le refuse plutôt que de le promettre.
"""
from .bench import Comparaison, TestDeNaissance, banc, comparer, constater_naissance
from .capability import NIVEAUX, Capacite, Preuve, Registre, SubstitutionRefusee
from .mission import Etape, Mission, Resultat, Trajectoire, executer

__all__ = ["NIVEAUX", "Capacite", "Comparaison", "Etape", "Mission", "Preuve", "Registre",
           "Resultat", "SubstitutionRefusee", "TestDeNaissance", "Trajectoire", "banc",
           "comparer", "executer", "constater_naissance"]
