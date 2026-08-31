"""Punctul de intrare. Ruleaza-l din radacina repo-ului:

    python -m gamebot.main record   --profile gamebot/profiles/exemplu.yaml --name padure
    python -m gamebot.main run      --profile gamebot/profiles/exemplu.yaml --route routes/padure
    python -m gamebot.main check    --profile gamebot/profiles/exemplu.yaml
    python -m gamebot.main calibrate region --name minimap
"""

from __future__ import annotations

import argparse
import logging
import platform
import sys
import time
from pathlib import Path
from typing import Optional

from .behaviors import ALL_BEHAVIORS
from .core.capture import ScreenCapture
from .core.config import Profile
from .core.engine import BehaviorEngine, BotContext
from .core.input_ctl import InputController
from .core.navigation import Localizer, RoutePlayer
from .core.recorder import RouteRecorder
from .core.route import Route
from .core.safety import KillSwitch, SessionGuard, StopFileWatcher, Watchdog, WatchdogConfig
from .core.vision import TemplateLibrary

PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULT_PROFILE = PACKAGE_DIR / "profiles" / "exemplu.yaml"
DEFAULT_ROUTES = PACKAGE_DIR / "routes"
DEFAULT_TEMPLATES = PACKAGE_DIR / "templates"

log = logging.getLogger("gamebot")


def enable_dpi_awareness() -> None:
    """Spune Windows-ului ca stim de scalarea ecranului.

    Fara asta, un proces Python pe un ecran cu scalare 125% primeste coordonate
    "virtualizate": mss captureaza la rezolutia fizica, dar clicurile pleaca in
    coordonate scalate. Rezultatul e ca botul vede corect si da click alaturi,
    cu atat mai departe cu cat esti mai jos pe ecran - genul de defect care pare
    ca "nu merge detectia", desi detectia e buna.

    Pe alte sisteme decat Windows nu are ce face.
    """
    if platform.system() != "Windows":
        return
    try:
        import ctypes

        # 2 = PER_MONITOR_DPI_AWARE. Exista din Windows 8.1.
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()  # varianta veche
        except Exception:
            log.debug("Nu am putut seta constientizarea DPI; scalarea poate deranja.")


def warn_if_black(frame, capture=None) -> bool:
    """Avertizeaza daca ecranul capturat e negru.

    Se intampla cand jocul ruleaza in fullscreen exclusiv: DirectX preia
    ecranul si captura iese neagra. Solutia e sa pui jocul pe fereastra sau
    fullscreen fara margini.
    """
    if frame is None or float(frame.mean()) > 2.0:
        return False
    print("\nATENTIE: captura de ecran e complet neagra.")
    print("Aproape sigur jocul e in fullscreen EXCLUSIV. Treci-l pe 'fereastra'")
    print("sau 'fullscreen fara margini' din setarile grafice si incearca iar.\n")
    return True


def setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        handlers=[
            logging.FileHandler(PACKAGE_DIR / "gamebot.log", encoding="utf-8"),
            logging.StreamHandler(sys.stdout) if verbose else logging.NullHandler(),
        ],
    )


def countdown(seconds: int, message: str = "Pornesc") -> None:
    """Iti da timp sa comuti pe fereastra jocului."""
    print(f"{message} in {seconds} secunde - comuta pe joc acum.")
    for remaining in range(seconds, 0, -1):
        print(f"  {remaining}...", end="\r", flush=True)
        time.sleep(1)
    print("  start!            ")


# --------------------------------------------------------------- inregistrare


def cmd_record(args: argparse.Namespace) -> int:
    profile = Profile.load(args.profile) if Path(args.profile).exists() else Profile()
    output = Path(args.output or (DEFAULT_ROUTES / args.name))

    if output.exists() and not args.force:
        print(f"Ruta '{output}' exista deja. Foloseste --force ca sa o rescrii.")
        return 1

    capture = None
    anchor_region = profile.region("minimap")
    try:
        capture = ScreenCapture(profile.monitor)
        if anchor_region is None:
            print("Profilul nu defineste `regions.minimap`. Inregistrez fara ancore,")
            print("deci botul nu va putea sa isi verifice pozitia pe traseu.")
            print("Ruleaza intai: python -m gamebot.main calibrate region --name minimap\n")
    except Exception as exc:
        print(f"Fara captura de ecran ({exc}); inregistrez doar input-ul.")

    setari = profile.section("record")
    try:
        recorder = RouteRecorder(
            name=args.name,
            output_dir=output,
            capture=capture,
            anchor_region=anchor_region,
            hotkeys=setari.get("hotkeys"),
            pause_key=str(setari.get("pause_key", "f9")),
            stop_key=str(setari.get("stop_key", "f10")),
            record_mouse_moves=not args.no_mouse,
        )
    except ValueError as exc:
        print(f"Eroare in profil: {exc}")
        return 1
    route = recorder.run()

    if capture:
        capture.close()
    return 0 if route.waypoints else 1


