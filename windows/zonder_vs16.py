"""Haalt de emoji-variantkiezer (U+FE0F) uit de app-bestanden van de Windows-bouw.

Pango op Windows zoekt voor tekens met die kiezer (bijv. ⚙️ ⚠️ ✏️) de lettertypefamilie "emoji",
en die kent hij daar niet: je krijgt dan een vakje met een code. Zonder de kiezer tekent Windows
dezelfde tekens gewoon (met Segoe UI Symbol of Segoe UI Emoji). Op Linux blijft alles zoals het is.
Gebruik: python zonder_vs16.py <map van marktplaats_suite>
"""
import pathlib
import sys

aangepast = 0
for pad in pathlib.Path(sys.argv[1]).rglob("*.py"):
    tekst = pad.read_text(encoding="utf-8")
    if "️" in tekst:
        pad.write_text(tekst.replace("️", ""), encoding="utf-8")
        aangepast += 1
print(f"   emoji-variantkiezers weggehaald uit {aangepast} bestanden")
