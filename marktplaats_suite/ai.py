"""AI-hulp: foto's bekijken en titel, omschrijving, kenmerken en waarde voorstellen.

Drie manieren (kies in 'AI-instellingen'):
  gemini     Google Gemini via een gratis API-sleutel (aistudio.google.com)
  openai     elke OpenAI-compatibele dienst: Ollama (lokaal, gratis, geen sleutel), OpenRouter,
             Mistral, OpenAI, LM Studio ...
  handmatig  geen API: de prompt gaat naar het klembord, jij plakt hem in Copilot, ChatGPT,
             DeepSeek of de Gemini-site, en plakt het antwoord terug in de app.
Het antwoord heeft altijd hetzelfde tekstformaat en wordt gelezen met gemini_import.parse.
"""
import base64
import io
import json
import os
import urllib.error
import urllib.request

from marktplaats_suite.common import data_dir

PROVIDERS = {
    "gemini": "Google Gemini (gratis API-sleutel)",
    "openai": "OpenAI-compatibel (Ollama lokaal, OpenRouter, Mistral, OpenAI ...)",
    "handmatig": "Geen API: prompt kopiëren en antwoord plakken (Copilot, ChatGPT, DeepSeek ...)",
}

STANDAARD = {
    "provider": "gemini",
    "gemini_sleutel": "",
    "gemini_model": "gemini-flash-latest",
    "openai_url": "http://localhost:11434/v1",
    "openai_sleutel": "",
    "openai_model": "qwen2.5vl",
    "max_fotos": 6,
}

PROMPT = """Je helpt bij het verkopen van tweedehands spullen op Marktplaats, Whoppah en Vinted. Bekijk de foto's van het object en schrijf het antwoord EXACT in dit formaat, in het Nederlands, zonder inleiding of afsluiting en zonder de woorden "titel" of "omschrijving":

<titel>

<omschrijving>

Details:
* Merk: ...
* Materiaal: ...
* Kleur: ...
* Stijl: ...
* Tijdsperiode: ...
* Staat: ...
* Afmetingen: L x B x H cm (alleen als je dit redelijk kunt schatten)
* Categorie: ...
* Marktplaats-categorie: ...

Geschatte waarde: € MIN tot € MAX

Regels:
- Titel: maximaal 60 tekens, op de eerste regel. Beschrijf de kern van het item en noem ALTIJD het soort voorwerp zelf (bijvoorbeeld Bank, Stoel, Lamp, Vaas, Kast), want daarmee kiest Marktplaats de juiste categorie. Dus niet 'Luxe chesterfield lederen zitting' maar 'Luxe chesterfield lederen bank'.
- Omschrijving: een mooie, verkopende, feitelijke tekst van een of twee alinea's. Verzin niets dat niet te zien is.
- Details: altijd met "* " als opsommingsteken. Laat een regel weg als je het niet kunt zien of weten.
- Staat: kies precies uit Nieuwstaat, Zo goed als nieuw, Gebruikt of Beschadigd.
- Categorie: kies precies uit: {categorieen}.
- Tijdsperiode: kies bij voorkeur uit: {tijdsperiodes}.
- Geschatte waarde: realistische tweedehandsprijs in hele euro's, alleen getallen.
{extra}"""


class AIFout(Exception):
    pass


def _pad():
    return os.path.join(data_dir(), "ai_instellingen.json")


def laad():
    cfg = dict(STANDAARD)
    try:
        with open(_pad(), encoding="utf-8") as f:
            cfg.update(json.load(f))
    except (OSError, ValueError):
        pass
    return cfg


def bewaar(cfg):
    pad = _pad()
    with open(pad, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    try:
        os.chmod(pad, 0o600)   # bevat een API-sleutel
    except OSError:
        pass


def prompt(categorieen=(), tijdsperiodes=(), extra=""):
    return PROMPT.format(
        categorieen=", ".join(categorieen) or "een passende hoofdcategorie",
        tijdsperiodes=", ".join(tijdsperiodes) or "Antiek, Vintage, Retro, Modern",
        extra=(f"- Extra info van de verkoper: {extra}\n" if extra else ""),
    )


def is_klaar(cfg):
    """True als er rechtstreeks een API-aanroep gedaan kan worden."""
    if cfg["provider"] == "gemini":
        return bool(cfg.get("gemini_sleutel", "").strip())
    if cfg["provider"] == "openai":
        return bool(cfg.get("openai_url", "").strip() and cfg.get("openai_model", "").strip())
    return False


def _jpeg_b64(pad, max_px=1024):
    from PIL import Image, ImageOps
    with Image.open(pad) as im:
        im = ImageOps.exif_transpose(im)
        if im.mode in ("RGBA", "LA", "P"):
            im = im.convert("RGBA")
            vlak = Image.new("RGB", im.size, (255, 255, 255))
            vlak.paste(im, mask=im.split()[3])
            im = vlak
        else:
            im = im.convert("RGB")
        im.thumbnail((max_px, max_px))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode()


def _post(url, body, headers):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        tekst = e.read().decode("utf-8", "replace")[:400]
        if e.code in (400, 401, 403):
            raise AIFout(f"De AI weigerde de aanvraag ({e.code}). Controleer API-sleutel en modelnaam.\n{tekst}")
        if e.code == 429:
            raise AIFout("Gratis limiet bereikt (te veel aanvragen). Wacht even en probeer opnieuw.")
        raise AIFout(f"AI-fout {e.code}: {tekst}")
    except urllib.error.URLError as e:
        raise AIFout(f"Geen verbinding met de AI: {e.reason}")
    except (TimeoutError, OSError) as e:
        raise AIFout(f"Geen verbinding met de AI: {e}")


def vraag(cfg, fotos, categorieen=(), tijdsperiodes=(), extra=""):
    """Stuurt de foto's naar de gekozen AI en geeft de antwoordtekst terug."""
    if not fotos:
        raise AIFout("Voeg eerst foto's toe.")
    if not is_klaar(cfg):
        raise AIFout("De AI is nog niet ingesteld (zie AI-instellingen).")
    tekst = prompt(categorieen, tijdsperiodes, extra)
    plaatjes = [_jpeg_b64(p) for p in fotos[: int(cfg.get("max_fotos", 6))]]

    if cfg["provider"] == "gemini":
        model = cfg.get("gemini_model") or STANDAARD["gemini_model"]
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        delen = [{"text": tekst}] + [{"inline_data": {"mime_type": "image/jpeg", "data": b}} for b in plaatjes]
        antw = _post(url, {"contents": [{"parts": delen}]}, {"x-goog-api-key": cfg["gemini_sleutel"].strip()})
        try:
            uit = "".join(d.get("text", "") for d in antw["candidates"][0]["content"]["parts"])
        except (KeyError, IndexError, TypeError):
            raise AIFout("Gemini gaf geen antwoord (mogelijk geblokkeerd door een filter).")
    else:
        basis = cfg["openai_url"].strip().rstrip("/")
        inhoud = [{"type": "text", "text": tekst}] + [
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b}} for b in plaatjes]
        kop = {"Authorization": "Bearer " + cfg["openai_sleutel"].strip()} if cfg.get("openai_sleutel", "").strip() else {}
        antw = _post(basis + "/chat/completions",
                     {"model": cfg["openai_model"].strip(), "messages": [{"role": "user", "content": inhoud}]}, kop)
        try:
            uit = antw["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise AIFout("De AI gaf een onverwacht antwoord.")
    if not (uit or "").strip():
        raise AIFout("De AI gaf een leeg antwoord.")
    return uit.strip()
