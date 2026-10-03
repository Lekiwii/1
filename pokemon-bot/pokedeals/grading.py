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


# (code, mots complets insensibles à la casse, abréviations en majuscules uniquement)
_LANGUAGES = [
    ("JP", r"japanese|japonaise?|japan|japanisch|giapponese|japon[ée]s", r"JP|JPN|JAP"),
    ("KR", r"korean|cor[ée]enne?|koreanisch", r"KR|KOR"),
    ("CN", r"chinese|chinoise?|chinesisch|s-chinese|t-chinese", r"CN|CHN"),
    ("FR", r"fran[çc]aise?|french|franz[öo]sisch", r"FR|VF"),
    ("DE", r"deutsch|german|allemande?", r"DE|GER"),
    ("IT", r"italiano|italian|italienne?", r"IT|ITA"),
    ("ES", r"espa[ñn]ol|spanish|espagnole?", r"ES|ESP"),
    ("EN", r"english|anglaise?|englisch|inglese", r"EN|ENG"),
]
_LANGUAGE_RE = [
    (code, re.compile(rf"\b(?:{words})\b", re.IGNORECASE), re.compile(rf"\b(?:{abbr})\b"))
    for code, words, abbr in _LANGUAGES
]
_FIRST_EDITION_RE = re.compile(r"\b(1st\s*ed(?:ition)?|first\s*edition|1(?:[èe]re|er)?\s*[ée]dition|edition\s*1)\b", re.IGNORECASE)


def explicit_language(title: str) -> str | None:
    """Langue indiquée dans le titre, ou None si le vendeur ne la précise pas."""
    for code, words, abbr in _LANGUAGE_RE:
        if words.search(title) or abbr.search(title):
            return code
    return None


def detect_language(title: str) -> str:
    """Langue de la carte annoncée ; « EN » par défaut (cas le plus courant sur eBay)."""
    return explicit_language(title) or "EN"


def is_first_edition(title: str) -> bool:
    return bool(_FIRST_EDITION_RE.search(title))


@dataclass(frozen=True)
class Variant:
    """Ce qui doit être identique pour comparer deux prix : note, langue, édition."""

    grade: Grade
    language: str
    first_edition: bool

    def __str__(self) -> str:
        return f"{self.grade} {self.language}" + (" 1st Ed." if self.first_edition else "")


def parse_variant(title: str) -> Variant | None:
    grade = parse_grade(title)
    if grade is None:
        return None
    return Variant(grade, detect_language(title), is_first_edition(title))
