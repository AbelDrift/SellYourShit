#!/usr/bin/env python3
"""
Marktplaats Automatisering - GTK Versie
Alle instellingen binnen de GUI
"""

import os
import shutil
from marktplaats_suite.common import IS_WINDOWS, zoek_programma, afbeeldingen_map, open_extern, data_dir, asset, get_xml_path, TabBasis, run_standalone
import sys
import time
import threading
import re
import json
import subprocess
from pathlib import Path

# GTK imports - deze komen van de systeem packages (python3-gi)
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
gi.require_version('Pango', '1.0')
from gi.repository import Gtk, Gdk, Pango, GLib, GdkPixbuf

# Probeer selenium te importeren
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.common.action_chains import ActionChains
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
except ImportError as e:
    print(f"❌ Fout: {e}")
    print("📌 Installeer selenium met: pip install selenium")
    raise

# ============================================
# CONFIGURATIE BESTAND
# ============================================

class ConfigManager:
    def __init__(self, config_file=None):
        self.config_file = config_file or os.path.join(data_dir(), "automater_config.json")
        self.config = self._load()

    def _load(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    return json.load(f)
            except:
                return self._default_config()
        return self._default_config()

    def _default_config(self):
        return {
            "storage": {
                "xml_path": ""
            },
            "browser": "auto",
            "vinted": {"prijs_terugval_factor": 0.85},
            "whoppah": {"prijs_factor": 1.25, "ondergrens_factor": 0.85, "stap_procent": 5,
                        "interval": "twee weken", "biedingen": True, "ophalen": True},
            "chrome": {
                "user_data_dir": "",   # leeg = eigen profiel van de app
                "profile": "Default"
            },
            "paths": {
                "base_image_path": afbeeldingen_map()
            },
            "preferences": {
                "max_title_length": 60,
                "wait_between_products": 3
            }
        }

    def save(self):
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=2)
            return True
        except Exception as e:
            print(f"Fout bij opslaan: {e}")
            return False

    def get(self, key, default=None):
        keys = key.split('.')
        value = self.config
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        return value

    def set(self, key, value):
        keys = key.split('.')
        target = self.config
        for k in keys[:-1]:
            if k not in target:
                target[k] = {}
            target = target[k]
        target[keys[-1]] = value
        self.save()

# ============================================
# LOGGING
# ============================================

class Logger:
    def __init__(self, text_view=None):
        self.text_view = text_view
        self.buffer = None
        if text_view:
            self.buffer = text_view.get_buffer()

    luisteraars = []   # functies die elke logregel krijgen (bijv. het losse uploadvenster)

    def log(self, msg, level="INFO"):
        timestamp = time.strftime("%H:%M:%S")
        formatted = f"[{timestamp}] {level}: {msg}\n"
        print(formatted, end="")
        for f in list(Logger.luisteraars):
            try:
                f(level, msg)
            except Exception:
                pass
        if self.buffer:
            # GTK is niet thread-safe. Het hele plaats-proces draait in een
            # achtergrondthread, dus rechtstreeks aan self.buffer/text_view
            # zitten (zoals hier eerder gebeurde, inclusief een handmatige
            # Gtk.main_iteration()-pomp) is een klassieke oorzaak van
            # willekeurige, moeilijk te reproduceren crashes. Via
            # GLib.idle_add gebeurt de daadwerkelijke widget-aanpassing
            # altijd op de GTK-hoofdthread.
            GLib.idle_add(self._append_to_buffer, formatted)

    def _append_to_buffer(self, formatted):
        end_iter = self.buffer.get_end_iter()
        self.buffer.insert(end_iter, formatted)
        mark = self.buffer.create_mark(None, self.buffer.get_end_iter(), False)
        self.text_view.scroll_to_mark(mark, 0.0, True, 0.0, 0.0)
        return False  # eenmalige idle-callback, niet herhalen

    def info(self, msg): self.log(msg, "INFO")
    def warning(self, msg): self.log(msg, "⚠️")
    def error(self, msg): self.log(msg, "❌")
    def success(self, msg): self.log(f"✅ {msg}", "SUCCESS")
    def step(self, num, msg): self.log(f"📍 Stap {num}: {msg}", "STEP")

# ============================================
# ALGEMENE VOORWAARDEN
# ============================================

ALGEMENE_VOORWAARDEN = """Algemene voorwaarden:
Wij zijn een kleine kringloopwinkel en proberen z.s.m. te reageren. Soms is het heel druk in de winkel en lukt dit niet dezelfde dag.

De richtprijs van een product baseren wij op bestaand aanbod en staat van het artikel met minimum/maximum schatting.

Graag alleen biedingen plaatsen via de bied optie van marktplaats. Advertenties laten we vaak minimaal 2 weken online staan voordat we akkoord gaan met het hoogste aannemelijke bod. Bedankt voor uw begrip 🙏🏻

Als wij akkoord gaan met uw bod, reserveren wij het product maximaal een week voor u. U kunt het product ophalen en afrekenen in onze winkel.

U bent altijd welkom in onze winkel, maar langskomen voor de Marktplaats advertenties zonder afspraak wordt niet op prijs gesteld. Dit gaat altijd via specifieke medewerkers.

Let op: Bij ophalen in de winkel vervalt het herroepingsrecht en kun je het product ter plekke testen.

Ons adres:
Kringloop HerNieuw
Willem Beukelszstraat 6B
3261 LV Oud-Beijerland

Openingstijden Kringloop:
Dinsdag t/m vrijdag 10.00 – 16.00 uur
Zaterdag 10:00-13:00 uur
Zondag en maandag Gesloten"""

# Kolomvolgorde - identiek aan marktplaats_productmanager.py, zodat
# beide apps dezelfde Sheet/XML kunnen lezen/schrijven.
from marktplaats_suite.common import COLUMNS
COL = {naam: idx for idx, naam in enumerate(COLUMNS)}

def build_description(product):
    """Advertentietekst voor Marktplaats/Vinted, altijd vers uit de productgegevens (advertentie.py)."""
    from marktplaats_suite.advertentie import advertentietekst
    row = product.get("row", [])
    data = dict(zip(COLUMNS, [(x or "") for x in row])) if row else dict(product.get("data") or {})
    if product.get("titel"):
        data["titel"] = product["titel"]
    return advertentietekst(data)

def _firefox_pad():
    return zoek_programma(["firefox", "firefox-esr"],
                          [r"%ProgramFiles%\Mozilla Firefox\firefox.exe",
                           r"%ProgramFiles(x86)%\Mozilla Firefox\firefox.exe",
                           r"%LOCALAPPDATA%\Mozilla Firefox\firefox.exe"])


