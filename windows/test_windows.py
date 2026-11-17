"""Rooktest voor de Windows-versie (draait op GitHub Actions met de meegeleverde Python).

Gebruik: dist\\SellYourShit\\python\\python.exe windows\\test_windows.py dist\\SellYourShit uitvoer_map
Start de app zonder interactie, registreert een product met twee foto's, haalt de achtergrond weg
met transparent-background (op de processor), opent het productvenster en maakt schermafdrukken.
"""
import glob
import os
import sys
import tempfile
import time
import traceback

for stroom in (sys.stdout, sys.stderr):
    try:
        stroom.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
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


def in_log(naam, data):
    """Bestand als base64 in de log: artefacten zijn niet overal te downloaden, de log wel."""
    import base64
    b = base64.b64encode(data).decode()
    print(f"BEGIN-BESTAND {naam}", flush=True)
    for i in range(0, len(b), 4000):
        print(b[i:i + 4000])
    print("EINDE-BESTAND", flush=True)


def schermafdruk(naam, venster=None):
    try:
        import io
        from PIL import Image, ImageGrab
        pad = os.path.join(UIT, naam)
        if venster is not None:
            # het venster zelf laten tekenen: werkt overal (een kopie van het scherm is op Windows zwart)
            import cairo
            b, h = venster.get_allocated_width(), venster.get_allocated_height()
            opp = cairo.ImageSurface(cairo.FORMAT_ARGB32, b, h)
            cr = cairo.Context(opp)
            cr.set_source_rgb(1, 1, 1)
            cr.paint()
            venster.draw(cr)
            opp.flush()
            opp.write_to_png(pad)
        else:
            ImageGrab.grab().save(pad)
        with Image.open(pad) as im:
            klein = im.convert("RGB")
        klein.thumbnail((1280, 1280))
        buf = io.BytesIO()
        klein.save(buf, "JPEG", quality=72)
        in_log(os.path.splitext(naam)[0] + ".jpg", buf.getvalue())
        print(f"   schermafdruk {naam}", flush=True)
    except Exception as e:
        print(f"   (geen schermafdruk: {e})", flush=True)


