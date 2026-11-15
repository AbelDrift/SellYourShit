#!/usr/bin/env python3
"""
Fotohulpmiddelen voor Nieuw Product: de bestandskiezer met grote pictogrammen en het
inspectievenster (roteren, zoomen, openen in GIMP). De verwerking zelf (verkleinen, achtergrond
verwijderen met transparent-background, versies met logo) staat in fotoverwerking.py.
"""

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import Gtk, Gdk, GLib, Gio, GdkPixbuf
import subprocess
import os
from marktplaats_suite.common import data_dir, asset, open_in_gimp
import shutil
import glob
import random
import string
import threading
import time
from PIL import Image
import tempfile
import json
from queue import Queue
import gc
import sys
import io

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

AFBEELDING_EXTENSIES = ('.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif')


def pak_zips_uit(zip_paden, doelmap):
    """Haalt alle foto's uit de opgegeven zip-bestanden zonder dat de gebruiker iets hoeft uit te pakken.

    Geeft (lijst_met_foto_paden, lijst_met_meldingen). De foto's komen plat in `doelmap`;
    bij dubbele bestandsnamen (bijv. IMG_001.jpg in twee zips) wordt het zip-nummer voor de
    naam gezet zodat niets wordt overschreven. Alleen de bestandsnaam wordt gebruikt (veilig
    tegen paden als ../ in een zip), verborgen/mac-metadata wordt overgeslagen.
    """
    import zipfile
    shutil.rmtree(doelmap, ignore_errors=True)
    os.makedirs(doelmap, exist_ok=True)
    paden, meldingen, gebruikt = [], [], set()
    for zip_pad in sorted(zip_paden):
        try:
            with zipfile.ZipFile(zip_pad) as z:
                aantal = 0
                for info in sorted(z.infolist(), key=lambda i: i.filename):
                    if info.is_dir():
                        continue
                    naam = os.path.basename(info.filename)
                    if (not naam or naam.startswith('.') or '__MACOSX' in info.filename
                            or not naam.lower().endswith(AFBEELDING_EXTENSIES)):
                        continue
                    doel_naam = naam
                    if doel_naam.lower() in gebruikt:
                        stam, ext = os.path.splitext(naam)
                        doel_naam = f"{os.path.splitext(os.path.basename(zip_pad))[0]}_{stam}{ext}"
                        teller = 2
                        while doel_naam.lower() in gebruikt:
                            doel_naam = f"{os.path.splitext(os.path.basename(zip_pad))[0]}_{stam}_{teller}{ext}"
                            teller += 1
                    gebruikt.add(doel_naam.lower())
                    doel = os.path.join(doelmap, doel_naam)
                    with z.open(info) as bron, open(doel, 'wb') as uit:
                        shutil.copyfileobj(bron, uit)
                    paden.append(doel)
                    aantal += 1
                if aantal:
                    meldingen.append(f"📦 {os.path.basename(zip_pad)}: {aantal} foto{'' if aantal == 1 else chr(39) + 's'} uitgepakt")
                else:
                    meldingen.append(f"⚠️ {os.path.basename(zip_pad)}: geen foto's gevonden")
        except zipfile.BadZipFile:
            meldingen.append(f"⚠️ {os.path.basename(zip_pad)} is geen geldige zip, overgeslagen")
        except Exception as e:
            meldingen.append(f"⚠️ {os.path.basename(zip_pad)}: {e}")
    return paden, meldingen


def run_safe_command(cmd, timeout=300):
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
        if result.returncode != 0:
            return False, result.stderr.decode('utf-8', errors='ignore')
        return True, result.stdout.decode('utf-8', errors='ignore')
    except subprocess.TimeoutExpired:
        return False, f"Timeout na {timeout} seconden"
    except Exception as e:
        return False, str(e)


