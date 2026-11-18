"""Test voor de Automater met Firefox en Chromium als snap (zoals op Ubuntu).

Draait op GitHub Actions (Ubuntu-runner met snapd), onder Xvfb, met de geïnstalleerde app:
    PATH=/snap/bin:$PATH ~/.local/share/marktplaats-suite/venv/bin/python linux/test_snap.py
"""
import logging
import os
import sys
import tempfile

os.environ["MARKTPLAATS_DATA_DIR"] = tempfile.mkdtemp(prefix="sys_snap_")
import gi  # noqa: E402
gi.require_version("Gtk", "3.0")
from marktplaats_suite import automater as am  # noqa: E402

logging.basicConfig(level=logging.INFO, format="   %(message)s")
log = logging.getLogger("snaptest")
log.success = log.info
fouten = []


def probeer(browser, pad):
    print(f"== {browser}: {pad} (snap: {am._is_snap(pad)})", flush=True)
    print(f"   realpath {os.path.realpath(pad)!r}, link {os.path.islink(pad)}"
          f"{' -> ' + os.readlink(pad) if os.path.islink(pad) else ''}", flush=True)
    auto = am.MarktplaatsAuto({"browser": browser}, log)
    if not auto.start_browser():
        fouten.append(f"{browser} start niet: {auto.last_error}")
        print("   FOUT", auto.last_error, flush=True)
        return
    try:
        auto.driver.get("data:text/html,<title>sellyourshit-ok</title><h1>ok</h1>")
        titel = auto.driver.title
        print("   titel:", titel, "| browser:", auto.driver.capabilities.get("browserName"),
              auto.driver.capabilities.get("browserVersion"), flush=True)
        if titel != "sellyourshit-ok":
            fouten.append(f"{browser}: verkeerde titel {titel!r}")
    finally:
        auto.driver.quit()


ff = am._firefox_pad()
probeer("firefox", ff)
if os.path.exists("/snap/bin/chromium"):
    am._chrome_pad = lambda: "/snap/bin/chromium"
    probeer("chrome", "/snap/bin/chromium")
print("== RESULTAAT:", "GESLAAGD" if not fouten else f"FOUT(EN): {fouten}", flush=True)
sys.exit(1 if fouten else 0)
