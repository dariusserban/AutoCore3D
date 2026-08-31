"""Fereastra aplicatiei: aceleasi comenzi, dar cu butoane in loc de terminal.

Fereastra nu contine logica botului. Fiecare buton porneste `gamebot.main` ca
proces separat si ii afiseaza iesirea in jurnal. Motivul e practic: captura de
ecran, ascultatorii de tastatura si ferestrele OpenCV de calibrare se poarta
prost cand impart firul de executie cu bucla de evenimente Tk. Asa, daca
fereastra merge, tot ce e sub ea merge deja - e acelasi cod rulat de linia de
comanda, cu aceleasi teste in spate.

Oprirea nu omoara procesul. Ii lasa un fisier-semnal pe care botul il verifica
si iese pe drumul normal, eliberand tastele. Un proces omorat brutal poate lasa
o tasta apasata, iar personajul alearga in perete dupa ce tu ai inchis totul.
"""

from __future__ import annotations

import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

try:
    import tkinter as tk
    from tkinter import messagebox, ttk
except Exception as exc:  # pragma: no cover
    raise SystemExit(
        "Nu gasesc tkinter. Reinstaleaza Python de la python.org "
        "(instalarea standard il include).\n"
        f"Detaliu: {exc}"
    )

from ..core import yaml_edit

# Paleta inchisa, ca sa nu ardem ochii langa un joc intunecat.
FUNDAL = "#15161b"
PANOU = "#1d1f27"
TEXT = "#d8dae3"
TEXT_SEC = "#8b8fa3"
ACCENT = "#7c5cff"
VERDE = "#3fb950"
ROSU = "#f04747"

REGIUNI_UZUALE = ["minimap", "health_bar", "target_health_bar", "cast_bar"]
CULORI_UZUALE = ["enemy_nameplate", "health", "resource_node", "cast_bar"]


