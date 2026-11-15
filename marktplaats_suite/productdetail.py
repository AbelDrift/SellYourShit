"""Detailvenster van één product: de advertentie 'in het rauw', alle fotoversies en de status.

Niet-modaal: je kunt meerdere open hebben en foto's/tekst rechtstreeks naar een browser slepen
of kopiëren voor platforms waar het plaatsen (nog) niet automatisch gaat."""
import os

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib, Pango

from marktplaats_suite.common import open_extern
from marktplaats_suite.fotoverwerking import lijst_fotos

VERSIES = [
    ("originelen", "Originelen"),
    ("zonder_logo", "Wit / zonder logo"),
    ("met_logo", "Met logo"),
    ("zonder_logo_bg", "Eigen achtergrond"),
    ("met_logo_bg", "Eigen achtergrond met logo"),
    ("transparant", "Transparant (PNG)"),
]

LABELS = {
    "artikelnummer": "Artikelnummer", "titel": "Titel", "categorie": "Categorie",
    "marktplaats_categorie": "Marktplaats-categorie", "vinted_categorie": "Vinted-categorie",
    "conditie": "Staat", "staat_details": "Staat-details", "tijdsperiode": "Tijdsperiode",
    "merk": "Merk", "materiaal": "Materiaal", "stijl": "Stijl", "kleur": "Kleur",
    "lengte": "Lengte (cm)", "breedte": "Breedte (cm)", "hoogte": "Hoogte (cm)", "gewicht": "Gewicht (kg)",
    "waarde_min": "Waarde min (€)", "waarde_max": "Waarde max (€)", "vraagprijs": "Vraagprijs (€)",
    "opslaglocatie": "Opslaglocatie", "sublocatie": "Sublocatie", "rij": "Rij",
    "aanmaakdatum": "Aangemaakt", "verwerkt_door": "Verwerkt door", "toegewezen_aan": "Toegewezen aan",
    "kanalen": "Kanalen", "extra_info_koper": "Extra info koper",
    "verkoopprijs": "Verkoopprijs (€)", "verkoopdatum": "Verkoopdatum", "leverwijze": "Leverwijze",
}


def _ja(waarde):
    return (waarde or "").strip().lower() == "ja"


