"""Modelul de "harta": ce inregistram cand joci tu si ce redam cand joaca botul.

O ruta e un lant de repere (waypoint-uri). Intre doua repere pastram exact
secventa de input pe care ai facut-o tu, cu temporizarea ei reala. La fiecare
reper pastram si o mica poza (de obicei minimapa) care serveste drept ancora:
la redare verificam ca ecranul seamana cu ce era acolo cand ai trecut tu, si
astfel stim daca botul mai e pe traseu sau s-a ratacit.

Avantajul redarii unei secvente inregistrate de om e ca temporizarea si
traiectoriile sunt umane din start - nu trebuie sintetizate.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, Optional

# Tipurile de reper. Botul se comporta diferit in fiecare: la 'combat' cauta
# mob-uri, la 'portal' da click si asteapta incarcarea hartii noi, la 'vendor'
# deschide meniuri.
WAYPOINT_KINDS = ("travel", "combat", "portal", "gather", "vendor", "repair", "idle", "safe")


@dataclass
class InputEvent:
    """Un singur eveniment de input, cu decalajul fata de cel dinainte.

    Tinem `dt` (delta), nu timpul absolut, ca sa putem taia sau lipi segmente
    de traseu fara sa recalculam nimic.
    """

    kind: str  # key_down | key_up | move | mouse_down | mouse_up | scroll
    dt: float
    key: Optional[str] = None
    x: Optional[int] = None
    y: Optional[int] = None
    button: Optional[str] = None
    amount: Optional[int] = None

    def as_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}

    @classmethod
    def from_dict(cls, data: dict) -> "InputEvent":
        return cls(
            kind=data["kind"],
            dt=float(data.get("dt", 0.0)),
            key=data.get("key"),
            x=data.get("x"),
            y=data.get("y"),
            button=data.get("button"),
            amount=data.get("amount"),
        )


@dataclass
class Portal:
    """Trecerea printr-un portal: un click, o ecrana de incarcare, alta harta.

    Nu poate fi redata ca un simplu click inregistrat, fiindca incarcarea
    dureaza de fiecare data altcat. De aceea o tratam separat: dam click,
    asteptam sa se schimbe si apoi sa se linisteasca ecranul, si abia dupa aia
    verificam ca am ajuns unde trebuie, comparand cu `dest_anchor`.
    """

    click: tuple[int, int]
    dest_anchor: Optional[str] = None  # cum arata harta noua, imediat dupa sosire
    template: Optional[str] = None  # sablon de cautat, daca portalul se muta pe ecran
    load_seconds: float = 20.0  # cat asteptam maximum sa se incarce

    def as_dict(self) -> dict:
        data: dict = {"click": list(self.click), "load_seconds": round(self.load_seconds, 2)}
        if self.dest_anchor:
            data["dest_anchor"] = self.dest_anchor
        if self.template:
            data["template"] = self.template
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "Portal":
        click = data.get("click") or [0, 0]
        return cls(
            click=(int(click[0]), int(click[1])),
            dest_anchor=data.get("dest_anchor"),
            template=data.get("template"),
            load_seconds=float(data.get("load_seconds", 20.0)),
        )


@dataclass
class Waypoint:
    """Un reper pe traseu si drumul de la el catre urmatorul."""

    index: int
    kind: str = "travel"
    label: str = ""
    anchor: Optional[str] = None  # nume de fisier in directorul rutei
    dwell: float = 0.0  # cate secunde stationeaza botul aici (farmat pe loc)
    portal: Optional[Portal] = None  # completat doar la reperele de tip 'portal'
    events: list[InputEvent] = field(default_factory=list)

    @property
    def duration(self) -> float:
        """Cat a durat, la inregistrare, drumul de aici pana la reperul urmator."""
        return sum(e.dt for e in self.events)

    def as_dict(self) -> dict:
        data = {
            "index": self.index,
            "kind": self.kind,
            "label": self.label,
            "anchor": self.anchor,
            "dwell": round(self.dwell, 3),
        }
        if self.portal is not None:
            data["portal"] = self.portal.as_dict()
        # Evenimentele la final: sunt partea lunga, iar asa restul reperului
        # ramane lizibil cand deschizi route.json ca sa reglezi ceva de mana.
        data["events"] = [e.as_dict() for e in self.events]
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "Waypoint":
        portal = data.get("portal")
        return cls(
            index=int(data["index"]),
            kind=data.get("kind", "travel"),
            label=data.get("label", ""),
            anchor=data.get("anchor"),
            dwell=float(data.get("dwell", 0.0)),
            portal=Portal.from_dict(portal) if portal else None,
            events=[InputEvent.from_dict(e) for e in data.get("events", [])],
        )


@dataclass
class Route:
    """Traseul complet, salvat ca un director cu `route.json` + ancorele PNG."""

    name: str
    waypoints: list[Waypoint] = field(default_factory=list)
    loop: bool = True  # traseul se inchide: ultimul reper duce inapoi la primul
    screen: Optional[dict] = None  # rezolutia la care s-a inregistrat
    created_at: float = field(default_factory=time.time)
    directory: Optional[Path] = None

    # ------------------------------------------------------------- acces

    def __len__(self) -> int:
        return len(self.waypoints)

    def __iter__(self) -> Iterable[Waypoint]:
        return iter(self.waypoints)

    def get(self, index: int) -> Waypoint:
        """Reperul de la index, cu wrap daca traseul e in bucla."""
        if not self.waypoints:
            raise IndexError("Ruta e goala.")
        if self.loop:
            return self.waypoints[index % len(self.waypoints)]
        return self.waypoints[min(index, len(self.waypoints) - 1)]

    def next_index(self, index: int) -> int:
        if self.loop:
            return (index + 1) % len(self.waypoints)
        return min(index + 1, len(self.waypoints) - 1)

    def of_kind(self, kind: str) -> list[Waypoint]:
        return [w for w in self.waypoints if w.kind == kind]

    @property
    def total_duration(self) -> float:
        return sum(w.duration + w.dwell for w in self.waypoints)

    def anchor_path(self, waypoint: Waypoint) -> Optional[Path]:
        return self.file(waypoint.anchor)

    def portal_anchor_path(self, waypoint: Waypoint) -> Optional[Path]:
        """Poza hartii de destinatie, folosita ca sa confirmam trecerea."""
        if waypoint.portal is None:
            return None
        return self.file(waypoint.portal.dest_anchor)

    def file(self, name: Optional[str]) -> Optional[Path]:
        """Rezolva un nume de fisier din ruta la o cale absoluta."""
        if not name or self.directory is None:
            return None
        return self.directory / name

    # ---------------------------------------------------------- persistenta

    def save(self, directory: str | Path) -> Path:
        """Scrie `route.json`. Ancorele sunt scrise de recorder, langa el."""
        target = Path(directory)
        target.mkdir(parents=True, exist_ok=True)
        self.directory = target
        payload = {
            "name": self.name,
            "loop": self.loop,
            "screen": self.screen,
            "created_at": self.created_at,
            "waypoints": [w.as_dict() for w in self.waypoints],
        }
        path = target / "route.json"
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return path

    @classmethod
    def load(cls, directory: str | Path) -> "Route":
        target = Path(directory)
        path = target / "route.json"
        if not path.exists():
            raise FileNotFoundError(f"Nu gasesc {path}. Inregistreaza intai o ruta.")
        data = json.loads(path.read_text(encoding="utf-8"))
        route = cls(
            name=data.get("name", target.name),
            loop=bool(data.get("loop", True)),
            screen=data.get("screen"),
            created_at=float(data.get("created_at", 0.0)),
            waypoints=[Waypoint.from_dict(w) for w in data.get("waypoints", [])],
        )
        route.directory = target
        return route

    def describe(self) -> str:
        """Rezumat pentru consola."""
        kinds: dict[str, int] = {}
        for w in self.waypoints:
            kinds[w.kind] = kinds.get(w.kind, 0) + 1
        parts = ", ".join(f"{k}:{v}" for k, v in sorted(kinds.items()))
        minutes = self.total_duration / 60
        return (
            f"Ruta '{self.name}': {len(self.waypoints)} repere ({parts}), "
            f"~{minutes:.1f} min pe tura, bucla={'da' if self.loop else 'nu'}"
        )
