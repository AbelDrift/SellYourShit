"""Fotoversies maken voor een nieuw product (geen GTK; draait in een achtergrondthread).

Resultaat in de doelmap (zelfde mappen als de oude Product Studio, dus de Uploader werkt ongewijzigd):
  originelen/       de foto's zoals ze zijn (volle grootte, onbewerkt)
  transparant/      PNG zonder achtergrond (vierkant)
  zonder_logo/      JPEG: witte achtergrond, of de foto zelf als 'wit' niet is gekozen
  met_logo/         idem, met watermerk/logo
  zonder_logo_bg/   JPEG met eigen achtergrond (kleur of afbeelding)
  met_logo_bg/      idem, met watermerk/logo

Voorbewerking zoals in de oude Product Studio: draaien volgens EXIF, verkleinen naar 50% en
eventueel kleuren verbeteren. Achtergrond verwijderen gaat met AlphaMaker (zie MOTOREN), altijd in
een apart proces (achtergrond_helper.py),
zodat een geheugenpiek of crash van het model de app niet meeneemt. Er staat steeds maar één
foto tegelijk in het geheugen.
"""
import glob
import importlib.util
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading

from PIL import Image, ImageOps

FOTO_EXT = (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif")
VERSIE_MAPPEN = ("transparant", "zonder_logo", "met_logo", "zonder_logo_bg", "met_logo_bg")
HELPER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "achtergrond_helper.py")


# Motoren voor het weghalen van de achtergrond: naam -> (label, uitleg, benodigde modules)
# Alleen modellen die commercieel gebruikt mogen worden: de app maakt foto's klaar voor verkoop.
# (RMBG-1.4, dat AlphaMaker voor objecten aanraadt, is alleen voor niet-commercieel gebruik.)
MOTOREN = {
    "alphamaker-licht": (
        "Snel – effen achtergrond (IS-Net)",
        "Snel en zuinig (±1 GB geheugen), voor producten op een effen achtergrond. "
        "Commercieel gebruik toegestaan (Apache-2.0).",
        ("onnxruntime", "scipy", "numpy")),
    "alphamaker-zwaar": (
        "Drukke achtergrond (InSPyReNet)",
        "Het model van transparent-background, met de randcorrectie van AlphaMaker. Voor "
        "rommelige achtergronden; trager en ±4 GB geheugen. Commercieel gebruik toegestaan (MIT).",
        ("transparent_background", "scipy", "numpy")),
}
STANDAARD_MOTOR = "alphamaker-licht"
# Opgeslagen keuzes van vóór deze standaard worden één keer naar de nieuwe standaard gezet.
MOTOR_STANDAARD_VERSIE = 4


def motor_beschikbaar(motor):
    if motor not in MOTOREN:
        return False
    return all(importlib.util.find_spec(m) is not None for m in MOTOREN[motor][2])


def beschikbare_motoren():
    return [m for m in MOTOREN if motor_beschikbaar(m)]


def heeft_transparent_background():
    return importlib.util.find_spec("transparent_background") is not None


def heeft_achtergrondverwijdering():
    """Is er minstens één manier om de achtergrond weg te halen?"""
    return bool(beschikbare_motoren())


def heeft_kleurverbetering():
    return all(importlib.util.find_spec(m) is not None for m in ("cv2", "numpy", "tqdm"))


def _naar_rgb(im, achtergrond=(255, 255, 255)):
    if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
        im = im.convert("RGBA")
        vlak = Image.new("RGB", im.size, achtergrond)
        vlak.paste(im, mask=im.split()[3])
        return vlak
    return im.convert("RGB")


