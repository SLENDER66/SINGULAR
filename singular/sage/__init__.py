"""Le Grand Sage : la surface qui observe, analyse et conseille.

Ce paquet est la partie de SINGULAR qui te parle. Il lit ton journal, ta
constitution et ta mémoire, et il te rend un avis. Il ne fait rien d'autre.

C'est délibéré, et c'est la même règle que le reste du dépôt applique à
l'exécution : penser n'est pas décider, décider n'est pas autoriser, autoriser
n'est pas exécuter. Le Sage occupe la première case. Il n'importe aucun module
de la frontière d'exécution -- un test le vérifie -- de sorte qu'aucune analyse,
aussi convaincante soit-elle, ne peut se transformer en acte sur le monde sans
que tu l'aies décidé toi-même.
"""
from .notice import Notice, NoticeItem, build_notice

__all__ = ["Notice", "NoticeItem", "build_notice"]
