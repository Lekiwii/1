"""Liens de recherche Vinted et Leboncoin.

Ces deux sites n'ont pas d'API publique et interdisent le scraping : le bot ne lit pas leurs
annonces, il prépare les recherches pour que tu y actives les alertes de l'appli.
"""
from urllib.parse import urlencode


def vinted(query: str) -> str:
    return "https://www.vinted.fr/catalog?" + urlencode({"search_text": f"pokemon {query}", "order": "newest_first"})


def leboncoin(query: str) -> str:
    return "https://www.leboncoin.fr/recherche?" + urlencode({"text": f"pokemon {query}", "sort": "time", "order": "desc"})
