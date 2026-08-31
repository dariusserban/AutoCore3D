"""Modificarea unei singure valori din profil, fara sa strici restul fisierului.

De ce nu folosim PyYAML: `yaml.safe_dump` rescrie tot fisierul si arunca la gunoi
comentariile. In profilul nostru comentariile SUNT documentatia - explica ce e
fiecare reglaj si cum se calibreaza. Daca fereastra de setari le-ar sterge la
prima bifa apasata, profilul ar deveni un morman de cifre fara inteles.

Asa ca lucram pe linii: gasim linia care contine cheia ceruta si ii schimbam
doar valoarea, pastrand indentarea si comentariul de la capatul liniei.
"""

from __future__ import annotations

import re
from typing import Any, Optional

# `  key: valoare  # comentariu`
_LINIE = re.compile(r"^(?P<indent>\s*)(?P<key>[A-Za-z_][A-Za-z0-9_]*)\s*:(?P<rest>.*)$")


def _formateaza(value: Any) -> str:
    """Scrie valoarea in forma YAML potrivita tipului ei."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    if text == "":
        return '""'
    # Ghilimele doar cand chiar trebuie: altfel profilul devine greu de citit.
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_./-]*", text):
        return text
    return '"{}"'.format(text.replace('"', '\\"'))


def _comentariu(rest: str) -> str:
    """Pastreaza comentariul de la capatul liniei, daca exista.

    Sarim peste diezii dinauntrul unui sir cu ghilimele, ca sa nu taiem
    o valoare de genul `culoare: "#ff0000"` in doua.
    """
    in_ghilimele = False
    for i, ch in enumerate(rest):
        if ch == '"':
            in_ghilimele = not in_ghilimele
        elif ch == "#" and not in_ghilimele:
            return "  " + rest[i:].strip()
    return ""


def set_value(text: str, section: Optional[str], key: str, value: Any) -> str:
    """Schimba `section.key` (sau cheia de la radacina daca section e None).

    Daca sectiunea exista dar cheia nu, o adauga la finalul sectiunii. Daca nici
    sectiunea nu exista, o creeaza la finalul fisierului.
    """
    linii = text.splitlines()

    if section is None:
        for i, linie in enumerate(linii):
            m = _LINIE.match(linie)
            if m and m.group("indent") == "" and m.group("key") == key:
                linii[i] = f"{key}: {_formateaza(value)}{_comentariu(m.group('rest'))}"
                return "\n".join(linii) + "\n"
        linii.append(f"{key}: {_formateaza(value)}")
        return "\n".join(linii) + "\n"

    start = None
    for i, linie in enumerate(linii):
        m = _LINIE.match(linie)
        if m and m.group("indent") == "" and m.group("key") == section:
            start = i
            break

    if start is None:
        linii.extend(["", f"{section}:", f"  {key}: {_formateaza(value)}"])
        return "\n".join(linii) + "\n"

    # Sectiunea tine pana la urmatoarea cheie de la marginea din stanga.
    sfarsit = len(linii)
    for i in range(start + 1, len(linii)):
        m = _LINIE.match(linii[i])
        if m and m.group("indent") == "":
            sfarsit = i
            break

    for i in range(start + 1, sfarsit):
        m = _LINIE.match(linii[i])
        if m and m.group("indent") and m.group("key") == key:
            indent = m.group("indent")
            linii[i] = f"{indent}{key}: {_formateaza(value)}{_comentariu(m.group('rest'))}"
            return "\n".join(linii) + "\n"

    # Cheia lipseste: o punem la finalul sectiunii, dupa ultima linie cu continut.
    inserare = sfarsit
    while inserare > start + 1 and not linii[inserare - 1].strip():
        inserare -= 1
    linii.insert(inserare, f"  {key}: {_formateaza(value)}")
    return "\n".join(linii) + "\n"


def set_many(text: str, valori: list[tuple[Optional[str], str, Any]]) -> str:
    """Aplica mai multe schimbari, una dupa alta."""
    for section, key, value in valori:
        text = set_value(text, section, key, value)
    return text
