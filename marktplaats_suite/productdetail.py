"""Productvenster: de advertentie 'in het rauw', alle gegevens, links, status en fotoversies.

Met ✏️ Bewerken pas je alles direct in dit venster aan (geen apart bewerkvenster meer).
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

# Tabblad Gegevens: (veld, label, soort)
GEGEVENS = [
    ("titel", "Titel", "titel"),
    ("categorie", "Categorie", "combo:categorie"),
    ("tijdsperiode", "Tijdsperiode", "combo:tijdsperiode"),
    ("conditie", "Staat", "keuze:conditie"),
    ("staat_details", "Staat-details", "tekst"),
    ("merk", "Merk", "tekst"),
    ("materiaal", "Materiaal", "tekst"),
    ("stijl", "Stijl", "tekst"),
    ("kleur", "Kleur", "tekst"),
    ("lengte", "Lengte (cm)", "getal"),
    ("breedte", "Breedte (cm)", "getal"),
    ("hoogte", "Hoogte (cm)", "getal"),
    ("gewicht", "Gewicht (kg)", "getal"),
    ("waarde_min", "Waarde min (€)", "getal"),
    ("waarde_max", "Waarde max (€)", "getal"),
    ("vraagprijs", "Vraagprijs (€)", "getal"),
    ("marktplaats_categorie", "Marktplaats-categorie", "tekst"),
    ("vinted_categorie", "Vinted-categorie", "tekst"),
    ("kanalen", "Kanalen", "kanalen"),
    ("extra_info_koper", "Extra info koper", "tekst"),
    ("opslaglocatie", "Opslaglocatie", "locatie"),
    ("sublocatie", "Sublocatie", "locatie"),
    ("rij", "Rij", "locatie"),
]

# Tabblad Overig: alle velden die nergens anders staan
OVERIG = [
    ("Online", [("online", "Online op Marktplaats", "janee"), ("online_whoppah", "Online op Whoppah", "janee"),
                ("online_vinted", "Online op Vinted", "janee")]),
    ("Verkoop", [("verkocht", "Verkocht", "janee"), ("verkoopprijs", "Verkoopprijs (€)", "getal"),
                 ("verkoopdatum", "Verkoopdatum", "tekst"), ("leverwijze", "Leverwijze", "tekst"),
                 ("track_trace", "Track & Trace", "tekst")]),
    ("Klant", [("klant_naam", "Naam", "tekst"), ("klant_telefoon", "Telefoon", "tekst"),
               ("klant_email", "E-mail", "tekst"), ("ophaal_afspraak", "Ophaalafspraak", "tekst")]),
    ("Reservering", [("gereserveerd", "Gereserveerd", "janee"), ("reserveprijs", "Reserveprijs (€)", "getal"),
                     ("reserveerdatum", "Reserveerdatum", "tekst"),
                     ("reservering_klant_naam", "Gereserveerd voor", "tekst")]),
    ("Registratie", [("aanmaakdatum", "Aanmaakdatum", "tekst"), ("aanmaaktijd", "Aanmaaktijd", "tekst"),
                     ("verwerkt_door", "Verwerkt door", "tekst"), ("toegewezen_aan", "Toegewezen aan", "tekst"),
                     ("folder_locatie", "Map", "alleen_lezen")]),
]
LINKS = [f"url_{i}" for i in range(1, 6)]
KANALEN = (("marktplaats", "Marktplaats"), ("whoppah", "Whoppah"), ("vinted", "Vinted"))


def _ja(waarde):
    return (waarde or "").strip().lower() == "ja"


def _scroll(kind):
    sw = Gtk.ScrolledWindow()
    sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    sw.add(kind)
    return sw


class ProductDetailVenster(Gtk.Window):
    def __init__(self, parent, product, productmap, omschrijving, op_bewerken=None, op_opslaan=None,
                 op_locatie=None, maak_tekst=None, keuzes=None, bewerken=False):
        super().__init__()
        if parent is not None:
            self.set_transient_for(parent)
        self.set_default_size(1000, 760)
        self.product = dict(product)
        self.productmap = productmap
        self.tekst = omschrijving or ""
        self.op_opslaan = op_opslaan        # functie(oud, nieuw); gooit een fout als opslaan mislukt
        self.op_locatie = op_locatie        # functie(venster, artikelnummer) voor 'Locatie wijzigen'
        self.maak_tekst = maak_tekst        # functie(product) -> advertentietekst
        self.keuzes = keuzes or {}
        self.bewerken = bool(bewerken and op_opslaan)
        self.widgets = {}
        self._pagina = 0
        self.connect("delete-event", self._sluiten_gevraagd)
        self.connect("key-press-event", self._toets)
        self._herbouw()

    # ------------------------------------------------------------------
    # opbouw
    # ------------------------------------------------------------------
    def _herbouw(self):
        if getattr(self, "notebook", None) is not None:
            self._pagina = self.notebook.get_current_page()
        kind = self.get_child()
        if kind is not None:
            self.remove(kind)
            kind.destroy()
        self.widgets = {}
        nr = self.product.get("artikelnummer", "")
        self.set_title(("✏️ " if self.bewerken else "") + f"{nr} · {self.product.get('titel', '')}")
        hoofd = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        hoofd.set_border_width(12)
        self.add(hoofd)
        hoofd.pack_start(self._kop(), False, False, 0)
        hoofd.pack_start(self._status(), False, False, 0)

        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        hoofd.pack_start(paned, True, True, 0)
        self.notebook = Gtk.Notebook()
        self.notebook.set_scrollable(True)
        paned.pack1(self.notebook, True, False)
        self.notebook.append_page(self._tab_advertentie(), Gtk.Label(label="Advertentie"))
        self.notebook.append_page(self._tab_gegevens(), Gtk.Label(label="Gegevens"))
        n_links = sum(1 for u in LINKS if (self.product.get(u) or "").strip())
        self.notebook.append_page(self._tab_links(), Gtk.Label(label=f"Links ({n_links})"))
        self.notebook.append_page(self._tab_overig(), Gtk.Label(label="Overig"))
        paned.pack2(self._fotos(), True, False)
        paned.set_position(500)

        hoofd.pack_start(self._onderrij(), False, False, 0)
        self.show_all()
        self.notebook.set_current_page(min(self._pagina, 3))

    def _kop(self):
        kop = Gtk.Box(spacing=8)
        nr = self.product.get("artikelnummer", "")
        titel = Gtk.Label()
        titel.set_markup(f"<span size='large'><b>{GLib.markup_escape_text(self.product.get('titel', ''))}</b></span>\n"
                         f"<small>{GLib.markup_escape_text(nr)}</small>")
        titel.set_xalign(0)
        titel.set_ellipsize(Pango.EllipsizeMode.END)
        kop.pack_start(titel, True, True, 0)
        if self.bewerken:
            l = Gtk.Label()
            l.set_markup("<span foreground='#e67e22'><b>✏️ Je bewerkt dit product</b></span>")
            kop.pack_start(l, False, False, 0)
        else:
            for tekst, waarde in (("Kopieer titel", self.product.get("titel", "")), ("Kopieer nummer", nr),
                                  ("Kopieer prijs", self.product.get("vraagprijs", ""))):
                b = Gtk.Button(label=tekst)
                b.connect("clicked", self._kopieer, waarde)
                kop.pack_start(b, False, False, 0)
        return kop

    def _status(self):
        status = Gtk.FlowBox()
        status.set_selection_mode(Gtk.SelectionMode.NONE)
        status.set_max_children_per_line(8)
        p = self.product
        kanalen = [k.strip() for k in (p.get("kanalen") or "marktplaats").split(",") if k.strip()]
        badges = []
        if _ja(p.get("verkocht")):
            badges.append(("💰 Verkocht" + (f" voor € {p['verkoopprijs']}" if p.get("verkoopprijs") else ""), "#c0392b"))
        if _ja(p.get("gereserveerd")):
            badges.append(("🔒 Gereserveerd", "#d35400"))
        for k, veld in (("marktplaats", "online"), ("whoppah", "online_whoppah"), ("vinted", "online_vinted")):
            if k in kanalen or _ja(p.get(veld)):
                aan = _ja(p.get(veld))
                badges.append((f"{'🟢' if aan else '⚪'} {k.capitalize()}: {'online' if aan else 'offline'}",
                               "#27ae60" if aan else "#7f8c8d"))
        for tekst, kleur in badges:
            l = Gtk.Label()
            l.set_markup(f"<span foreground='{kleur}'><b>{GLib.markup_escape_text(tekst)}</b></span>")
            status.add(l)
        return status

    def _onderrij(self):
        onder = Gtk.Box(spacing=6)
        map_ok = bool(self.productmap and os.path.isdir(self.productmap))
        b_map = Gtk.Button(label="📂 Open productmap")
        b_map.connect("clicked", lambda *_: map_ok and open_extern(self.productmap))
        b_map.set_sensitive(map_ok)
        onder.pack_start(b_map, False, False, 0)
        if self.bewerken:
            opslaan = Gtk.Button(label="💾 Opslaan")
            opslaan.get_style_context().add_class("suggested-action")
            opslaan.set_tooltip_text("Ctrl+S")
            opslaan.connect("clicked", lambda *_: self._opslaan())
            annuleer = Gtk.Button(label="Annuleren")
            annuleer.connect("clicked", lambda *_: self._stop_bewerken())
            onder.pack_end(opslaan, False, False, 0)
            onder.pack_end(annuleer, False, False, 0)
        else:
            if self.op_opslaan:
                b_bew = Gtk.Button(label="✏️ Bewerken")
                b_bew.connect("clicked", lambda *_: self.start_bewerken())
                onder.pack_start(b_bew, False, False, 0)
            sluit = Gtk.Button(label="Sluiten")
            sluit.connect("clicked", lambda *_: self.destroy())
            onder.pack_end(sluit, False, False, 0)
            self.set_focus(sluit)
        return onder

    # --- tabbladen ---
    def _tab_advertentie(self):
        adv = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        adv.set_border_width(6)
        tv = Gtk.TextView()
        tv.set_wrap_mode(Gtk.WrapMode.WORD)
        if self.bewerken:
            uitleg = Gtk.Label()
            uitleg.set_markup("<small>Omschrijving. De regels voor afmeting, staat, waarde en artikelnummer en de "
                              "algemene voorwaarden komen er bij het plaatsen automatisch bij.</small>")
            uitleg.set_xalign(0)
            uitleg.set_line_wrap(True)
            adv.pack_start(uitleg, False, False, 0)
            tv.get_buffer().set_text(self.product.get("omschrijving") or "")
            self.widgets["omschrijving"] = ("tekstvak", tv)
        else:
            tv.set_editable(False)
            tv.get_buffer().set_text(self.tekst)
        adv.pack_start(_scroll(tv), True, True, 0)
        if not self.bewerken:
            b = Gtk.Button(label="📋 Kopieer omschrijving")
            b.connect("clicked", self._kopieer, self.tekst)
            adv.pack_start(b, False, False, 0)
        return adv

    def _rij(self, grid, rij, label, kind):
        l = Gtk.Label(label=label, xalign=0)
        l.get_style_context().add_class("dim-label")
        l.set_valign(Gtk.Align.START if isinstance(kind, Gtk.ScrolledWindow) else Gtk.Align.CENTER)
        grid.attach(l, 0, rij, 1, 1)
        kind.set_hexpand(True)
        grid.attach(kind, 1, rij, 1, 1)

    def _waarde_label(self, waarde):
        w = Gtk.Label(xalign=0)
        if (waarde or "").strip():
            w.set_text(waarde)
        else:
            w.set_markup("<span foreground='#888888'>—</span>")
        w.set_selectable(True)
        w.set_line_wrap(True)
        return w

    def _invoer(self, veld, soort):
        """Bewerkbaar widget voor een veld; bewaart (soort, widget) in self.widgets."""
        waarde = self.product.get(veld) or ""
        if soort.startswith("combo:"):
            w = Gtk.ComboBoxText.new_with_entry()
            for optie in self.keuzes.get(soort.split(":", 1)[1], []):
                w.append_text(optie)
            w.get_child().set_text(waarde)
            self.widgets[veld] = ("combo", w)
            return w
        if soort.startswith("keuze:"):
            w = Gtk.ComboBoxText()
            opties = list(self.keuzes.get(soort.split(":", 1)[1], []))
            if waarde and waarde not in opties:
                opties.append(waarde)
            for optie in [""] + opties:
                w.append_text(optie)
            w.set_active(([""] + opties).index(waarde) if waarde in opties else 0)
            self.widgets[veld] = ("keuze", w)
            return w
        if soort == "kanalen":
            box = Gtk.Box(spacing=10)
            gekozen = [k.strip() for k in (waarde or "marktplaats").split(",") if k.strip()]
            checks = {}
            for sleutel, naam in KANALEN:
                c = Gtk.CheckButton(label=naam)
                c.set_active(sleutel in gekozen)
                checks[sleutel] = c
                box.pack_start(c, False, False, 0)
            self.widgets[veld] = ("kanalen", checks)
            return box
        if soort == "janee":
            w = Gtk.CheckButton(label="ja")
            w.set_active(_ja(waarde))
            self.widgets[veld] = ("janee", w)
            return w
        if soort == "titel":
            box = Gtk.Box(spacing=6)
            e = Gtk.Entry()
            e.set_text(waarde)
            teller = Gtk.Label()

            def tel(*_):
                n = len(e.get_text())
                teller.set_markup(f"<small>{n}/60</small>" if n <= 60 else f"<small><span foreground='red'>{n}/60</span></small>")
            e.connect("changed", tel)
            tel()
            box.pack_start(e, True, True, 0)
            box.pack_start(teller, False, False, 0)
            self.widgets[veld] = ("tekst", e)
            return box
        if soort == "tekstvak":
            tv = Gtk.TextView()
            tv.set_wrap_mode(Gtk.WrapMode.WORD)
            tv.get_buffer().set_text(waarde)
            sw = _scroll(tv)
            sw.set_min_content_height(120)
            self.widgets[veld] = ("tekstvak", tv)
            return sw
        e = Gtk.Entry()
        e.set_text(waarde)
        if soort == "getal":
            e.set_width_chars(10)
            e.set_hexpand(False)
        self.widgets[veld] = ("tekst", e)
        return e

    def _tab_gegevens(self):
        grid = Gtk.Grid(column_spacing=12, row_spacing=5)
        grid.set_border_width(8)
        rij = 0
        locatie_knop_gezet = False
        for veld, label, soort in GEGEVENS:
            if self.bewerken and soort != "locatie":
                kind = self._invoer(veld, soort)
            elif soort == "kanalen":
                kind = self._waarde_label(", ".join(n for k, n in KANALEN
                                                    if k in (self.product.get(veld) or "marktplaats")))
            else:
                kind = self._waarde_label(self.product.get(veld))
            if self.bewerken and soort == "locatie" and not locatie_knop_gezet and self.op_locatie:
                box = Gtk.Box(spacing=8)
                box.pack_start(kind, True, True, 0)
                b = Gtk.Button(label="📍 Locatie wijzigen…")
                b.set_tooltip_text("Verandert ook het artikelnummer, de map en de barcode")
                b.connect("clicked", lambda *_: self.op_locatie(self, self.product.get("artikelnummer", "")))
                box.pack_start(b, False, False, 0)
                kind = box
                locatie_knop_gezet = True
            self._rij(grid, rij, label, kind)
            rij += 1
        try:
            from marktplaats_suite.verzending import advies
            adv = advies(self.product.get("lengte"), self.product.get("breedte"),
                         self.product.get("hoogte"), self.product.get("gewicht"))
        except Exception:
            adv = None
        if not self.bewerken:
            from marktplaats_suite.verzending import advies_regel
            bewaard = (self.product.get("verzendadvies") or "").strip()
            nu = advies_regel(adv) if adv else ""
            if bewaard:
                self._rij(grid, rij, "Verzendadvies\n(bij registratie)", self._waarde_label(bewaard))
                rij += 1
            if nu and nu != bewaard:
                self._rij(grid, rij, "Verzendadvies nu", self._waarde_label(nu))
        return _scroll(grid)

    def _tab_links(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_border_width(8)
        if self.bewerken:
            grid = Gtk.Grid(column_spacing=12, row_spacing=5)
            for i, veld in enumerate(LINKS):
                e = self._invoer(veld, "tekst")
                e.set_placeholder_text("https://www.marktplaats.nl/v/...")
                self._rij(grid, i, f"Link {i + 1}", e)
            box.pack_start(grid, False, False, 0)
            return box
        urls = [(self.product.get(u) or "").strip() for u in LINKS]
        urls = [u for u in urls if u]
        if urls:
            for u in urls:
                lb = Gtk.LinkButton.new_with_label(u, u)
                lb.set_halign(Gtk.Align.START)
                lb.connect("activate-link", lambda w: (open_extern(w.get_uri()), True)[1])
                box.pack_start(lb, False, False, 0)
        else:
            box.pack_start(Gtk.Label(label="Nog geen links naar platforms.", xalign=0), False, False, 0)
        return box

    def _tab_overig(self):
        grid = Gtk.Grid(column_spacing=12, row_spacing=5)
        grid.set_border_width(8)
        rij = 0
        for kop, velden in OVERIG:
            k = Gtk.Label(xalign=0)
            k.set_markup(f"<b>{kop}</b>")
            k.set_margin_top(6 if rij else 0)
            grid.attach(k, 0, rij, 2, 1)
            rij += 1
            for veld, label, soort in velden:
                if self.bewerken and soort != "alleen_lezen":
                    kind = self._invoer(veld, soort)
                else:
                    waarde = self.product.get(veld) or ""
                    if soort == "janee":
                        waarde = "ja" if _ja(waarde) else ("nee" if waarde else "")
                    kind = self._waarde_label(waarde)
                self._rij(grid, rij, label, kind)
                rij += 1
        k = Gtk.Label(xalign=0)
        k.set_markup("<b>Algemene voorwaarden voor dit product</b> <small>(leeg = de algemene)</small>")
        k.set_margin_top(6)
        grid.attach(k, 0, rij, 2, 1)
        rij += 1
        if self.bewerken:
            grid.attach(self._invoer("algemene_voorwaarden", "tekstvak"), 0, rij, 2, 1)
        else:
            grid.attach(self._waarde_label(self.product.get("algemene_voorwaarden")), 0, rij, 2, 1)
        return _scroll(grid)

    # --- foto's ---
    def _fotos(self):
        fotos_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        fotos_box.set_border_width(4)
        hint = Gtk.Label()
        hint.set_markup("<small>Sleep foto's naar een uploadveld in je browser · dubbelklik = openen</small>")
        hint.set_xalign(0)
        fotos_box.pack_start(hint, False, False, 0)
        lijst = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        fotos_box.pack_start(_scroll(lijst), True, True, 0)
        gevonden = 0
        for sub, naam in VERSIES:
            fotos = lijst_fotos(os.path.join(self.productmap, sub)) if self.productmap else []
            if not fotos:
                continue
            gevonden += 1
            lijst.pack_start(self._fotosectie(naam, os.path.join(self.productmap, sub), fotos), False, False, 0)
        if not gevonden:
            lijst.pack_start(Gtk.Label(label="Geen foto's gevonden in de productmap.", xalign=0), False, False, 0)
        return fotos_box

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

    # ------------------------------------------------------------------
    # bewerken
    # ------------------------------------------------------------------
    def start_bewerken(self):
        if self.op_opslaan:
            self.bewerken = True
            self._herbouw()

    def _stop_bewerken(self):
        self.bewerken = False
        self._herbouw()

    def _verzamel(self):
        """Nieuwe waarden uit de invoervelden (alleen wat echt veranderd is, de rest blijft precies gelijk)."""
        nieuw = dict(self.product)
        for veld, (soort, w) in self.widgets.items():
            oud = self.product.get(veld) or ""
            if soort == "tekst":
                waarde = w.get_text().strip()
            elif soort == "combo":
                waarde = w.get_child().get_text().strip()
            elif soort == "keuze":
                waarde = w.get_active_text() or ""
            elif soort == "tekstvak":
                buf = w.get_buffer()
                waarde = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), True).strip()
            elif soort == "janee":
                if w.get_active() == _ja(oud):
                    continue           # niet aangeraakt: '' blijft '' (geen onnodige 'nee')
                waarde = "ja" if w.get_active() else "nee"
            elif soort == "kanalen":
                waarde = ",".join(k for k, _ in KANALEN if w[k].get_active())
                oud_lijst = [k.strip() for k in (oud or "marktplaats").split(",") if k.strip()]
                if waarde == ",".join(k for k, _ in KANALEN if k in oud_lijst):
                    continue
            else:
                continue
            if waarde != oud.strip():
                nieuw[veld] = waarde
        return nieuw

    def _gewijzigd(self):
        return self.bewerken and self._verzamel() != self.product

    def _opslaan(self):
        nieuw = self._verzamel()
        if len(nieuw.get("titel", "")) > 60:
            self._melding("De titel is langer dan 60 tekens. Maak hem korter.", Gtk.MessageType.WARNING)
            return False
        if not nieuw.get("titel", "").strip():
            self._melding("De titel mag niet leeg zijn.", Gtk.MessageType.WARNING)
            return False
        if nieuw != self.product:
            try:
                self.op_opslaan(dict(self.product), nieuw)
            except Exception as e:
                self._melding(f"Opslaan mislukt: {e}", Gtk.MessageType.ERROR)
                return False
            self.product = nieuw
            if self.maak_tekst:
                try:
                    self.tekst = self.maak_tekst(nieuw)
                except Exception:
                    pass
        self.bewerken = False
        self._herbouw()
        return True

    def _melding(self, tekst, soort=Gtk.MessageType.INFO):
        d = Gtk.MessageDialog(transient_for=self, flags=0, message_type=soort, buttons=Gtk.ButtonsType.OK, text=tekst)
        d.run()
        d.destroy()

    def _sluiten_gevraagd(self, *_):
        if not self._gewijzigd():
            return False
        d = Gtk.MessageDialog(transient_for=self, flags=0, message_type=Gtk.MessageType.QUESTION,
                              buttons=Gtk.ButtonsType.NONE, text="Wijzigingen opslaan?")
        d.add_buttons("Niet opslaan", Gtk.ResponseType.NO, "Annuleren", Gtk.ResponseType.CANCEL,
                      "Opslaan", Gtk.ResponseType.YES)
        r = d.run()
        d.destroy()
        if r == Gtk.ResponseType.YES:
            return not self._opslaan()      # dicht als opslaan lukt
        return r != Gtk.ResponseType.NO     # Niet opslaan = sluiten, Annuleren = open laten

    def _toets(self, w, event):
        ctrl = event.state & Gdk.ModifierType.CONTROL_MASK
        if self.bewerken and ctrl and event.keyval in (Gdk.KEY_s, Gdk.KEY_S):
            self._opslaan()
            return True
        return False

    def _kopieer(self, widget, tekst):
        kl = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        kl.set_text(tekst or "", -1)
        kl.store()
        oud = widget.get_label()
        widget.set_label("✅ Gekopieerd")
        GLib.timeout_add(1200, lambda: (widget.set_label(oud), False)[1])
