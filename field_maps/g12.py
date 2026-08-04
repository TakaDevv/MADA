"""
Field map for Série G n°12 bis (2025) — Déclaration définitive IFU.

Every coordinate below was measured directly on
static/forms/g12.pdf using pdfplumber word/line extraction
(top-down y), then converted to PDF bottom-up y with:

    y = PAGE_HEIGHT - bottom_from_pdfplumber + 2

Only pages 0 and 1 (index) carry fillable fields — page 2 and 3 of the
official PDF are the printed "Rappel du régime" notice (AR + FR) and
contain no blanks, so nothing is drawn on them.

If you need to nudge anything, use tools/calibrate.py to render a grid
over the exact page and re-measure.
"""
from pdf_engine import F

PAGE_H = 841.92  # A4 portrait, points


def build_g12_fields(d: dict) -> dict:
    """
    d: dict of raw form values, keys documented inline below.
    Returns {page_index: [F, ...]} ready for pdf_engine.fill_pdf.
    """
    def y(bottom):
        return PAGE_H - bottom + 2

    page0 = [
        # -- en-tête administration --
        F(x=75,  y=y(67.7),  text=d.get("wilaya", "")),                 # DIW DE ...
        F(x=112, y=y(79.4),  text=d.get("structure", "")),              # Structure
        F(x=126, y=y(91.1),  text=d.get("recette_impots", "")),         # Recette des Impôts de
        F(x=99,  y=y(102.9), text=d.get("commune", "")),                # Commune de

        # -- titre : année concernée --
        F(x=508, y=y(180.1), text=d.get("annee", "")),                  # DE L'ANNEE :
        F(x=234, y=y(216.2), text=d.get("periode_du", "")),             # Période du
        F(x=350, y=y(216.2), text=d.get("periode_au", "")),             # au

        # -- I. Identification du contribuable (colonne française) --
        F(x=165, y=y(304.1), text=d.get("raison_sociale", ""), max_width=118),
        F(x=133, y=y(322.1), text=d.get("activite", ""), max_width=150),
        F(x=141, y=y(340.1), text=d.get("date_debut_activite", "")),
        F(x=113, y=y(357.1), text=d.get("activite_exoneree", "")),
        F(x=200, y=y(422.0), text=d.get("adresse_activite", ""), max_width=85),
        F(x=195, y=y(439.6), text=d.get("adresse_domicile", ""), max_width=95),
        F(x=196, y=y(457.1), text=d.get("nif", "")),
        F(x=204, y=y(474.5), text=d.get("nin", "")),
        F(x=167, y=y(492.0), text=d.get("numero_article", "")),
        F(x=132, y=y(509.5), text=d.get("telephone", "")),

        # -- II. Volet réservé aux salaires --
        F(x=118, y=y(555.4), text=d.get("nb_salaries", "")),
        F(x=207, y=y(573.4), text=d.get("salaires_bruts", ""), align="left"),
        F(x=199, y=y(591.5), text=d.get("charges_sociales", ""), align="left"),
        F(x=178, y=y(609.6), text=d.get("irg_annuel_acquitte", ""), align="left"),
    ]

    # -- III. Chiffre d'affaires / recettes définitifs (page index 1) --
    # Column x centers (left edge to start drawing, values right-padded
    # inside each cell so they never cross into the vertical rules):
    COL_IMP1 = 148    # Imposable (réalisé)
    COL_EXO1 = 198    # Exonéré (réalisé)
    COL_GLB1 = 253    # Global (réalisé)
    COL_IMP2 = 303    # Imposable (prévisionnel)
    COL_EXO2 = 361    # Exonéré (prévisionnel)
    COL_GLB2 = 418    # Global (prévisionnel)
    COL_CPL = 465     # Montant complémentaire (3)=(1)-(2)
    COL_IFU = 528     # IFU complémentaire (A)

    ROW_VENTE = y(131.4)      # Activités de production/vente de marchandises — 5%
    ROW_SERVICE = y(173.9)    # Prestations de services — 12%
    ROW_AUTOENT = y(218.4)    # Auto-entrepreneur — 0,5%
    ROW_TOTAL = y(256.8)

    def row(row_y, prefix):
        return [
            F(x=COL_IMP1, y=row_y, text=d.get(f"{prefix}_imp_realise", ""), max_width=45),
            F(x=COL_EXO1, y=row_y, text=d.get(f"{prefix}_exo_realise", ""), max_width=45),
            F(x=COL_GLB1, y=row_y, text=d.get(f"{prefix}_glb_realise", ""), max_width=45),
            F(x=COL_IMP2, y=row_y, text=d.get(f"{prefix}_imp_previsionnel", ""), max_width=45),
            F(x=COL_EXO2, y=row_y, text=d.get(f"{prefix}_exo_previsionnel", ""), max_width=45),
            F(x=COL_GLB2, y=row_y, text=d.get(f"{prefix}_glb_previsionnel", ""), max_width=45),
            F(x=COL_CPL,  y=row_y, text=d.get(f"{prefix}_complementaire", ""), max_width=45),
            F(x=COL_IFU,  y=row_y, text=d.get(f"{prefix}_ifu_complementaire", ""), max_width=45),
        ]

    page1 = []
    page1 += row(ROW_VENTE, "vente")
    page1 += row(ROW_SERVICE, "service")
    page1 += row(ROW_AUTOENT, "autoentrepreneur")
    page1 += row(ROW_TOTAL, "total")

    page1 += [
        F(x=240, y=y(475.2), text=d.get("revenu_net", "")),             # IV. Revenu net correspondant
        F(x=440, y=y(452.5), text=d.get("ifu_a_payer", "")),            # IFU A PAYER (A)+(B)

        # -- signature / lieu / date --
        F(x=82,  y=y(531.9), text=d.get("lieu_signature", "")),
        F(x=172, y=y(531.9), text=d.get("date_signature", "")),

        # -- paiement intégral de l'IFU --
        F(x=72,  y=y(659.8), text=d.get("lieu_paiement", "")),
        F(x=155, y=y(659.8), text=d.get("date_paiement", "")),
        F(x=80,  y=y(715.2), text=d.get("montant_ifu_chiffres", "")),
        F(x=76,  y=y(726.9), text=d.get("montant_ifu_lettres", "")),
        F(x=80,  y=y(738.4), text=d.get("quittance_numero", "")),
        F(x=175, y=y(738.4), text=d.get("quittance_date", "")),
    ]

    return {0: page0, 1: page1}
