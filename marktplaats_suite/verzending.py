"""Verzendadvies voor Marktplaats: welke pakketklasse en vervoerder passen bij een product.

De limieten en prijzen komen uit de Marktplaats-pakketkeuze (stand november 2026) en staan in
`verzendtabel.json` in de datamap. Pas die gerust aan als prijzen of limieten veranderen.
"""
import json
import os

from marktplaats_suite.common import data_dir

# (klasse, vervoerder, variant, max_kg, (l, b, h) in cm, prijs in euro)
STANDAARD_TABEL = [
    ["Brievenbuspakje", "Budbee", "afhaalpunt", 2, [28, 17.5, 6.5], 2.59],
    ["Brievenbuspakje", "DHL", "thuis", 2, [38, 26.5, 3.2], 4.40],
    ["Brievenbuspakje", "PostNL", "thuis", 2, [38, 26.5, 3.2], 4.40],
    ["Klein pakket", "Budbee", "afhaalpunt", 3, [34, 24, 7], 2.89],
    ["Klein pakket", "DHL", "afhaalpunt", 3, [80, 50, 35], 3.99],
    ["Klein pakket", "DHL", "thuis", 3, [80, 50, 35], 6.29],
    ["Klein pakket", "PostNL", "afhaalpunt", 3, [30, 30, 20], 5.39],
    ["Klein pakket", "PostNL", "thuis", 3, [30, 30, 20], 6.39],
    ["Gemiddeld pakket", "Budbee", "afhaalpunt", 10, [50, 34, 18], 3.49],
    ["Gemiddeld pakket", "DHL", "afhaalpunt", 10, [80, 50, 35], 4.29],
    ["Gemiddeld pakket", "DHL", "thuis", 10, [80, 50, 35], 6.59],
    ["Gemiddeld pakket", "PostNL", "afhaalpunt", 10, [40, 40, 30], 5.69],
    ["Gemiddeld pakket", "PostNL", "thuis", 10, [40, 40, 30], 6.69],
    ["Groot pakket", "Budbee", "afhaalpunt", 20, [59.8, 40, 25], 4.99],
    ["Groot pakket", "DHL", "afhaalpunt", 20, [80, 50, 35], 5.99],
    ["Groot pakket", "DHL", "thuis", 20, [80, 50, 35], 7.99],
    ["Groot pakket", "PostNL", "afhaalpunt", 23, [50, 50, 40], 7.49],
    ["Groot pakket", "PostNL", "thuis", 23, [50, 50, 40], 8.49],
]

VERVOERDERS = ["Budbee", "DHL", "PostNL", "Brenger"]   # zoals Marktplaats ze aanbiedt

STANDAARD_INSTELLINGEN = {
    # welke vervoerders je wilt gebruiken; uit = het advies kiest de eerstvolgende beste optie
    "vervoerders_aan": {"Budbee": True, "DHL": True, "PostNL": True, "Brenger": True},
    # extra cm per afmeting en extra kg voor verpakkingsmateriaal
    "verpakkingsmarge_cm": 2,
    "verpakkingsgewicht_kg": 0.3,
    # categorieën (deel van de naam, hoofdletterongevoelig) waarvoor Marktplaats alleen Brenger toont
    "brenger_categorieen": ["bijzettafel"],
    "alternatieve_categorieen": ["Krukjes", "Overige meubels"],
    "tabel": STANDAARD_TABEL,
}


def _pad():
    return os.path.join(data_dir(), "verzendtabel.json")


def laad_instellingen():
    data = json.loads(json.dumps(STANDAARD_INSTELLINGEN))
    try:
        with open(_pad(), encoding="utf-8") as f:
            data.update(json.load(f))
    except Exception:
        pass
    return data


def vervoerders_aan(instellingen=None):
    ins = instellingen or laad_instellingen()
    aan = dict(STANDAARD_INSTELLINGEN["vervoerders_aan"])
    aan.update(ins.get("vervoerders_aan") or {})
    return aan