# ---------------------------------------------------------------------- rulare


def build_context(args: argparse.Namespace, profile: Profile, capture, kill_switch: KillSwitch) -> BotContext:
    """Asambleaza toate piesele intr-un context gata de rulat."""
    controller = InputController(
        dry_run=args.dry_run,
        click_radius=int(profile.section("input").get("click_radius", 3)),
        move_speed=float(profile.section("input").get("move_speed", 1.0)),
    )
    templates = TemplateLibrary(args.templates or DEFAULT_TEMPLATES)

    safety = profile.safety
    watchdog = Watchdog(
        WatchdogConfig(
            stuck_seconds=float(safety.get("stuck_seconds", 90)),
            max_deaths=int(safety.get("max_deaths", 3)),
        )
    )
    session = SessionGuard(
        max_runtime_minutes=float(args.max_minutes if args.max_minutes is not None else safety.get("max_runtime_minutes", 0)),
        take_breaks=bool(safety.get("breaks", True)),
    )

    player: Optional[RoutePlayer] = None
    if args.route:
        route = Route.load(args.route)
        print(route.describe())
        localizer = Localizer(
            route, capture, profile.region("minimap"),
            threshold=profile.threshold("anchor_match", 0.72),
        )
        player = RoutePlayer(
            route,
            controller,
            localizer,
            speed=args.speed,
            should_continue=kill_switch.running,
            capture=capture,
            templates=templates,
        )
        monitor = capture.monitor
        player.set_screen(monitor.width, monitor.height)

    return BotContext(
        profile=profile,
        capture=capture,
        controller=controller,
        templates=templates,
        kill_switch=kill_switch,
        watchdog=watchdog,
        session=session,
        player=player,
    )


def cmd_run(args: argparse.Namespace) -> int:
    profile = Profile.load(args.profile)
    print(f"Profil: {profile.name}")

    problems = profile.missing_pieces()
    if problems:
        print("\nAvertismente de configurare:")
        for problem in problems:
            print(f"  - {problem}")
        print()

    if args.dry_run:
        print(">>> MOD DE PROBA: nu se trimite niciun input catre joc. <<<\n")

    capture = ScreenCapture(profile.monitor)
    kill_switch = KillSwitch(
        key=str(profile.safety.get("kill_key", "f12")),
    ).start(pause_key=str(profile.safety.get("pause_key", "f11")))

    opritor: Optional[StopFileWatcher] = None
    if getattr(args, "stop_file", None):
        # Fereastra aplicatiei ne cere oprirea lasand fisierul asta pe disc.
        opritor = StopFileWatcher(args.stop_file, kill_switch).start()

    ctx = build_context(args, profile, capture, kill_switch)
    # Kill switch-ul trebuie sa elibereze tastele imediat, nu dupa ce bucla
    # principala apuca sa observe oprirea.
    kill_switch.on_stop = ctx.controller.release_all

    engine = BehaviorEngine(ctx, [cls() for cls in ALL_BEHAVIORS], tick=float(args.tick))

    ctx.refresh()
    if warn_if_black(ctx.frame):
        ctx.controller.release_all()
        kill_switch.close()
        capture.close()
        return 1

    if ctx.player is not None and not args.from_start:
        ctx.player.jump_to_nearest()

    countdown(args.delay)

    reason = "necunoscut"
    try:
        reason = engine.run_forever()
    except KeyboardInterrupt:
        reason = "intrerupt de la tastatura (Ctrl+C)"
    finally:
        ctx.controller.release_all()
        kill_switch.close()
        if opritor is not None:
            opritor.close()
        capture.close()

    print(f"\nOprit: {reason}")
    print(ctx.stats.summary())
    return 0


# ----------------------------------------------------------------- diagnostic


