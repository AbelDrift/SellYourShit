"""Rooktest voor de Windows-versie (draait op GitHub Actions met de meegeleverde Python).

Gebruik: dist\\SellYourShit\\python\\python.exe windows\\test_windows.py dist\\SellYourShit uitvoer_map
Start de app zonder interactie, registreert een product met twee foto's, haalt de achtergrond weg
met transparent-background (op de processor), opent het productvenster en maakt schermafdrukken.
"""
import os
import sys
import tempfile
import time
import traceback

PROG = os.path.abspath(sys.argv[1])
UIT = os.path.abspath(sys.argv[2])
os.makedirs(UIT, exist_ok=True)
sys.path.insert(0, PROG)
os.environ["MARKTPLAATS_DATA_DIR"] = tempfile.mkdtemp(prefix="sys_data_")
fouten = []


def stap(tekst):
    print(f"== {tekst}", flush=True)


def controleer(voorwaarde, tekst):
    print(("   OK   " if voorwaarde else "   FOUT ") + tekst, flush=True)
    if not voorwaarde:
        fouten.append(tekst)


def schermafdruk(naam):
    try:
        from PIL import ImageGrab
        ImageGrab.grab().save(os.path.join(UIT, naam))
        print(f"   schermafdruk {naam}", flush=True)
    except Exception as e:
        print(f"   (geen schermafdruk: {e})", flush=True)


try:
    stap("omgeving")
    if sys.platform == "win32":
        import start_sellyourshit as starter
        starter.omgeving()
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk, GLib
    print(f"   Python {sys.version.split()[0]}, GTK {Gtk.get_major_version()}.{Gtk.get_minor_version()}.{Gtk.get_micro_version()}, PyGObject {gi.__version__}")
    if sys.platform == "win32":
        controleer(os.path.exists(os.environ.get("GDK_PIXBUF_MODULE_FILE", "")), "lijst met beeldformaten aangemaakt")
        controleer(os.path.isfile(os.environ.get("SELLYOURSHIT_TB_CKPT", "")), "meegeleverd model gevonden")

    def tik(n=10):
        for _ in range(n):
            while Gtk.events_pending():
                Gtk.main_iteration()
            time.sleep(0.03)

    def sluit_dialogen():
        for x in Gtk.Window.list_toplevels():
            if isinstance(x, Gtk.MessageDialog) and x.get_visible():
                print("   melding weggeklikt:", x.get_property("text"), flush=True)
                x.response(Gtk.ResponseType.OK)
        return True
    GLib.timeout_add(500, sluit_dialogen)

    stap("hoofdvenster")
    from marktplaats_suite import productmanager as pm, __version__
    print("   SellYourShit", __version__)
    um = pm.UserManager()
    um.voeg_toe("test", "x")
    w = pm.MainWindow("test", um)
    w.resize(1300, 850)
    w.show_all()
    tik(20)
    controleer(w.automater_app is not None, "Product Uploader geladen")
    schermafdruk("1_nieuw_product.png")

    stap("foto's toevoegen en verwerken (transparent-background op de processor)")
    from PIL import Image, ImageDraw
    t = w.registreer_tab
    fotos = []
    for i, kleur in enumerate(((210, 60, 60), (60, 160, 90))):
        p = os.path.join(tempfile.gettempdir(), f"testfoto_{i}.jpg")
        im = Image.new("RGB", (1600, 1200), kleur)
        ImageDraw.Draw(im).ellipse((450, 250, 1150, 950), fill=(30, 30, 160))
        im.save(p, quality=90)
        fotos.append(p)
    t._voeg_fotos_toe(fotos)
    tik(5)
    controleer(len(t.fotos) == 2, "twee foto's in de preview")
    klaar = {}
    begin = time.time()
    t._verwerk_fotos({"verkleinen": True, "kleur_verbeteren": True, "transparant": True, "wit": True},
                     klaar=lambda ok: klaar.setdefault("ok", ok))
    while "ok" not in klaar and time.time() - begin < 1500:
        tik(1)
    print(f"   verwerken duurde {time.time() - begin:.0f} s; status: {t.foto_status.get_text()}", flush=True)
    controleer(klaar.get("ok") is True, "foto's verwerkt")
    controleer(sorted(t.versies) == ["originelen", "transparant", "zonder_logo"], f"versies: {sorted(t.versies)}")
    if t.versies.get("transparant"):
        with Image.open(t.versies["transparant"][0]) as im:
            alfa = im.getchannel("A").getextrema()
        controleer(im.mode == "RGBA" and alfa[0] <= 10 and alfa[1] >= 245,
                   f"transparante PNG met doorzichtige en dichte delen ({im.mode}, alfa {alfa})")
    schermafdruk("2_na_verwerken.png")

    stap("product registreren en productvenster")
    t.titel_entry.set_text("Testbeeldje Windows")
    for e, v in ((t.lengte_entry, "20"), (t.breedte_entry, "15"), (t.hoogte_entry, "10"), (t.gewicht_entry, "1")):
        e.set_text(v)
    for c in (t.opslaglocatie_combo, t.sublocatie_combo, t.rij_combo):
        c.set_active(0)
    t.barcode_check.set_active(True)
    t._on_opslaan(None)
    tik(10)
    o = w.overzicht_tab
    controleer(len(o.store) == 1, "product staat in Product Management")
    if len(o.store):
        nr = o.store[0][0]
        map_ = pm.vind_product_map(nr, o.config)
        controleer(os.path.isdir(os.path.join(map_, "transparant")), f"productmap met fotoversies: {map_}")
        controleer(any(f.endswith("_barcode.png") for f in os.listdir(map_)), "barcode gemaakt")
        o._open_detail(nr)
        tik(20)
        schermafdruk("3_productvenster.png")

    stap("printers (Windows)")
    printers = pm.get_cups_printers()
    print("   gevonden:", printers, flush=True)
    controleer(isinstance(printers, list), "printerlijst opgehaald")
    testprinter = os.environ.get("SYS_TESTPRINTER")
    if testprinter and len(o.store):
        barcode = next(os.path.join(map_, f) for f in os.listdir(map_) if f.endswith("_barcode.png"))
        pm.print_barcode(barcode, {"print_method": "cups", "printer_name": testprinter}, False)
        uitvoer = os.environ["SYS_TESTPRINTER_UIT"]
        for _ in range(100):
            if os.path.exists(uitvoer) and os.path.getsize(uitvoer) > 0:
                break
            time.sleep(0.2)
        controleer(os.path.exists(uitvoer) and os.path.getsize(uitvoer) > 1000,
                   f"barcode geprint naar {testprinter} ({os.path.getsize(uitvoer) if os.path.exists(uitvoer) else 0} bytes)")

    stap("overige onderdelen")
    from marktplaats_suite import ai, advertentie, verzending, common
    print("   GIMP:", common.gimp_pad(), "| lettertype:", common.lettertype_vet(), flush=True)
    controleer(common.lettertype_vet() is not None, "lettertype voor etiketten gevonden")
    print("   datamap:", common.data_dir(), flush=True)
except Exception:
    traceback.print_exc()
    fouten.append("onverwachte fout")

print("== RESULTAAT:", "GESLAAGD" if not fouten else f"{len(fouten)} FOUT(EN): {fouten}", flush=True)
sys.exit(1 if fouten else 0)
