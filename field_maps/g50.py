"""
Field map for Série G n°50 (2025) — Bordereau-avis de versement.

Measured the same way as g12.py: pdfplumber word-extraction on
static/forms/g50.pdf (landscape A4, 842.52 x 596.04 pt).

STATUS
------
Page 0 (page index 0) is FULLY calibrated for:
  - header identification block (Mois/Année, Commune, Nom/raison sociale,
    Profession/Activité, Adresse, NIN, NIF, Article d'imposition)
  - Bloc 1: IBS/ICBS - Acompte/Solde de liquidation (code E1M10 + 3 lines)
  - Bloc 4: IRG/Traitements et salaires (E1L20 Barème line)

Pages 1-5 (TLS, timbre, TVA, récapitulation, rappels) are NOT yet
calibrated — the last page is pure notice text with no fields, but
pages 1-4 do have blanks that still need coordinates. Use
tools/calibrate.py on static/forms/g50.pdf to finish them with the same
technique used here (render page -> pdfplumber word/line extraction ->
convert top/bottom to bottom-up y). This is intentionally left as the
next increment rather than guessed, since misplaced text on a real form
that gets filed with the DGI is worse than an honest gap.
"""
from pdf_engine import F

PAGE_H = 596.04  # landscape A4, points


def _digits_in_boxes(value: str, box_x0s: list, y: float, size: float = 8.5):
    """Places one character per pre-measured box (NIN / NIF / Article)."""
    out = []
    value = (value or "").strip()
    for ch, x in zip(value, box_x0s):
        out.append(F(x=x + 1, y=y, text=ch, size=size, align="left"))
    return out


NIN_BOXES = [39.4, 48.0, 56.6, 65.2, 73.8, 82.5, 91.0, 99.6, 108.3, 116.8,
             125.4, 133.9, 142.6, 151.2, 159.9, 168.4, 177.0, 185.5, 194.2]
NIF_BOXES = [40.1, 48.1, 56.2, 64.2, 72.3, 80.3, 88.3, 96.4, 104.4, 112.6,
             120.6, 128.7, 136.7, 144.9, 152.9, 160.9, 169.0, 177.1, 185.2, 193.2]
ARTICLE_BOXES = [102.1, 108.6, 115.1, 121.6, 130.2, 136.7, 143.1, 151.7,
                 160.3, 166.8, 175.3, 184.0]


def build_g50_fields(d: dict) -> dict:
    def y(bottom):
        return PAGE_H - bottom + 2

    page0 = [
        F(x=222, y=y(62.0),  text=d.get("mois", "")),                # Mois de
        F(x=209, y=y(79.2),  text=d.get("annee", "")),                # Année
        F(x=83,  y=y(131.0), text=d.get("commune", "")),              # COMMUNE DE
        F(x=323, y=y(124.1), text=d.get("raison_sociale", ""), max_width=175),  # M :
        F(x=386, y=y(152.4), text=d.get("profession_activite", ""), max_width=178),
        F(x=357, y=y(166.1), text=d.get("adresse", ""), max_width=260),
    ]
    page0 += _digits_in_boxes(d.get("nin", ""), NIN_BOXES, y(154.2))
    page0 += _digits_in_boxes(d.get("nif", ""), NIF_BOXES, y(172.7))
    page0 += _digits_in_boxes(d.get("numero_article", ""), ARTICLE_BOXES, y(191.2))

    # Bloc 1 - IBS/ICBS : Acompte / Solde de liquidation
    page0 += [
        F(x=690, y=y(236.5), text=d.get("ibs_acompte_provisionnel", ""), align="left"),
        F(x=690, y=y(250.1), text=d.get("ibs_solde_liquidation", ""), align="left"),
        F(x=690, y=y(263.7), text=d.get("icbs_acompte_provisionnel", ""), align="left"),
        F(x=690, y=y(277.3), text=d.get("icbs_solde_liquidation", ""), align="left"),
        F(x=655, y=y(290.8), text=d.get("bloc1_total", ""), align="left"),  # TOTAL (1)
    ]

    # Bloc 4 - IRG / Traitements, salaires, pensions et rentes viagères (E1L20)
    page0 += [
        F(x=690, y=y(491.0), text=d.get("irg_traitements_salaires", ""), align="left"),
    ]

    return {0: page0}