def crop_and_scale_background(bg_image_path, target_size):
    """Schaal de achtergrondafbeelding op de kortste zijde en crop center."""
    try:
        bg_img = Image.open(bg_image_path)
        target_width, target_height = target_size

        bg_width, bg_height = bg_img.size
        target_ratio = target_width / target_height
        bg_ratio = bg_width / bg_height

        if bg_ratio > target_ratio:
            new_height = target_height
            new_width = int(target_height * bg_ratio)
        else:
            new_width = target_width
            new_height = int(target_width / bg_ratio)

        bg_img = bg_img.resize((new_width, new_height), Image.Resampling.LANCZOS)

        left = (new_width - target_width) // 2
        top = (new_height - target_height) // 2
        right = left + target_width
        bottom = top + target_height

        bg_img = bg_img.crop((left, top, right, bottom))
        return bg_img
    except Exception as e:
        print(f"Fout bij schalen achtergrond: {e}")
        return None


class ImagePreviewWindow(Gtk.Window):
    def __init__(self, parent, image_files):
        super().__init__(title="Inspecteer Afbeeldingen - Transparante Achtergrond")
        self.parent = parent
        self.image_files = image_files
        self.current_index = 0
        self.current_pixbuf = None
        self.rotation_angle = 0
        self.original_pixbuf = None
        self.zoom_level = 100
        self.is_loading = False
        self.current_image_path = None

        self.set_default_size(Gdk.Screen.width(), Gdk.Screen.height())
        self.set_position(Gtk.WindowPosition.CENTER)
        self.maximize()
        self.set_border_width(10)

        main_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.add(main_vbox)

        title_box = Gtk.Box(spacing=10)
        main_vbox.pack_start(title_box, False, False, 0)

        title_label = Gtk.Label()
        title_label.set_markup("<span size='large' weight='bold'>Inspecteer Afbeeldingen</span>")
        title_box.pack_start(title_label, True, True, 0)

        self.status_label = Gtk.Label()
        self.status_label.set_xalign(0)
        title_box.pack_start(self.status_label, True, True, 10)

        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled_window.set_shadow_type(Gtk.ShadowType.IN)
        main_vbox.pack_start(scrolled_window, True, True, 0)

        self.event_box = Gtk.EventBox()
        self.event_box.set_events(Gdk.EventMask.SCROLL_MASK | Gdk.EventMask.BUTTON_PRESS_MASK)
        self.event_box.connect("scroll-event", self.on_scroll_zoom)
        scrolled_window.add(self.event_box)

        self.image = Gtk.Image()
        self.event_box.add(self.image)

        toolbar_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        toolbar_box.set_size_request(-1, 140)
        main_vbox.pack_start(toolbar_box, False, False, 0)

        control_row1 = Gtk.Box(spacing=10)
        toolbar_box.pack_start(control_row1, False, False, 0)

        rotate_frame = Gtk.Frame(label="Rotatie")
        rotate_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        rotate_frame.add(rotate_box)
        control_row1.pack_start(rotate_frame, False, False, 0)

        rotate_btn_box = Gtk.Box(spacing=5)
        rotate_box.pack_start(rotate_btn_box, False, False, 0)

        self.rotate_left_btn = Gtk.Button(label="↺ -90°")
        self.rotate_left_btn.connect("clicked", self.rotate_left)
        rotate_btn_box.pack_start(self.rotate_left_btn, False, False, 0)

        self.rotate_right_btn = Gtk.Button(label="↻ +90°")
        self.rotate_right_btn.connect("clicked", self.rotate_right)
        rotate_btn_box.pack_start(self.rotate_right_btn, False, False, 0)

        self.rotate_reset_btn = Gtk.Button(label="⟲ Reset")
        self.rotate_reset_btn.connect("clicked", self.reset_rotation)
        rotate_btn_box.pack_start(self.rotate_reset_btn, False, False, 0)

        self.rotation_label = Gtk.Label(label="0°")
        rotate_btn_box.pack_start(self.rotation_label, False, False, 10)

        rot_scale_box = Gtk.Box(spacing=5)
        rotate_box.pack_start(rot_scale_box, False, False, 0)

        self.rotation_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 360, 1)
        self.rotation_scale.set_value(0)
        self.rotation_scale.set_size_request(200, -1)
        self.rotation_scale.connect("value-changed", self.on_rotation_scale_changed)
        rot_scale_box.pack_start(self.rotation_scale, True, True, 0)

        zoom_frame = Gtk.Frame(label="Zoom")
        zoom_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        zoom_frame.add(zoom_box)
        control_row1.pack_start(zoom_frame, False, False, 0)

        zoom_btn_box = Gtk.Box(spacing=5)
        zoom_box.pack_start(zoom_btn_box, False, False, 0)

        self.zoom_out_btn = Gtk.Button(label="🔍−")
        self.zoom_out_btn.connect("clicked", self.zoom_out)
        zoom_btn_box.pack_start(self.zoom_out_btn, False, False, 0)

        self.zoom_in_btn = Gtk.Button(label="🔍+")
        self.zoom_in_btn.connect("clicked", self.zoom_in)
        zoom_btn_box.pack_start(self.zoom_in_btn, False, False, 0)

        self.zoom_fit_btn = Gtk.Button(label="⟐ Passend")
        self.zoom_fit_btn.connect("clicked", self.zoom_fit)
        zoom_btn_box.pack_start(self.zoom_fit_btn, False, False, 0)

        self.zoom_100_btn = Gtk.Button(label="100%")
        self.zoom_100_btn.connect("clicked", self.zoom_100)
        zoom_btn_box.pack_start(self.zoom_100_btn, False, False, 0)

        self.zoom_label = Gtk.Label(label="100%")
        zoom_btn_box.pack_start(self.zoom_label, False, False, 10)

        zoom_scale_box = Gtk.Box(spacing=5)
        zoom_box.pack_start(zoom_scale_box, False, False, 0)

        self.zoom_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 10, 400, 1)
        self.zoom_scale.set_value(100)
        self.zoom_scale.set_size_request(200, -1)
        self.zoom_scale.connect("value-changed", self.on_zoom_scale_changed)
        zoom_scale_box.pack_start(self.zoom_scale, True, True, 0)

        zoom_percent_label = Gtk.Label(label="%")
        zoom_scale_box.pack_start(zoom_percent_label, False, False, 0)

        control_row2 = Gtk.Box(spacing=10)
        toolbar_box.pack_start(control_row2, False, False, 0)

        nav_frame = Gtk.Frame(label="Navigatie")
        nav_box = Gtk.Box(spacing=5)
        nav_frame.add(nav_box)
        control_row2.pack_start(nav_frame, False, False, 0)

        self.prev_btn = Gtk.Button(label="◀ Vorige")
        self.prev_btn.connect("clicked", self.prev_image)
        nav_box.pack_start(self.prev_btn, False, False, 0)

        self.next_btn = Gtk.Button(label="Volgende ▶")
        self.next_btn.connect("clicked", self.next_image)
        nav_box.pack_start(self.next_btn, False, False, 0)

        self.progress_label = Gtk.Label(label="1/1")
        nav_box.pack_start(self.progress_label, False, False, 10)

        info_frame = Gtk.Frame(label="Informatie")
        info_box = Gtk.Box(spacing=5)
        info_frame.add(info_box)
        control_row2.pack_start(info_frame, False, False, 0)

        self.image_info_label = Gtk.Label(label="")
        info_box.pack_start(self.image_info_label, False, False, 0)

        action_frame = Gtk.Frame(label="Acties")
        action_box = Gtk.Box(spacing=5)
        action_frame.add(action_box)
        control_row2.pack_start(action_frame, False, False, 0)

        self.open_gimp_btn = Gtk.Button(label="🖌 Open in GIMP")
        self.open_gimp_btn.connect("clicked", self.open_in_gimp)
        action_box.pack_start(self.open_gimp_btn, False, False, 0)

        self.refresh_btn = Gtk.Button(label="⟳ Vernieuw")
        self.refresh_btn.connect("clicked", self.refresh_current)
        action_box.pack_start(self.refresh_btn, False, False, 0)

        control_row3 = Gtk.Box(spacing=10)
        toolbar_box.pack_start(control_row3, False, False, 0)

        process_frame = Gtk.Frame(label="Verwerking")
        process_box = Gtk.Box(spacing=20)
        process_frame.add(process_box)
        control_row3.pack_start(process_frame, True, True, 0)

        self.cancel_btn = Gtk.Button(label="❌ Annuleren")
        self.cancel_btn.connect("clicked", self.cancel_processing)
        process_box.pack_start(self.cancel_btn, False, False, 0)

        self.continue_btn = Gtk.Button(label="✅ Proces Voortzetten")
        self.continue_btn.get_style_context().add_class("suggested-action")
        self.continue_btn.connect("clicked", self.continue_processing)
        process_box.pack_start(self.continue_btn, False, False, 0)

        GLib.idle_add(self.load_first_image)
        self.show_all()

    def load_first_image(self):
        self.load_image(0)
        return False

    def on_scroll_zoom(self, widget, event):
        if event.direction == Gdk.ScrollDirection.UP:
            self.zoom_in(None)
            return True
        elif event.direction == Gdk.ScrollDirection.DOWN:
            self.zoom_out(None)
            return True
        return False

    def on_rotation_scale_changed(self, widget):
        if not self.original_pixbuf:
            return
        self.rotation_angle = int(self.rotation_scale.get_value())
        self.rotation_label.set_text(f"{self.rotation_angle}°")
        self.update_display()

    def on_zoom_scale_changed(self, widget):
        if not self.original_pixbuf:
            return
        self.zoom_level = int(self.zoom_scale.get_value())
        self.zoom_label.set_text(f"{self.zoom_level}%")
        self.update_display()

    def zoom_in(self, widget):
        if not self.original_pixbuf:
            return
        new_zoom = min(400, self.zoom_level + 10)
        self.zoom_level = new_zoom
        self.zoom_scale.set_value(new_zoom)
        self.zoom_label.set_text(f"{new_zoom}%")
        self.update_display()

    def zoom_out(self, widget):
        if not self.original_pixbuf:
            return
        new_zoom = max(10, self.zoom_level - 10)
        self.zoom_level = new_zoom
        self.zoom_scale.set_value(new_zoom)
        self.zoom_label.set_text(f"{new_zoom}%")
        self.update_display()

    def zoom_fit(self, widget):
        if not self.original_pixbuf:
            return
        allocation = self.event_box.get_allocation()
        width = allocation.width - 20
        height = allocation.height - 20

        orig_width = self.original_pixbuf.get_width()
        orig_height = self.original_pixbuf.get_height()

        if width > 0 and height > 0:
            scale_x = width / orig_width
            scale_y = height / orig_height
            scale = min(scale_x, scale_y) * 100
            new_zoom = int(max(10, min(400, scale)))
            self.zoom_level = new_zoom
            self.zoom_scale.set_value(new_zoom)
            self.zoom_label.set_text(f"{new_zoom}%")
            self.update_display()

    def zoom_100(self, widget):
        if not self.original_pixbuf:
            return
        self.zoom_level = 100
        self.zoom_scale.set_value(100)
        self.zoom_label.set_text("100%")
        self.update_display()

    def update_display(self):
        if not self.original_pixbuf or not self.current_image_path:
            return

        try:
            orig_width = self.original_pixbuf.get_width()
            orig_height = self.original_pixbuf.get_height()

            scale = self.zoom_level / 100.0
            new_width = int(orig_width * scale)
            new_height = int(orig_height * scale)

            if new_width > 0 and new_height > 0:
                scaled_pixbuf = self.original_pixbuf.scale_simple(
                    new_width, new_height, GdkPixbuf.InterpType.BILINEAR
                )
            else:
                scaled_pixbuf = self.original_pixbuf.copy()

            if self.rotation_angle != 0:
                data = scaled_pixbuf.get_pixels()
                pil_img = Image.frombytes('RGBA', (scaled_pixbuf.get_width(), scaled_pixbuf.get_height()), data)
                rotated_pil = pil_img.rotate(self.rotation_angle, expand=True, resample=Image.Resampling.BICUBIC)

                with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                    rotated_pil.save(tmp.name, 'PNG')
                    tmp_path = tmp.name

                self.current_pixbuf = GdkPixbuf.Pixbuf.new_from_file(tmp_path)
                os.unlink(tmp_path)
            else:
                self.current_pixbuf = scaled_pixbuf

            self.image.set_from_pixbuf(self.current_pixbuf)

        except Exception as e:
            self.status_label.set_text(f"Fout: {e}")

    def load_image(self, index):
        if self.is_loading:
            return

        if 0 <= index < len(self.image_files):
            self.is_loading = True
            self.current_index = index
            self.rotation_angle = 0
            self.rotation_label.set_text("0°")
            self.rotation_scale.set_value(0)

            self.current_image_path = self.image_files[index]
            if not os.path.exists(self.current_image_path):
                self.status_label.set_text(f"Bestand niet gevonden: {self.current_image_path}")
                self.is_loading = False
                return

            try:
                if self.original_pixbuf:
                    del self.original_pixbuf
                if self.current_pixbuf:
                    del self.current_pixbuf

                self.original_pixbuf = GdkPixbuf.Pixbuf.new_from_file(self.current_image_path)

                filename = os.path.basename(self.current_image_path)
                size = f"{self.original_pixbuf.get_width()}x{self.original_pixbuf.get_height()}"
                self.image_info_label.set_text(f"{filename}  |  {size}px")
                self.status_label.set_text(f"Afbeelding {index + 1} van {len(self.image_files)}")
                self.progress_label.set_text(f"{index + 1}/{len(self.image_files)}")

                GLib.idle_add(self.zoom_fit, None)
                gc.collect()

            except Exception as e:
                self.status_label.set_text(f"Fout bij laden: {e}")
            finally:
                self.is_loading = False

    def rotate_image(self, degrees):
        if not self.original_pixbuf:
            return

        new_angle = (self.rotation_angle + degrees) % 360
        self.rotation_angle = new_angle
        self.rotation_label.set_text(f"{new_angle}°")
        self.rotation_scale.set_value(new_angle)

        self.update_display()
        self.status_label.set_text(f"Afbeelding geroteerd naar {new_angle}°")
        self.save_rotation()

    def save_rotation(self):
        if not self.original_pixbuf or self.rotation_angle == 0 or not self.current_image_path:
            return True

        try:
            pil_img = Image.open(self.current_image_path)

            if self.rotation_angle != 0:
                rotated_pil = pil_img.rotate(self.rotation_angle, expand=True, resample=Image.Resampling.BICUBIC)
            else:
                rotated_pil = pil_img

            if self.current_image_path.lower().endswith((".jpg", ".jpeg")) and rotated_pil.mode != "RGB":
                rotated_pil = rotated_pil.convert("RGB")
            rotated_pil.save(self.current_image_path)

            self.original_pixbuf = GdkPixbuf.Pixbuf.new_from_file(self.current_image_path)

            # BELANGRIJK: de rotatie is nu permanent in het bestand gebakken,
            # dus rotation_angle terug naar 0. Zonder dit werd bij de volgende
            # update_display() dezelfde hoek NOG EEN KEER bovenop de al-
            # geroteerde pixbuf gezet - vandaar dat een enkele +90°-klik
            # zichtbaar naar 180° "sprong".
            self.rotation_angle = 0
            self.rotation_label.set_text("0°")
            self.rotation_scale.set_value(0)

            self.update_display()
            self.status_label.set_text(f"Rotatie opgeslagen")
            return True
        except Exception as e:
            self.status_label.set_text(f"Fout bij opslaan: {e}")
            return False

    def rotate_left(self, widget):
        # PIL's Image.rotate() draait tegen de klok in bij een POSITIEVE hoek.
        # Het ↺-icoon (tegen de klok in) moet dus +90 sturen, niet -90 -
        # anders draait de knop met het CCW-icoon in werkelijkheid met de klok mee.
        self.rotate_image(90)

    def rotate_right(self, widget):
        self.rotate_image(-90)

    def reset_rotation(self, widget):
        self.rotation_angle = 0
        self.rotation_label.set_text("0°")
        self.rotation_scale.set_value(0)

        try:
            if self.current_image_path and os.path.exists(self.current_image_path):
                self.original_pixbuf = GdkPixbuf.Pixbuf.new_from_file(self.current_image_path)
                self.update_display()
                self.status_label.set_text("Rotatie gereset")
        except Exception as e:
            self.status_label.set_text(f"Fout bij resetten: {e}")

    def prev_image(self, widget):
        if self.current_index > 0:
            self.save_rotation()
            self.load_image(self.current_index - 1)

    def next_image(self, widget):
        if self.current_index < len(self.image_files) - 1:
            self.save_rotation()
            self.load_image(self.current_index + 1)

    def open_in_gimp(self, widget):
        try:
            self.save_rotation()
            open_in_gimp([self.current_image_path])
            self.status_label.set_text("Afbeelding geopend in GIMP")
        except FileNotFoundError:
            self.status_label.set_text("GIMP niet geïnstalleerd")

    def refresh_current(self, widget):
        self.load_image(self.current_index)

    def cancel_processing(self, widget):
        self.parent.cancel_processing()
        self.destroy()

    def continue_processing(self, widget):
        if self.save_rotation():
            if self.current_pixbuf:
                del self.current_pixbuf
            if self.original_pixbuf:
                del self.original_pixbuf
            gc.collect()
            self.parent.process_after_inspection()
            self.destroy()
        else:
            dialog = Gtk.MessageDialog(
                parent=self,
                flags=0,
                message_type=Gtk.MessageType.WARNING,
                buttons=Gtk.ButtonsType.YES_NO,
                text="Rotatie opslaan mislukt!"
            )
            dialog.format_secondary_text("Wil je doorgaan zonder de rotatie op te slaan?")
            response = dialog.run()
            dialog.destroy()

            if response == Gtk.ResponseType.YES:
                self.parent.process_after_inspection()
                self.destroy()