def _chrome_pad():
    return zoek_programma(["google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome"],
                          [r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
                           r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
                           r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"])


def _is_snap(pad):
    """Of deze browser een snap is: Ubuntu levert Firefox en Chromium als snap."""
    if not pad or IS_WINDOWS:
        return False
    echt = os.path.realpath(pad)
    if pad.startswith("/snap/") or echt.startswith("/snap/") or os.path.basename(echt) == "snap":
        return True
    try:
        with open(echt, "rb") as f:
            kop = f.read(4096)
        return kop.startswith(b"#!") and b"/snap/" in kop   # /usr/bin/firefox op Ubuntu is een startscript
    except OSError:
        return False


# Een snap-browser kan niet in de /tmp van andere programma's en niet in verborgen mappen zoals
# ~/.local kijken. Gebruik daarom het programma en de driver uit de snap zelf, met het profiel in ~/snap.
SNAP_BROWSERS = {
    "firefox": ("/snap/firefox/current/usr/lib/firefox/firefox",
                ("/snap/bin/geckodriver", "/snap/bin/firefox.geckodriver"), "~/snap/firefox/common"),
    "chromium": ("/snap/chromium/current/usr/lib/chromium-browser/chrome",
                 ("/snap/bin/chromium.chromedriver",), "~/snap/chromium/common"),
}


def _snap_onderdelen(naam):
    """(programma, driver, profielmap) voor een snap-browser; None voor wat er niet is."""
    programma, drivers, map_ = SNAP_BROWSERS[naam]
    driver = next((d for d in drivers if os.path.exists(d)), None)
    return (programma if os.path.exists(programma) else None, driver,
            os.path.join(os.path.expanduser(map_), "sellyourshit_profiel"))


# ============================================
# MARKTPLAATS AUTOMATOR
# ============================================

class MarktplaatsAuto:
    def __init__(self, config, logger):
        self.config = config
        self.logger = logger
        self.driver = None
        self.wait = None
        self.running = False
        self.products = []
        self.pending = []
        self.current = None
        self.step = 0
        self.wait_for_user = False
        self.was_skipped = False
        self.on_wait_for_user = None
        self.on_vraag_logo = None
        self.start_url = "https://www.marktplaats.nl/plaats"
        self._logo_keuze = None
        self.user_logged_in = False

    # ------------------------------------------------------------
    # Foto's zoeken: welke map uit Product Studio moet er geüpload worden?
    # ------------------------------------------------------------
    _FOTO_EXT = ('.jpg', '.jpeg', '.png', '.gif', '.webp')

    def _fotos_in(self, map_pad):
        if not os.path.isdir(map_pad):
            return []
        return sorted(os.path.join(map_pad, f) for f in os.listdir(map_pad)
                      if f.lower().endswith(self._FOTO_EXT))

    def _basismappen(self):
        kandidaten = [self.config.get('paths.base_image_path', "")]
        try:
            with open(os.path.join(data_dir(), "fotomanager_config.json")) as fh:
                uitvoer = json.load(fh).get('output_dir', '')
            if uitvoer:
                kandidaten.append(os.path.dirname(uitvoer.rstrip('/')))
        except Exception:
            pass
        xml = get_xml_path() or ""
        if xml:
            xml = os.path.expanduser(xml)
            kandidaten.append(xml if os.path.isdir(xml) else os.path.dirname(xml))
        kandidaten.append(os.path.expanduser("~/Marktplaats/Producten"))
        kandidaten.append(afbeeldingen_map())
        gezien, uit = set(), []
        for k in kandidaten:
            k = os.path.expanduser(k or "")
            if k and k not in gezien:
                gezien.add(k)
                uit.append(k)
        return uit

    def _zoek_fotos(self, artikel, modus="vraag"):
        """Kiest de map met foto's voor Marktplaats (nooit 'transparant': PNG's zonder achtergrond)."""
        artikelmap = None
        for basis in self._basismappen():
            kandidaat = os.path.join(basis, artikel)
            if os.path.isdir(kandidaat):
                artikelmap = kandidaat
                break
        if not artikelmap:
            self.logger.warning(f"   ⚠️ Geen map '{artikel}' gevonden in: " + ", ".join(self._basismappen()))
            return []

        # Gekozen achtergrond (niet wit) heeft eigen mappen; 'met_logo' bevat bij
        # 'originele achtergrond behouden' de foto's met de originele achtergrond.
        if self._fotos_in(os.path.join(artikelmap, "zonder_logo_bg")) or \
           self._fotos_in(os.path.join(artikelmap, "met_logo_bg")):
            met, zonder = "met_logo_bg", "zonder_logo_bg"
        else:
            met, zonder = "met_logo", "zonder_logo"
        met_fotos = self._fotos_in(os.path.join(artikelmap, met))
        zonder_fotos = self._fotos_in(os.path.join(artikelmap, zonder))

        if modus == "zonder" and zonder_fotos:
            gekozen, fotos = zonder, zonder_fotos
        elif met_fotos and zonder_fotos:
            keuze = self._logo_keuze
            if keuze is None:
                keuze = self.on_vraag_logo(artikel) if self.on_vraag_logo else "met"
                if keuze == "stop":
                    self.running = False
                    return []
                if isinstance(keuze, tuple):   # (keuze, onthouden)
                    keuze, onthouden = keuze
                    if onthouden:
                        self._logo_keuze = keuze
            gekozen = met if keuze == "met" else zonder
            fotos = met_fotos if keuze == "met" else zonder_fotos
        elif met_fotos:
            gekozen, fotos = met, met_fotos
        elif zonder_fotos:
            gekozen, fotos = zonder, zonder_fotos
        else:
            self.logger.warning(f"   ⚠️ Geen foto's in {artikelmap} (gezocht in {met}/ en {zonder}/)")
            return []
        self.logger.info(f"   📁 Foto's uit: {os.path.join(artikelmap, gekozen)}")
        return fotos

    _OMSCHRIJVING_SELECTORS = [
        "div.RichTextEditor-module-editorInput[data-testid='text-editor-input_nl-NL']",
        "[data-testid^='text-editor-input']",
        "div[class*='RichTextEditor'][contenteditable='true']",
        "div[contenteditable='true'][role='textbox']",
        "div[contenteditable='true']",
        "textarea[name='description']",
        "textarea",
    ]

    def _vul_omschrijving(self, tekst):
        """Zoekt het omschrijvingsveld (meerdere mogelijke selectors), vult het en controleert het resultaat."""
        veld = None
        eind = time.time() + 20
        while time.time() < eind and veld is None:
            for sel in self._OMSCHRIJVING_SELECTORS:
                for el in self.driver.find_elements(By.CSS_SELECTOR, sel):
                    try:
                        if el.is_displayed():
                            veld = el
                            self.logger.info(f"   ℹ️ Omschrijvingsveld gevonden via: {sel}")
                            break
                    except Exception:
                        continue
                if veld is not None:
                    break
            if veld is None:
                time.sleep(0.5)
        if veld is None:
            raise RuntimeError("omschrijvingsveld niet gevonden op de pagina (selector verouderd?)")

        self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", veld)
        try:
            veld.click()
        except Exception:
            self.driver.execute_script("arguments[0].focus();", veld)
        time.sleep(0.3)

        if veld.tag_name.lower() == "textarea":
            veld.send_keys(tekst)
        else:
            for regel in tekst.split("\n"):
                if regel.strip():
                    self.driver.execute_script(
                        "document.execCommand('insertText', false, arguments[0]);", regel)
                veld.send_keys(Keys.ENTER)
                time.sleep(0.05)

        ingevuld = self.driver.execute_script(
            "return (arguments[0].value !== undefined && arguments[0].tagName==='TEXTAREA')"
            " ? arguments[0].value : arguments[0].innerText;", veld) or ""
        if len(ingevuld.strip()) < min(20, len(tekst.strip())):
            # Terugval: tekst direct in het veld zetten en het input-event afvuren
            self.driver.execute_script(
                "var e=arguments[0],t=arguments[1];e.focus();"
                "if(e.tagName==='TEXTAREA'){e.value=t;}else{e.innerText=t;}"
                "e.dispatchEvent(new InputEvent('input',{bubbles:true,inputType:'insertText',data:t}));"
                "e.dispatchEvent(new Event('change',{bubbles:true}));", veld, tekst)
            time.sleep(0.3)
            self.logger.info("   ℹ️ Omschrijving via terugvalmethode ingevuld")
        self.logger.info("   ✅ Omschrijving ingevuld")

    def start_browser(self):
        for k in [k for k in os.environ if k.startswith("QT_")]:
            os.environ.pop(k, None)
        keuze = self.config.get('browser', 'auto')
        if keuze == 'auto':
            ff, ch = _firefox_pad(), _chrome_pad()
            # een gewone (niet-snap) Chrome werkt het zekerst als Firefox een snap is (Ubuntu)
            keuze = 'chrome' if (ff and _is_snap(ff) and ch and not _is_snap(ch)) else ('firefox' if ff else 'chrome')
        return self._start_firefox() if keuze == 'firefox' else self._start_chrome()

    def _start_firefox(self):
        from selenium.webdriver.firefox.options import Options as FFOptions
        self.logger.info("🚀 Start Firefox...")
        pad = _firefox_pad()
        if not pad:
            self.last_error = ("Firefox is niet gevonden. Installeer Firefox of kies Chrome bij Instellingen." if IS_WINDOWS
                               else "Firefox is niet gevonden. Installeer firefox-esr of kies Chrome bij Instellingen.")
            self.logger.error(self.last_error)
            return False
        # Eigen profiel: één keer inloggen op Marktplaats, daarna onthouden.
        profiel = os.path.join(data_dir(), "firefox_profiel")
        driver = None
        if _is_snap(pad):
            programma, driver, profiel = _snap_onderdelen("firefox")
            pad = programma or pad
            self.logger.info("   Firefox is een snap: driver en profiel uit de snap")
        os.makedirs(profiel, exist_ok=True)
        opts = FFOptions()
        opts.binary_location = pad
        opts.add_argument("-profile")
        opts.add_argument(profiel)
        opts.set_preference("dom.webdriver.enabled", False)
        opts.set_preference("useAutomationExtension", False)
        try:
            if driver:
                from selenium.webdriver.firefox.service import Service as FFService
                self.driver = webdriver.Firefox(options=opts, service=FFService(executable_path=driver))
            else:
                self.driver = webdriver.Firefox(options=opts)
            try:
                self.driver.set_window_size(1600, 1000)
            except Exception:
                pass
            self.wait = WebDriverWait(self.driver, 15)
            self.logger.success("Firefox gestart!")
            return True
        except Exception as e:
            self.last_error = str(e).strip().splitlines()[0][:200] if str(e).strip() else repr(e)
            self.logger.error(f"Firefox fout: {e}")
            self.logger.info("💡 Sluit het automatiserings-Firefox-venster als dat nog openstaat en probeer opnieuw")
            return False

    def _start_chrome(self):
        self.logger.info("🚀 Start Chrome...")
        options = Options()
        chrome_config = self.config.get('chrome', {})
        user_data_dir = chrome_config.get('user_data_dir') or ""
        profile = chrome_config.get('profile', "Default")
        standaard_dirs = {os.path.normpath(os.path.expanduser("~/.config/google-chrome")),
                          os.path.normpath(os.path.expanduser("~/.config/chromium")), "", "."}
        if IS_WINDOWS:
            standaard_dirs.add(os.path.normpath(os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data")))
        if os.path.normpath(os.path.expanduser(user_data_dir)) in standaard_dirs:
            # Recente Chrome-versies laten automatisering op het standaardprofiel niet toe,
            # en dan start Chrome niet. Eigen profiel: één keer inloggen, daarna onthouden.
            user_data_dir = os.path.join(data_dir(), "chrome_profiel")
            profile = "Default"
            os.makedirs(user_data_dir, exist_ok=True)
        pad = _chrome_pad()
        driver = None
        if pad and _is_snap(pad):
            programma, driver, snap_profiel = _snap_onderdelen("chromium")
            pad = programma or pad
            if user_data_dir == os.path.join(data_dir(), "chrome_profiel"):
                user_data_dir = snap_profiel
                os.makedirs(user_data_dir, exist_ok=True)
            self.logger.info("   Chromium is een snap: driver en profiel uit de snap")
        if pad:
            options.binary_location = pad
        else:
            self.last_error = ("Google Chrome is niet geïnstalleerd. Installeer Chrome of kies Firefox." if IS_WINDOWS else
                               "Chrome of Chromium is niet geïnstalleerd. Draai ./install.sh --met-chrome")
            self.logger.error(self.last_error)
            return False

        options.add_argument(f"--user-data-dir={user_data_dir}")
        options.add_argument(f"--profile-directory={profile}")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--window-size=1920,1080')

        try:
            if driver:
                from selenium.webdriver.chrome.service import Service as ChromeService
                self.driver = webdriver.Chrome(options=options, service=ChromeService(executable_path=driver))
            else:
                self.driver = webdriver.Chrome(options=options)
            self.wait = WebDriverWait(self.driver, 15)
            self.logger.success("Chrome gestart!")
            return True
        except Exception as e:
            self.last_error = str(e).strip().splitlines()[0][:200] if str(e).strip() else repr(e)
            self.logger.error(f"Chrome fout: {e}")
            self.logger.info("💡 Zorg dat dit Chrome-profiel niet al open staat en probeer opnieuw")
            return False

    def wait_for_manual_login(self):
        self.logger.info("=" * 50)
        self.logger.info("🔑 LOG IN OP MARKTPLAATS")
        self.logger.info("=" * 50)
        self.logger.info("📌 Open de browser en log handmatig in op Marktplaats")
        self.logger.info("📌 Na het inloggen, klik op de knop 'Ingelogd' in de GUI")
        self.logger.info("=" * 50)

        self.driver.get("https://www.marktplaats.nl")
        time.sleep(2)

        while not self.user_logged_in and self.running:
            time.sleep(0.5)

        if not self.running:
            return False

        self.logger.success("✅ Gebruiker heeft ingelogd!")
        time.sleep(2)
        return True

    def load_products(self):
        self.logger.info("📄 Laden uit lokaal XML-bestand...")
        xml_path = get_xml_path()
        if not xml_path:
            self.logger.error("XML-pad niet ingesteld!")
            return False
        if not os.path.exists(xml_path):
            self.logger.error(f"XML-bestand niet gevonden: {xml_path}")
            return False

        try:
            import xml.etree.ElementTree as ET
            tree = ET.parse(xml_path)
            root = tree.getroot()

            rows = []
            for idx, prod_el in enumerate(root.findall("product"), start=2):
                row = []
                for c in COLUMNS:
                    el = prod_el.find(c)
                    row.append(el.text if el is not None and el.text else "")

                artikelnummer = row[COL["artikelnummer"]].strip() if row[COL["artikelnummer"]] else ""
                titel = row[COL["titel"]].strip() if len(row) > COL["titel"] and row[COL["titel"]] else ""
                categorie = row[COL["categorie"]].strip() if len(row) > COL["categorie"] and row[COL["categorie"]] else ""
                online = row[COL["online"]].strip().lower() if len(row) > COL["online"] and row[COL["online"]] else ""
                verkocht = row[COL["verkocht"]].strip().lower() if len(row) > COL["verkocht"] and row[COL["verkocht"]] else ""
                kanalen = [k.strip().lower() for k in (row[COL["kanalen"]] or "").split(",") if k.strip()] or ["marktplaats"]

                filter_ = getattr(self, "filter_nummers", None)
                if filter_ is not None and artikelnummer not in filter_:
                    continue  # alleen de producten die in Product Management zijn gekozen
                if verkocht == "ja":
                    continue  # verkochte producten niet opnieuw plaatsen
                if online == "ja" or "marktplaats" not in kanalen:
                    continue  # al op Marktplaats, of niet voor Marktplaats bedoeld

                if artikelnummer and titel:
                    rows.append({
                        "rij": idx,
                        "artikelnummer": artikelnummer,
                        "titel": titel,
                        "categorie": categorie or titel,
                        "data": dict(zip(COLUMNS, [x or "" for x in row])),
                        "row": row
                    })

            self.products = rows
            self.pending = rows.copy()
            self.logger.info(f"✅ {len(rows)} producten geladen uit XML")
            return True

        except Exception as e:
            self.logger.error(f"Fout bij laden uit XML: {e}")
            return False

    def process_products(self):
        total = len(self.pending)
        processed = 0

        for product in self.pending:
            if not self.running:
                break

            processed += 1
            self.current = product
            self.logger.info(f"\n{'='*50}")
            self.logger.info(f"📦 Product {processed}/{total}: {product['artikelnummer']}")
            self.logger.info(f"📝 Titel: {product['titel']}")
            product["verzend_tekst"] = self._verzend_tekst(product)
            for regel in product["verzend_tekst"].split("\n"):
                self.logger.info(f"📦 {regel}")
            if getattr(self, "on_verzendadvies", None):
                self.on_verzendadvies(product["verzend_tekst"])
            self.logger.info(f"{'='*50}")

            if not self.process_one_product(product):
                self.logger.warning(f"⏭️ Product {product['artikelnummer']} overgeslagen")
                continue

            if processed < total and self.running:
                wait_time = self.config.get('preferences.wait_between_products', 3)
                self.logger.info(f"⏳ Wacht {wait_time} seconden...")
                time.sleep(wait_time)

        if self.running:
            self.logger.success(f"🎉 Alle {processed} producten verwerkt!")
        else:
            self.logger.info(f"⏹️ Gestopt na {processed} producten")

    # ------------------------------------------------------------------
    # Keuzes op de Marktplaats-pagina op basis van tekst (radio/checkbox)
    # ------------------------------------------------------------------
    _JS_ZOEK_KEUZE = """
        const soort = arguments[0], tekst = arguments[1].toLowerCase(), begin = arguments[2];
        const norm = s => s.replace(/\\s+/g, ' ').trim().toLowerCase();
        let beste = null, besteLen = 1e9;
        for (const inp of document.querySelectorAll('input[type=' + soort + ']')) {
            // zoek de bijbehorende tekst: label[for], omringend label, ouder of grootouder (alleen korte teksten)
            const lbl = inp.id ? document.querySelector('label[for="' + inp.id + '"]') : null;
            const kandidaten = [lbl, inp.closest('label'), inp.parentElement,
                                inp.parentElement && inp.parentElement.parentElement];
            let t = '';
            for (const c of kandidaten) {
                const ct = c ? norm(c.textContent || '') : '';
                if (ct && ct.length < 120) { t = ct; break; }
            }
            if (!t) continue;
            const ok = begin ? t.startsWith(tekst) : t.includes(tekst);
            if (ok && t.length < besteLen) { beste = inp; besteLen = t.length; }
        }
        return beste;
    """

    _JS_KLIK_LABEL = """
        const inp = arguments[0];
        const lbl = (inp.id && document.querySelector('label[for="' + inp.id + '"]')) || inp.closest('label') || inp.parentElement;
        if (lbl) { lbl.scrollIntoView({block:'center'}); lbl.click(); return true; }
        return false;
    """

    def _zet_keuze(self, soort, tekst, aan=True, begin=False):
        """Zet een radio/checkbox aan of uit op basis van de zichtbare tekst.

        None als hij niet gevonden is, True als hij daarna goed staat, False als dat niet lukte."""
        inp = self.driver.execute_script(self._JS_ZOEK_KEUZE, soort, tekst, begin)
        if inp is None:
            return None
        for poging in range(3):
            if bool(self.driver.execute_script("return arguments[0].checked;", inp)) == aan:
                return True
            if poging == 0:
                self.driver.execute_script(
                    "arguments[0].scrollIntoView({block:'center'}); arguments[0].click();", inp)
            elif poging == 1:
                self.driver.execute_script(self._JS_KLIK_LABEL, inp)   # sommige knoppen reageren alleen op het label
            time.sleep(0.4)
        return bool(self.driver.execute_script("return arguments[0].checked;", inp)) == aan

    def _klik_verder(self):
        """Klikt op de knop 'Verder'; valt terug op Tab-navigatie zoals voorheen."""
        try:
            knop = self.driver.find_element(
                By.XPATH, "//button[normalize-space()='Verder' or .//*[normalize-space()='Verder']]")
            self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", knop)
            knop.click()
            return
        except Exception:
            self.logger.warning("   ⚠️ Knop 'Verder' niet gevonden, ik probeer toetsenbordnavigatie")
        actions = ActionChains(self.driver)
        for _ in range(4):
            actions.send_keys(Keys.TAB)
        actions.send_keys(Keys.ENTER).perform()

    def _verzendadvies(self, product):
        from marktplaats_suite.verzending import advies
        row = product["row"]
        def veld(naam):
            return row[COL[naam]] if len(row) > COL[naam] else ""
        return advies(veld("lengte"), veld("breedte"), veld("hoogte"), veld("gewicht"))

    def _verzend_tekst(self, product):
        """Het advies van bij de registratie, plus het advies van nu als dat anders is."""
        from marktplaats_suite.verzending import advies_regel
        row = product["row"]
        bewaard = (row[COL["verzendadvies"]] if len(row) > COL["verzendadvies"] else "") or ""
        try:
            nu = advies_regel(self._verzendadvies(product))
        except Exception:
            nu = ""
        if bewaard and (not nu or nu == bewaard):
            return f"Verzendadvies (bij registratie): {bewaard}"
        if bewaard:
            return f"Verzendadvies (bij registratie): {bewaard}\nVerzendadvies nu (met je huidige voorkeur): {nu}"
        return f"Verzendadvies: {nu}" if nu else "Verzendadvies: geen (afmetingen of gewicht ontbreken)"

    def _kies_pakketgrootte(self, klasse):
        """Zoekt het keuzerondje van de pakketgrootte op een paar manieren (tekst kan afwijken)."""
        for tekst, begin in ((klasse.lower(), True), (klasse.split()[0].lower(), True), (klasse.lower(), False)):
            if self._zet_keuze("radio", tekst, True, begin=begin):
                return True
        return False

    def _vervoerder_tekst(self, naam):
        """(tekst, begin) waarmee het vinkje van deze vervoerder te vinden is, of None."""
        for begin in (True, False):
            if self.driver.execute_script(self._JS_ZOEK_KEUZE, "checkbox", naam.lower(), begin) is not None:
                return naam.lower(), begin
        return None

    def _stel_verzending_in(self, product):
        """Vinkt de gekozen vervoerders aan (of uit) en kiest de pakketgrootte volgens het verzendadvies."""
        from marktplaats_suite.verzending import VERVOERDERS
        a = self._verzendadvies(product)
        if not a:
            self.logger.info("   ℹ️ Verzending: geen advies (afmetingen of gewicht ontbreken), handmatig instellen")
            return
        zoek = {n: self._vervoerder_tekst(n) for n in VERVOERDERS}
        aanwezig = {n for n, z in zoek.items() if z}
        if not aanwezig:
            if a["soort"] == "ophalen" and self._zet_keuze("radio", "ophalen", True, begin=True):
                self.logger.info("   ✅ Levering: ophalen (geen van de gekozen vervoerders past)")
            else:
                self.logger.warning(f"   ⚠️ Geen vervoerders gevonden in het formulier: stel zelf in → {a['tekst']}")
            return
        if a["soort"] == "pakket" and not aanwezig & {"Budbee", "DHL", "PostNL"}:
            self.logger.warning(f"   ⚠️ Deze categorie toont geen pakketvervoerders (alleen {', '.join(sorted(aanwezig))}). "
                                f"Advies: {a['tekst']}; kies zelf of kies een andere categorie")
            return
        mislukt = []
        for naam in VERVOERDERS:
            if naam in aanwezig:
                tekst, begin = zoek[naam]
                if self._zet_keuze("checkbox", tekst, naam in a["vervoerders"], begin=begin) is False:
                    mislukt.append(naam)
        if mislukt:
            self.logger.warning(f"   ⚠️ Kon {', '.join(mislukt)} niet goed (uit)vinken: controleer de vervoerders")
        if a["soort"] == "pakket":
            if self._kies_pakketgrootte(a["klasse"]):
                self.logger.info(f"   ✅ Verzending: {a['klasse']} via {', '.join(v for v in a['vervoerders'] if v in aanwezig)}")
            else:
                self.logger.warning(f"   ⚠️ Pakketgrootte niet automatisch gekozen: kies zelf '{a['klasse']}'")
        elif a["soort"] == "brenger":
            if "Brenger" in aanwezig:
                self.logger.info("   ✅ Verzending: Brenger")
            else:
                self.logger.warning("   ⚠️ Brenger staat niet in dit formulier: kies zelf een verzendmethode of ophalen")
        else:
            if self._zet_keuze("radio", "ophalen", True, begin=True):
                self.logger.info("   ✅ Levering: ophalen (geen van de gekozen vervoerders past)")
            else:
                self.logger.warning("   ⚠️ Geen van de gekozen vervoerders past: zet de levering zelf op ophalen")

    def process_one_product(self, product):
        """Plaatst het product op Marktplaats."""
        return self._plaats_marktplaats(product)

    def _plaats_marktplaats(self, product):
        try:
            self.start_url = "https://www.marktplaats.nl/plaats"
            self.step = 1
            self.logger.step(self.step, "Naar plaats pagina")
            self.driver.get("https://www.marktplaats.nl/plaats")
            time.sleep(2)

            self.step = 2
            self.logger.step(self.step, "Categorie invullen")
            max_len = self.config.get('preferences.max_title_length', 60)
            cat = product['categorie'][:max_len].strip()
            cat = re.sub(r'[^\x00-\x7F]+', '', cat)

            try:
                cat_field = self.driver.find_element(By.CSS_SELECTOR,
                    "input[placeholder*='Categorie'], input[placeholder*='categorie']")
            except:
                cat_field = self.driver.find_element(By.CSS_SELECTOR, "input[name='keywords']")

            cat_field.clear()
            cat_field.send_keys(cat)
            time.sleep(0.3)
            cat_field.send_keys(Keys.ENTER)
            time.sleep(1)
            self.logger.info(f"   ✅ Categorie: {cat}")

            self.step = 3
            self.logger.step(self.step, "Titel invullen")
            title = product['titel'][:max_len].strip()
            title = re.sub(r'[^\x00-\x7F]+', '', title)

            title_field = self.wait.until(
                EC.presence_of_element_located((By.NAME, "keywords"))
            )
            title_field.clear()
            title_field.send_keys(title)
            time.sleep(0.3)
            title_field.send_keys(Keys.ENTER)
            time.sleep(1)

            row = product["row"]
            gewenste_cat = (row[COL["marktplaats_categorie"]] if len(row) > COL["marktplaats_categorie"] else "").strip()
            if gewenste_cat:
                try:
                    if self._zet_keuze("radio", gewenste_cat, True):
                        self.logger.info(f"   ✅ Marktplaats-categorie gekozen: {gewenste_cat}")
                    else:
                        self.logger.warning(f"   ⚠️ Categorie '{gewenste_cat}' niet in de suggesties, eerste suggestie blijft staan")
                except Exception as e:
                    self.logger.warning(f"   ⚠️ Categorie kiezen mislukt ({e}), eerste suggestie blijft staan")
            vraag = getattr(self, "on_controleer_categorie", None)
            if vraag:
                self.logger.info("   ⏸️ Wacht op bevestiging van de categorie...")
                if not vraag(product.get("titel", "")):
                    self.logger.info("   ⏹️ Gestopt bij categoriecontrole")
                    self.running = False
                    return False
            self._klik_verder()
            time.sleep(2)
            self.logger.info(f"   ✅ Titel: {title}")

            self.step = 4
            self.logger.step(self.step, "Foto's uploaden")
            images = self._zoek_fotos(product['artikelnummer'])

            if images:
                file_input = self.driver.find_element(By.CSS_SELECTOR, "input[type='file']")
                file_input.send_keys("\n".join(images[:10]))
                time.sleep(5)
                self.logger.info(f"   ✅ {len(images[:10])} foto's geüpload")
            else:
                self.logger.info("   ⚠️ Geen foto's gevonden")

            self.step = 5
            self.logger.step(self.step, "Omschrijving invullen")
            description = build_description(product)

            if description:
                try:
                    self._vul_omschrijving(description)
                except Exception as e:
                    self.logger.warning(f"   ⚠️ Omschrijving invullen mislukt: {e}")
            else:
                self.logger.info("   ⚠️ Geen omschrijving-data gevonden, overgeslagen")

            if self.config.get('preferences.auto_verzending', True):
                try:
                    self._stel_verzending_in(product)
                except Exception as e:
                    self.logger.warning(f"   ⚠️ Verzending automatisch instellen mislukt: {e}")

            self.step = 6
            self.logger.step(self.step, "Wacht op gebruiker")
            self.logger.info("")
            self.logger.info("📝 ADVERTENTIE IS BIJNA KLAAR!")
            self.logger.info("📝 Maak de advertentie handmatig af:")
            self.logger.info("   1. Controleer de beschrijving")
            self.logger.info("   2. Controleer verzending, prijs en eventuele extra velden")
            for regel in product.get("verzend_tekst", "").split("\n"):
                if regel:
                    self.logger.info(f"      📦 {regel}")
            self.logger.info("   3. Klik op 'Plaats advertentie'")
            self.logger.info("")
            self.logger.info("⏸️ Klik op 'Volgende' als de advertentie geplaatst is, of 'Overslaan' om dit product bewust over te slaan")

            self.was_skipped = False
            self.wait_for_user = True
            if self.on_wait_for_user:
                self.on_wait_for_user()
            while self.wait_for_user and self.running:
                time.sleep(0.5)

            self.wait_for_user = False
            if self.was_skipped:
                self.logger.warning(f"⏭️ Product {product['artikelnummer']} bewust overgeslagen")
            else:
                self.logger.success(f"✅ Product {product['artikelnummer']} voltooid!")
                try:
                    huidige_url = ""
                    try:
                        huidige_url = self.driver.current_url
                    except Exception:
                        pass
                    self._mark_product_online(product['artikelnummer'], huidige_url)
                    if huidige_url:
                        self.logger.info(f"   📤 Gemarkeerd als 'online', URL opgeslagen: {huidige_url}")
                    else:
                        self.logger.info("   📤 Gemarkeerd als 'online' in de opslag")
                except Exception as e:
                    self.logger.warning(f"   ⚠️ Kon niet als 'online' markeren in de opslag: {e}")
            return True

        except Exception as e:
            self.logger.error(f"Fout bij product {product['artikelnummer']}: {e}")
            return False

    def _mark_product_online(self, artikelnummer, advertentie_url=None, kolom="online"):
        """Zet 'online' op ja voor dit product in de XML, zodat een
        volgende uploadsessie dit product overslaat en
        marktplaats_productmanager.py het meteen als online toont. Slaat
        ook de huidige browser-URL op (in het eerste lege url_1..url_5-
        veld), indien gegeven."""
        import xml.etree.ElementTree as ET
        xml_path = get_xml_path()
        if not xml_path or not os.path.exists(xml_path):
            raise FileNotFoundError(f"XML-bestand niet gevonden: {xml_path}")
        tree = ET.parse(xml_path)
        root = tree.getroot()
        gevonden = False
        for prod_el in root.findall("product"):
            nr_el = prod_el.find("artikelnummer")
            if nr_el is not None and (nr_el.text or "").strip() == artikelnummer:
                online_el = prod_el.find(kolom)
                if online_el is None:
                    online_el = ET.SubElement(prod_el, kolom)
                online_el.text = "ja"
                if advertentie_url:
                    # Zet de URL in het eerste lege url_1..url_5-veld (een
                    # product kan op meerdere pagina's tegelijk staan).
                    for slot in ("url_1", "url_2", "url_3", "url_4", "url_5"):
                        slot_el = prod_el.find(slot)
                        bestaande_waarde = (slot_el.text or "").strip() if slot_el is not None else ""
                        if not bestaande_waarde:
                            if slot_el is None:
                                slot_el = ET.SubElement(prod_el, slot)
                            slot_el.text = advertentie_url
                            break
                gevonden = True
                break
        if not gevonden:
            raise ValueError("Artikelnummer niet gevonden in XML")
        tree.write(xml_path, encoding="utf-8", xml_declaration=True)

    def go_to_next(self):
        self.wait_for_user = False

    def skip_current(self):
        self.was_skipped = True
        try:
            self.logger.info("⏭️ Overslaan - pagina verlaten...")
            self.driver.get(getattr(self, "start_url", "https://www.marktplaats.nl/plaats"))
        except Exception as e:
            self.logger.warning(f"Kon niet terugkeren naar plaats-pagina: {e}")
        self.wait_for_user = False

    def stop(self):
        self.running = False

    def close(self):
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
            self.driver = None

# ============================================
# GTK GUI
# ============================================

class App:
    def __init__(self):
        # GTK zet automatisch de juiste WM_CLASS!
        self.window = TabBasis(title="Automater")
        self.window.set_title("Marktplaats Automatisering")
        self.window.set_default_size(1000, 750)
        self.window.set_position(Gtk.WindowPosition.CENTER)
        self.window.set_border_width(10)

        # Zet het icoon (als beschikbaar)
        try:
            icon_path = asset("logo.png")
            if os.path.exists(icon_path):
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(icon_path, 64, 64)
                self.window.set_icon(pixbuf)
        except:
            pass

        # Configuratie
        self.config = ConfigManager()
        self.logger = Logger()
        self.auto = MarktplaatsAuto(self.config, self.logger)
        self.auto.on_wait_for_user = self._on_wait_for_user
        try:
            from marktplaats_suite import bridge
            bridge.start(self.config)
        except Exception:
            pass
        self.auto.on_vraag_logo = self._vraag_logo
        self.auto.on_controleer_categorie = self._controleer_categorie
        self.auto.on_verzendadvies = lambda t: GLib.idle_add(
            lambda: (self.upload_venster and self.upload_venster.zet_verzendadvies(t), False)[1])
        self.upload_venster = None
        self.na_upload = None       # bijv. Product Management verversen
        self.running = False

        self._setup_ui()
        self._load_config_to_gui()

        self.logger.info("🚀 Klaar om te starten!")


    def _setup_ui(self):
        """Eén overzicht: starten, instellingen en log. De voortgang komt in een klein apart venster."""
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        vbox.set_border_width(10)
        self.window.add(vbox)

        # --- starten ---
        actie = Gtk.Box(spacing=8)
        vbox.pack_start(actie, False, False, 0)
        self.start_btn = Gtk.Button(label="🚀 Upload alle offline producten naar Marktplaats")
        self.start_btn.get_style_context().add_class("suggested-action")
        self.start_btn.connect("clicked", lambda *_: self.start_upload(None, self.window.top()))
        actie.pack_start(self.start_btn, False, False, 0)
        self.script_btn = Gtk.Button(label="🧩 Userscripts (Whoppah en Vinted)")
        self.script_btn.set_tooltip_text("Vul Whoppah en Vinted in je eigen, ingelogde Firefox in met userscripts.")
        self.script_btn.connect("clicked", self._toon_userscript)
        actie.pack_start(self.script_btn, False, False, 0)
        self.status_label = Gtk.Label()
        self.status_label.set_markup("<span foreground='green'>✅ Klaar</span>")
        actie.pack_end(self.status_label, False, False, 0)

        hint = Gtk.Label()
        hint.set_markup("<small><i>De voortgang (inloggen, volgende, overslaan, stop) verschijnt in een klein apart venster. "
                        "Alleen bepaalde producten? Selecteer ze in 📊 Product Management en kies 🚀 Upload naar Marktplaats. "
                        "Whoppah en Vinted vul je in je eigen Firefox in met de userscripts.</i></small>")
        hint.set_xalign(0)
        hint.set_line_wrap(True)
        vbox.pack_start(hint, False, False, 0)

        # --- instellingen ---
        frame = Gtk.Frame(label=" Instellingen ")
        vbox.pack_start(frame, False, False, 0)
        grid = Gtk.Grid(column_spacing=10, row_spacing=6)
        grid.set_border_width(10)
        frame.add(grid)

        def lbl(tekst):
            l = Gtk.Label(label=tekst)
            l.set_halign(Gtk.Align.END)
            return l

        grid.attach(lbl("Browser:"), 0, 0, 1, 1)
        self.browser_combo = Gtk.ComboBoxText()
        for sleutel, tekst in (("auto", "Automatisch (Firefox als die er is, anders Chrome)"),
                               ("firefox", "Firefox (eigen profiel; je logt één keer in)"),
                               ("chrome", "Chrome / Chromium")):
            self.browser_combo.append(sleutel, tekst)
        self.browser_combo.set_active_id("auto")
        grid.attach(self.browser_combo, 1, 0, 3, 1)

        grid.attach(lbl("Chrome-profiel:"), 0, 1, 1, 1)
        self.profile_path_entry = Gtk.Entry()
        self.profile_path_entry.set_hexpand(True)
        self.profile_path_entry.set_tooltip_text("Alleen voor Chrome")
        grid.attach(self.profile_path_entry, 1, 1, 1, 1)
        grid.attach(lbl("naam:"), 2, 1, 1, 1)
        self.profile_name_entry = Gtk.Entry()
        self.profile_name_entry.set_width_chars(12)
        self.profile_name_entry.set_tooltip_text("Alleen voor Chrome")
        grid.attach(self.profile_name_entry, 3, 1, 1, 1)

        grid.attach(lbl("Extra fotomap:"), 0, 2, 1, 1)
        path_box = Gtk.Box(spacing=5)
        self.image_path_entry = Gtk.Entry()
        self.image_path_entry.set_hexpand(True)
        self.image_path_entry.set_tooltip_text("Foto's worden eerst in de productmappen gezocht, daarna hier")
        path_box.pack_start(self.image_path_entry, True, True, 0)
        browse_path_btn = Gtk.Button(label="Bladeren")
        browse_path_btn.connect("clicked", self._browse_path)
        path_box.pack_start(browse_path_btn, False, False, 0)
        grid.attach(path_box, 1, 2, 3, 1)

        grid.attach(lbl("XML-bestand:"), 0, 3, 1, 1)
        self.xml_path_entry = Gtk.Entry()  # alleen-lezen weergave van het centrale pad
        self.xml_path_entry.set_editable(False)
        self.xml_path_entry.set_can_focus(False)
        self.xml_path_entry.set_tooltip_text("Stel je in via ⚙️ Instellingen rechtsboven in het hoofdvenster")
        grid.attach(self.xml_path_entry, 1, 3, 3, 1)

        grid.attach(lbl("Max. titellengte:"), 0, 4, 1, 1)
        self.max_title_entry = Gtk.Entry()
        self.max_title_entry.set_width_chars(6)
        self.max_title_entry.set_halign(Gtk.Align.START)
        grid.attach(self.max_title_entry, 1, 4, 1, 1)
        grid.attach(lbl("Wacht tussen producten (sec):"), 2, 4, 1, 1)
        self.wait_products_entry = Gtk.Entry()
        self.wait_products_entry.set_width_chars(6)
        grid.attach(self.wait_products_entry, 3, 4, 1, 1)

        self.auto_verzending_check = Gtk.CheckButton(
            label="Verzending automatisch instellen (vervoerders en pakketgrootte op basis van afmetingen en gewicht)")
        grid.attach(self.auto_verzending_check, 0, 5, 4, 1)

        vv_hint = Gtk.Label(xalign=0)
        vv_hint.set_markup("<small><i>Welke vervoerders je wilt gebruiken (Budbee, DHL, PostNL, Brenger) kies je bij "
                           "📝 Nieuw Product, onder het verzendadvies.</i></small>")
        grid.attach(vv_hint, 1, 6, 3, 1)

        save_btn = Gtk.Button(label="💾 Opslaan")
        save_btn.set_halign(Gtk.Align.END)
        save_btn.connect("clicked", self._save_config)
        grid.attach(save_btn, 3, 7, 1, 1)

        # --- log (ingeklapt) ---
        log_exp = Gtk.Expander(label="📝 Log van de laatste upload")
        vbox.pack_start(log_exp, True, True, 0)
        log_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        log_exp.add(log_box)
        clear_btn = Gtk.Button(label="🗑️ Wis log")
        clear_btn.set_halign(Gtk.Align.START)
        clear_btn.connect("clicked", self._clear_log)
        log_box.pack_start(clear_btn, False, False, 0)
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_min_content_height(220)
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        log_box.pack_start(scrolled, True, True, 0)
        self.log_text_view = Gtk.TextView()
        self.log_text_view.set_editable(False)
        self.log_text_view.set_wrap_mode(Gtk.WrapMode.WORD)
        self.log_text_view.modify_font(Pango.FontDescription("Monospace 9"))
        scrolled.add(self.log_text_view)

        self.logger = Logger(self.log_text_view)
        self.auto.logger = self.logger

    def _browse_path(self, widget):
        dialog = Gtk.FileChooserDialog(
            title="Selecteer afbeeldingen map",
            parent=self.window.top(),
            action=Gtk.FileChooserAction.SELECT_FOLDER
        )
        dialog.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OPEN, Gtk.ResponseType.OK
        )

        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            self.image_path_entry.set_text(dialog.get_filename())
        dialog.destroy()

    def _load_config_to_gui(self):
        storage = self.config.get('storage', {})
        self.xml_path_entry.set_text(get_xml_path())

        self.browser_combo.set_active_id(self.config.get('browser', 'auto') or 'auto')
        chrome = self.config.get('chrome', {})
        self.profile_path_entry.set_text(chrome.get('user_data_dir', ""))
        self.profile_name_entry.set_text(chrome.get('profile', "Default"))

        paths = self.config.get('paths', {})
        self.image_path_entry.set_text(paths.get('base_image_path', afbeeldingen_map()))

        prefs = self.config.get('preferences', {})
        self.max_title_entry.set_text(str(prefs.get('max_title_length', 60)))
        self.wait_products_entry.set_text(str(prefs.get('wait_between_products', 3)))
        self.auto_verzending_check.set_active(bool(prefs.get('auto_verzending', True)))

    def _save_config(self, widget, stil=False):
        self.config.set('browser', self.browser_combo.get_active_id() or 'auto')
        self.config.set('chrome.user_data_dir', self.profile_path_entry.get_text().strip())
        self.config.set('chrome.profile', self.profile_name_entry.get_text().strip())
        self.config.set('paths.base_image_path', self.image_path_entry.get_text().strip())
        self.config.set('preferences.max_title_length', int(self.max_title_entry.get_text().strip() or 60))
        self.config.set('preferences.wait_between_products', int(self.wait_products_entry.get_text().strip() or 3))
        self.config.set('preferences.auto_verzending', self.auto_verzending_check.get_active())

        if stil:
            return
        self.logger.success("Instellingen opgeslagen")
        if not self.running:
            self.status_label.set_markup("<span foreground='green'>✅ Instellingen opgeslagen</span>")

    def _toon_userscript(self, widget):
        from marktplaats_suite import bridge
        draait = bridge.start(self.config)
        url = f"http://127.0.0.1:{bridge.POORT}/whoppah.user.js"
        d = Gtk.MessageDialog(transient_for=self.window, flags=0, message_type=Gtk.MessageType.INFO,
                              buttons=Gtk.ButtonsType.CLOSE, text="Userscripts voor Whoppah en Vinted")
        d.format_secondary_text(
            ("De Suite levert nu producten aan de scripts (alleen op deze computer).\n\n" if draait else
             "Let op: poort %d is al in gebruik; draait er al een Suite?\n\n" % bridge.POORT) +
            "Eenmalig installeren (Violentmonkey of Tampermonkey in Firefox):\n"
            "1. Open de link(s) hieronder in Firefox en bevestig de installatie.\n"
            "2. Ga naar Whoppah of Vinted (ingelogd) en begin met een nieuwe advertentie; voeg de foto's zelf toe.\n"
            "3. Rechtsonder staat het paneel: kies je product, de rest vult het script in.\n\n"
            "Whoppah: " + url + "\nVinted:  " + url.replace("whoppah", "vinted"))
        d.add_button("Kopieer Whoppah-link", 10)
        d.add_button("Kopieer Vinted-link", 12)
        d.add_button("Kopieer producten (JSON)", 11)
        r = d.run()
        cb = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        if r == 10:
            cb.set_text(url, -1)
        elif r == 12:
            cb.set_text(url.replace("whoppah", "vinted"), -1)
        elif r == 11:
            cb.set_text(bridge.json_voor_klembord(self.config), -1)
        d.destroy()

    def start_upload(self, artikelnummers=None, parent=None):
        """Start het plaatsen op Marktplaats: alleen deze artikelnummers, of None = alle offline producten.
        De voortgang verschijnt in een klein los venster (UploadVenster)."""
        if self.running:
            if self.upload_venster:
                self.upload_venster.present()
            return
        self.auto.filter_nummers = set(artikelnummers) if artikelnummers else None
        self._save_config(None, stil=True)
        self.upload_venster = UploadVenster(self, parent or self.window.top(),
                                            len(artikelnummers) if artikelnummers else None)
        self.running = True
        self.auto._logo_keuze = None
        self.auto.running = True
        self.auto.user_logged_in = False
        self.start_btn.set_sensitive(False)
        self.status_label.set_markup("<span foreground='blue'>🔄 Bezig met uploaden (zie het aparte venster)</span>")
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        try:
            if not self.auto.start_browser():
                GLib.idle_add(self._on_error, "Browser starten mislukt: " + getattr(self.auto, "last_error", "zie Log"))
                return

            GLib.idle_add(self._update_status, "🔑 Wacht op inloggen...")

            if not self.auto.wait_for_manual_login():
                GLib.idle_add(self._on_error, "Inloggen geannuleerd")
                return

            if not self.auto.load_products():
                GLib.idle_add(self._on_error, "Geen producten gevonden")
                return

            GLib.idle_add(self._update_status, "🔄 Bezig met verwerken...")
            self.auto.process_products()
            GLib.idle_add(self._on_finished)

        except Exception as e:
            GLib.idle_add(self._on_error, str(e))

    def _logged_in(self, widget):
        self.auto.user_logged_in = True
        if self.upload_venster:
            self.upload_venster.zet_knoppen(ingelogd=False)
        self.logger.info("✅ Ingelogd bevestigd!")

    def _next(self, widget):
        if self.upload_venster:
            self.upload_venster.zet_knoppen(volgende=False)
        self.logger.info("⏭️ Door naar volgende...")
        self.auto.go_to_next()

    def _skip(self, widget):
        if self.upload_venster:
            self.upload_venster.zet_knoppen(volgende=False)
        self.logger.info("⏩ Overslaan...")
        threading.Thread(target=self.auto.skip_current, daemon=True).start()

    def _vraag_logo(self, artikel):
        """Wordt vanuit de werkthread aangeroepen; toont een popup en wacht op het antwoord."""
        resultaat = {}
        klaar = threading.Event()

        def toon():
            d = Gtk.MessageDialog(parent=(self.upload_venster or self.window.top()), flags=0, message_type=Gtk.MessageType.QUESTION,
                                  buttons=Gtk.ButtonsType.NONE,
                                  text=f"Foto's voor {artikel}: met of zonder logo/watermerk?")
            d.format_secondary_text("Er zijn twee sets foto's gemaakt. Welke wil je op Marktplaats uploaden?")
            d.add_button("Met logo/watermerk", Gtk.ResponseType.YES)
            d.add_button("Zonder logo/watermerk", Gtk.ResponseType.NO)
            d.add_button("Stoppen", Gtk.ResponseType.CANCEL)
            onthoud = Gtk.CheckButton(label="Onthoud deze keuze voor de volgende producten in deze run")
            d.get_content_area().pack_start(onthoud, False, False, 6)
            d.show_all()
            r = d.run()
            resultaat['v'] = ("met" if r == Gtk.ResponseType.YES else
                              "zonder" if r == Gtk.ResponseType.NO else "stop",
                              onthoud.get_active())
            d.destroy()
            klaar.set()
            return False

        GLib.idle_add(toon)
        klaar.wait()
        return resultaat['v']

    def _controleer_categorie(self, titel):
        """Pauze vanuit de werkthread: gebruiker kan de categorie in de browser nog wijzigen."""
        resultaat = {}
        klaar = threading.Event()

        def toon():
            d = Gtk.MessageDialog(parent=(self.upload_venster or self.window.top()), flags=0, message_type=Gtk.MessageType.QUESTION,
                                  buttons=Gtk.ButtonsType.NONE,
                                  text=f"Juiste categorie voor '{titel}'?")
            d.format_secondary_text("Controleer de gekozen categorie in de browser en wijzig die "
                                    "indien nodig. Klik daarna op 'Ja, verder'.")
            d.add_button("Ja, verder", Gtk.ResponseType.YES)
            d.add_button("Stoppen", Gtk.ResponseType.CANCEL)
            d.set_keep_above(True)
            d.show_all()
            resultaat['v'] = d.run() == Gtk.ResponseType.YES
            d.destroy()
            klaar.set()
            return False

        GLib.idle_add(toon)
        klaar.wait()
        return resultaat['v']

    def _on_wait_for_user(self):
        GLib.idle_add(self._enable_next)

    def _stop(self, widget):
        self.running = False
        self.auto.running = False
        self.auto.stop()
        self.start_btn.set_sensitive(True)
        self.status_label.set_markup("<span foreground='red'>⏹️ Gestopt</span>")
        self.logger.info("⏹️ Gestopt door gebruiker")
        if self.upload_venster:
            self.upload_venster.klaar("⏹️ Gestopt")

    def _enable_next(self):
        if self.upload_venster:
            self.upload_venster.zet_knoppen(volgende=True)

    def _update_status(self, msg):
        self.status_label.set_markup(f"<span foreground='blue'>{GLib.markup_escape_text(msg)}</span>")
        if self.upload_venster:
            self.upload_venster.zet_status(msg)

    def _on_error(self, msg):
        self.logger.error(f"❌ {msg}")
        self.status_label.set_markup(f"<span foreground='red'>❌ Fout: {GLib.markup_escape_text(msg)}</span>")
        self.start_btn.set_sensitive(True)
        self.running = False
        if self.upload_venster:
            self.upload_venster.klaar(f"❌ {msg}")

    def _on_finished(self):
        self.logger.success("🎉 Alle producten verwerkt!")
        self.status_label.set_markup("<span foreground='green'>✅ Klaar!</span>")
        if self.upload_venster:
            self.upload_venster.klaar("✅ Klaar!")
        if self.na_upload:
            try:
                self.na_upload()
            except Exception:
                pass
        self.start_btn.set_sensitive(True)
        self.running = False

    def _clear_log(self, widget):
        buffer = self.log_text_view.get_buffer()
        buffer.set_text("")
        self.logger.info("🗑️ Log gewist")

    def kan_sluiten(self):
        """True als afsluiten mag; vraagt bevestiging als de automatisering draait."""
        if self.running:
            dialog = Gtk.MessageDialog(
                parent=self.window.top(),
                flags=Gtk.DialogFlags.MODAL,
                message_type=Gtk.MessageType.QUESTION,
                buttons=Gtk.ButtonsType.YES_NO,
                text="Automatisering draait nog. Echt afsluiten?"
            )
            response = dialog.run()
            dialog.destroy()
            if response == Gtk.ResponseType.NO:
                return False
        return True

    def sluit(self):
        try:
            self.auto.close()
        except Exception:
            pass


class UploadVenster(Gtk.Window):
    """Klein los venster met de voortgang van het plaatsen op Marktplaats."""

    def __init__(self, app, parent, aantal):
        super().__init__(title="Uploaden naar Marktplaats")
        self.app = app
        if parent is not None:
            self.set_transient_for(parent)
        self.set_default_size(460, -1)
        self.set_keep_above(True)
        self.set_position(Gtk.WindowPosition.CENTER_ON_PARENT if parent else Gtk.WindowPosition.CENTER)
        self.connect("delete-event", self._sluiten_gevraagd)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_border_width(12)
        self.add(box)
        wat = Gtk.Label()
        wat.set_xalign(0)
        wat.set_markup("<small>" + (f"{aantal} geselecteerd{'e' if aantal != 1 else ''} product{'en' if aantal != 1 else ''}"
                                    if aantal else "Alle offline producten") + "</small>")
        box.pack_start(wat, False, False, 0)
        self.status = Gtk.Label()
        self.status.set_xalign(0)
        self.status.set_markup("<b>🔄 Browser starten...</b>")
        box.pack_start(self.status, False, False, 0)
        self.balk = Gtk.ProgressBar()
        self.balk.set_show_text(True)
        self.balk.set_text(f"0 van {aantal}" if aantal else "")
        box.pack_start(self.balk, False, False, 0)
        self.verzend = Gtk.Label()
        self.verzend.set_xalign(0)
        self.verzend.set_line_wrap(True)
        self.verzend.set_max_width_chars(60)
        self.verzend.set_no_show_all(True)
        box.pack_start(self.verzend, False, False, 0)
        self.regel = Gtk.Label(label="Log in op Marktplaats in het browservenster en klik daarna op 'Ingelogd'.")
        self.regel.set_xalign(0)
        self.regel.set_line_wrap(True)
        self.regel.set_max_width_chars(60)
        box.pack_start(self.regel, False, False, 0)
        knoppen = Gtk.Box(spacing=6, homogeneous=True)
        self.k_login = Gtk.Button(label="🔑 Ingelogd")
        self.k_login.connect("clicked", app._logged_in)
        self.k_volgende = Gtk.Button(label="⏭️ Volgende")
        self.k_volgende.connect("clicked", app._next)
        self.k_over = Gtk.Button(label="⏩ Overslaan")
        self.k_over.connect("clicked", app._skip)
        self.k_stop = Gtk.Button(label="⏹️ Stop")
        self.k_stop.connect("clicked", app._stop)
        for k in (self.k_login, self.k_volgende, self.k_over, self.k_stop):
            knoppen.pack_start(k, True, True, 0)
        box.pack_start(knoppen, False, False, 0)
        self.k_volgende.set_sensitive(False)
        self.k_over.set_sensitive(False)
        self.k_sluit = Gtk.Button(label="Sluiten")
        self.k_sluit.connect("clicked", lambda *_: self._weg())
        self.k_sluit.set_no_show_all(True)
        box.pack_start(self.k_sluit, False, False, 0)

        log_exp = Gtk.Expander(label="Log")
        log_sw = Gtk.ScrolledWindow()
        log_sw.set_min_content_height(180)
        log_sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.log_view = Gtk.TextView()
        self.log_view.set_editable(False)
        self.log_view.set_wrap_mode(Gtk.WrapMode.WORD)
        self.log_view.modify_font(Pango.FontDescription("Monospace 8"))
        log_sw.add(self.log_view)
        log_exp.add(log_sw)
        box.pack_start(log_exp, True, True, 0)
        Logger.luisteraars.append(self._log)
        self.show_all()

    def _log(self, niveau, msg):
        GLib.idle_add(self._log_ui, niveau, msg)

    def _log_ui(self, niveau, msg):
        tekst = msg.strip()
        if not tekst or set(tekst) <= {"="}:
            return False
        m = re.search(r"Product (\d+)/(\d+)", tekst)
        if m:
            i, n = int(m.group(1)), int(m.group(2))
            self.balk.set_fraction((i - 1) / max(1, n))
            self.balk.set_text(f"{i} van {n}")
            self.status.set_markup(f"<b>📦 Product {i} van {n}</b>")
        if "producten geladen" in tekst:
            self.status.set_markup(f"<b>{GLib.markup_escape_text(tekst)}</b>")
        kleur = {"❌": "red", "⚠️": "#b9770e", "SUCCESS": "green"}.get(niveau)
        t = GLib.markup_escape_text(tekst[:200])
        self.regel.set_markup(f"<span foreground='{kleur}'>{t}</span>" if kleur else t)
        buf = self.log_view.get_buffer()
        buf.insert(buf.get_end_iter(), time.strftime("%H:%M:%S ") + tekst + "\n")
        self.log_view.scroll_to_mark(buf.get_insert(), 0.0, False, 0.0, 1.0)
        return False

    def zet_status(self, msg):
        self.status.set_markup(f"<b>{GLib.markup_escape_text(msg)}</b>")

    def zet_verzendadvies(self, tekst):
        regels = [GLib.markup_escape_text(r) for r in tekst.split("\n") if r]
        self.verzend.set_markup("\n".join("📦 " + r for r in regels))
        self.verzend.show()

    def zet_knoppen(self, ingelogd=None, volgende=None):
        if ingelogd is not None:
            self.k_login.set_sensitive(ingelogd)
        if volgende is not None:
            self.k_volgende.set_sensitive(volgende)
            self.k_over.set_sensitive(volgende)
            if volgende:
                self.status.set_markup("<b>👀 Controleer de advertentie en klik op Volgende</b>")

    def klaar(self, tekst):
        self.status.set_markup(f"<b>{GLib.markup_escape_text(tekst)}</b>")
        if tekst.startswith("✅"):
            self.balk.set_fraction(1.0)
        for k in (self.k_login, self.k_volgende, self.k_over, self.k_stop):
            k.set_sensitive(False)
        self.k_sluit.show()

    def _sluiten_gevraagd(self, *_):
        if self.app.running:
            d = Gtk.MessageDialog(transient_for=self, flags=0, message_type=Gtk.MessageType.QUESTION,
                                  buttons=Gtk.ButtonsType.YES_NO, text="Uploaden stoppen?")
            d.format_secondary_text("Het product dat nu in de browser openstaat wordt niet afgemaakt.")
            stoppen = d.run() == Gtk.ResponseType.YES
            d.destroy()
            if not stoppen:
                return True
            self.app._stop(None)
        self._weg()
        return True

    def _weg(self):
        if self._log in Logger.luisteraars:
            Logger.luisteraars.remove(self._log)
        if self.app.upload_venster is self:
            self.app.upload_venster = None
        self.destroy()


# ============================================
# MAIN
# ============================================

def main():
    run_standalone(lambda: App().window, "Marktplaats Automatisering", 1000, 750)


if __name__ == "__main__":
    main()
