"""Culesul cu tasta: gasirea obiectelor in cerc si lista neagra."""

import time

import pytest

from gamebot.core.config import Profile
from gamebot.core.pickup import Blacklist, culori_din_profil, find_loot
from gamebot.tests.conftest import make_frame

GALBEN = [([25, 200, 200], [35, 255, 255])]
CENTRU = (200, 150)  # centrul cadrului sintetic


def test_gaseste_toate_obiectele_fara_raza():
    assert len(find_loot(make_frame(nodes=3), GALBEN, CENTRU, min_area=100)) == 3


def test_cercul_taie_ce_e_in_afara():
    """Ce se vede in cerc e exact ce se aduna - asta e intelegerea cu ecranul."""
    cadru = make_frame(nodes=3)

    # Mob-urile sunt la (55, 215), (115, 215), (175, 215); centrul e (200, 150).
    departe = find_loot(cadru, GALBEN, CENTRU, radius=50, min_area=100)
    aproape = find_loot(cadru, GALBEN, CENTRU, radius=400, min_area=100)

    assert departe == []
    assert len(aproape) == 3


def test_cele_mai_apropiate_primele():
    """Personajul se deplaseaza cel mai putin daca incepe cu ce e langa el."""
    gasite = find_loot(make_frame(nodes=3), GALBEN, CENTRU, min_area=100)
    distante = [abs(b.center[0] - CENTRU[0]) for b in gasite]
    assert distante == sorted(distante)


def test_offsetul_muta_rezultatele_in_coordonate_de_ecran():
    """Cand cadrul e decupajul unei ferestre, clicurile trebuie sa cada corect."""
    fara = find_loot(make_frame(nodes=1), GALBEN, CENTRU, min_area=100)
    cu = find_loot(make_frame(nodes=1), GALBEN, CENTRU, min_area=100, offset=(950, 102))

    assert cu[0].center[0] == fara[0].center[0] + 950
    assert cu[0].center[1] == fara[0].center[1] + 102


def test_imaginea_goala_nu_arunca():
    import numpy as np

    assert find_loot(np.zeros((0, 0, 3), dtype=np.uint8), GALBEN, CENTRU) == []
    assert find_loot(None, GALBEN, CENTRU) == []


# ------------------------------------------------------------- lista neagra


def test_lista_neagra_retine_si_uita():
    lista = Blacklist(seconds=0.2, distance=30)
    lista.add(100, 100)

    assert lista.contains(105, 105)
    assert not lista.contains(200, 200)

    time.sleep(0.25)
    assert not lista.contains(105, 105)


def test_lista_neagra_scoate_obiectul_din_rezultate():
    cadru = make_frame(nodes=3)
    lista = Blacklist()
    primul = find_loot(cadru, GALBEN, CENTRU, min_area=100)[0]
    lista.add(*primul.center)

    ramase = find_loot(cadru, GALBEN, CENTRU, min_area=100, blacklist=lista)

    assert len(ramase) == 2
    assert primul.center not in [b.center for b in ramase]


def test_golirea_listei():
    lista = Blacklist()
    lista.add(1, 1)
    lista.clear()
    assert not lista.contains(1, 1)


# ---------------------------------------------------------------- culorile


def test_culorile_se_iau_din_profil():
    profil = Profile.from_dict({
        "colors": {
            "loot_auriu": {"low": [18, 110, 120], "high": [32, 255, 255]},
            "loot_verde": {"low": [40, 90, 90], "high": [80, 255, 255]},
        }
    })

    culori = culori_din_profil(profil, ["loot_auriu", "loot_verde"])

    assert len(culori) == 2
    assert culori[0][0] == [18, 110, 120]


def test_culorile_inexistente_se_sar_in_tacere():
    """O culoare scrisa gresit in profil nu trebuie sa opreasca culesul."""
    profil = Profile.from_dict({"colors": {"a": {"low": [0, 0, 0], "high": [1, 1, 1]}}})
    assert len(culori_din_profil(profil, ["a", "inexistenta"])) == 1


def test_profilul_de_dso_are_culori_de_loot():
    from pathlib import Path

    cale = Path(__file__).resolve().parents[1] / "profiles" / "drakensang.yaml"
    profil = Profile.load(cale)
    culori = culori_din_profil(profil, profil.section("loot")["colors"])

    assert len(culori) >= 3, "profilul livrat trebuie sa poata cauta obiecte din prima"


def test_profilul_de_dso_are_setari_de_cules_cu_tasta():
    from pathlib import Path

    cale = Path(__file__).resolve().parents[1] / "profiles" / "drakensang.yaml"
    pickup = Profile.load(cale).section("pickup")

    assert pickup["hotkey"] == "f7"
    assert pickup["radius"] > 0


