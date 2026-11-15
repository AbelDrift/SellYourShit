"""Klein los voortgangsvenster, zodat het hoofdvenster overzichtelijk blijft."""
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib


class VoortgangsVenster(Gtk.Window):
    """Compact venster met titel, voortgangsbalk en statusregel. Alle methodes zijn veilig om
    vanuit een achtergrondthread aan te roepen (ze gaan via GLib.idle_add)."""

    def __init__(self, parent, titel, op_annuleren=None, onbepaald=False):
        super().__init__(title=titel)
        if parent is not None:
            self.set_transient_for(parent)
        self.set_default_size(380, 110)
        self.set_resizable(False)
        self.set_position(Gtk.WindowPosition.CENTER_ON_PARENT if parent else Gtk.WindowPosition.CENTER)
        self.set_keep_above(True)
        self.set_deletable(False)
        self._onbepaald = onbepaald
        self._timer = None
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_border_width(14)
        self.add(box)
        self.tekst = Gtk.Label(label="Bezig...")
        self.tekst.set_xalign(0)
        self.tekst.set_line_wrap(True)
        box.pack_start(self.tekst, False, False, 0)
        self.balk = Gtk.ProgressBar()
        box.pack_start(self.balk, False, False, 0)
        self.stop_knop = None
        if op_annuleren:
            self.stop_knop = Gtk.Button(label="Annuleren")
            self.stop_knop.connect("clicked", lambda *_: (op_annuleren(), self.stop_knop.set_sensitive(False)))
            box.pack_start(self.stop_knop, False, False, 0)
        self.show_all()
        if onbepaald:
            self._timer = GLib.timeout_add(120, self._puls)

    def _puls(self):
        self.balk.pulse()
        return True

    def zet(self, fractie=None, tekst=None):
        def doe():
            if tekst is not None:
                self.tekst.set_text(tekst)
            if fractie is not None and not self._onbepaald:
                self.balk.set_fraction(max(0.0, min(1.0, fractie)))
            return False
        GLib.idle_add(doe)

    def sluit(self):
        def doe():
            if self._timer:
                GLib.source_remove(self._timer)
                self._timer = None
            self.destroy()
            return False
        GLib.idle_add(doe)
