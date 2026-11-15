# SellYourShit

<p align="center"><img src="marktplaats_suite/assets/icon.png" width="160" alt="SellYourShit logo"></p>

**SellYourShit** is één app met alle Marktplaats-tools van HerNieuw, voor **Debian en Ubuntu** (en afgeleiden)
en **Windows 10/11** (installatieprogramma, zie [Installeren op Windows](#installeren-op-windows)):

Alles in **één venster** met tabs:

| Tab | Was | Doel |
|---|---|---|
| 📝 Nieuw Product | MarktplaatsProductmanager + FotoManager | Foto's, AI-omschrijving, fotoversies en artikel aanmaken in één tab |
| 📊 Product Management / 📈 Sales Dashboard | MarktplaatsProductmanager | Overzicht, detailvenster (dubbelklik), uploaden, verkocht/retour/gereserveerd, statistieken |
| 🔍 Product Scanner | MarktplaatsScanner | USB-barcodescanner met productinfo en foto |
| 🤖 Product Uploader | MarktplaatsAutomater | Advertenties automatisch plaatsen, nu alleen voor Marktplaats (Selenium + Chrome/Chromium) |

Start met `sellyourshit` (of `marktplaats-suite`) of via het applicatiemenu.

**Centrale instellingen** (⚙️ rechtsboven): het XML-bestand wordt maar op één plek ingesteld en geldt voor alle tabs.
Algemene voorwaarden bewerk je in een eigen tekstvak met vet/schuin (knoppen of Ctrl+B / Ctrl+I), met import
uit .docx/.txt, een voorbeeld zoals het op Marktplaats verschijnt, en een vinkje om voorwaarden wel of niet
onder advertenties te plaatsen.

## Installeren (Debian en Ubuntu)

```bash
git clone https://github.com/AbelDrift/SellYourShit.git
cd SellYourShit
./install.sh                 # basis
./install.sh --met-chrome    # + Google Chrome (amd64) voor de Automater
./install.sh --met-ai        # + AI-achtergrondverwijdering (groot: torch)
```

Wat het doet: apt-pakketten (`python3-gi`, `gir1.2-gtk-3.0`, `imagemagick`, …), een eigen
virtuele omgeving in `~/.local/share/marktplaats-suite/venv` (met `--system-site-packages`,
dus geen conflict met PEP 668), starters in `~/.local/bin` en het applicatiemenu.
Verwijderen: `./uninstall.sh` (`--alles` wist ook je gegevens).

## Installeren op Windows

1. Download **`SellYourShit-<versie>-setup.exe`** bij de nieuwste
   [release](https://github.com/AbelDrift/SellYourShit/releases/latest) (ongeveer 600 MB).
2. Dubbelklik erop. Je hebt geen beheerdersrechten nodig: de app komt in
   `%LOCALAPPDATA%\Programs\SellYourShit`, met een snelkoppeling in het Startmenu (en desgewenst op het bureaublad).
   Zegt Windows *"Windows heeft uw pc beschermd"*? Het installatieprogramma is niet digitaal ondertekend:
   klik op **Meer informatie** en dan **Toch uitvoeren**.
3. Klaar. Alles zit erin: Python, GTK, het weghalen van de achtergrond (transparent-background op de processor,
   het model wordt meegeleverd) en printen via elke Windows-printer.

- **Bijwerken:** download de nieuwe setup.exe en voer hem uit; je producten en instellingen blijven staan.
- **Verwijderen:** Windows-instellingen → Apps → SellYourShit. Je gegevens blijven staan.
- **Product Uploader:** installeer Firefox of Google Chrome. **GIMP** is optioneel (voor *Open in GIMP*).
- **Printen:** kies bij ⚙️ Instellingen → Printer de methode *Windows-printer* en je printer. Een etiketprinter
  (Brother QL, DYMO) gebruik je met de Windows-driver; het etiketformaat stel je in bij de printerinstellingen van
  Windows. De barcode komt op ware grootte (op A4 linksboven) en wordt op een klein etiket passend gemaakt.
- **Gegevens:** `%APPDATA%\SellYourShit` (instellingen, producten.xml); productmappen standaard in
  `%USERPROFILE%\HERNIEUW\Marktplaats`.
- **Start de app niet?** De foutmelding staat in `%LOCALAPPDATA%\SellYourShit\sellyourshit.log`.

Het installatieprogramma wordt automatisch gebouwd en getest op een Windows-machine van GitHub
(`.github/workflows/windows.yml`, zie de map `windows/`), bij elke nieuwe versie.

## Gegevens

Alles (producten.xml, `suite_config.json` met XML-pad en voorwaarden, instellingen, input/output van de fotomanager, thumbnail-cache) staat in
`~/.local/share/marktplaats-suite/` (Windows: `%APPDATA%\SellYourShit`), of in `$MARKTPLAATS_DATA_DIR`. Bestaande bestanden uit de
losse apps (`producten.xml`, `productmanager_config.json`, `scanner_config.json`) kopieer je
naar die map; de fotomanager-instellingen heten nu `fotomanager_config.json`
(was `~/.marktplaats_manager_config.json`).

## Verschillen met Ubuntu-only installers

- Geen `chromium-chromedriver` (Ubuntu-snap): Selenium haalt zelf de passende driver op; `chromium-driver` (Debian) wordt als reserve geprobeerd.
- Geen `apt-key` (verwijderd in recente Debian): Chrome via het officiële `.deb`.
- Geen `pip --user` / `--break-system-packages`: alles in een venv.

## Bekende beperkingen

- Linux: GTK3 onder X11/XWayland (starters zetten `GDK_BACKEND=x11`).
- Windows: achtergrond weghalen gaat alleen op de processor (geen videokaart); de eerste keer duurt het laden van het model even.
- De thumbnail-fallback in de scanner leest Marktplaats-pagina's uit en kan breken als de site verandert.
- Getest op syntax en installeerbaarheid; de GUI zelf moet op een echt Debian/Ubuntu-bureaublad worden uitgeprobeerd.

## Verzendadvies en slimme Automater

- In **Registreren** verschijnt onder afmetingen/gewicht een live **verzendadvies**: welke pakketklasse en
  vervoerder passen (inclusief 2 cm / 0,3 kg verpakkingsmarge) en wat het kost. Limieten en prijzen staan in
  `verzendtabel.json` in de datamap en zijn aanpasbaar.
- Het veld **Marktplaats-categorie** bepaalt welke suggestie de Automater kiest (anders de eerste). Je krijgt
  een waarschuwing als de gekozen categorie alleen Brenger toont terwijl het product in een pakket past.
- Bij **📝 Nieuw Product** kies je onder het verzendadvies je **voorkeur vervoerders** (Budbee, DHL, PostNL,
  Brenger). Dat wordt je standaard, ook voor het uploaden. Het advies gebruikt alleen je voorkeur
  (goedkoopste passende pakket, anders Brenger, anders alleen ophalen) en noemt tussen haakjes wat bij de
  andere vervoerders ook kan, met prijs. Bijvoorbeeld: *Klein pakket via DHL (afhaalpunt €3,99, thuis €6,29)
  (ook mogelijk, niet in je voorkeur: Budbee gemiddeld pakket afhaalpunt €3,49, PostNL afhaalpunt €5,39)*.
- Het advies wordt bij het registreren **bij het product bewaard**. Bij het uploaden staat het in de log en
  in het voortgangsvenster, bij de start van het product én nog eens bij "controleer de advertentie".
  Is je voorkeur sindsdien veranderd, dan zie je ook het advies van nu. Het staat ook in het productvenster.
- De **Uploader** vinkt de geadviseerde vervoerders aan, de andere uit, en kiest de pakketgrootte (uit te
  zetten in zijn instellingen). Lukt een vinkje niet via het vakje zelf, dan probeert hij het via het label.
  Controleer de advertentie altijd voor je op "Plaats advertentie" klikt.
- Alle onderdelen delen één kolomlijst voor `producten.xml`; de Scanner past bij "verkocht" alleen dat ene
  product aan en wist geen velden van andere onderdelen meer.


## Whoppah en Vinted (userscripts)

De Product Uploader plaatst op **Marktplaats** (foto's, omschrijving, verzending). Whoppah en Vinted weigeren een
door de Uploader bestuurde browser (veiligheidscontrole), daarom vul je die in je **eigen, ingelogde Firefox** in met
twee userscripts. Foto's voeg je zelf toe, het definitief plaatsen doe je ook zelf.

1. Installeer de Firefox-extensie Violentmonkey of Tampermonkey.
2. Start de Suite en klik in de Product Uploader op **🧩 Userscripts**. Open de links
   (`http://127.0.0.1:8765/whoppah.user.js` en `http://127.0.0.1:8765/vinted.user.js`) in Firefox en bevestig de installatie.
3. Open Whoppah ("Advertentie plaatsen") of `vinted.nl/items/new`, voeg de foto's toe en kies rechtsonder in het paneel je product.
   Lukt ophalen niet, gebruik dan "Kopieer producten (JSON)" in de Suite en plak dat in het paneel.

**Whoppah:** details controleren/overschrijven (merk, titel, stijl, kleur, materiaal, staat), maten, prijs (Marktplaatsprijs x 1,25,
ondergrens x 0,85, Smart Drop 5% elke twee weken) en verzending (Pakket tot 100x50x50 cm, anders Koerier).
Prijsregels aanpassen kan in `automater_config.json` onder `"whoppah"`.

**Vinted:** titel, beschrijving, categorie (uit "Vinted-categorie", anders de suggestie van Vinted), merk (anders "Geen merk"),
staat, kleur (max. 2), materiaal, prijs (= 'Min. waarde', anders 85% van de vraagprijs) en pakketformaat Klein/Middel/Groot.
Verkoop je namens een winkel of kringloop, gebruik dan een Vinted Pro-account.

De brug in de Suite luistert alleen op 127.0.0.1 en accepteert alleen verzoeken met een lokale hostnaam.

## Nieuw product: foto's, AI en fotoversies in één tab

1. **📷 Import foto's**: kies foto's of zip-bestanden; de kiezer begint altijd in je Downloads-map.
   Een zip toont de eerste foto en hoeveel foto's erin zitten; bij importeren worden alleen de foto's
   eruit gehaald. Mappen open je met dubbelklik (⬆ Omhoog gaat terug). De app werkt op kopieën; je
   bronbestanden en zips blijven staan.
2. **🤖 Import details van AI**: de AI bekijkt de foto's en vult titel (max. 60 tekens, altijd met het
   soort voorwerp erin, bijv. *bank*), omschrijving met een `Details:`-lijst (`* `-opsommingstekens),
   categorie, tijdsperiode, stijl, merk, kleur, staat en waarde in. De vraagprijs wordt het gemiddelde
   van de waardeschatting als je die nog niet had ingevuld.
3. **🖼️ Foto editor**: voorbewerking zoals in de oude Product Studio (verkleinen naar 50% en
   automatisch kleuren verbeteren; geldt ook als je de editor niet opent) en optioneel extra versies:
   transparant, witte achtergrond, eigen achtergrond (kleur of afbeelding), en die versies ook met
   logo/watermerk. Achtergrond verwijderen gebeurt met transparent-background in een apart proces,
   één foto tegelijk. Hier kun je ook roteren
   (inspecteren) of de foto's openen in GIMP. De keuzes onder de preview (original / transparant /
   white / custom bg) laten zien welke versie je bekijkt.
4. **💾 Product registreren**: artikelnummer, productmap, barcode en alle foto's komen in één keer
   op hun plek (`originelen/`, `zonder_logo/`, `met_logo/`, ...). Het artikelnummer komt als
   `* Artikelnummer:` onderaan de details in de advertentietekst.

**⚙️ AI settings**: kies zelf welke AI je gebruikt.
- **Google Gemini** (standaard): gratis API-sleutel aanmaken op https://aistudio.google.com/apikey.
- **OpenAI-compatibel**: Ollama lokaal (gratis, geen sleutel, geen internet; bijv. `ollama pull qwen2.5vl`),
  OpenRouter, Mistral, OpenAI, LM Studio.
- **Handmatig, zonder API**: de app zet de prompt op je klembord; plak die met je foto's in Copilot,
  ChatGPT, DeepSeek of de Gemini-site en plak het antwoord terug (ook via **📋 Plak AI-tekst**).

Voor transparant/wit/eigen achtergrond is achtergrondverwijdering nodig: installeer met
`./install.sh --met-ai` (transparent-background).

## Product Management

- **Dubbelklik** op een product opent het productvenster: de advertentietekst zoals hij geplaatst wordt,
  alle gegevens, links naar platforms, online/verkocht-status en alle fotoversies. Foto's sleep je zo
  naar een uploadveld in je browser; titel, nummer, prijs en omschrijving kopieer je met één klik.
- Met **✏️ Bewerken** pas je het product in datzelfde venster aan (ook via Acties → Bewerken): de
  omschrijving in Advertentie, de productgegevens in Gegevens, de links in Links en alle overige velden
  (online, verkoop, klant, reservering, registratie, eigen voorwaarden) in **Overig**. Opslaan met de knop
  of Ctrl+S; ongedaan maken werkt zoals altijd. Locatie wijzigen (nieuw artikelnummer) kan er ook.
- **🚀 Upload naar Marktplaats** (onderaan, of rechtermuisknop): upload de geselecteerde producten of
  alle offline producten. De voortgang verschijnt in een klein los venster met de knoppen
  Ingelogd / Volgende / Overslaan / Stop en een uitklapbare log; het hoofdvenster blijft vrij.
- Het tabblad **🤖 Product Uploader** is één overzicht: alle offline producten uploaden, de
  userscripts voor Whoppah/Vinted, de instellingen en de log van de laatste upload. Ook vanaf daar
  verschijnt de voortgang in het kleine aparte venster.