def cmd_check(args: argparse.Namespace) -> int:
    """Citeste ecranul o data si arata ce intelege botul din el.

    E cel mai rapid mod de a-ti da seama daca ai gresit o regiune sau o culoare:
    daca aici scrie ca ai 0% viata cand tu ai bara plina, profilul e gresit, nu
    botul.
    """
    profile = Profile.load(args.profile)
    print(f"Profil: {profile.name}\n")

    problems = profile.missing_pieces()
    if problems:
        print("Lipsuri in profil:")
        for problem in problems:
            print(f"  - {problem}")
    else:
        print("Profilul pare complet.")

    print("\nRegiuni definite:")
    for name, region in profile.regions.items():
        print(f"  {name:<20} {region.width}x{region.height} la ({region.left}, {region.top})")

    templates = TemplateLibrary(args.templates or DEFAULT_TEMPLATES)
    print(f"\nSabloane disponibile: {', '.join(templates.available()) or 'niciunul'}")

    countdown(args.delay, "Citesc ecranul")

    capture = ScreenCapture(profile.monitor)
    kill_switch = KillSwitch()
    ctx = BotContext(
        profile=profile,
        capture=capture,
        controller=InputController(dry_run=True),
        templates=templates,
        kill_switch=kill_switch,
        watchdog=Watchdog(),
        session=SessionGuard(),
    )
    ctx.refresh()
    warn_if_black(ctx.frame)

    def as_percent(value: Optional[float]) -> str:
        return "nedefinit" if value is None else f"{value*100:5.1f}%"

    print("\nCe vede botul acum:")
    print(f"  viata personajului : {as_percent(ctx.health)}")
    print(f"  viata tintei       : {as_percent(ctx.target_health)}")
    print(f"  tinta selectata    : {'da' if ctx.has_target() else 'nu'}")
    print(f"  mob-uri detectate  : {len(ctx.find_blobs('enemy_nameplate', min_area=40))}")
    print(f"  noduri detectate   : {len(ctx.find_blobs('resource_node', min_area=80))}")

    snapshot = Path(args.templates or DEFAULT_TEMPLATES).parent / "check_snapshot.png"
    capture.save(snapshot)
    print(f"\nCaptura salvata pentru comparatie: {snapshot}")
    capture.close()
    return 0


def cmd_learn(args: argparse.Namespace) -> int:
    """Deduce rotatia de abilitati din luptele inregistrate pe o ruta."""
    from .core import learning

    profile = Profile.load(args.profile) if Path(args.profile).exists() else Profile()
    route = Route.load(args.route)
    print(route.describe())

    # Tastele cu rost cunoscut apar si ele in lupta, dar nu sunt atacuri.
    cunoscute = [
        profile.key(name)
        for name in ("heal", "loot", "interact", "target_next", "mount", "escape",
                     "forward", "back", "left", "right", "jump")
    ]
    kinds = ("combat", "travel") if args.include_travel else ("combat",)
    rotation = learning.analyze(route, kinds=kinds, exclude=cunoscute,
                                min_presses=args.min_presses)

    print()
    print(rotation.describe())

    if not rotation.abilities:
        print("\nNu am ce invata. Marcheaza zonele de lupta cu F6 la inregistrare")
        print("si bate-te acolo cateva minute, folosind abilitatile ca de obicei.")
        return 1

    print("\nAdauga in profil, sub `combat:`\n")
    for ability in rotation.abilities:
        print(f"    - {{key: \"{ability.key}\", cooldown: {ability.cooldown:.1f}}}")
    print(f"\n  global_cooldown: {rotation.global_cooldown:.2f}\n")

    if args.write:
        _write_rotation(Path(args.profile), rotation)
    else:
        print("Copiaza blocul de mai sus in profil, sau ruleaza din nou cu --write.")
    return 0


def _write_rotation(profile_path: Path, rotation) -> None:
    """Scrie rotatia invatata direct in profil, cu o copie de siguranta.

    Scrierea trece prin PyYAML, care nu pastreaza comentariile din fisier. De
    aceea salvam intai originalul ca `.bak` si spunem clar ce s-a pierdut -
    daca tii la comentarii, copiaza blocul de mai sus de mana.
    """
    import yaml

    data = yaml.safe_load(profile_path.read_text(encoding="utf-8")) or {}
    data.setdefault("combat", {}).update(rotation.as_profile_section())

    backup = profile_path.with_suffix(profile_path.suffix + ".bak")
    backup.write_text(profile_path.read_text(encoding="utf-8"), encoding="utf-8")
    profile_path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    print(f"Scris in {profile_path} (copie a originalului in {backup.name}).")
    print("Atentie: comentariile din profil s-au pierdut la rescriere.")


def cmd_gui(args: argparse.Namespace) -> int:
    """Deschide fereastra. Toata logica ramane in comenzile de mai sus."""
    from .ui.app import porneste

    return porneste(PACKAGE_DIR.parent)


def cmd_routes(args: argparse.Namespace) -> int:
    directory = Path(args.dir or DEFAULT_ROUTES)
    if not directory.exists():
        print(f"Nu exista {directory} - nu ai inregistrat inca nicio ruta.")
        return 0
    found = 0
    for candidate in sorted(directory.iterdir()):
        if (candidate / "route.json").exists():
            print(f"  {candidate.name:<24} {Route.load(candidate).describe()}")
            found += 1
    if not found:
        print(f"Niciun traseu in {directory}.")
    return 0


