"""Starter voor SellYourShit op Windows.

Zet de omgeving voor de meegeleverde GTK klaar (DLL's, typelibs, pictogrammen, beeldformaten) en
start daarna de app. Fouten bij het opstarten komen in een melding en in
%LOCALAPPDATA%\\SellYourShit\\sellyourshit.log, want pythonw.exe heeft geen consolevenster.
"""
import os
import subprocess
import sys
import traceback

HIER = os.path.dirname(os.path.abspath(__file__))
GTK = os.path.join(HIER, "gtk")
LOKAAL = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "SellYourShit")
MODEL = os.path.join(HIER, "modellen", "ckpt_base.pth")   # transparent-background, meegeleverd
_dll_mappen = []


def omgeving():
    """Omgevingsvariabelen en DLL-paden voor GTK; ook gebruikt door de test."""
    os.makedirs(LOKAAL, exist_ok=True)
    gtk_bin = os.path.join(GTK, "bin")
    os.environ["PATH"] = gtk_bin + os.pathsep + os.environ.get("PATH", "")
    _dll_mappen.append(os.add_dll_directory(gtk_bin))
    os.environ["GI_TYPELIB_PATH"] = os.path.join(GTK, "lib", "girepository-1.0")
    os.environ["XDG_DATA_DIRS"] = os.path.join(GTK, "share")
    os.environ.setdefault("GSETTINGS_SCHEMA_DIR", os.path.join(GTK, "share", "glib-2.0", "schemas"))
    if os.path.isfile(MODEL):
        os.environ["SELLYOURSHIT_TB_CKPT"] = MODEL
    # De lijst met beeldformaat-modules bevat volledige paden: per installatie opnieuw maken.
    moduledir = os.path.join(GTK, "lib", "gdk-pixbuf-2.0", "2.10.0", "loaders")
    cache = os.path.join(LOKAAL, "loaders.cache")
    stempel = os.path.join(LOKAAL, "loaders.pad")
    os.environ["GDK_PIXBUF_MODULEDIR"] = moduledir
    try:
        actueel = open(stempel, encoding="utf-8").read() == moduledir and os.path.exists(cache)
    except OSError:
        actueel = False
    if not actueel:
        try:
            uit = subprocess.run([os.path.join(gtk_bin, "gdk-pixbuf-query-loaders.exe")],
                                 capture_output=True, text=True, timeout=60,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
            if uit.strip():
                with open(cache, "w", encoding="utf-8") as f:
                    f.write(uit)
                with open(stempel, "w", encoding="utf-8") as f:
                    f.write(moduledir)
        except Exception:
            pass
    if os.path.exists(cache):
        os.environ["GDK_PIXBUF_MODULE_FILE"] = cache
    # eigen pictogram in de taakbalk (anders groepeert Windows hem onder Python)
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("HerNieuw.SellYourShit")
    except Exception:
        pass


def melding(tekst):
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, tekst, "SellYourShit", 0x10)
    except Exception:
        pass


def start():
    os.makedirs(LOKAAL, exist_ok=True)
    log = open(os.path.join(LOKAAL, "sellyourshit.log"), "w", encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr = log
    try:
        omgeving()
        import runpy
        runpy.run_module("marktplaats_suite", run_name="__main__")
    except SystemExit:
        pass
    except Exception:
        traceback.print_exc()
        melding("SellYourShit kon niet starten.\n\n" + traceback.format_exc()[-1500:] +
                f"\n\nDe volledige melding staat in {os.path.join(LOKAAL, 'sellyourshit.log')}")


if __name__ == "__main__":
    start()
