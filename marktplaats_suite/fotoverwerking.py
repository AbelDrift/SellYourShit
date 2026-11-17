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
# Markeringsbestand in zonder_logo/: daar staan witte achtergronden (anders de foto zelf, zie boven).
WIT_MARKER = ".witte_achtergrond"


def heeft_witte_versie(map_):
    """Staan er in map_/zonder_logo foto's met een witte achtergrond?"""
    return os.path.exists(os.path.join(map_, "zonder_logo", WIT_MARKER))
HELPER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "achtergrond_helper.py")


# Motoren voor het weghalen van de achtergrond: naam -> (label, uitleg, benodigde modules)
# Drie standen, volgens het advies van AlphaMaker; allemaal commercieel toegestaan, want de app
# maakt foto's klaar voor verkoop. (RMBG-1.4 is alleen voor niet-commercieel gebruik: niet gebruikt.)
MOTOREN = {
    "alphamaker-licht": (
        "Licht – IS-Net",
        "Snel (±3 s per foto) en zuinig (±1 GB geheugen). Voor producten op een effen "
        "achtergrond. Licentie Apache-2.0.",
        ("onnxruntime", "scipy", "numpy")),
    "alphamaker-medium": (
        "Medium – InSPyReNet",
        "Nauwkeuriger, ook bij een drukke achtergrond; het model van transparent-background. "
        "Trager (±15 s per foto), ±4 GB geheugen. Licentie MIT.",
        ("transparent_background", "scipy", "numpy")),
    "alphamaker-zwaar": (
        "Zwaar – BiRefNet general",
        "Het nauwkeurigst, vooral bij haar. Erg traag (±40 s per foto) en 5 GB geheugen of meer: "
        "alleen voor pc's met 16 GB RAM. Het model wordt de eerste keer gedownload. Licentie MIT.",
        ("torch", "timm", "kornia", "transformers", "safetensors", "einops", "scipy", "numpy")),
}
STANDAARD_MOTOR = "alphamaker-licht"
# Opgeslagen keuzes van vóór deze standaard worden één keer omgezet (zie productmanager).
MOTOR_STANDAARD_VERSIE = 5


# Ongeveer nodig vrij werkgeheugen per motor in GB (gemeten: licht 0,9, medium 3,9; zwaar 5+).
GEHEUGEN_NODIG = {"alphamaker-licht": 1.2, "alphamaker-medium": 4.5, "alphamaker-zwaar": 6.0}


def _geheugen():
    """(vrij, totaal) in bytes, met vrij = beschikbaar werkgeheugen plus vrije swap; None als onbekend."""
    try:
        info = {}
        with open("/proc/meminfo") as f:
            for regel in f:
                naam, _, rest = regel.partition(":")
                if rest.split():
                    info[naam] = int(rest.split()[0]) * 1024
        return info["MemAvailable"] + info.get("SwapFree", 0), info["MemTotal"]
    except (OSError, KeyError, ValueError):
        pass
    try:
        import psutil
        return psutil.virtual_memory().available + psutil.swap_memory().free, psutil.virtual_memory().total
    except Exception:
        return None


def _gb(n):
    return f"{n / 2 ** 30:.1f}".replace(".", ",")


_scope = None


