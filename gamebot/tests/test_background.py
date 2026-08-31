"""Modul de fundal: traducerea tastelor si interfata backend-ului.

Partile care ating Windows nu pot fi testate aici, dar traducerea numelor de
taste in coduri virtuale poate - si acolo se strecoara greselile: o tasta
netradusa inseamna o abilitate care nu se apasa niciodata, in tacere.
"""

import pytest

from gamebot.core.background import PostMessageBackend, WindowCapture, vk_code


@pytest.mark.parametrize("nume,cod", [
    ("1", 0x31), ("9", 0x39),
    ("w", 0x57), ("W", 0x57),
    ("space", 0x20), ("enter", 0x0D), ("escape", 0x1B), ("tab", 0x09),
    ("f1", 0x70), ("f5", 0x74), ("f12", 0x7B),
])
def test_traduce_tastele_uzuale(nume, cod):
    assert vk_code(nume) == cod


def test_tastele_necunoscute_nu_arunca():
    """Mai bine o tasta ignorata decat botul oprit de o exceptie in lupta."""
    assert vk_code("inexistenta") is None
    assert vk_code("") is None
    assert vk_code("f99") is None


def test_toate_tastele_dintr_o_rotatie_tipica_sunt_traduse():
    for tasta in ["1", "2", "3", "4", "5", "q", "e", "r", "space"]:
        assert vk_code(tasta) is not None, f"'{tasta}' nu ar fi apasata niciodata"


def test_backend_ul_are_metodele_cerute_de_controller():
    """Trebuie sa poata inlocui backend-ul obisnuit fara ca restul sa stie."""
    for metoda in ("move_to", "mouse_down", "mouse_up", "key_down", "key_up",
                   "scroll", "position"):
        assert callable(getattr(PostMessageBackend, metoda, None)), metoda


def test_captura_are_interfata_de_captura():
    for metoda in ("grab", "grab_cached", "save", "close", "monitor"):
        assert hasattr(WindowCapture, metoda), metoda


def test_pe_alt_sistem_refuza_explicit():
    """Pe Linux/macOS trebuie sa spuna clar ca nu exista, nu sa crape ciudat."""
    import platform

    if platform.system() == "Windows":
        pytest.skip("test pentru sistemele fara suport")
    with pytest.raises(RuntimeError, match="Windows"):
        WindowCapture(0)
