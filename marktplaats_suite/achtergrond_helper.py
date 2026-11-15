"""Achtergrond verwijderen met transparent-background, als apart proces.

fotoverwerking.py start dit met:  python -I achtergrond_helper.py bron1 doel1 bron2 doel2 ...
Het model wordt één keer geladen en de foto's gaan één voor één. Per foto komt er een regel
'KLAAR n' of 'FOUT n melding' op stdout. Een geheugenpiek of crash van het model raakt zo alleen
dit proces en niet de app. Zelfde instellingen als de oude Product Studio: mode 'base', CPU, rgba.
"""
import os
import sys

# Pad naar een meegeleverd model (Windows-installatie); anders downloadt transparent-background
# het de eerste keer zelf naar ~/.transparent-background.
MODEL_VAR = "SELLYOURSHIT_TB_CKPT"


def main(argv):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    from PIL import Image
    from transparent_background import Remover

    ckpt = os.environ.get(MODEL_VAR)
    remover = Remover(mode="base", device="cpu", ckpt=ckpt if ckpt and os.path.isfile(ckpt) else None)
    paren = list(zip(argv[0::2], argv[1::2]))
    for nr, (bron, doel) in enumerate(paren, 1):
        try:
            with Image.open(bron) as im:
                uit = remover.process(im.convert("RGB"), type="rgba")
            if not isinstance(uit, Image.Image):
                uit = Image.fromarray(uit)
            uit.save(doel, "PNG")
            print(f"KLAAR {nr}", flush=True)
        except Exception as e:  # één mislukte foto houdt de rest niet tegen
            melding = str(e).replace("\n", " ")[:200]
            print(f"FOUT {nr} {melding}", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