def _vierkant(im):
    zijde = max(im.size)
    doek = Image.new("RGBA", (zijde, zijde), (0, 0, 0, 0))
    doek.paste(im, ((zijde - im.width) // 2, (zijde - im.height) // 2), im)
    return doek


def _achtergrond_afbeelding(pad, grootte):
    """Schaal op de kortste zijde en crop in het midden (zelfde als de oude Studio)."""
    with Image.open(pad) as bron:
        bg = bron.convert("RGB")
    w, h = grootte
    schaal = max(w / bg.width, h / bg.height)
    bg = bg.resize((max(w, round(bg.width * schaal)), max(h, round(bg.height * schaal))), Image.LANCZOS)
    l, t = (bg.width - w) // 2, (bg.height - h) // 2
    return bg.crop((l, t, l + w, t + h))


def _logo_en_watermerk(jpg, watermerk, logo):
    """Watermerk over de hele foto, logo rechtsboven (max. 25% van de breedte)."""
    basis = jpg.convert("RGBA")
    if watermerk and os.path.exists(watermerk):
        with Image.open(watermerk) as w:
            wm = w.convert("RGBA").resize(basis.size, Image.LANCZOS)
        basis = Image.alpha_composite(basis, wm)
    if logo and os.path.exists(logo):
        with Image.open(logo) as l:
            lg = l.convert("RGBA")
        maxb = max(1, basis.width // 4)
        if lg.width > maxb:
            lg = lg.resize((maxb, max(1, round(lg.height * maxb / lg.width))), Image.LANCZOS)
        basis.alpha_composite(lg, (max(0, basis.width - lg.width - 10), 10))
    return basis.convert("RGB")


def _bereid_voor(bron, doel, verkleinen):
    """Draait volgens EXIF, verkleint eventueel naar 50% en slaat op als JPEG."""
    with Image.open(bron) as im:
        icc = im.info.get("icc_profile")
        im = _naar_rgb(ImageOps.exif_transpose(im))
    if verkleinen:
        im = im.resize((max(1, im.width // 2), max(1, im.height // 2)), Image.LANCZOS)
    im.save(doel, "JPEG", quality=95, **({"icc_profile": icc} if icc else {}))


def _verbeter_kleur(pad):
    from marktplaats_suite.image_enhancer import auto_enhance
    auto_enhance(pad, pad)


def _lees_regels(stroom, wachtrij):
    for regel in stroom:
        wachtrij.put(regel)


def verwijder_achtergrond(paden, uitmap, voortgang=None, stop=lambda: False, motor=STANDAARD_MOTOR,
                          melding=None):
    """Maakt voor elke foto een PNG zonder achtergrond in uitmap, met de gekozen motor.

    Geeft (gelukt, meldingen) terug, met gelukt = {bronpad: pngpad}. melding(tekst) krijgt
    tussentijdse berichten (zoals 'model downloaden'). Gooit RuntimeError als het proces niet
    kan starten of halverwege wegvalt (bijvoorbeeld door te weinig geheugen)."""
    if not motor_beschikbaar(motor):
        from marktplaats_suite.common import installatie_hint
        naam = MOTOREN[motor][0] if motor in MOTOREN else motor
        raise RuntimeError(f"{naam} is niet geïnstalleerd ({installatie_hint(ai=True)}).")
    os.makedirs(uitmap, exist_ok=True)
    doelen = [os.path.join(uitmap, os.path.splitext(os.path.basename(p))[0] + ".png") for p in paden]
    args = [x for paar in zip(paden, doelen) for x in paar]
    env = {k: v for k, v in os.environ.items() if not k.startswith("QT_")}
    gelukt, meld = {}, []

    def verwerk(regel):
        delen = regel.strip().split(" ", 2)
        if len(delen) < 2 or delen[0] not in ("KLAAR", "FOUT") or not delen[1].isdigit():
            if melding and "downloaden" in regel:      # AlphaMaker meldt het downloaden van een model
                melding("Model downloaden (eenmalig, kan even duren)...")
            return  # overige uitvoer van het model negeren
        i = int(delen[1]) - 1
        if not 0 <= i < len(paden):
            return
        if delen[0] == "KLAAR" and os.path.exists(doelen[i]):
            gelukt[paden[i]] = doelen[i]
        else:
            reden = delen[2] if len(delen) > 2 else "onbekende fout"
            meld.append(f"Foto {i + 1}: achtergrond verwijderen mislukt ({reden}).")
        if voortgang:
            voortgang(i + 1, len(paden))

    python, extra = sys.executable, {}
    if sys.platform == "win32":
        # pythonw.exe (de app zonder console) heeft geen gewone uitvoer; python.exe zonder venster wel
        kandidaat = os.path.join(os.path.dirname(python), "python.exe")
        if os.path.basename(python).lower() == "pythonw.exe" and os.path.exists(kandidaat):
            python = kandidaat
        extra["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors="replace") as foutlog:
        proc = subprocess.Popen([python, "-I", HELPER, f"--motor={motor}"] + args, stdout=subprocess.PIPE, stderr=foutlog,
                                stdin=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace",
                                env=env, **extra)
        regels = queue.Queue()
        lezer = threading.Thread(target=_lees_regels, args=(proc.stdout, regels), daemon=True)
        lezer.start()
        while True:
            try:
                verwerk(regels.get(timeout=0.3))
                continue
            except queue.Empty:
                pass
            if stop():
                proc.kill()
                proc.wait()
                return gelukt, meld
            if not lezer.is_alive():
                break
        while not regels.empty():
            verwerk(regels.get())
        code = proc.wait()
        if code != 0:
            if code in (-9, 3221225495):   # SIGKILL (geheugenbewaking Linux) / STATUS_NO_MEMORY (Windows)
                raise RuntimeError("Achtergrond verwijderen is afgebroken door te weinig geheugen. "
                                   "Zet 'Verkleinen naar 50%' aan of gebruik minder foto's tegelijk.")
            foutlog.seek(0)
            staart = foutlog.read()[-600:].strip()
            raise RuntimeError(f"Achtergrond verwijderen mislukt (code {code}).\n{staart}")
    return gelukt, meld


def maak_versies(fotos, doelmap, opties, voortgang=None, stop=lambda: False):
    """fotos: lijst paden. opties (dict):
         verkleinen (bool, standaard True)   -> naar 50%, zoals de oude Product Studio
         kleur_verbeteren (bool)             -> automatisch (opencv nodig)
         transparant, wit, custom, met_logo (bool)
         motor (str, zie MOTOREN)            -> waarmee de achtergrond weggaat
         bg_kleur ('#rrggbb') of bg_afbeelding (pad)  -> voor 'custom'
         watermerk, logo (paden)
       Geeft (uit, meldingen) terug; uit = {"mapnaam": [paden]}."""
    n = len(fotos)
    meld = []
    os.makedirs(doelmap, exist_ok=True)
    for sub in VERSIE_MAPPEN:
        shutil.rmtree(os.path.join(doelmap, sub), ignore_errors=True)   # oude versies niet mengen
    uit = {"originelen": []}

    # 1. originelen: onbewerkt en op volle grootte bewaren
    d = os.path.join(doelmap, "originelen")
    os.makedirs(d, exist_ok=True)
    for i, p in enumerate(fotos):
        if os.path.abspath(os.path.dirname(p)) == os.path.abspath(d):
            uit["originelen"].append(p)
            continue
        doel = os.path.join(d, f"foto_{i + 1:03d}" + os.path.splitext(p)[1].lower())
        shutil.copy2(p, doel)
        uit["originelen"].append(doel)

    wit, custom, transp = opties.get("wit"), opties.get("custom"), opties.get("transparant")
    achtergrond = bool(wit or custom or transp)
    verkleinen = opties.get("verkleinen", True)
    kleur = opties.get("kleur_verbeteren", False)
    if kleur and not heeft_kleurverbetering():
        kleur = False
        from marktplaats_suite.common import installatie_hint
        meld.append(f"Kleuren verbeteren overgeslagen: opencv ontbreekt ({installatie_hint(ai=True)}).")

    # voortgangsbalk: elke fase krijgt een deel naar hoe lang hij ongeveer duurt
    gewicht = {"voor": 3 if kleur else 1, "achter": 8 if achtergrond else 0, "versies": 1}
    begin = {"voor": 0, "achter": gewicht["voor"], "versies": gewicht["voor"] + gewicht["achter"]}
    totaal = sum(gewicht.values())

    def fase(naam, klaar, tekst):
        if voortgang:
            voortgang((begin[naam] + gewicht[naam] * klaar / max(1, n)) / totaal, tekst)

    werk = tempfile.mkdtemp(prefix=".bewerk_", dir=os.path.dirname(os.path.abspath(doelmap)))
    try:
        # 2. voorbereiden: draaien, verkleinen, kleuren
        voorbereid = []
        for i, p in enumerate(uit["originelen"]):
            if stop():
                return uit, meld
            wat = "Verkleinen" if verkleinen else "Voorbereiden"
            if kleur:
                wat += " en kleuren verbeteren"
            fase("voor", i, f"{wat}: foto {i + 1} van {n}")
            doel = os.path.join(werk, f"foto_{i + 1:03d}.jpg")
            _bereid_voor(p, doel, verkleinen)
            if kleur:
                try:
                    _verbeter_kleur(doel)
                except Exception as e:
                    meld.append(f"Foto {i + 1}: kleuren verbeteren mislukt ({e}).")
            voorbereid.append(doel)

        # 3. achtergrond verwijderen (apart proces, met de gekozen motor)
        pngs = {}
        if achtergrond:
            motor = opties.get("motor") or STANDAARD_MOTOR
            if not motor_beschikbaar(motor) and beschikbare_motoren():
                meld.append(f"{MOTOREN.get(motor, (motor,))[0]} is niet geïnstalleerd; "
                            f"{MOTOREN[beschikbare_motoren()[0]][0]} gebruikt.")
                motor = beschikbare_motoren()[0]
            naam = MOTOREN[motor][0] if motor in MOTOREN else motor
            fase("achter", 0, f"Achtergrond verwijderen met {naam} (model laden)...")
            pngs, m = verwijder_achtergrond(
                voorbereid, os.path.join(werk, "png"),
                voortgang=lambda k, t: fase("achter", k, f"Achtergrond verwijderen ({naam}): foto {k} van {t}"),
                stop=stop, motor=motor, melding=lambda tekst: fase("achter", 0, tekst))
            meld += m
            if stop():
                return uit, meld

        # 4. versies maken, één foto tegelijk
        wm, lg = opties.get("watermerk"), opties.get("logo")
        met_logo = bool(opties.get("met_logo") and ((wm and os.path.exists(wm)) or (lg and os.path.exists(lg))))
        if opties.get("met_logo") and not met_logo:
            meld.append("Geen logo of watermerk gekozen: versies met logo overgeslagen.")
        k = (opties.get("bg_kleur") or "#ffffff").lstrip("#")
        try:
            bg_rgb = tuple(int(k[j:j + 2], 16) for j in (0, 2, 4))
        except ValueError:
            bg_rgb = (255, 255, 255)
        bg_afb = opties.get("bg_afbeelding") if opties.get("bg_afbeelding") and os.path.exists(opties["bg_afbeelding"]) else None

        def bewaar(sub, im, naam, **kw):
            map_ = os.path.join(doelmap, sub)
            os.makedirs(map_, exist_ok=True)
            pad = os.path.join(map_, naam)
            im.save(pad, **kw)
            uit.setdefault(sub, []).append(pad)

        for i, prep in enumerate(voorbereid):
            if stop():
                return uit, meld
            fase("versies", i, f"Versies maken: foto {i + 1} van {n}")
            naam = f"foto_{i + 1:03d}"
            png = pngs.get(prep)
            with Image.open(prep) as pim:
                icc = pim.info.get("icc_profile")
                maat = pim.size
                # foto met eigen achtergrond: als 'wit' niet gekozen is (of als het verwijderen mislukte)
                basis = pim.convert("RGB") if not (wit and png) else None
            jpg = {"format": "JPEG", "quality": 95, **({"icc_profile": icc} if icc else {})}
            if basis is not None:
                bewaar("zonder_logo", basis, naam + ".jpg", **jpg)
                if met_logo:
                    bewaar("met_logo", _logo_en_watermerk(basis, wm, lg), naam + ".jpg", **jpg)
                del basis
            if png:
                with Image.open(png) as tim:
                    rgba = tim.convert("RGBA")
                if rgba.size != maat:
                    rgba = rgba.resize(maat, Image.LANCZOS)
                rgba = _vierkant(rgba)
                if transp:
                    bewaar("transparant", rgba, naam + ".png", format="PNG")
                if wit:
                    w = _naar_rgb(rgba)
                    bewaar("zonder_logo", w, naam + ".jpg", **jpg)
                    if met_logo:
                        bewaar("met_logo", _logo_en_watermerk(w, wm, lg), naam + ".jpg", **jpg)
                    del w
                if custom:
                    if bg_afb:
                        c = _achtergrond_afbeelding(bg_afb, rgba.size)
                        c.paste(rgba, (0, 0), rgba)
                    else:
                        c = _naar_rgb(rgba, bg_rgb)
                    bewaar("zonder_logo_bg", c, naam + ".jpg", **jpg)
                    if met_logo:
                        bewaar("met_logo_bg", _logo_en_watermerk(c, wm, lg), naam + ".jpg", **jpg)
                    del c
                del rgba
        if voortgang:
            voortgang(1.0, "Klaar")
        return uit, meld
    finally:
        shutil.rmtree(werk, ignore_errors=True)


def lijst_fotos(map_):
    uit = []
    for p in sorted(glob.glob(os.path.join(map_, "*"))):
        if p.lower().endswith(FOTO_EXT):
            uit.append(p)
    return uit