def downloads_map():
    """De Downloads-map van de gebruiker (XDG), anders ~/Downloads, anders de thuismap."""
    for pad in (GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOWNLOAD),
                os.path.expanduser("~/Downloads")):
        if pad and os.path.isdir(pad):
            return pad
    return os.path.expanduser("~")


def _zip_fotos(zip_pad):
    """Namen van de foto's in een zip (zelfde filter als pak_zips_uit)."""
    import zipfile
    with zipfile.ZipFile(zip_pad) as z:
        return [i.filename for i in sorted(z.infolist(), key=lambda i: i.filename)
                if not i.is_dir() and os.path.basename(i.filename)
                and not os.path.basename(i.filename).startswith('.') and '__MACOSX' not in i.filename
                and i.filename.lower().endswith(AFBEELDING_EXTENSIES)]


class CustomFileChooser(Gtk.Dialog):
    """Eigen bestandskiezer met grote pictogrammen: mappen, zip-bestanden en foto's.

    Mappen open je met dubbelklik; zip-bestanden tonen de eerste foto en het aantal foto's erin.
    Miniaturen worden op de achtergrond geladen, zodat ook een volle Downloads-map meteen opent."""

    MINI = 120

    def __init__(self, parent, title="Selecteer foto's of zip-bestanden", select_multiple=True, start_folder=None):
        super().__init__(title=title, transient_for=parent, flags=0)
        self.set_default_size(950, 700)
        self.set_modal(True)

        self.selected_files = []
        self.select_multiple = select_multiple
        self._laad_token = 0
        self._iconen = {}
        self.current_folder = start_folder if start_folder and os.path.isdir(start_folder) else downloads_map()

        self.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OK, Gtk.ResponseType.OK)

        vbox = self.get_content_area()
        vbox.set_spacing(10)

        top_box = Gtk.Box(spacing=5)
        vbox.pack_start(top_box, False, False, 0)

        up_btn = Gtk.Button(label="⬆ Omhoog")
        up_btn.set_tooltip_text("Naar de bovenliggende map")
        up_btn.connect("clicked", self.go_up)
        top_box.pack_start(up_btn, False, False, 0)

        dl_btn = Gtk.Button(label="⬇ Downloads")
        dl_btn.connect("clicked", lambda *_: self.load_folder(downloads_map()))
        top_box.pack_start(dl_btn, False, False, 0)

        self.path_entry = Gtk.Entry()
        self.path_entry.set_placeholder_text("Pad naar map met foto's...")
        self.path_entry.connect("activate", self.on_path_enter)
        top_box.pack_start(self.path_entry, True, True, 0)

        browse_btn = Gtk.Button(label="📂 Bladeren")
        browse_btn.connect("clicked", self.browse_folder)
        top_box.pack_start(browse_btn, False, False, 0)

        refresh_btn = Gtk.Button(label="🔄 Vernieuw")
        refresh_btn.connect("clicked", self.refresh_current_folder)
        top_box.pack_start(refresh_btn, False, False, 0)

        self.folder_label = Gtk.Label()
        self.folder_label.set_xalign(0)
        vbox.pack_start(self.folder_label, False, False, 0)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_size_request(-1, 450)
        vbox.pack_start(scrolled, True, True, 0)

        self.icon_store = Gtk.ListStore(GdkPixbuf.Pixbuf, str, str)
        self.icon_view = Gtk.IconView()
        self.icon_view.set_model(self.icon_store)
        self.icon_view.set_pixbuf_column(0)
        self.icon_view.set_text_column(1)
        self.icon_view.set_item_width(140)
        self.icon_view.set_columns(0)
        self.icon_view.set_selection_mode(Gtk.SelectionMode.MULTIPLE if select_multiple else Gtk.SelectionMode.SINGLE)
        self.icon_view.set_activate_on_single_click(False)
        self.icon_view.set_tooltip_text("Dubbelklik op een map om hem te openen")
        self.icon_view.connect("item-activated", self.on_item_activated)
        scrolled.add(self.icon_view)

        info_box = Gtk.Box(spacing=20)
        vbox.pack_start(info_box, False, False, 5)

        self.selected_label = Gtk.Label()
        self.selected_label.set_markup("<small>0 bestanden geselecteerd</small>")
        info_box.pack_start(self.selected_label, True, True, 0)

        if select_multiple:
            select_all_btn = Gtk.Button(label="Alles selecteren")
            select_all_btn.connect("clicked", self.select_all)
            info_box.pack_start(select_all_btn, False, False, 0)

            deselect_all_btn = Gtk.Button(label="Alles deselecteren")
            deselect_all_btn.connect("clicked", self.deselect_all)
            info_box.pack_start(deselect_all_btn, False, False, 0)

        self.icon_view.connect("selection-changed", self.on_selection_changed)

        self.load_folder(self.current_folder)
        self.show_all()

    # --- pictogrammen en miniaturen ---
    def _icoon(self, soort):
        if soort not in self._iconen:
            namen = {"map": ("folder", "inode-directory"),
                     "zip": ("application-zip", "package-x-generic", "application-x-archive"),
                     "foto": ("image-x-generic", "image")}[soort]
            pb = None
            thema = Gtk.IconTheme.get_default()
            for naam in namen:
                try:
                    pb = thema.load_icon(naam, 96, Gtk.IconLookupFlags.FORCE_SIZE)
                    break
                except Exception:
                    continue
            if pb is None:
                pb = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8, 96, 96)
                pb.fill({"map": 0xD9A44AFF, "zip": 0x8E7CC3FF}.get(soort, 0x88888888))
            self._iconen[soort] = pb
        return self._iconen[soort]

    def _pixbuf_van(self, bron):
        """Kleine miniatuur van een foto (pad of bestandsobject), rechtop volgens EXIF."""
        from PIL import ImageOps
        with Image.open(bron) as im:
            im.draft("RGB", (self.MINI * 2, self.MINI * 2))
            im = ImageOps.exif_transpose(im)
            im.thumbnail((self.MINI, self.MINI))
            buf = io.BytesIO()
            if im.mode in ("RGBA", "LA", "P"):
                im.convert("RGBA").save(buf, format="PNG")
            else:
                im.convert("RGB").save(buf, format="JPEG", quality=85)
        loader = GdkPixbuf.PixbufLoader.new()
        loader.write(buf.getvalue())
        loader.close()
        return loader.get_pixbuf()

    def _zip_miniatuur(self, pad):
        import zipfile
        namen = _zip_fotos(pad)
        aantal = {0: "geen foto's", 1: "1 foto"}.get(len(namen), f"{len(namen)} foto's")
        tekst = f"📦 {os.path.basename(pad)}\n{aantal}"
        pb = None
        if namen:
            with zipfile.ZipFile(pad) as z, z.open(namen[0]) as f:
                pb = self._pixbuf_van(io.BytesIO(f.read()))
        return pb, tekst

    def load_folder(self, folder_path):
        self._laad_token += 1
        token = self._laad_token
        self.icon_store.clear()
        self.selected_files = []
        self.selected_label.set_markup("<small>0 bestanden geselecteerd</small>")

        if not os.path.isdir(folder_path):
            self.folder_label.set_markup(f"<span color='red'>Map bestaat niet: {GLib.markup_escape_text(folder_path)}</span>")
            return

        self.current_folder = folder_path
        self.path_entry.set_text(folder_path)

        image_extensions = ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.tiff', '.tif')
        mappen, zips, fotos = [], [], []
        try:
            for naam in sorted(os.listdir(folder_path), key=str.lower):
                if naam.startswith('.'):
                    continue
                pad = os.path.join(folder_path, naam)
                if os.path.isdir(pad):
                    mappen.append((naam, pad))
                elif naam.lower().endswith('.zip'):
                    zips.append((naam, pad))
                elif naam.lower().endswith(image_extensions):
                    fotos.append((naam, pad))
        except Exception as e:
            self.folder_label.set_markup(f"<span color='red'>Fout bij lezen map: {GLib.markup_escape_text(str(e))}</span>")
            return

        werk = []
        for naam, pad in mappen:
            self.icon_store.append([self._icoon("map"), f"📁 {naam}", pad])
        for naam, pad in zips:
            werk.append((self.icon_store.append([self._icoon("zip"), f"📦 {naam}", pad]), pad, "zip"))
        for naam, pad in fotos:
            werk.append((self.icon_store.append([self._icoon("foto"), naam, pad]), pad, "foto"))

        delen = ["1 foto" if len(fotos) == 1 else f"{len(fotos)} foto's"]
        if zips:
            delen.append(f"{len(zips)} zip-bestand{'en' if len(zips) != 1 else ''}")
        if mappen:
            delen.append(f"{len(mappen)} map{'pen' if len(mappen) != 1 else ''}")
        self.folder_label.set_markup(f"<b>{GLib.markup_escape_text(folder_path)}</b>  <small>({', '.join(delen)})</small>")

        def miniaturen():
            for it, pad, soort in werk:
                if token != self._laad_token:
                    return
                try:
                    if soort == "zip":
                        pb, tekst = self._zip_miniatuur(pad)
                        self.icon_store.set_value(it, 1, tekst)
                    else:
                        pb = self._pixbuf_van(pad)
                    if pb is not None:
                        self.icon_store.set_value(it, 0, pb)
                except Exception as e:
                    print(f"Miniatuur mislukt voor {pad}: {e}")
                yield True
        stappen = miniaturen()
        GLib.idle_add(lambda: next(stappen, False))

    def go_up(self, widget):
        boven = os.path.dirname(self.current_folder.rstrip(os.sep)) or os.sep
        self.load_folder(boven)

    def browse_folder(self, widget):
        dialog = Gtk.FileChooserDialog(title="Selecteer map met foto's", transient_for=self,
                                       action=Gtk.FileChooserAction.SELECT_FOLDER)
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OK, Gtk.ResponseType.OK)
        dialog.set_current_folder(self.current_folder)
        if dialog.run() == Gtk.ResponseType.OK:
            self.load_folder(dialog.get_filename())
        dialog.destroy()

    def refresh_current_folder(self, widget):
        self.load_folder(self.current_folder)

    def on_path_enter(self, widget):
        folder_path = os.path.expanduser(self.path_entry.get_text().strip())
        if folder_path and os.path.isdir(folder_path):
            self.load_folder(folder_path)

    def on_item_activated(self, icon_view, path):
        file_path = self.icon_store[path][2]
        if os.path.isdir(file_path):
            self.load_folder(file_path)
        elif os.path.isfile(file_path):
            # dubbelklik op een foto of zip: die kiezen (plus wat al geselecteerd was)
            icon_view.select_path(path)
            self.on_selection_changed(icon_view)
            self.response(Gtk.ResponseType.OK)

    def on_selection_changed(self, icon_view):
        self.selected_files = [self.icon_store[p][2] for p in sorted(icon_view.get_selected_items(),
                                                                       key=lambda p: p.get_indices()[0])
                               if os.path.isfile(self.icon_store[p][2])]
        n_zip = sum(1 for f in self.selected_files if f.lower().endswith('.zip'))
        extra = f" ({n_zip} zip)" if n_zip else ""
        self.selected_label.set_markup(f"<small><b>{len(self.selected_files)}</b> bestanden geselecteerd{extra}</small>")

    def select_all(self, widget):
        for rij in self.icon_store:
            if os.path.isfile(rij[2]):
                self.icon_view.select_path(rij.path)

    def deselect_all(self, widget):
        self.icon_view.unselect_all()

    def get_filenames(self):
        return self.selected_files