class GamebotApp:
    def __init__(self, root: tk.Tk, repo_root: Path) -> None:
        self.root = root
        self.repo = repo_root
        self.proces: subprocess.Popen | None = None
        self.jurnal_coada: queue.Queue[str] = queue.Queue()
        self.stop_file = self.repo / "gamebot" / ".stop"
        self.actiune_curenta = ""

        root.title("gamebot")
        root.geometry("940x660")
        root.configure(bg=FUNDAL)
        root.protocol("WM_DELETE_WINDOW", self._la_inchidere)

        self._stil()
        self._bara_sus()
        self._taburi()
        self._bara_jos()

        self._reincarca_liste()
        self._citeste_profil_in_formular()
        self.root.after(120, self._pompeaza_jurnalul)

    # ------------------------------------------------------------- aspect

    def _stil(self) -> None:
        stil = ttk.Style()
        try:
            stil.theme_use("clam")
        except tk.TclError:
            pass
        stil.configure("TFrame", background=FUNDAL)
        stil.configure("Panou.TFrame", background=PANOU)
        stil.configure("TLabel", background=FUNDAL, foreground=TEXT)
        stil.configure("Sec.TLabel", background=FUNDAL, foreground=TEXT_SEC)
        stil.configure("TCheckbutton", background=FUNDAL, foreground=TEXT)
        stil.configure("TNotebook", background=FUNDAL, borderwidth=0)
        stil.configure("TNotebook.Tab", background=PANOU, foreground=TEXT_SEC, padding=(16, 8))
        stil.map("TNotebook.Tab", background=[("selected", FUNDAL)],
                 foreground=[("selected", TEXT)])
        stil.configure("TButton", background=PANOU, foreground=TEXT, borderwidth=0, padding=8)
        stil.map("TButton", background=[("active", "#2a2d38")])
        stil.configure("Accent.TButton", background=ACCENT, foreground="#ffffff", padding=10)
        stil.map("Accent.TButton", background=[("active", "#6a4ce0")])

    def _bara_sus(self) -> None:
        bara = ttk.Frame(self.root, padding=(14, 12, 14, 6))
        bara.pack(fill="x")

        ttk.Label(bara, text="gamebot", font=("Segoe UI", 15, "bold")).pack(side="left")
        ttk.Label(bara, text="  autopilot pentru Drakensang Online",
                  style="Sec.TLabel").pack(side="left")

        self.eticheta_stare = ttk.Label(bara, text="oprit", style="Sec.TLabel",
                                        font=("Segoe UI", 10, "bold"))
        self.eticheta_stare.pack(side="right")

        rand = ttk.Frame(self.root, padding=(14, 0, 14, 8))
        rand.pack(fill="x")

        ttk.Label(rand, text="Profil:").pack(side="left")
        self.profil = ttk.Combobox(rand, width=26, state="readonly")
        self.profil.pack(side="left", padx=(6, 16))
        self.profil.bind("<<ComboboxSelected>>", lambda e: self._citeste_profil_in_formular())

        ttk.Label(rand, text="Ruta:").pack(side="left")
        self.ruta = ttk.Combobox(rand, width=26, state="readonly")
        self.ruta.pack(side="left", padx=(6, 16))

        ttk.Button(rand, text="Reincarca", command=self._reincarca_liste).pack(side="left")

    def _taburi(self) -> None:
        self.taburi = ttk.Notebook(self.root)
        self.taburi.pack(fill="both", expand=True, padx=14, pady=(0, 8))

        self._tab_autopilot()
        self._tab_lupta()
        self._tab_calibrare()
        self._tab_jurnal()

    def _tab_autopilot(self) -> None:
        f = ttk.Frame(self.taburi, padding=16)
        self.taburi.add(f, text="AUTOPILOT")

        ttk.Label(f, text="Invata traseul", font=("Segoe UI", 11, "bold")).grid(
            row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(f, text="Mergi tu drumul, marcheaza reperele, botul il reia dupa aceea.",
                  style="Sec.TLabel").grid(row=1, column=0, columnspan=3, sticky="w", pady=(0, 10))

        ttk.Label(f, text="Nume ruta noua:").grid(row=2, column=0, sticky="w")
        self.ruta_noua = ttk.Entry(f, width=24)
        self.ruta_noua.grid(row=2, column=1, sticky="w", padx=8)
        ttk.Button(f, text="Inregistreaza", command=self._inregistreaza).grid(row=2, column=2, sticky="w")

        ttk.Label(f, text="F4 portal   F5 drum   F6 zona de lupta   F8 vendor   F10 stop",
                  style="Sec.TLabel").grid(row=3, column=0, columnspan=3, sticky="w", pady=(6, 16))

        ttk.Label(f, text="Invata abilitatile", font=("Segoe UI", 11, "bold")).grid(
            row=4, column=0, columnspan=3, sticky="w")
        ttk.Label(f, text="Din luptele inregistrate pe ruta selectata sus.",
                  style="Sec.TLabel").grid(row=5, column=0, columnspan=3, sticky="w", pady=(0, 8))
        ttk.Button(f, text="Invata din ruta", command=self._invata).grid(row=6, column=0, sticky="w")
        ttk.Button(f, text="Scrie in profil", command=lambda: self._invata(scrie=True)).grid(
            row=6, column=1, sticky="w", padx=8)

        ttk.Separator(f, orient="horizontal").grid(row=7, column=0, columnspan=3,
                                                   sticky="ew", pady=18)

        ttk.Label(f, text="Rulare", font=("Segoe UI", 11, "bold")).grid(
            row=8, column=0, columnspan=3, sticky="w", pady=(0, 8))

        self.proba = tk.BooleanVar(value=False)
        ttk.Checkbutton(f, text="Proba (nu trimite input in joc)",
                        variable=self.proba).grid(row=9, column=0, columnspan=2, sticky="w")

        self.de_la_inceput = tk.BooleanVar(value=False)
        ttk.Checkbutton(f, text="Incepe de la primul reper, fara sa se localizeze",
                        variable=self.de_la_inceput).grid(row=10, column=0, columnspan=2, sticky="w")

        ttk.Label(f, text="Minute (gol = cat scrie in profil):").grid(row=11, column=0,
                                                                     sticky="w", pady=(8, 0))
        self.minute = ttk.Entry(f, width=8)
        self.minute.grid(row=11, column=1, sticky="w", padx=8, pady=(8, 0))

    def _tab_lupta(self) -> None:
        f = ttk.Frame(self.taburi, padding=16)
        self.taburi.add(f, text="LUPTA")
        self.campuri: dict[str, tuple] = {}

        def rand(nr, eticheta, cheie, sectiune, ajutor=""):
            ttk.Label(f, text=eticheta).grid(row=nr, column=0, sticky="w", pady=4)
            e = ttk.Entry(f, width=12)
            e.grid(row=nr, column=1, sticky="w", padx=8)
            if ajutor:
                ttk.Label(f, text=ajutor, style="Sec.TLabel").grid(row=nr, column=2, sticky="w")
            self.campuri[cheie] = (sectiune, cheie, e, "text")

        ttk.Label(f, text="Stil de lupta").grid(row=0, column=0, sticky="w", pady=4)
        self.mod = ttk.Combobox(f, width=10, state="readonly", values=["aim", "target"])
        self.mod.grid(row=0, column=1, sticky="w", padx=8)
        ttk.Label(f, text="aim = ARPG (DSO); target = MMO cu tinta selectata",
                  style="Sec.TLabel").grid(row=0, column=2, sticky="w")

        self.doar_in_cale = tk.BooleanVar(value=True)
        ttk.Checkbutton(f, text="Trece prin: se bate doar cu ce-i iese in cale",
                        variable=self.doar_in_cale).grid(row=1, column=0, columnspan=3,
                                                         sticky="w", pady=6)

        rand(2, "Raza de angajare", "engage_radius", "combat", "pixeli de la personaj")
        rand(3, "Raza gramezii", "cluster_radius", "combat", "cat de larg grupeaza mobii")
        rand(4, "Pauza intre abilitati", "global_cooldown", "combat", "secunde")
        rand(5, "Timp maxim pe lupta", "max_fight_seconds", "combat", "secunde")
        rand(6, "Se vindeca sub", "heal_below", "thresholds", "0.55 = 55% viata")
        rand(7, "Tasta vindecare", "heal", "keys", "")
        rand(8, "Tasta montura", "mount", "keys", "gol = nu urca deloc")

        ttk.Separator(f, orient="horizontal").grid(row=9, column=0, columnspan=3,
                                                   sticky="ew", pady=14)
        ttk.Button(f, text="Salveaza in profil", style="Accent.TButton",
                   command=self._salveaza_profil).grid(row=10, column=0, sticky="w")
        ttk.Label(f, text="Comentariile din profil se pastreaza.",
                  style="Sec.TLabel").grid(row=10, column=1, columnspan=2, sticky="w", padx=8)

    def _tab_calibrare(self) -> None:
        f = ttk.Frame(self.taburi, padding=16)
        self.taburi.add(f, text="CALIBRARE")

        ttk.Label(f, text="Fara pasul asta botul nu vede nimic.",
                  font=("Segoe UI", 11, "bold")).grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(f, text="Fiecare buton face o poza dupa 4 secunde - comuta pe joc - "
                          "apoi tragi un dreptunghi cu mouse-ul.",
                  style="Sec.TLabel").grid(row=1, column=0, columnspan=3, sticky="w", pady=(0, 14))

        ttk.Label(f, text="Regiune:").grid(row=2, column=0, sticky="w", pady=4)
        self.regiune = ttk.Combobox(f, width=22, values=REGIUNI_UZUALE)
        self.regiune.set(REGIUNI_UZUALE[0])
        self.regiune.grid(row=2, column=1, sticky="w", padx=8)
        ttk.Button(f, text="Calibreaza regiunea",
                   command=lambda: self._calibreaza("region", self.regiune.get())).grid(
            row=2, column=2, sticky="w")

        ttk.Label(f, text="Culoare:").grid(row=3, column=0, sticky="w", pady=4)
        self.culoare = ttk.Combobox(f, width=22, values=CULORI_UZUALE)
        self.culoare.set(CULORI_UZUALE[0])
        self.culoare.grid(row=3, column=1, sticky="w", padx=8)
        ttk.Button(f, text="Calibreaza culoarea",
                   command=lambda: self._calibreaza("color", self.culoare.get())).grid(
            row=3, column=2, sticky="w")

        ttk.Label(f, text="Sablon:").grid(row=4, column=0, sticky="w", pady=4)
        self.sablon = ttk.Entry(f, width=24)
        self.sablon.grid(row=4, column=1, sticky="w", padx=8)
        ttk.Button(f, text="Salveaza sablonul",
                   command=lambda: self._calibreaza("template", self.sablon.get())).grid(
            row=4, column=2, sticky="w")

        ttk.Separator(f, orient="horizontal").grid(row=5, column=0, columnspan=3,
                                                   sticky="ew", pady=18)
        ttk.Button(f, text="Verifica ce vede botul", style="Accent.TButton",
                   command=self._verifica).grid(row=6, column=0, sticky="w")
        ttk.Label(f, text="Daca aici scrie 0% viata cand bara ta e plina, profilul e gresit.",
                  style="Sec.TLabel").grid(row=6, column=1, columnspan=2, sticky="w", padx=8)

    def _tab_jurnal(self) -> None:
        f = ttk.Frame(self.taburi, padding=(12, 12))
        self.taburi.add(f, text="JURNAL")

        self.jurnal = tk.Text(f, bg="#0f1014", fg=TEXT, insertbackground=TEXT,
                              relief="flat", wrap="word", font=("Consolas", 9))
        bara = ttk.Scrollbar(f, command=self.jurnal.yview)
        self.jurnal.configure(yscrollcommand=bara.set)
        self.jurnal.pack(side="left", fill="both", expand=True)
        bara.pack(side="right", fill="y")

    def _bara_jos(self) -> None:
        bara = ttk.Frame(self.root, padding=(14, 8, 14, 14))
        bara.pack(fill="x")

        self.buton_start = ttk.Button(bara, text="PORNESTE", style="Accent.TButton",
                                      command=self._porneste)
        self.buton_start.pack(side="left")
        self.buton_stop = ttk.Button(bara, text="OPRESTE", command=self._opreste,
                                     state="disabled")
        self.buton_stop.pack(side="left", padx=8)

        ttk.Label(bara, text="F12 opreste imediat, chiar si cand jocul are focusul.   F11 pauza.",
                  style="Sec.TLabel").pack(side="right")

    # ------------------------------------------------------------- unelte

    def _cale_profil(self) -> Path:
        return self.repo / "gamebot" / "profiles" / self.profil.get()

    def _cale_ruta(self) -> Path | None:
        nume = self.ruta.get()
        return (self.repo / "gamebot" / "routes" / nume) if nume else None

    def _reincarca_liste(self) -> None:
        profile = sorted(p.name for p in (self.repo / "gamebot" / "profiles").glob("*.yaml"))
        self.profil["values"] = profile
        if profile and self.profil.get() not in profile:
            self.profil.set("drakensang.yaml" if "drakensang.yaml" in profile else profile[0])

        rute_dir = self.repo / "gamebot" / "routes"
        rute = sorted(d.name for d in rute_dir.iterdir()
                      if (d / "route.json").exists()) if rute_dir.exists() else []
        self.ruta["values"] = rute
        if rute and self.ruta.get() not in rute:
            self.ruta.set(rute[0])

    def _scrie(self, text: str) -> None:
        self.jurnal_coada.put(text)

    def _pompeaza_jurnalul(self) -> None:
        """Muta liniile din coada in caseta de text, pe firul lui Tk."""
        adaugat = False
        while True:
            try:
                self.jurnal.insert("end", self.jurnal_coada.get_nowait())
                adaugat = True
            except queue.Empty:
                break
        if adaugat:
            self.jurnal.see("end")

        if self.proces is not None and self.proces.poll() is not None:
            self._la_terminarea_procesului()

        self.root.after(120, self._pompeaza_jurnalul)

    def _ruleaza(self, argumente: list[str], titlu: str, arata_jurnalul: bool = True) -> None:
        """Porneste `gamebot.main` intr-un proces separat si ii citeste iesirea."""
        if self.proces is not None:
            messagebox.showinfo("gamebot", "Ruleaza deja ceva. Opreste intai.")
            return

        if self.stop_file.exists():
            self.stop_file.unlink()

        comanda = [sys.executable, "-m", "gamebot.main"] + argumente
        self._scrie(f"\n=== {titlu} ===\n")
        try:
            self.proces = subprocess.Popen(
                comanda, cwd=str(self.repo), stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, bufsize=1,
                encoding="utf-8", errors="replace",
            )
        except Exception as exc:
            self._scrie(f"Nu am putut porni: {exc}\n")
            return

        self.actiune_curenta = titlu
        threading.Thread(target=self._citeste_iesirea, args=(self.proces,), daemon=True).start()

        self.buton_start.configure(state="disabled")
        self.buton_stop.configure(state="normal")
        self.eticheta_stare.configure(text=titlu.lower(), foreground=VERDE)
        if arata_jurnalul:
            self.taburi.select(3)

    def _citeste_iesirea(self, proces: subprocess.Popen) -> None:
        if proces.stdout is None:
            return
        for linie in proces.stdout:
            self.jurnal_coada.put(linie)

    def _la_terminarea_procesului(self) -> None:
        cod = self.proces.returncode if self.proces else 0
        self.proces = None
        self._scrie(f"--- {self.actiune_curenta} incheiat (cod {cod}) ---\n")
        self.buton_start.configure(state="normal")
        self.buton_stop.configure(state="disabled")
        self.eticheta_stare.configure(text="oprit", foreground=TEXT_SEC)
        if self.stop_file.exists():
            self.stop_file.unlink()
        self._reincarca_liste()

    # ------------------------------------------------------------- actiuni

    def _porneste(self) -> None:
        ruta = self._cale_ruta()
        if ruta is None:
            messagebox.showwarning("gamebot", "N-ai nicio ruta. Inregistreaza intai una.")
            return

        argumente = ["run", "--profile", str(self._cale_profil()), "--route", str(ruta),
                     "--stop-file", str(self.stop_file)]
        if self.proba.get():
            argumente.append("--dry-run")
        if self.de_la_inceput.get():
            argumente.append("--from-start")
        minute = self.minute.get().strip()
        if minute:
            argumente += ["--max-minutes", minute]

        self._ruleaza(argumente, "Rulare")

    def _opreste(self) -> None:
        """Cere oprirea prin fisier-semnal, ca botul sa elibereze tastele."""
        if self.proces is None:
            return
        self._scrie("Cer oprirea...\n")
        self.stop_file.touch()
        self.buton_stop.configure(state="disabled")
        threading.Thread(target=self._forteaza_daca_nu_iese, daemon=True).start()

    def _forteaza_daca_nu_iese(self) -> None:
        proces = self.proces
        if proces is None:
            return
        for _ in range(80):  # ~8 secunde
            if proces.poll() is not None:
                return
            time.sleep(0.1)
        self.jurnal_coada.put("Nu a raspuns la oprire; inchid procesul fortat.\n")
        try:
            proces.terminate()
        except Exception:
            pass

    def _inregistreaza(self) -> None:
        nume = self.ruta_noua.get().strip()
        if not nume:
            messagebox.showwarning("gamebot", "Da-i un nume rutei.")
            return
        self._ruleaza(["record", "--profile", str(self._cale_profil()),
                       "--name", nume, "--force"], "Inregistrare")

    def _invata(self, scrie: bool = False) -> None:
        ruta = self._cale_ruta()
        if ruta is None:
            messagebox.showwarning("gamebot", "Alege o ruta inregistrata.")
            return
        argumente = ["learn", "--profile", str(self._cale_profil()), "--route", str(ruta)]
        if scrie:
            argumente.append("--write")
        self._ruleaza(argumente, "Invatare abilitati")

    def _calibreaza(self, ce: str, nume: str) -> None:
        if not nume.strip():
            messagebox.showwarning("gamebot", "Scrie ce anume calibrezi.")
            return
        self._ruleaza(["calibrate", ce, "--name", nume.strip(),
                       "--profile", str(self._cale_profil())], f"Calibrare {ce}")

    def _verifica(self) -> None:
        self._ruleaza(["check", "--profile", str(self._cale_profil())], "Verificare ecran")

    # -------------------------------------------------------------- profil

    def _citeste_profil_in_formular(self) -> None:
        """Umple campurile din tabul de lupta cu ce scrie in profil."""
        try:
            import yaml

            date = yaml.safe_load(self._cale_profil().read_text(encoding="utf-8")) or {}
        except Exception as exc:
            self._scrie(f"Nu pot citi profilul: {exc}\n")
            return

        combat = date.get("combat") or {}
        self.mod.set(str(combat.get("mode", "target")))
        self.doar_in_cale.set(bool(combat.get("only_when_blocking", False)))

        implicite = {
            "engage_radius": combat.get("engage_radius", 260),
            "cluster_radius": combat.get("cluster_radius", 160),
            "global_cooldown": combat.get("global_cooldown", 1.4),
            "max_fight_seconds": combat.get("max_fight_seconds", 45),
            "heal_below": (date.get("thresholds") or {}).get("heal_below", 0.55),
            "heal": (date.get("keys") or {}).get("heal", ""),
            "mount": (date.get("keys") or {}).get("mount", ""),
        }
        for cheie, valoare in implicite.items():
            _, _, camp, _ = self.campuri[cheie]
            camp.delete(0, "end")
            camp.insert(0, str(valoare))

    def _salveaza_profil(self) -> None:
        cale = self._cale_profil()
        try:
            text = cale.read_text(encoding="utf-8")
        except Exception as exc:
            messagebox.showerror("gamebot", f"Nu pot citi profilul: {exc}")
            return

        schimbari: list[tuple[str, str, object]] = [
            ("combat", "mode", self.mod.get()),
            ("combat", "only_when_blocking", bool(self.doar_in_cale.get())),
        ]
        for cheie, (sectiune, _, camp, _) in self.campuri.items():
            brut = camp.get().strip()
            schimbari.append((sectiune, cheie, _numar_sau_text(brut)))

        try:
            nou = yaml_edit.set_many(text, schimbari)
            import yaml

            yaml.safe_load(nou)  # nu scriem un profil pe care nu-l mai putem citi
        except Exception as exc:
            messagebox.showerror("gamebot", f"Setarile ar strica profilul: {exc}")
            return

        cale.write_text(nou, encoding="utf-8")
        self._scrie(f"Profil salvat: {cale.name}\n")
        messagebox.showinfo("gamebot", "Salvat.")

    def _la_inchidere(self) -> None:
        if self.proces is not None:
            if not messagebox.askokcancel("gamebot", "Botul inca ruleaza. Il opresc si ies?"):
                return
            self.stop_file.touch()
            for _ in range(50):
                if self.proces.poll() is not None:
                    break
                time.sleep(0.1)
            if self.proces.poll() is None:
                self.proces.terminate()
        if self.stop_file.exists():
            self.stop_file.unlink()
        self.root.destroy()


def _numar_sau_text(brut: str):
    """Pastreaza tipul: cifrele raman cifre, restul ramane sir."""
    if brut == "":
        return ""
    try:
        return int(brut)
    except ValueError:
        pass
    try:
        return float(brut)
    except ValueError:
        return brut


def porneste(repo_root: Path) -> int:
    root = tk.Tk()
    GamebotApp(root, repo_root)
    root.mainloop()
    return 0