def _eigen_scope():
    """Begin van de opdracht die het hulpproces in een eigen systemd-scope start, of [] (geen systemd).

    Haalt Linux bij een geheugentekort een proces weg, dan sluit systemd daarna de hele scope waar
    dat proces in zat. Zonder eigen scope is dat die van de app, of van de terminal waaruit de app
    gestart is: dan verdwijnen app en terminal mee. In een eigen scope stopt alleen het hulpproces."""
    global _scope
    if _scope is None:
        _scope = []
        prog = shutil.which("systemd-run") if sys.platform.startswith("linux") else None
        if prog:
            cmd = [prog, "--user", "--scope", "--quiet", "--collect",
                   "--description=SellYourShit: achtergrond verwijderen"]
            try:
                if subprocess.run(cmd + ["true"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                  stderr=subprocess.DEVNULL, timeout=15).returncode == 0:
                    _scope = cmd
            except (OSError, subprocess.SubprocessError):
                pass
    return _scope


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


# Logo als watermerk: zo vaak over de foto (raster), zwart-wit en zo zichtbaar
LOGO_WATERMERK_RASTER = 3          # 3 x 3 = 9 keer
LOGO_WATERMERK_ZICHTBAAR = 0.05    # 5% zichtbaar (95% doorzichtig)


def _logo_als_watermerk(maat, logo):
    """Watermerk van maat (b, h) uit het logo: het logo in zwart-wit, 9x verspreid over de foto
    (3 x 3, elk logo in het midden van zijn vak, maximaal 60% van het vak) en 5% zichtbaar."""
    b, h = maat
    with Image.open(logo) as l:
        lg = l.convert("RGBA")
    n = LOGO_WATERMERK_RASTER
    vak_b, vak_h = b / n, h / n
    schaal = min(vak_b * 0.6 / lg.width, vak_h * 0.6 / lg.height)
    lg = lg.resize((max(1, round(lg.width * schaal)), max(1, round(lg.height * schaal))), Image.LANCZOS)
    grijs = lg.convert("L")                                          # zwart-wit
    alfa = lg.getchannel("A").point(lambda a: round(a * LOGO_WATERMERK_ZICHTBAAR))
    tegel = Image.merge("RGBA", (grijs, grijs, grijs, alfa))
    laag = Image.new("RGBA", (b, h), (0, 0, 0, 0))
    for rij in range(n):
        for kolom in range(n):
            x = round(kolom * vak_b + (vak_b - tegel.width) / 2)
            y = round(rij * vak_h + (vak_h - tegel.height) / 2)
            laag.alpha_composite(tegel, (max(0, x), max(0, y)))
    return laag


def _logo_en_watermerk(jpg, watermerk, logo, logo_als_watermerk=False):
    """Watermerk over de hele foto, logo rechtsboven (max. 25% van de breedte).
    Met logo_als_watermerk wordt het watermerk uit het logo gemaakt (zie _logo_als_watermerk)."""
    basis = jpg.convert("RGBA")
    if logo_als_watermerk and logo and os.path.exists(logo):
        basis = Image.alpha_composite(basis, _logo_als_watermerk(basis.size, logo))
    elif watermerk and os.path.exists(watermerk):
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
        raise RuntimeError(f"{MOTOREN[motor][0] if motor in MOTOREN else motor} is niet geïnstalleerd "
                           f"({installatie_hint(ai=True)}).")
    naam = MOTOREN[motor][0] if motor in MOTOREN else motor
    kort = naam.split(" – ")[0]
    nodig = GEHEUGEN_NODIG.get(motor, 0) * 2 ** 30
    if motor == "alphamaker-licht":
        advies = "Sluit andere programma's (bijvoorbeeld de browser) of zet 'Verkleinen naar 50%' aan."
    else:
        advies = ("Sluit andere programma's (bijvoorbeeld de browser) of kies in de foto-editor een "
                  "lichtere stand.")
    geheugen = _geheugen()
    if geheugen and nodig and geheugen[0] < nodig * 0.8:
        raise RuntimeError(f"Te weinig vrij geheugen voor {naam}: er is {_gb(geheugen[0])} GB vrij en "
                           f"{kort} heeft ongeveer {_gb(nodig)} GB nodig. {advies}")
    # Wordt het geheugen toch bijna vol, dan stopt de app het hulpproces zelf, vóór Linux ingrijpt.
    drempel = max(300 * 2 ** 20, geheugen[1] * 4 // 100) if geheugen else 0
    os.makedirs(uitmap, exist_ok=True)
    doelen = [os.path.join(uitmap, os.path.splitext(os.path.basename(p))[0] + ".png") for p in paden]
    args = [x for paar in zip(paden, doelen) for x in paar]
    env = {k: v for k, v in os.environ.items() if not k.startswith("QT_")}
    if sys.platform.startswith("linux"):
        # vrijgegeven geheugen meteen teruggeven: scheelt bij medium ±250 MB piek en 400 MB daarna
        env.setdefault("MALLOC_MMAP_THRESHOLD_", "262144")
        env.setdefault("MALLOC_TRIM_THRESHOLD_", "262144")
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
        proc = subprocess.Popen(_eigen_scope() + [python, "-I", HELPER, f"--motor={motor}"] + args,
                                stdout=subprocess.PIPE, stderr=foutlog,
                                stdin=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace",
                                env=env, **extra)
        regels = queue.Queue()
        lezer = threading.Thread(target=_lees_regels, args=(proc.stdout, regels), daemon=True)
        lezer.start()
        vol = False
        while True:
            try:
                verwerk(regels.get(timeout=0.25))
            except queue.Empty:
                pass
            if stop():
                proc.kill()
                proc.wait()
                return gelukt, meld
            if drempel and not vol:
                nu = _geheugen()
                if nu and nu[0] < drempel:
                    vol = True
                    proc.kill()
            if not lezer.is_alive():
                break
        while not regels.empty():
            verwerk(regels.get())
        code = proc.wait()
        if code != 0:
            if vol or code in (-9, 3221225495):   # SIGKILL (geheugentekort Linux) / STATUS_NO_MEMORY (Windows)
                vrij = f" (bij de start was er {_gb(geheugen[0])} GB vrij)" if geheugen else ""
                hoeveel = f" {kort} heeft ongeveer {_gb(nodig)} GB nodig." if nodig else ""
                raise RuntimeError(f"Achtergrond verwijderen met {naam} is gestopt: het werkgeheugen raakte "
                                   f"vol{vrij}.{hoeveel} {advies}")
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
         logo_als_watermerk (bool)           -> watermerk uit het logo maken (9x, zwart-wit, 5%)
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
        lwm = bool(opties.get("logo_als_watermerk"))
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

        wit_gemaakt = False
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
                    bewaar("met_logo", _logo_en_watermerk(basis, wm, lg, lwm), naam + ".jpg", **jpg)
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
                    wit_gemaakt = True
                    if met_logo:
                        bewaar("met_logo", _logo_en_watermerk(w, wm, lg, lwm), naam + ".jpg", **jpg)
                    del w
                if custom:
                    if bg_afb:
                        c = _achtergrond_afbeelding(bg_afb, rgba.size)
                        c.paste(rgba, (0, 0), rgba)
                    else:
                        c = _naar_rgb(rgba, bg_rgb)
                    bewaar("zonder_logo_bg", c, naam + ".jpg", **jpg)
                    if met_logo:
                        bewaar("met_logo_bg", _logo_en_watermerk(c, wm, lg, lwm), naam + ".jpg", **jpg)
                    del c
                del rgba
        if wit_gemaakt:
            open(os.path.join(doelmap, "zonder_logo", WIT_MARKER), "w").close()
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