def bewaar_vervoerders(aan):
    """Slaat op welke vervoerders aan staan (in verzendtabel.json, de rest blijft zoals het is)."""
    try:
        with open(_pad(), encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = json.loads(json.dumps(STANDAARD_INSTELLINGEN))
    data["vervoerders_aan"] = {v: bool(aan.get(v, True)) for v in VERVOERDERS}
    with open(_pad(), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def sla_standaard_op_als_nodig():
    """Schrijft de standaardtabel weg, zodat de gebruiker hem kan aanpassen."""
    if not os.path.exists(_pad()):
        with open(_pad(), "w", encoding="utf-8") as f:
            json.dump(STANDAARD_INSTELLINGEN, f, indent=2, ensure_ascii=False)


def _getal(tekst):
    try:
        return float(str(tekst).strip().replace(",", "."))
    except (ValueError, AttributeError):
        return None


def verzendadvies(lengte, breedte, hoogte, gewicht, instellingen=None):
    """Geeft een lijst passende opties (goedkoopste eerst), of None als afmetingen/gewicht ontbreken.

    Elke optie: {"klasse","vervoerder","variant","prijs","ruimte_over": bool_krap}
    """
    ins = instellingen or laad_instellingen()
    l, b, h, kg = (_getal(x) for x in (lengte, breedte, hoogte, gewicht))
    if None in (l, b, h, kg) or min(l, b, h) <= 0 or kg <= 0:
        return None
    marge = float(ins["verpakkingsmarge_cm"])
    product = sorted((l + marge, b + marge, h + marge), reverse=True)
    kg_totaal = kg + float(ins["verpakkingsgewicht_kg"])
    aan = vervoerders_aan(ins)
    opties = []
    for klasse, vervoerder, variant, max_kg, afm, prijs in ins["tabel"]:
        if not aan.get(vervoerder, True):
            continue   # vervoerder staat uit
        limiet = sorted(afm, reverse=True)
        if kg_totaal <= max_kg and all(p <= m for p, m in zip(product, limiet)):
            opties.append({"klasse": klasse, "vervoerder": vervoerder, "variant": variant, "prijs": prijs})
    opties.sort(key=lambda o: o["prijs"])
    return opties


def past_in_pakket(lengte, breedte, hoogte, gewicht, instellingen=None):
    adv = verzendadvies(lengte, breedte, hoogte, gewicht, instellingen)
    return bool(adv)


def _euro(x):
    return f"€{x:.2f}".replace(".", ",")


def advies(lengte, breedte, hoogte, gewicht, instellingen=None):
    """Het verzendadvies met alleen de vervoerders die aan staan.

    None als afmetingen of gewicht ontbreken, anders een dict met:
      soort        "pakket", "brenger" of "ophalen"
      klasse       pakketklasse (alleen bij pakket), bijv. "Klein pakket"
      vervoerders  aan te vinken vervoerders op Marktplaats
      goedkoopst   goedkoopste optie (klasse, vervoerder, variant, prijs) of None
      uit          vervoerders die uit staan
      tekst        korte omschrijving voor het formulier en de log
    """
    ins = instellingen or laad_instellingen()
    opties = verzendadvies(lengte, breedte, hoogte, gewicht, ins)
    if opties is None:
        return None
    aan = vervoerders_aan(ins)
    uit = [v for v in VERVOERDERS if not aan.get(v, True)]
    # wat ook zou kunnen bij vervoerders die niet in je voorkeur staan (per vervoerder de goedkoopste)
    alles_aan = dict(ins, vervoerders_aan={v: True for v in VERVOERDERS})
    alle = verzendadvies(lengte, breedte, hoogte, gewicht, alles_aan) or []
    alternatieven, gezien = [], set()
    for o in alle:
        if o["vervoerder"] in uit and o["vervoerder"] not in gezien:
            gezien.add(o["vervoerder"])
            alternatieven.append(o)
    basis = {"uit": uit, "alternatieven": alternatieven}
    if opties:
        g = opties[0]
        klasse = g["klasse"]
        vervoerders = []
        for o in opties:
            if o["klasse"] == klasse and o["vervoerder"] not in vervoerders:
                vervoerders.append(o["vervoerder"])
        if len(vervoerders) == 1:
            prijzen = ", ".join(f"{o['variant']} {_euro(o['prijs'])}" for o in opties if o["klasse"] == klasse)
            tekst = f"{klasse} via {vervoerders[0]} ({prijzen})"
        else:
            tekst = f"{klasse} via {', '.join(vervoerders)} (goedkoopst: {g['vervoerder']} {g['variant']} {_euro(g['prijs'])})"
        return dict(basis, soort="pakket", klasse=klasse, vervoerders=vervoerders, goedkoopst=g, tekst=tekst,
                    alternatieven_tekst=alternatieven_tekst(alternatieven, klasse))
    waarom = "past niet in een pakket" + (" van je voorkeursvervoerders" if alle else "")
    if aan.get("Brenger", True):
        return dict(basis, soort="brenger", klasse=None, vervoerders=["Brenger"], goedkoopst=None,
                    tekst=f"Brenger ({waarom})", alternatieven_tekst=alternatieven_tekst(alternatieven))
    return dict(basis, soort="ophalen", klasse=None, vervoerders=[], goedkoopst=None,
                tekst=f"alleen ophalen ({waarom} en Brenger staat uit)",
                alternatieven_tekst=alternatieven_tekst(alternatieven))


def alternatieven_tekst(alternatieven, klasse=None):
    """'Budbee €3,49, PostNL gemiddeld pakket €5,69' (pakketklasse alleen als die afwijkt)."""
    delen = []
    for o in alternatieven:
        k = "" if o["klasse"] == klasse else f" {o['klasse'].lower()}"
        delen.append(f"{o['vervoerder']}{k} {o['variant']} {_euro(o['prijs'])}")
    return ", ".join(delen)


def advies_tekst(lengte, breedte, hoogte, gewicht, mp_categorie="", instellingen=None):
    """Korte tekst voor in het formulier. Lege string als er niets te melden is."""
    ins = instellingen or laad_instellingen()
    a = advies(lengte, breedte, hoogte, gewicht, ins)
    if a is None:
        return ""
    icoon = "📦" if a["soort"] == "pakket" else "🚚"
    regels = [f"{icoon} Verzendadvies: {a['tekst']}"]
    if a["alternatieven"]:
        regels.append(f"   (ook mogelijk, niet in je voorkeur: {a['alternatieven_tekst']})")
    cat = (mp_categorie or "").lower()
    if a["soort"] == "pakket" and cat and any(k in cat for k in ins["brenger_categorieen"]):
        alt = " of ".join(ins["alternatieve_categorieen"])
        regels.append(f"⚠️ In de categorie '{mp_categorie}' toont Marktplaats alleen Brenger. "
                      f"Dit product past in een pakket: overweeg {alt}.")
    return "\n".join(regels)


def advies_regel(a):
    """Eén regel met het advies en de alternatieven (voor bij het product en in de log)."""
    if not a:
        return ""
    tekst = a["tekst"]
    if a.get("alternatieven"):
        tekst += f"; ook mogelijk, niet in je voorkeur: {a['alternatieven_tekst']}"
    return tekst


def kies_automatisch(lengte, breedte, hoogte, gewicht, instellingen=None):
    """Voor de Uploader: hetzelfde als advies() (None als afmetingen of gewicht ontbreken)."""
    return advies(lengte, breedte, hoogte, gewicht, instellingen)