class ProductDetailVenster(Gtk.Window):
    def __init__(self, parent, product, productmap, omschrijving, op_bewerken=None):
        nr = product.get("artikelnummer", "")
        super().__init__(title=f"{nr} · {product.get('titel', '')}")
        if parent is not None:
            self.set_transient_for(parent)
        self.set_default_size(1000, 720)
        self.product = product
        self.productmap = productmap

        hoofd = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        hoofd.set_border_width(12)
        self.add(hoofd)

        # --- kop: artikelnummer, titel, status ---
        kop = Gtk.Box(spacing=8)
        titel = Gtk.Label()
        titel.set_markup(f"<span size='large'><b>{GLib.markup_escape_text(product.get('titel', ''))}</b></span>\n"
                         f"<small>{GLib.markup_escape_text(nr)}</small>")
        titel.set_xalign(0)
        titel.set_selectable(True)
        titel.set_ellipsize(Pango.EllipsizeMode.END)
        kop.pack_start(titel, True, True, 0)
        for tekst, waarde in (("Kopieer titel", product.get("titel", "")), ("Kopieer nummer", nr),
                              ("Kopieer prijs", product.get("vraagprijs", ""))):
            b = Gtk.Button(label=tekst)
            b.connect("clicked", self._kopieer, waarde)
            kop.pack_start(b, False, False, 0)
        hoofd.pack_start(kop, False, False, 0)

        status = Gtk.FlowBox()
        status.set_selection_mode(Gtk.SelectionMode.NONE)
        status.set_max_children_per_line(8)
        kanalen = [k.strip() for k in (product.get("kanalen") or "marktplaats").split(",") if k.strip()]
        badges = []
        if _ja(product.get("verkocht")):
            badges.append(("💰 Verkocht" + (f" voor € {product['verkoopprijs']}" if product.get("verkoopprijs") else ""), "#c0392b"))
        if _ja(product.get("gereserveerd")):
            badges.append(("🔒 Gereserveerd", "#d35400"))
        for k, veld in (("marktplaats", "online"), ("whoppah", "online_whoppah"), ("vinted", "online_vinted")):
            if k in kanalen or _ja(product.get(veld)):
                aan = _ja(product.get(veld))
                badges.append((f"{'🟢' if aan else '⚪'} {k.capitalize()}: {'online' if aan else 'offline'}",
                               "#27ae60" if aan else "#7f8c8d"))
        for tekst, kleur in badges:
            l = Gtk.Label()
            l.set_markup(f"<span foreground='{kleur}'><b>{GLib.markup_escape_text(tekst)}</b></span>")
            status.add(l)
        hoofd.pack_start(status, False, False, 0)

        # --- midden: links de advertentie, rechts foto's ---
        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        hoofd.pack_start(paned, True, True, 0)

        nb = Gtk.Notebook()
        paned.pack1(nb, True, False)

        # Advertentie
        adv = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        adv.set_border_width(6)
        sw = Gtk.ScrolledWindow()
        tv = Gtk.TextView()
        tv.set_wrap_mode(Gtk.WrapMode.WORD)
        tv.set_editable(False)
        tv.get_buffer().set_text(omschrijving or "")
        sw.add(tv)
        adv.pack_start(sw, True, True, 0)
        b = Gtk.Button(label="📋 Kopieer omschrijving")
        b.connect("clicked", self._kopieer, omschrijving or "")
        adv.pack_start(b, False, False, 0)
        nb.append_page(adv, Gtk.Label(label="Advertentie"))

        # Gegevens
        grid = Gtk.Grid(column_spacing=12, row_spacing=4)
        grid.set_border_width(8)
        rij = 0
        for k, naam in LABELS.items():
            v = (product.get(k) or "").strip()
            if not v:
                continue
            l = Gtk.Label(label=naam, xalign=0)
            l.get_style_context().add_class("dim-label")
            w = Gtk.Label(label=v, xalign=0)
            w.set_selectable(True)
            w.set_line_wrap(True)
            grid.attach(l, 0, rij, 1, 1)
            grid.attach(w, 1, rij, 1, 1)
            rij += 1
        try:
            from marktplaats_suite.verzending import advies
            adv = advies(product.get("lengte"), product.get("breedte"), product.get("hoogte"), product.get("gewicht"))
        except Exception:
            adv = None
        if adv:
            l = Gtk.Label(label="Verzendadvies", xalign=0)
            l.get_style_context().add_class("dim-label")
            w = Gtk.Label(label=adv["tekst"], xalign=0)
            w.set_selectable(True)
            w.set_line_wrap(True)
            grid.attach(l, 0, rij, 1, 1)
            grid.attach(w, 1, rij, 1, 1)
            rij += 1
        sw2 = Gtk.ScrolledWindow()
        sw2.add(grid)
        nb.append_page(sw2, Gtk.Label(label="Gegevens"))

        # Links
        links = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        links.set_border_width(8)
        urls = [product.get(f"url_{i}", "").strip() for i in range(1, 6)]
        urls = [u for u in urls if u]
        if urls:
            for u in urls:
                lb = Gtk.LinkButton.new_with_label(u, u)
                lb.set_halign(Gtk.Align.START)
                lb.connect("activate-link", lambda w: (open_extern(w.get_uri()), True)[1])
                links.pack_start(lb, False, False, 0)
        else:
            links.pack_start(Gtk.Label(label="Nog geen links naar platforms.", xalign=0), False, False, 0)
        nb.append_page(links, Gtk.Label(label=f"Links ({len(urls)})"))

        # Foto's
        fotos_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        fotos_box.set_border_width(4)
        hint = Gtk.Label()
        hint.set_markup("<small>Sleep foto's naar een uploadveld in je browser · dubbelklik = openen</small>")
        hint.set_xalign(0)
        fotos_box.pack_start(hint, False, False, 0)
        fsw = Gtk.ScrolledWindow()
        fsw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        lijst = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        fsw.add(lijst)
        fotos_box.pack_start(fsw, True, True, 0)
        gevonden = 0
        for sub, naam in VERSIES:
            fotos = lijst_fotos(os.path.join(productmap, sub)) if productmap else []
            if not fotos:
                continue
            gevonden += 1
            lijst.pack_start(self._fotosectie(naam, os.path.join(productmap, sub), fotos), False, False, 0)
        if not gevonden:
            lijst.pack_start(Gtk.Label(label="Geen foto's gevonden in de productmap.", xalign=0), False, False, 0)
        paned.pack2(fotos_box, True, False)
        paned.set_position(480)

        # --- onderrij ---
        onder = Gtk.Box(spacing=6)
        b_map = Gtk.Button(label="📂 Open productmap")
        b_map.connect("clicked", lambda *_: productmap and os.path.isdir(productmap) and open_extern(productmap))
        b_map.set_sensitive(bool(productmap and os.path.isdir(productmap)))
        onder.pack_start(b_map, False, False, 0)
        if op_bewerken:
            b_bew = Gtk.Button(label="✏️ Bewerken")
            b_bew.connect("clicked", lambda *_: (self.destroy(), op_bewerken()))
            onder.pack_start(b_bew, False, False, 0)
        sluit = Gtk.Button(label="Sluiten")
        sluit.connect("clicked", lambda *_: self.destroy())
        onder.pack_end(sluit, False, False, 0)
        hoofd.pack_start(onder, False, False, 0)
        self.set_focus(sluit)

    def _fotosectie(self, naam, map_, fotos):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        kop = Gtk.Box(spacing=6)
        l = Gtk.Label()
        l.set_markup(f"<b>{GLib.markup_escape_text(naam)}</b> <small>({len(fotos)})</small>")
        l.set_xalign(0)
        kop.pack_start(l, True, True, 0)
        b = Gtk.Button(label="📂")
        b.set_relief(Gtk.ReliefStyle.NONE)
        b.set_tooltip_text("Open deze map")
        b.connect("clicked", lambda *_: open_extern(map_))
        kop.pack_start(b, False, False, 0)
        box.pack_start(kop, False, False, 0)

        store = Gtk.ListStore(GdkPixbuf.Pixbuf, str, str)
        for p in fotos:
            try:
                pb = GdkPixbuf.Pixbuf.new_from_file_at_size(p, 96, 96)
                pb = pb.apply_embedded_orientation() or pb
            except Exception:
                continue
            store.append([pb, os.path.basename(p), p])
        view = Gtk.IconView(model=store)
        view.set_pixbuf_column(0)
        view.set_text_column(1)
        view.set_item_width(100)
        view.set_selection_mode(Gtk.SelectionMode.MULTIPLE)
        view.connect("item-activated", lambda v, pad: open_extern(store[pad][2]))
        # slepen naar browser/bestandsbeheer
        view.enable_model_drag_source(Gdk.ModifierType.BUTTON1_MASK, [], Gdk.DragAction.COPY)
        view.drag_source_add_uri_targets()

        def drag_data(v, ctx, data, info, tijd):
            paden = [store[p][2] for p in v.get_selected_items()]
            data.set_uris([GLib.filename_to_uri(p, None) for p in paden])
        view.connect("drag-data-get", drag_data)
        box.pack_start(view, False, False, 0)
        return box

    def _kopieer(self, widget, tekst):
        kl = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        kl.set_text(tekst or "", -1)
        kl.store()
        oud = widget.get_label()
        widget.set_label("✅ Gekopieerd")
        GLib.timeout_add(1200, lambda: (widget.set_label(oud), False)[1])
