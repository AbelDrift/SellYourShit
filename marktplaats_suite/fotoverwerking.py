"""Fotoversies maken voor een nieuw product (geen GTK; draait in een achtergrondthread).

Resultaat in de doelmap (zelfde mappen als de oude Product Studio, dus de Uploader werkt ongewijzigd):
  originelen/       de foto's zoals ze zijn
  transparant/      PNG zonder achtergrond (vierkant)
  zonder_logo/      JPEG: wit (of het origineel als wit niet is gevraagd)
  met_logo/         idem, met watermerk/logo
  zonder_logo_bg/   JPEG met eigen achtergrond (kleur of afbeelding)
  met_logo_bg/      idem, met watermerk/logo
"""
import glob
import os
import shutil
import subprocess
import sys
import tempfile

from PIL import Image, ImageOps

FOTO_EXT = (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif")


def _open(pad):
    im = Image.open(pad)
    return ImageOps.exif_transpose(im)


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
    bg = Image.open(pad).convert("RGB")
    w, h = grootte
    schaal = max(w / bg.width, h / bg.height)
    bg = bg.resize((max(w, round(bg.width * schaal)), max(h, round(bg.height * schaal))), Image.LANCZOS)
    l, t = (bg.width - w) // 2, (bg.height - h) // 2
    return bg.crop((l, t, l + w, t + h))


def _logo_en_watermerk(jpg, watermerk, logo):
    """Watermerk over de hele foto, logo rechtsboven (max. 25% van de breedte)."""
    basis = jpg.convert("RGBA")
    if watermerk and os.path.exists(watermerk):
        wm = Image.open(watermerk).convert("RGBA").resize(basis.size, Image.LANCZOS)
        basis = Image.alpha_composite(basis, wm)
    if logo and os.path.exists(logo):
        lg = Image.open(logo).convert("RGBA")
        maxb = max(1, basis.width // 4)
        if lg.width > maxb:
            lg = lg.resize((maxb, max(1, round(lg.height * maxb / lg.width))), Image.LANCZOS)
        basis.alpha_composite(lg, (max(0, basis.width - lg.width - 10), 10))
    return basis.convert("RGB")


def verwijder_achtergrond(paden, uitmap):
    """Zet PNG's zonder achtergrond in uitmap (zelfde bestandsnaam .png). Probeert rembg, dan
    transparent-background. Geeft een lijst paden terug; gooit RuntimeError als geen van beide werkt."""
    os.makedirs(uitmap, exist_ok=True)
    try:
        from rembg import remove
    except Exception:
        remove = None
    if remove:
        uit = []
        for p in paden:
            doel = os.path.join(uitmap, os.path.splitext(os.path.basename(p))[0] + ".png")
            with open(p, "rb") as f:
                data = remove(f.read())
            with open(doel, "wb") as f:
                f.write(data)
            uit.append(doel)
        return uit

    tb = os.path.join(os.path.dirname(sys.executable), "transparent-background")
    if os.path.isfile(tb):
        cmd = [tb]
    elif shutil.which("transparent-background"):
        cmd = ["transparent-background"]
    else:
        try:
            import transparent_background  # noqa: F401
            cmd = [sys.executable, "-c", "from transparent_background.Remover import console; console()"]
        except Exception:
            raise RuntimeError("Geen achtergrondverwijderaar gevonden. Installeer met ./install.sh --met-ai "
                               "(rembg of transparent-background).")
    tmp = tempfile.mkdtemp()
    try:
        for p in paden:
            shutil.copy2(p, os.path.join(tmp, os.path.basename(p)))
        env = {k: v for k, v in os.environ.items() if not k.startswith("QT_")}
        r = subprocess.run(cmd + ["--source", tmp, "--dest", uitmap, "--type", "rgba", "--mode", "base",
                                  "--device", "cpu", "--format", "png"],
                           capture_output=True, text=True, timeout=1800, env=env)
        if r.returncode != 0:
            raise RuntimeError("Achtergrond verwijderen mislukt: " + (r.stderr or r.stdout)[-300:])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    uit = []
    for p in paden:
        doel = os.path.join(uitmap, os.path.splitext(os.path.basename(p))[0] + ".png")
        if os.path.exists(doel):
            uit.append(doel)
    if not uit:
        raise RuntimeError("Achtergrond verwijderen gaf geen resultaat.")
    return uit


def maak_versies(fotos, doelmap, opties, voortgang=None, stop=lambda: False):
    """fotos: lijst paden. opties (dict):
         transparant, wit, custom (bool), met_logo (bool)
         bg_kleur ('#rrggbb') of bg_afbeelding (pad)  -> voor 'custom'
         watermerk, logo (paden)
       Geeft {"mapnaam": [paden]} terug."""
    def stap(f, tekst):
        if voortgang:
            voortgang(f, tekst)

    os.makedirs(doelmap, exist_ok=True)
    uit = {}
    n = len(fotos)
    nodig_png = opties.get("transparant") or opties.get("wit") or opties.get("custom")

    # 1. originelen (staan ze al in doelmap/originelen, dan blijven ze waar ze zijn)
    d = os.path.join(doelmap, "originelen")
    os.makedirs(d, exist_ok=True)
    for sub in ("transparant", "zonder_logo", "met_logo", "zonder_logo_bg", "met_logo_bg"):
        shutil.rmtree(os.path.join(doelmap, sub), ignore_errors=True)   # oude versies niet mengen
    uit["originelen"] = []
    for i, p in enumerate(fotos):
        if os.path.abspath(os.path.dirname(p)) == os.path.abspath(d):
            uit["originelen"].append(p)
            continue
        doel = os.path.join(d, f"foto_{i + 1:03d}" + os.path.splitext(p)[1].lower())
        shutil.copy2(p, doel)
        uit["originelen"].append(doel)
    stap(0.05, "Originelen opgeslagen")

    # 2. achtergrond verwijderen (alleen als nodig)
    pngs = []
    if nodig_png:
        stap(0.1, "Achtergrond verwijderen (kan even duren)...")
        tmp = tempfile.mkdtemp()
        try:
            pngs = verwijder_achtergrond(uit["originelen"], tmp)
            if stop():
                return uit
            pngs = [_vierkant(_open(p).convert("RGBA")) for p in pngs]
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        if opties.get("transparant"):
            d = os.path.join(doelmap, "transparant")
            os.makedirs(d, exist_ok=True)
            uit["transparant"] = []
            for i, im in enumerate(pngs):
                doel = os.path.join(d, f"foto_{i + 1:03d}.png")
                im.save(doel, "PNG")
                uit["transparant"].append(doel)
    stap(0.6, "Versies maken...")

    # 3. JPEG-versies
    wm, lg = opties.get("watermerk"), opties.get("logo")
    met_logo = bool(opties.get("met_logo") and ((wm and os.path.exists(wm)) or (lg and os.path.exists(lg))))

    def schrijf(naam, afbeeldingen):
        d = os.path.join(doelmap, naam)
        os.makedirs(d, exist_ok=True)
        uit[naam] = []
        for i, im in enumerate(afbeeldingen):
            doel = os.path.join(d, f"foto_{i + 1:03d}.jpg")
            im.save(doel, "JPEG", quality=95)
            uit[naam].append(doel)

    basis_sets = []   # (map zonder logo, map met logo, [RGB-afbeeldingen])
    if opties.get("wit") and pngs:
        basis_sets.append(("zonder_logo", "met_logo", [_naar_rgb(im) for im in pngs]))
    elif not opties.get("wit"):
        # 'laten zoals het is': de originelen als JPEG, zodat de Uploader ze vindt
        basis_sets.append(("zonder_logo", "met_logo", [_naar_rgb(_open(p)) for p in uit["originelen"]]))
    if opties.get("custom") and pngs:
        sets = []
        for im in pngs:
            if opties.get("bg_afbeelding") and os.path.exists(opties["bg_afbeelding"]):
                bg = _achtergrond_afbeelding(opties["bg_afbeelding"], im.size)
                bg.paste(im, (0, 0), im)
                sets.append(bg)
            else:
                k = (opties.get("bg_kleur") or "#ffffff").lstrip("#")
                rgb = tuple(int(k[j:j + 2], 16) for j in (0, 2, 4))
                sets.append(_naar_rgb(im, rgb))
        basis_sets.append(("zonder_logo_bg", "met_logo_bg", sets))

    totaal = max(1, len(basis_sets))
    for k, (zonder, met, ims) in enumerate(basis_sets):
        if stop():
            return uit
        schrijf(zonder, ims)
        if met_logo:
            schrijf(met, [_logo_en_watermerk(im, wm, lg) for im in ims])
        stap(0.6 + 0.4 * (k + 1) / totaal, "Versies maken...")
    stap(1.0, "Klaar")
    return uit


def lijst_fotos(map_):
    uit = []
    for p in sorted(glob.glob(os.path.join(map_, "*"))):
        if p.lower().endswith(FOTO_EXT):
            uit.append(p)
    return uit