def cmd_calibrate(args: argparse.Namespace) -> int:
    from .tools import calibrate

    profile = Profile.load(args.profile) if Path(args.profile).exists() else Profile()
    monitor = profile.monitor

    if args.what == "region":
        calibrate.calibrate_region(args.name, monitor)
    elif args.what == "template":
        calibrate.calibrate_template(args.name, args.templates or DEFAULT_TEMPLATES, monitor)
    elif args.what == "color":
        calibrate.calibrate_color(args.name, monitor)
    return 0


# ------------------------------------------------------------------ argumente


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gamebot",
        description="Bot de farmat prin vedere pe ecran si input simulat.",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="loguri detaliate in consola")
    parser.add_argument("--profile", default=str(DEFAULT_PROFILE), help="fisierul YAML de profil")
    parser.add_argument("--templates", default=None, help="directorul cu sabloane PNG")

    # Aceleasi optiuni, acceptate si DUPA comanda. Fara asta, argparse cere ca
    # `--profile` sa vina neaparat inaintea subcomenzii, iar forma naturala
    # (`check --profile X`) esueaza cu "unrecognized arguments" - exact felul
    # in care le scrie orice om si in care le cheama si bot.bat.
    #
    # SUPPRESS e esential: fara el, subparserul ar pune la loc valoarea
    # implicita peste ce ai dat inaintea comenzii, si optiunea s-ar pierde
    # tacut in ordinea cealalta.
    comune = argparse.ArgumentParser(add_help=False)
    comune.add_argument("-v", "--verbose", action="store_true", default=argparse.SUPPRESS,
                        help="loguri detaliate in consola")
    comune.add_argument("--profile", default=argparse.SUPPRESS, help="fisierul YAML de profil")
    comune.add_argument("--templates", default=argparse.SUPPRESS,
                        help="directorul cu sabloane PNG")

    sub = parser.add_subparsers(dest="command", required=True, parser_class=lambda **kw:
                                argparse.ArgumentParser(parents=[comune], **kw))

    rec = sub.add_parser("record", help="inregistreaza o ruta jucand tu")
    rec.add_argument("--name", required=True, help="numele rutei")
    rec.add_argument("--output", default=None, help="unde se salveaza (implicit gamebot/routes/<name>)")
    rec.add_argument("--force", action="store_true", help="rescrie ruta daca exista")
    rec.add_argument("--no-mouse", action="store_true", help="nu inregistra miscarile mouse-ului")
    rec.set_defaults(func=cmd_record)

    run = sub.add_parser("run", help="porneste botul")
    run.add_argument("--route", default=None, help="directorul rutei inregistrate")
    run.add_argument("--dry-run", action="store_true", help="decide, dar nu trimite input")
    run.add_argument("--speed", type=float, default=1.0, help="viteza de redare a rutei (0.5-2.0)")
    run.add_argument("--tick", type=float, default=0.25, help="pauza intre cicluri de decizie")
    run.add_argument("--delay", type=int, default=5, help="secunde de asteptare inainte de start")
    run.add_argument("--max-minutes", type=float, default=None, help="opreste dupa atatea minute")
    run.add_argument("--from-start", action="store_true", help="incepe de la reperul 0, fara localizare")
    run.add_argument("--stop-file", default=None,
                     help="opreste-te elegant cand apare fisierul asta (folosit de fereastra)")
    run.set_defaults(func=cmd_run)

    gui = sub.add_parser("gui", help="deschide fereastra aplicatiei")
    gui.set_defaults(func=cmd_gui)

    check = sub.add_parser("check", help="verifica profilul si arata ce vede botul")
    check.add_argument("--delay", type=int, default=5)
    check.set_defaults(func=cmd_check)

    learn = sub.add_parser("learn", help="deduce rotatia de abilitati din luptele inregistrate")
    learn.add_argument("--route", required=True, help="directorul rutei inregistrate")
    learn.add_argument("--write", action="store_true", help="scrie rezultatul direct in profil")
    learn.add_argument("--include-travel", action="store_true",
                       help="analizeaza si segmentele de drum, nu doar cele de lupta")
    learn.add_argument("--min-presses", type=int, default=3,
                       help="cate apasari sunt necesare ca o tasta sa conteze")
    learn.set_defaults(func=cmd_learn)

    routes = sub.add_parser("routes", help="listeaza rutele inregistrate")
    routes.add_argument("--dir", default=None)
    routes.set_defaults(func=cmd_routes)

    cal = sub.add_parser("calibrate", help="masoara regiuni, culori si sabloane")
    cal.add_argument("what", choices=["region", "template", "color"])
    cal.add_argument("--name", required=True, help="numele elementului calibrat")
    cal.set_defaults(func=cmd_calibrate)

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    setup_logging(args.verbose)
    enable_dpi_awareness()
    try:
        return args.func(args)
    except FileNotFoundError as exc:
        print(f"Eroare: {exc}")
        return 1
    except RuntimeError as exc:
        print(f"Eroare: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
