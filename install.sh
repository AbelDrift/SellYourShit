#!/usr/bin/env bash
# SellYourShit - installatie voor Linux: Debian 12+, Ubuntu 22.04+ (ook 26.04 en 26.10) en afgeleiden
# zoals Linux Mint, Pop!_OS en Zorin; Fedora; Arch, Manjaro en EndeavourOS; openSUSE Tumbleweed.
# Gebruik:  ./install.sh [--met-ai] [--met-chrome]
#   --met-ai      ook AI-achtergrondverwijdering (AlphaMaker licht/medium/zwaar: IS-Net, InSPyReNet, BiRefNet; groot!)
#   --met-chrome  Google Chrome (of Chromium) installeren voor de Automater
set -euo pipefail

MET_AI=0; MET_CHROME=0
for a in "$@"; do
  case "$a" in
    --met-ai) MET_AI=1 ;;
    --met-chrome) MET_CHROME=1 ;;
    -h|--help) sed -n 2,7p "$0"; exit 0 ;;
    *) echo "Onbekende optie: $a" >&2; exit 1 ;;
  esac
done

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PREFIX="${XDG_DATA_HOME:-$HOME/.local/share}/marktplaats-suite"
VENV="$PREFIX/venv"

[ "$(id -u)" -ne 0 ] || { echo "Draai dit als gewone gebruiker, niet als root (sudo wordt zelf gebruikt)."; exit 1; }

# Pakketbeheerder: apt (Debian/Ubuntu/Mint), dnf (Fedora), pacman (Arch/Manjaro), zypper (openSUSE)
if command -v apt-get >/dev/null; then PM=apt
elif command -v dnf >/dev/null; then PM=dnf
elif command -v pacman >/dev/null; then PM=pacman
elif command -v zypper >/dev/null; then PM=zypper
else
  echo "Geen apt, dnf, pacman of zypper gevonden. Installeer zelf Python 3 met PyGObject en GTK 3"
  echo "(python3-gi / python-gobject en gtk3) en draai dit script daarna met SYS_KLAAR=1."
  [ "${SYS_KLAAR:-0}" = 1 ] || exit 1
  PM=geen
fi

if pgrep -f "python.* -m marktplaats_suite" >/dev/null 2>&1; then
  echo "!!  SellYourShit draait nog. Sluit de app; na de installatie start je hem opnieuw,"
  echo "    anders blijf je met de oude versie werken."
fi

. /etc/os-release 2>/dev/null || true
echo "==> Systeem: ${PRETTY_NAME:-onbekend} ($(uname -m), $PM)"

installeer() {   # verplichte pakketten
  case "$PM" in
    apt)    sudo apt-get install -y "$@" ;;
    dnf)    sudo dnf install -y "$@" ;;
    pacman) sudo pacman -S --needed --noconfirm "$@" ;;
    zypper) sudo zypper --non-interactive install "$@" ;;
    geen)   true ;;
  esac
}
probeer() {      # optionele pakketten: mogen ontbreken
  local p
  for p in "$@"; do
    installeer "$p" >/dev/null 2>&1 || echo "   ($p niet beschikbaar - overgeslagen, is optioneel)"
  done
}

echo "==> Systeempakketten ($PM)"
case "$PM" in
  apt)
    sudo apt-get update
    installeer python3 python3-venv python3-pip python3-gi python3-gi-cairo gir1.2-gtk-3.0 \
      xdg-utils desktop-file-utils ca-certificates ;;
  dnf)
    installeer python3 python3-pip python3-gobject gtk3 xdg-utils desktop-file-utils ca-certificates ;;
  pacman)
    installeer python python-gobject python-cairo gtk3 xdg-utils desktop-file-utils ca-certificates \
      || { echo "Tip: werk eerst je systeem bij met: sudo pacman -Syu"; exit 1; } ;;
  zypper)
    installeer python3 python3-pip python3-gobject python3-gobject-cairo python3-gobject-Gdk \
      typelib-1_0-Gtk-3_0 xdg-utils desktop-file-utils ca-certificates ;;
esac
# lettertypen (tekst op etiketten, emoji in de app), webp-foto's bekijken en 'Open in GIMP'
case "$PM" in
  apt)    probeer fonts-dejavu-core fonts-noto-color-emoji webp-pixbuf-loader gimp ;;
  dnf)    probeer dejavu-sans-fonts google-noto-color-emoji-fonts webp-pixbuf-loader gimp ;;
  pacman) probeer ttf-dejavu noto-fonts-emoji webp-pixbuf-loader gimp ;;
  zypper) probeer dejavu-fonts noto-coloremoji-fonts webp-pixbuf-loader gimp ;;
