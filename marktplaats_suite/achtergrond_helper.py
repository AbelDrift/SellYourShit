"""Achtergrond verwijderen als apart proces, met transparent-background of AlphaMaker.

fotoverwerking.py start dit met:
    python -I achtergrond_helper.py --motor=NAAM bron1 doel1 bron2 doel2 ...
Motoren (zie fotoverwerking.MOTOREN):
    transparent-background   InSPyReNet, zoals de oude Product Studio (mode 'base', CPU, rgba)
    alphamaker-licht         AlphaMaker met IS-Net (ONNX Runtime): snel, ~1 GB geheugen, met
                             AlphaMakers randkleurcorrectie
Het model wordt één keer geladen en de foto's gaan één voor één. Per foto komt er een regel
'KLAAR n' of 'FOUT n melding' op stdout. Een geheugenpiek of crash van het model raakt zo alleen
dit proces en niet de app.
"""
import os
import sys

# Pad naar een meegeleverd transparent-background-model (Windows-installatie); anders downloadt
# transparent-background het de eerste keer zelf naar ~/.transparent-background.
MODEL_VAR = "SELLYOURSHIT_TB_CKPT"


def _remover():
    from transparent_background import Remover
    ckpt = os.environ.get(MODEL_VAR)
    return Remover(mode="base", device="cpu", ckpt=ckpt if ckpt and os.path.isfile(ckpt) else None)


def _alphamaker():
    """De meegeleverde AlphaMaker uit de map naast dit script (marktplaats_suite/alphamaker).

    Rechtstreeks uit die map geladen: met -I staat de map van dit script niet op het pad, en zo
    kan er ook geen andere (oudere) geïnstalleerde versie van de app tussenkomen."""
    import importlib
    import importlib.util
    map_ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "alphamaker")
    naam = "sellyourshit_alphamaker"
    if naam not in sys.modules:
        spec = importlib.util.spec_from_file_location(naam, os.path.join(map_, "__init__.py"),
                                                      submodule_search_locations=[map_])
        pakket = importlib.util.module_from_spec(spec)
        sys.modules[naam] = pakket
        spec.loader.exec_module(pakket)
    return importlib.import_module(naam + ".core")


def maak_verwerker(motor):
    """Geeft een functie PIL-afbeelding -> RGBA-afbeelding zonder achtergrond."""
    from PIL import Image
    if motor == "transparent-background":
        remover = _remover()

        def verwerk(im):
            uit = remover.process(im.convert("RGB"), type="rgba")
            return uit if isinstance(uit, Image.Image) else Image.fromarray(uit)
        return verwerk
    if motor == "alphamaker-licht":
        core = _alphamaker()
        return lambda im: core.cutout(im, "isnet-general")
    raise ValueError(f"onbekende motor: {motor}")


def main(argv):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    motor = "transparent-background"
    if argv and argv[0].startswith("--motor="):
        motor, argv = argv[0].split("=", 1)[1], argv[1:]
    from PIL import Image

    verwerk = maak_verwerker(motor)
    paren = list(zip(argv[0::2], argv[1::2]))
    for nr, (bron, doel) in enumerate(paren, 1):
        try:
            with Image.open(bron) as im:
                im.load()
                uit = verwerk(im)
            uit.save(doel, "PNG")
            print(f"KLAAR {nr}", flush=True)
        except Exception as e:  # één mislukte foto houdt de rest niet tegen
            melding = str(e).replace("\n", " ")[:200]
            print(f"FOUT {nr} {melding}", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
