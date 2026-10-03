"""Reconnaissance des cartes gradées (vérifiées) à partir du titre d'une annonce."""
import re
from dataclasses import dataclass

GRADERS = ("PSA", "BGS", "CGC", "SGC", "TAG", "ACE", "PCA", "BECKETT")

_GRADE_RE = re.compile(
    r"\b(PSA|BGS|CGC|SGC|TAG|ACE|PCA|BECKETT)\s*(?:GEM\s*(?:MINT|MT)\s*|MINT\s*|PRISTINE\s*|BLACK\s*LABEL\s*)?"
    r"(10|[1-9](?:[.,]5)?)(?![\d.,/])",
    re.IGNORECASE,
)

# Annonces à écarter : faux, contrefaçons, lots, boîtiers vides, cartes non gradées…
_BLACKLIST = re.compile(
    r"\b(proxy|replica|r[ée]plique|fake|custom|orica|fan\s*made|reprint|"
    r"lot|bundle|empty|vide|label\s*only|case\s*only|slab\s*only|"
    r"ungraded|non\s*grad[ée]e?|not\s*graded|raw|pr[ée]\s*grad|pregrade|"
    r"grade\s*it|ready\s*to\s*grade|psa\s*ready|candidate|"
    r"booster|display|etb|coffret|sealed|scell[ée])\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Grade:
    grader: str
    grade: float

    def __str__(self) -> str:
        grade = int(self.grade) if self.grade.is_integer() else self.grade
        return f"{self.grader} {grade}"


def parse_grade(title: str) -> Grade | None:
    """Renvoie la note si le titre décrit une seule carte gradée par un organisme reconnu."""
    if _BLACKLIST.search(title):
        return None
    matches = _GRADE_RE.findall(title)
    if not matches:
        return None
    found = {(g.upper().replace("BECKETT", "BGS"), float(n.replace(",", "."))) for g, n in matches}
    if len(found) != 1:  # plusieurs notes différentes = lot ou titre ambigu
        return None
    grader, grade = found.pop()
    return Grade(grader, grade)


def strip_grade(title: str) -> str:
    """Le titre sans la mention de la note (« Umbreon PSA 10 » -> « Umbreon »)."""
    return _GRADE_RE.sub(" ", title)