esac

PY="$(command -v python3 || true)"
[ -n "$PY" ] || { echo "python3 niet gevonden."; exit 1; }
PYV="$("$PY" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
"$PY" -c 'import sys; sys.exit(sys.version_info < (3, 9))' \
  || { echo "Python $PYV is te oud: SellYourShit heeft Python 3.9 of nieuwer nodig."; exit 1; }
if ! "$PY" -c 'import gi; gi.require_version("Gtk", "3.0"); from gi.repository import Gtk' 2>/dev/null; then
  echo "!!  Python $PYV kan GTK 3 niet laden (PyGObject of GTK 3 ontbreekt)."
  echo "    Installeer het PyGObject-pakket van je distributie voor deze Python en GTK 3, en probeer opnieuw."
  exit 1
fi

echo "==> Virtuele omgeving: $VENV (Python $PYV)"
# --system-site-packages: zodat PyGObject van het systeem zichtbaar blijft; werkt met PEP 668.
# Na een systeemupgrade met een nieuwere Python (bijv. Ubuntu 24.04 -> 26.04) de omgeving opnieuw maken.
OPNIEUW=()
if [ -e "$VENV/pyvenv.cfg" ]; then
  OUD="$("$VENV/bin/python" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || echo kapot)"
  if [ "$OUD" != "$PYV" ]; then
    echo "   bestaande omgeving is van Python $OUD: opnieuw maken"
    OPNIEUW=(--clear)
  fi
fi
"$PY" -m venv --system-site-packages "${OPNIEUW[@]}" "$VENV"
"$VENV/bin/python" -m pip install --upgrade pip
AI_MISLUKT=0
if [ "$MET_AI" -eq 1 ]; then
  if ! "$VENV/bin/python" -m pip install "$SRC[ai]"; then
    echo "!!  De AI-pakketten konden niet geïnstalleerd worden voor Python $PYV."
    echo "    SellYourShit wordt zonder achtergrond weghalen geïnstalleerd; de rest werkt gewoon."
    AI_MISLUKT=1; MET_AI=0
    "$VENV/bin/python" -m pip install "$SRC"
  fi
else
  "$VENV/bin/python" -m pip install "$SRC"
fi
# rembg wordt niet meer gebruikt; oude installatie opruimen
"$VENV/bin/python" -m pip uninstall -y rembg >/dev/null 2>&1 || true

if [ "$MET_AI" -eq 1 ]; then
  # AlphaMaker zelf zit in de app; alleen het model voor Licht (IS-Net, ±170 MB) alvast ophalen,
  # anders doet de app dat de eerste keer zelf.
  AM_DIR="${ALPHAMAKER_MODELS:-$HOME/.cache/alphamaker}"
  haal_model() {   # naam url sha256
    [ -f "$AM_DIR/$1.onnx" ] && return 0
    echo "==> Model $1 voor AlphaMaker (±170 MB, even geduld)"
    mkdir -p "$AM_DIR"
    if ! "$VENV/bin/python" - "$2" "$AM_DIR/$1.onnx" "$3" <<'PY'
import hashlib, os, sys, urllib.request
url, doel, sha = sys.argv[1:4]
h = hashlib.sha256()
try:
    with urllib.request.urlopen(url, timeout=60) as r, open(doel + ".part", "wb") as f:
        for blok in iter(lambda: r.read(1 << 20), b""):
            f.write(blok)
            h.update(blok)
    if sha and h.hexdigest() != sha:
        raise ValueError("controlegetal klopt niet")
    os.replace(doel + ".part", doel)
except Exception as e:
    if os.path.exists(doel + ".part"):
        os.remove(doel + ".part")
    sys.exit(f"   {e}")
PY
    then
      echo "   (downloaden lukte niet: de app haalt het model de eerste keer zelf op)"
    fi
  }
  haal_model isnet-general https://github.com/danielgatis/rembg/releases/download/v0.0.0/isnet-general-use.onnx \
    60920e99c45464f2ba57bee2ad08c919a52bbf852739e96947fbb4358c0d964a
fi