# ------------------------------------------------------ proba de culoare (F8)


def _masoara(imagine):
    """Ce face F8: mediana HSV a unui patrat mic, largita intr-un interval.

    Mediana, nu media: pe marginea unei litere apar pixeli antialiasati de alta
    culoare, iar media i-ar amesteca intr-o nuanta care nu exista pe ecran.
    """
    import cv2
    import numpy as np

    hsv = cv2.cvtColor(imagine, cv2.COLOR_BGR2HSV).reshape(-1, 3)
    median = np.median(hsv, axis=0).astype(int)
    low = np.clip(median - np.array([8, 60, 60]), [0, 0, 0], [179, 255, 255])
    high = np.clip(median + np.array([8, 40, 40]), [0, 0, 0], [179, 255, 255])
    return list(low), list(high)


def test_culoarea_masurata_gaseste_obiectele():
    """Cheia intregului mod: ce masori cu F8 trebuie sa si functioneze pus in profil.

    Fara asta, utilizatorul pune in profil niste cifre care arata a masuratoare
    dar nu prind nimic - exact felul de esec tacut pe care il evitam.
    """
    cadru = make_frame(nodes=2)
    # Un patrat de 9x9 din mijlocul unei etichete, ca sub cursor.
    low, high = _masoara(cadru[211:220, 46:55])

    gasite = find_loot(cadru, [(low, high)], CENTRU, min_area=100)

    assert len(gasite) == 2


def test_o_proba_buna_prinde_o_bucatica_din_ecran():
    """Eticheta unui obiect ocupa foarte putin; asa se recunoaste o proba buna."""
    from gamebot.core.pickup import acoperire

    cadru = make_frame(nodes=2)
    low, high = _masoara(cadru[211:220, 46:55])

    assert acoperire(cadru, low, high) < 0.05


def test_o_proba_luata_de_pe_fundal_e_recunoscuta():
    """Arata la fel de "masurata" ca una buna, dar prinde jumatate din ecran.

    Fara verificarea asta ar ajunge linistita in profil si botul n-ar gasi
    niciodata nimic - genul de esec care pare al codului, nu al probei.
    """
    from gamebot.core.pickup import acoperire

    cadru = make_frame(nodes=2)
    low, high = _masoara(cadru[50:59, 300:309])

    assert acoperire(cadru, low, high) > 0.05


# ---------------------------------- filtre care evita obiectele inexistente


def test_petele_prea_mari_nu_sunt_obiecte():
    """Un monstru de culoarea potrivita nu e loot.

    Detectia pe culoare nu poate face diferenta singura: intervalul pentru
    etichete verzi prinde la fel de bine un monstru verde. Marimea o poate.
    """
    import numpy as np

    cadru = make_frame(nodes=1)
    # Un "monstru" galben, mult mai mare decat o eticheta.
    cadru[60:160, 240:340] = (0, 220, 220)

    fara_filtru = find_loot(cadru, GALBEN, CENTRU, min_area=100)
    cu_filtru = find_loot(cadru, GALBEN, CENTRU, min_area=100, max_area=3000)

    assert len(fara_filtru) == 2
    assert len(cu_filtru) == 1, "pata mare trebuia ignorata"


def test_cercul_desenat_de_noi_nu_e_cules():
    """Captura de ecran include propriul nostru cerc.

    Culoarea lui poate cadea in intervalul cautat, si atunci botul isi vede
    cercul drept un inel de obiecte si alearga dupa el la nesfarsit. Exact asta
    s-a intamplat in joc.
    """
    import numpy as np

    cadru = make_frame(nodes=0)
    # Un punct pe inel, la raza 100 de centru, si unul inauntru.
    cadru[215:225, 295:305] = (0, 220, 220)   # (300, 220) -> la 122 de centru
    cadru[145:155, 245:255] = (0, 220, 220)   # (250, 150) -> la 50 de centru

    fara = find_loot(cadru, GALBEN, CENTRU, min_area=50)
    cu = find_loot(cadru, GALBEN, CENTRU, min_area=50, exclude_ring=(122.0, 12.0))

    assert len(fara) == 2
    assert len(cu) == 1
    assert abs(cu[0].center[0] - 250) < 6, "trebuia sa ramana cel dinauntru"


def test_excluderea_inelului_nu_atinge_restul():
    cadru = make_frame(nodes=3)
    toate = find_loot(cadru, GALBEN, CENTRU, min_area=100)
    cu_inel = find_loot(cadru, GALBEN, CENTRU, min_area=100, exclude_ring=(500.0, 12.0))

    assert len(cu_inel) == len(toate)
