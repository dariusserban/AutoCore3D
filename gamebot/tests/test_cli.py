"""Linia de comanda: optiunile trebuie sa mearga in ambele pozitii.

argparse cere implicit ca optiunile parserului principal sa vina inaintea
subcomenzii. Forma naturala - `check --profile X` - esua cu "unrecognized
arguments", desi asa o scrie orice om si asa o cheama si bot.bat.
"""

import pytest

from gamebot.main import build_parser


def parse(*argv):
    return build_parser().parse_args(list(argv))


def test_profilul_merge_dupa_comanda():
    args = parse("check", "--profile", "profiles/al_meu.yaml")
    assert args.command == "check"
    assert args.profile == "profiles/al_meu.yaml"


def test_profilul_merge_inainte_de_comanda():
    args = parse("--profile", "profiles/al_meu.yaml", "check")
    assert args.profile == "profiles/al_meu.yaml"


def test_valoarea_data_inainte_nu_e_stearsa_de_subcomanda():
    """Capcana clasica: subparserul isi pune valoarea implicita peste a ta."""
    args = parse("--profile", "inainte.yaml", "routes")
    assert args.profile == "inainte.yaml"


def test_fara_profil_ramane_cel_implicit():
    assert parse("routes").profile.endswith("exemplu.yaml")


def test_verbose_merge_in_ambele_pozitii():
    assert parse("-v", "routes").verbose
    assert parse("routes", "-v").verbose
    assert not parse("routes").verbose


def test_templates_merge_dupa_comanda():
    assert parse("check", "--templates", "sabloane").templates == "sabloane"


@pytest.mark.parametrize("comanda", ["record", "run", "check", "learn", "routes", "calibrate"])
def test_toate_comenzile_accepta_optiunile_comune(comanda):
    """Fiecare subcomanda trebuie sa stie de --profile, nu doar unele."""
    argumente = {
        "record": ["--name", "x"],
        "run": [],
        "check": [],
        "learn": ["--route", "x"],
        "routes": [],
        "calibrate": ["region", "--name", "x"],
    }[comanda]
    args = parse(comanda, *argumente, "--profile", "p.yaml")
    assert args.profile == "p.yaml"


def test_optiunile_proprii_ale_comenzii_raman_intacte():
    args = parse("run", "--route", "r", "--dry-run", "--speed", "1.5", "--profile", "p.yaml")
    assert args.route == "r" and args.dry_run and args.speed == 1.5
    assert args.profile == "p.yaml"
