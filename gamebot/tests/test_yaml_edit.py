"""Editarea profilului fara pierderea comentariilor."""

import yaml

from gamebot.core import yaml_edit

PROFIL = """\
# Profil de test
name: test
monitor: 1

combat:
  mode: aim             # aim sau target
  engage_radius: 260    # pixeli
  only_when_blocking: true
  abilities: []

safety:
  kill_key: f12
"""


def citeste(text: str) -> dict:
    return yaml.safe_load(text)


def test_schimba_o_valoare_si_pastreaza_comentariul():
    rezultat = yaml_edit.set_value(PROFIL, "combat", "engage_radius", 400)

    # Alinierea se normalizeaza la doua spatii; comentariul e ce conteaza.
    assert "engage_radius: 400  # pixeli" in rezultat
    assert citeste(rezultat)["combat"]["engage_radius"] == 400


def test_comentariile_din_fisier_raman_toate():
    rezultat = yaml_edit.set_value(PROFIL, "combat", "mode", "target")

    assert "# Profil de test" in rezultat
    assert "# aim sau target" in rezultat
    assert citeste(rezultat)["combat"]["mode"] == "target"


def test_booleanul_se_scrie_in_forma_yaml():
    rezultat = yaml_edit.set_value(PROFIL, "combat", "only_when_blocking", False)

    assert "only_when_blocking: false" in rezultat
    assert citeste(rezultat)["combat"]["only_when_blocking"] is False


def test_cheie_de_la_radacina():
    rezultat = yaml_edit.set_value(PROFIL, None, "monitor", 2)
    assert citeste(rezultat)["monitor"] == 2


def test_cheia_lipsa_se_adauga_in_sectiune():
    rezultat = yaml_edit.set_value(PROFIL, "combat", "global_cooldown", 1.2)

    date = citeste(rezultat)
    assert date["combat"]["global_cooldown"] == 1.2
    # Nu trebuie sa aterizeze in sectiunea urmatoare.
    assert "kill_key" in date["safety"]


def test_sectiunea_lipsa_se_creeaza():
    rezultat = yaml_edit.set_value(PROFIL, "mount", "retry_seconds", 30)
    assert citeste(rezultat)["mount"]["retry_seconds"] == 30


def test_nu_confunda_o_cheie_cu_alta_din_alta_sectiune():
    """`kill_key` din safety nu trebuie atins cand scriem in combat."""
    rezultat = yaml_edit.set_value(PROFIL, "combat", "kill_key", "x")

    date = citeste(rezultat)
    assert date["safety"]["kill_key"] == "f12"
    assert date["combat"]["kill_key"] == "x"


def test_sirul_gol_ramane_sir():
    rezultat = yaml_edit.set_value(PROFIL, "combat", "mode", "")
    assert citeste(rezultat)["combat"]["mode"] == ""


def test_diezul_dintr_o_valoare_nu_e_luat_drept_comentariu():
    text = 'culori:\n  fundal: "#ff0000"  # rosu\n'
    rezultat = yaml_edit.set_value(text, "culori", "fundal", "#00ff00")

    assert citeste(rezultat)["culori"]["fundal"] == "#00ff00"
    assert "# rosu" in rezultat


def test_mai_multe_schimbari_deodata():
    rezultat = yaml_edit.set_many(PROFIL, [
        ("combat", "mode", "target"),
        ("combat", "engage_radius", 150),
        ("safety", "kill_key", "f8"),
    ])

    date = citeste(rezultat)
    assert date["combat"]["mode"] == "target"
    assert date["combat"]["engage_radius"] == 150
    assert date["safety"]["kill_key"] == "f8"


def test_profilul_real_ramane_valid_dupa_editare():
    from pathlib import Path

    cale = Path(__file__).resolve().parents[1] / "profiles" / "drakensang.yaml"
    original = cale.read_text(encoding="utf-8")

    rezultat = yaml_edit.set_many(original, [
        ("combat", "engage_radius", 320),
        ("combat", "only_when_blocking", False),
        ("safety", "max_runtime_minutes", 45),
    ])

    date = citeste(rezultat)
    assert date["combat"]["engage_radius"] == 320
    assert date["combat"]["only_when_blocking"] is False
    assert date["safety"]["max_runtime_minutes"] == 45
    # Documentatia din profil trebuie sa supravietuiasca.
    assert original.count("#") - 2 <= rezultat.count("#") <= original.count("#")
