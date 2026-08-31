"""Franele: oprire, detectie de blocaj, limite de sesiune."""

import time

from gamebot.core.safety import KillSwitch, SessionGuard, Watchdog, WatchdogConfig
from gamebot.tests.conftest import make_frame


def test_kill_switch_opreste_si_anunta():
    apelat = []
    kill = KillSwitch(on_stop=lambda: apelat.append(True))

    assert kill.running()
    kill.stop()

    assert kill.stopped and not kill.running()
    assert apelat == [True]


def test_kill_switch_nu_anunta_de_doua_ori():
    apelat = []
    kill = KillSwitch(on_stop=lambda: apelat.append(True))
    kill.stop()
    kill.stop()
    assert len(apelat) == 1


def test_pauza_opreste_rularea_dar_nu_e_oprire():
    kill = KillSwitch()
    kill.toggle_pause()

    assert kill.paused and not kill.running()
    assert not kill.stopped

    kill.toggle_pause()
    assert kill.running()


def test_watchdog_vede_ecranul_inghetat():
    watchdog = Watchdog(WatchdogConfig(stuck_seconds=0.2))
    frame = make_frame()

    watchdog.observe_frame(frame)
    watchdog.observe_frame(frame.copy())
    time.sleep(0.25)
    watchdog.observe_frame(frame.copy())

    assert watchdog.is_stuck()
    assert "blocat" in (watchdog.should_abort() or "")


def test_watchdog_se_linisteste_cand_ecranul_se_schimba():
    watchdog = Watchdog(WatchdogConfig(stuck_seconds=0.2))
    watchdog.observe_frame(make_frame(1.0))
    time.sleep(0.25)
    watchdog.observe_frame(make_frame(0.2, nodes=3))

    assert not watchdog.is_stuck()
    assert watchdog.should_abort() is None


def test_watchdog_opreste_dupa_prea_multe_morti():
    watchdog = Watchdog(WatchdogConfig(max_deaths=2))
    watchdog.observe_frame(make_frame())

    watchdog.record_death()
    assert watchdog.should_abort() is None

    watchdog.record_death()
    assert "murit" in (watchdog.should_abort() or "")


def test_limita_de_sesiune():
    guard = SessionGuard(max_runtime_minutes=0.0)
    assert not guard.expired()  # 0 = fara limita

    limitat = SessionGuard(max_runtime_minutes=1.0)
    limitat.started_at = time.monotonic() - 120
    assert limitat.expired()


def test_pauzele_se_reprogrameaza_dupa_fiecare_pauza():
    guard = SessionGuard(work_minutes=(0.001, 0.001), break_minutes=(0.0001, 0.0001))
    time.sleep(0.1)
    assert guard.break_due()

    guard.take_break()

    assert not guard.break_due()


def test_pauza_se_intrerupe_la_oprire():
    guard = SessionGuard(work_minutes=(1, 1), break_minutes=(10, 10))
    guard._pending_break = 30.0
    kill = KillSwitch()
    kill.stop()

    inceput = time.monotonic()
    guard.take_break(interruptible=kill.running)

    assert time.monotonic() - inceput < 2.0, "pauza a ignorat oprirea"


def test_pauzele_pot_fi_dezactivate():
    guard = SessionGuard(take_breaks=False)
    guard._next_break_at = 0.0
    assert not guard.break_due()


# ------------------------------------------------- oprirea prin fisier-semnal


def test_fisierul_semnal_opreste_botul(tmp_path):
    """Fereastra cere oprirea lasand un fisier; botul iese pe drumul normal."""
    from gamebot.core.safety import StopFileWatcher

    semnal = tmp_path / ".stop"
    kill = KillSwitch()
    watcher = StopFileWatcher(semnal, kill)

    assert not watcher.check()
    assert kill.running()

    semnal.touch()

    assert watcher.check()
    assert kill.stopped


def test_fara_fisier_nu_opreste_nimic(tmp_path):
    from gamebot.core.safety import StopFileWatcher

    kill = KillSwitch()
    StopFileWatcher(tmp_path / "nu_exista", kill).check()
    assert kill.running()


def test_firul_de_supraveghere_reactioneaza(tmp_path):
    from gamebot.core.safety import StopFileWatcher

    semnal = tmp_path / ".stop"
    kill = KillSwitch()
    watcher = StopFileWatcher(semnal, kill, interval=0.05).start()
    try:
        semnal.touch()
        for _ in range(40):
            if kill.stopped:
                break
            time.sleep(0.05)
        assert kill.stopped, "supraveghetorul n-a vazut fisierul"
    finally:
        watcher.close()