echo "==> Starters"
mkdir -p "$HOME/.local/bin" "$HOME/.local/share/applications" "$PREFIX"
cp "$SRC/marktplaats_suite/assets/icon.png" "$PREFIX/icon.png"
cat > "$HOME/.local/bin/marktplaats-suite" <<LAUNCH
#!/usr/bin/env bash
# X11 (onder Wayland via XWayland) voor betrouwbare vensterherkenning; zonder XWayland gewoon Wayland
if [ -z "\${GDK_BACKEND:-}" ] && [ -n "\${DISPLAY:-}" ]; then export GDK_BACKEND=x11; fi
exec "$VENV/bin/python" -m marktplaats_suite "\$@"
LAUNCH
chmod +x "$HOME/.local/bin/marktplaats-suite"
ln -sf "$HOME/.local/bin/marktplaats-suite" "$HOME/.local/bin/sellyourshit"

cat > "$HOME/.local/share/applications/marktplaats-suite.desktop" <<DESK
[Desktop Entry]
Version=1.0
Type=Application
Name=SellYourShit
Comment=Producten, foto's, scanner en automater in één venster
Exec=$HOME/.local/bin/marktplaats-suite
Icon=$PREFIX/icon.png
Terminal=false
StartupNotify=true
StartupWMClass=marktplaats_suite
Categories=Utility;Office;
DESK
# oude losse starters uit eerdere versies opruimen
rm -f "$HOME"/.local/share/applications/marktplaats-{productmanager,fotomanager,barcode_scanner,automater_gtk}.desktop
# menu-items van de oude losse installers (andere bestandsnamen) opruimen op basis van de naam
for d in "$HOME"/.local/share/applications/*.desktop "$HOME"/Desktop/*.desktop; do
  [ -f "$d" ] || continue
  if grep -qE '^Name=Marktplaats (Automat|Barcode|Foto|Product)' "$d"; then
    echo "   oude starter verwijderd: $d"; rm -f "$d"
  fi
done
update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true

if [ "$MET_CHROME" -eq 1 ]; then
  ( set +e
  echo "==> Browser voor de Automater"
  if command -v google-chrome >/dev/null || command -v google-chrome-stable >/dev/null; then
    echo "   Chrome is al aanwezig"
  elif [ "$(uname -m)" = x86_64 ] && { [ "$PM" = apt ] || [ "$PM" = dnf ] || [ "$PM" = zypper ]; }; then
    TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
    if [ "$PM" = apt ]; then PAKKET="$TMP/chrome.deb"; URL=https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
    else PAKKET="$TMP/chrome.rpm"; URL=https://dl.google.com/linux/direct/google-chrome-stable_current_x86_64.rpm; fi
    "$VENV/bin/python" -c 'import sys, urllib.request; urllib.request.urlretrieve(sys.argv[1], sys.argv[2])' "$URL" "$PAKKET"
    case "$PM" in
      apt) sudo apt-get install -y "$PAKKET" ;;
      dnf) sudo dnf install -y "$PAKKET" ;;
      zypper) sudo zypper --non-interactive --no-gpg-checks install "$PAKKET" ;;
    esac
  else
    echo "   Geen Google Chrome voor dit systeem; Chromium wordt geïnstalleerd."
    case "$PM" in
      apt) sudo apt-get install -y chromium 2>/dev/null || sudo apt-get install -y chromium-browser ;;
      *) installeer chromium ;;
    esac
  fi
  # Selenium (4.6+) haalt zelf de passende chromedriver op; Debian-pakket als reserve.
  [ "$PM" = apt ] && sudo apt-get install -y chromium-driver >/dev/null 2>&1
  true
  ) || echo "   Chrome-installatie mislukt; installeer Chrome of Chromium handmatig."
fi

case ":$PATH:" in *":$HOME/.local/bin:"*) ;; *) echo "Tip: voeg ~/.local/bin toe aan je PATH (log opnieuw in).";; esac
VERSIE="$("$VENV/bin/python" -c 'import marktplaats_suite as m; print(m.__version__)' 2>/dev/null || echo '?')"
echo "==> Klaar: SellYourShit $VERSIE is geïnstalleerd (je ziet het nummer rechtsonder in de app)."
if [ "$AI_MISLUKT" -eq 1 ]; then
  echo "!!  Zonder AI: de AI-pakketten (torch e.d.) zijn er nog niet voor Python $PYV."
fi
if pgrep -f "python.* -m marktplaats_suite" >/dev/null 2>&1; then
  echo "!!  De oude versie draait nog: sluit SellYourShit en start hem opnieuw."
fi
echo "    Start 'SellYourShit' vanuit het menu, of: sellyourshit"
echo "    Gegevens staan in: $PREFIX"
