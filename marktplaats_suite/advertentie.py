"""De advertentietekst van een product, op één plek opgebouwd.

Gebruikt door omschrijving.txt (Nieuw Product, bewerken), het detailvenster, de Uploader
(Marktplaats) en de bridge voor Vinted, zodat overal dezelfde tekst staat.

Opbouw:
    titel
    omschrijving (met eventueel een 'Details:'-lijst, bijvoorbeeld van de AI)
    Details: één doorlopende lijst met '* '-opsommingstekens; de regels van de app
             (afmeting, staat, schades, waarde, artikelnummer) komen onderaan dezelfde lijst
    algemene voorwaarden

Staat een gegeven zowel in de omschrijving als in de velden van de app (bijv. '* Staat: Gebruikt'
van de AI en de gekozen staat), dan blijft alleen de regel van de app staan: die is leidend.
"""
import re

_BULLET = re.compile(r"^\s*[*\-•]\s+([^:]{1,40}):")
_DETAILS_KOP = re.compile(r"^\s*\**\s*details\s*\**\s*:?\s*\**\s*$", re.I)

# welke regels uit de omschrijving vervallen als de app zelf die regel toevoegt
_VERVANGT = {
    "afmeting": {"afmeting", "afmetingen", "maat", "maten", "formaat", "afmeting (lxbxh)",
                 "afmeting (lxbxh & g)", "afmetingen (lxbxh)"},
    "gewicht": {"gewicht"},
    "staat": {"staat", "conditie", "toestand", "conditie/staat"},
    "schades": {"schade", "schades", "gebreken"},
    "waarde": {"waarde", "geschatte waarde"},
    "artikelnummer": {"artikelnummer"},
}


def _sleutel(regel):
    m = _BULLET.match(regel)
    return m.group(1).strip().lower() if m else None


def _is_bullet(regel):
    return bool(re.match(r"^\s*[*\-•]\s+\S", regel))


def app_regels(product):
    """De vaste Details-regels uit de velden van de app, plus welke soorten erin zitten."""
    g = lambda k: (product.get(k) or "").strip()
    regels, soorten = [], set()
    dims = [f"{x}cm" for x in (g("lengte"), g("breedte"), g("hoogte")) if x]
    gewicht = g("gewicht")
    if dims and gewicht:
        regels.append(f"Afmeting (LxBxH & G): {' x '.join(dims)} & {gewicht} kg")
        soorten |= {"afmeting", "gewicht"}
    elif dims:
        regels.append(f"Afmeting (LxBxH): {' x '.join(dims)}")
        soorten.add("afmeting")
    elif gewicht:
        regels.append(f"Gewicht: {gewicht} kg")
        soorten.add("gewicht")
    if g("conditie"):
        regels.append(f"Conditie/Staat: {g('conditie')}")
        soorten.add("staat")
    if g("staat_details"):
        regels.append(f"Schades: {g('staat_details')}")
        soorten.add("schades")
    if g("waarde_min"):
        regels.append(f"Waarde: {g('waarde_min')}" + (f" ~{g('waarde_max')}" if g("waarde_max") else ""))
        soorten.add("waarde")
    if g("artikelnummer"):
        regels.append(f"Artikelnummer: {g('artikelnummer')}")
        soorten.add("artikelnummer")
    return regels, soorten


def omschrijving_met_details(omschrijving, product):
    """Omschrijving met de app-regels in dezelfde Details-lijst, zonder dubbele regels."""
    nieuw, soorten = app_regels(product)
    weg = set().union(*(_VERVANGT[s] for s in soorten)) if soorten else set()
    regels = [r.rstrip() for r in (omschrijving or "").replace("\r", "").split("\n")]
    regels = [r for r in regels if _sleutel(r) not in weg]
    while regels and not regels[-1].strip():
        regels.pop()
    if not nieuw:
        return re.sub(r"\n{3,}", "\n\n", "\n".join(regels)).strip()
    bullets = ["* " + r for r in nieuw]

    kop = max((i for i, r in enumerate(regels) if _DETAILS_KOP.match(r)), default=None)
    if kop is not None:
        # achter de laatste opsomming van het Details-blok (lege regels ertussen tellen niet)
        laatste = kop
        for i in range(kop + 1, len(regels)):
            if _is_bullet(regels[i]):
                laatste = i
            elif regels[i].strip():
                break
        regels = regels[:laatste + 1] + bullets + regels[laatste + 1:]
        # lege regels binnen de lijst weghalen
        blok_eind = laatste + len(bullets)
        regels = regels[:kop + 1] + [r for r in regels[kop + 1:blok_eind + 1] if r.strip()] + regels[blok_eind + 1:]
    elif regels and _is_bullet(regels[-1]):
        regels += bullets                     # omschrijving eindigt al met een lijst
    else:
        regels += ([""] if regels else []) + ["Details:"] + bullets
    return re.sub(r"\n{3,}", "\n\n", "\n".join(regels)).strip()


def advertentietekst(product, met_voorwaarden=True):
    """Volledige advertentietekst: titel, omschrijving met Details, algemene voorwaarden."""
    delen = []
    titel = (product.get("titel") or "").strip()
    if titel:
        delen.append(titel)
    tekst = omschrijving_met_details(product.get("omschrijving") or "", product)
    if tekst:
        delen.append(tekst)
    if met_voorwaarden:
        from marktplaats_suite.voorwaarden import voorwaarden_voor_advertentie
        voorwaarden = (product.get("algemene_voorwaarden") or "").strip() or voorwaarden_voor_advertentie()
        if voorwaarden:
            delen.append(voorwaarden)
    return "\n\n".join(delen)