try:
    stap("omgeving")
    if sys.platform == "win32":
        controleer(sys.flags.utf8_mode == 1, "Python draait in UTF-8-modus (zoals de snelkoppelingen)")
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

    stap("lettertypen")
    gi.require_version("PangoCairo", "1.0")
    from gi.repository import Pango, PangoCairo
    fm = PangoCairo.FontMap.get_default()
    fams = sorted(f.get_name() for f in fm.list_families())
    print(f"   {type(fm).__name__}: {len(fams)} families, o.a.",
          [f for f in fams if f.startswith(("Segoe", "Consolas", "Arial", "Courier"))][:14], flush=True)
    print("   GTK-lettertype:", Gtk.Settings.get_default().props.gtk_font_name, "| Pango", Pango.version_string(), flush=True)
    ctx = fm.create_context()
    for tekst, font in (("Nieuw Product", "Sans 10"), ("\U0001F4DD Nieuw Product \U0001F680 \u2705 \U0001F4E6", "Sans 10"),
                        ("\u2699 \u26a0 \u270f \U0001F5D1 \U0001F5BC Instellingen", "Segoe UI 9"),
                        ("log 12:00 INFO", "Monospace 9"), ("gewone tekst", "Segoe UI 9")):
        print(f"   test {font!r} {tekst!r} ...", flush=True)
        lay = Pango.Layout.new(ctx)
        lay.set_font_description(Pango.FontDescription(font))
        lay.set_text(tekst, -1)
        onbekend = lay.get_unknown_glyphs_count()
        controleer(onbekend == 0, f"{font!r}: alle tekens hebben een lettertype ({onbekend} onbekend)")

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

    if sys.platform == "win32":
        import marktplaats_suite
        met_vs16 = [os.path.basename(p) for p in glob.glob(os.path.join(os.path.dirname(marktplaats_suite.__file__), "*.py"))
                    if "\ufe0f" in open(p, encoding="utf-8").read()]
        controleer(not met_vs16, f"geen emoji-variantkiezers in de app ({met_vs16})")

    stap("hoofdvenster")
    from marktplaats_suite import productmanager as pm, __version__
    print("   SellYourShit", __version__)
    um = pm.UserManager()
    um.voeg_toe("test", "x")
    w = pm.MainWindow("test", um)
    w.resize(1300, 850)
    w.show_all()
    w.move(0, 0)
    tik(20)
    controleer(w.automater_app is not None, "Product Uploader geladen")
    schermafdruk("0_scherm.png")
    schermafdruk("1_nieuw_product.png", w)

    stap("foto's toevoegen")
    from PIL import Image, ImageDraw
    from marktplaats_suite import fotoverwerking as fv
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
    print("   motoren:", fv.beschikbare_motoren(), "| standaard:", t._standaard_foto_opties().get("motor"), flush=True)
    alle_drie = ["alphamaker-licht", "alphamaker-medium", "alphamaker-zwaar"]
    if sys.platform == "win32":
        controleer(fv.beschikbare_motoren() == alle_drie, "licht (IS-Net), medium (InSPyReNet) en zwaar (BiRefNet) beschikbaar")
    controleer(t._standaard_foto_opties().get("motor") == "alphamaker-licht", "licht (IS-Net) is de standaard")
    if sys.platform == "win32":
        controleer(os.path.isfile(os.path.join(os.environ.get("ALPHAMAKER_MODELS", ""), "isnet-general.onnx")),
                   "meegeleverd IS-Net-model gevonden")
    eigen_cache = os.path.join(os.path.expanduser("~"), ".cache", "alphamaker", "isnet-general.onnx")

    def verwerk_met(motor, naam, schermnaam):
        stap(f"achtergrond weghalen met {naam}")
        opties = {"verkleinen": True, "kleur_verbeteren": True, "transparant": True, "wit": True}
        if motor:
            opties["motor"] = motor
        klaar = {}
        begin = time.time()
        t._verwerk_fotos(opties, klaar=lambda ok: klaar.setdefault("ok", ok))
        while "ok" not in klaar and time.time() - begin < 1500:
            tik(1)
        print(f"   {naam} duurde {time.time() - begin:.0f} s; status: {t.foto_status.get_text()}", flush=True)
        controleer(klaar.get("ok") is True, f"foto's verwerkt met {naam}")
        controleer(sorted(t.versies) == ["originelen", "transparant", "zonder_logo"], f"versies: {sorted(t.versies)}")
        if t.versies.get("transparant"):
            with Image.open(t.versies["transparant"][0]) as im:
                alfa = im.getchannel("A").getextrema()
            controleer(im.mode == "RGBA" and alfa[0] <= 10 and alfa[1] >= 245,
                       f"{naam}: doorzichtige en dichte delen ({im.mode}, alfa {alfa})")
        schermafdruk(schermnaam, w)

    verwerk_met(None, "licht - IS-Net (standaard)", "2_licht_isnet.png")
    verwerk_met("alphamaker-medium", "medium - InSPyReNet", "2a_medium_inspyrenet.png")
    if fv.motor_beschikbaar("alphamaker-zwaar"):
        verwerk_met("alphamaker-zwaar", "zwaar - BiRefNet general", "2b_zwaar_birefnet.png")
    if sys.platform == "win32":
        modellen = os.environ.get("ALPHAMAKER_MODELS", "")
        inhoud = sorted(os.listdir(modellen))
        controleer(inhoud == ["hf", "isnet-general.onnx"], f"modellenmap: meegeleverd IS-Net + gedownload BiRefNet ({inhoud})")
        controleer(os.path.isfile(os.path.join(modellen, "hf", "birefnet-general", "model.safetensors")),
                   "BiRefNet general de eerste keer gedownload naar de programmamap")
        controleer(not os.path.exists(eigen_cache), "geen modellen in ~/.cache")

    stap("foto-editor (keuze van de motor)")

    def editor_vastleggen():
        for x in Gtk.Window.list_toplevels():
            if isinstance(x, Gtk.Dialog) and x.get_title() == "Foto editor" and x.get_visible():
                schermafdruk("2c_foto_editor.png", x)
                x.response(Gtk.ResponseType.CLOSE)
                return False
        return True
    GLib.timeout_add(800, editor_vastleggen)
    t._on_foto_editor(None)
    tik(5)

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
        w.notebook.set_current_page(1)
        tik(10)
        schermafdruk("3_product_management.png", w)
        o._open_detail(nr)
        tik(20)
        det = [x for x in Gtk.Window.list_toplevels() if x.get_visible() and x is not w and (x.get_title() or "").startswith(nr)]
        controleer(bool(det), "productvenster geopend")
        if det:
            det[0].move(0, 0)
            tik(10)
            schermafdruk("4_productvenster.png", det[0])
            det[0].destroy()
            tik(5)
        if w.automater_app is not None:
            w.notebook.set_current_page(w.notebook.page_num(w.automater_app.window))
            tik(10)
            schermafdruk("5_product_uploader.png", w)

    stap("printers (Windows)")
    printers = pm.get_cups_printers()
    print("   gevonden:", printers, flush=True)
    testprinter = os.environ.get("SYS_TESTPRINTER")
    controleer(isinstance(printers, list) and (not testprinter or testprinter in printers), "printerlijst opgehaald")
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
        if os.path.exists(uitvoer):
            time.sleep(1)
            in_log("barcode_print.pdf", open(uitvoer, "rb").read())

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
