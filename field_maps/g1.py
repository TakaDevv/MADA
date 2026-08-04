"""
Field map for Série G n°1 (2025) — Déclaration annuelle des revenus (IRG).

Measured the same way as g12.py / g50.py: pdfplumber word/box extraction on
static/forms/g1.pdf (portrait A4, 595.32 x 841.92 pt, 7 pages).

STATUS
------
Calibrated:
  - page index 0 : identification du contribuable, résidence (commune /
    wilaya / code postal), compte, téléphone/fax/email, situation
    familiale, conjoint, nombre d'enfants à charge, signature.
  - page index 5 : partie V (charges déductibles) + VI (résumé des
    revenus et charges — c'est la page qui porte le revenu net imposable
    final, donc la plus importante à avoir juste) + signature.

NOT calibrated yet (pages 1-4, index 1 to 4): les tableaux détaillés par
catégorie de revenu (bénéfices industriels/commerciaux, bénéfices non
commerciaux, revenus agricoles, revenus fonciers, plus-values sur valeurs
mobilières...). Le contribuable reporte de toute façon les TOTAUX de ces
catégories directement dans le résumé (page index 5, section VI) — c'est
donc la partie qui manque le moins pour un dépôt correct, mais le détail
ligne à ligne de chaque catégorie n'est pas encore stamped. Utilisez
tools/calibrate.py sur ces pages pour continuer, même méthode que pour
tout le reste de ce fichier.
"""
from pdf_engine import F

PAGE_H = 841.92  # A4 portrait, points


def _boxes(value, xs, y, size=8.5):
    out = []
    value = (value or "").strip()
    for ch, x in zip(value, xs):
        out.append(F(x=x + 1, y=y, text=ch, size=size, align="left"))
    return out


# -- boîtes chiffre-par-chiffre mesurées sur static/forms/g1.pdf, page 0 --
NIF_BOXES = [236.6, 245.5, 254.6, 263.5, 272.5, 281.5, 295.9, 304.8, 313.8,
             322.8, 331.7, 340.7, 349.7, 358.6, 367.6, 376.6, 385.5, 394.6,
             403.5, 412.5, 421.5, 430.5]
ARTICLE_BOXES = [332.1, 341.1, 350.1, 359.1, 368.1, 377.1, 386.1, 395.1,
                 404.1, 413.0, 421.9, 430.9]
NIN_BOXES = [270.6, 279.6, 288.6, 297.6, 306.6, 315.6, 324.6, 333.6, 342.6,
             351.6, 360.5, 369.4, 378.5, 387.4, 396.3, 405.3, 414.3, 423.3,
             432.3]
CP_RESIDENCE_BOXES = [129.0, 137.3, 145.6, 154.0, 162.3, 170.5]
CP_ANCIENNE_BOXES = [128.8, 137.1, 145.3, 153.7, 162.0, 170.3]
CONJOINT_NIF_BOXES = [229.8, 239.1, 248.2, 257.4, 266.5, 275.7, 291.1, 300.2,
                       309.4, 318.5, 327.6, 336.9, 346.0, 355.2, 364.3, 373.5,
                       382.7, 391.8, 401.0, 410.1, 419.4, 428.1]
CONJOINT_NIN_BOXES = [317.7, 326.7, 335.7, 344.7, 353.7, 362.7, 371.7, 380.6,
                       389.7, 398.6, 407.5, 416.6, 425.6, 434.6, 443.5, 452.4,
                       461.4, 470.4, 479.4]

# marques à cocher (situation familiale) : x mesuré juste à gauche du mot
# arabe correspondant (la case précède le libellé en lecture RTL)
SITUATION_MARK_X = {
    "celibataire": 526.9,
    "marie": 418.6,
    "veuf": 326.4,
    "divorce": 241.1,
}


def build_g1_fields(d: dict) -> dict:
    def y(bottom):
        return PAGE_H - bottom + 2

    page0 = [
        F(x=48,  y=y(322.5), text=d.get("nom_prenoms", ""), max_width=430),
        F(x=48,  y=y(335.2), text=d.get("date_lieu_naissance", ""), max_width=430),
        F(x=48,  y=y(347.8), text=d.get("profession", ""), max_width=430),
        F(x=48,  y=y(360.6), text=d.get("adresse_residence", ""), max_width=430),

        F(x=436, y=y(386.2), text=d.get("commune_residence", ""), max_width=124),
        F(x=250, y=y(386.2), text=d.get("wilaya_residence", ""), max_width=176),

        F(x=436, y=y(412.2), text=d.get("ancienne_commune", ""), max_width=124),
        F(x=247, y=y(412.2), text=d.get("ancienne_wilaya", ""), max_width=176),

        F(x=202, y=y(424.8), text=d.get("compte_bancaire", ""), max_width=290),
        F(x=36,  y=y(424.8), text=d.get("compte_postal", ""), max_width=126),

        F(x=45,  y=y(437.4), text=d.get("telephone", ""), max_width=104),
        F(x=205, y=y(437.4), text=d.get("email", ""), max_width=138),
        F(x=360, y=y(437.4), text=d.get("fax", ""), max_width=176),

        F(x=50,  y=y(525.1), text=d.get("conjoint_nom", ""), max_width=413),
        F(x=54,  y=y(554.5), text=d.get("conjoint_naissance", ""), max_width=408),

        F(x=48,  y=y(601.9), text=d.get("nb_enfants_charge", "")),

        F(x=245, y=y(696.4), text=d.get("lieu_date_signature", ""), max_width=108),
    ]
    page0 += _boxes(d.get("nif", ""), NIF_BOXES, y(139.7))
    page0 += _boxes(d.get("numero_article", ""), ARTICLE_BOXES, y(155.9))
    page0 += _boxes(d.get("nin", ""), NIN_BOXES, y(172.1))
    page0 += _boxes(d.get("code_postal_residence", ""), CP_RESIDENCE_BOXES, y(386.2), size=7)
    page0 += _boxes(d.get("ancien_code_postal", ""), CP_ANCIENNE_BOXES, y(412.2), size=7)
    page0 += _boxes(d.get("conjoint_nif", ""), CONJOINT_NIF_BOXES, y(570.9))
    page0 += _boxes(d.get("conjoint_nin", ""), CONJOINT_NIN_BOXES, y(585.0))

    situation = d.get("situation_familiale", "")
    if situation in SITUATION_MARK_X:
        page0.append(F(x=SITUATION_MARK_X[situation], y=y(510.4), text="X", size=9))

    # -- page index 5 : V. Charges déductibles + VI. Résumé --------------
    page5 = [
        F(x=131, y=y(326.1), text=d.get("revenus_fonciers_liberatoire", ""), max_width=98, align="left"),
        F(x=131, y=y(342.0), text=d.get("plus_values_cession", ""), max_width=98, align="left"),
        F(x=131, y=y(356.5), text=d.get("revenus_mobiliers_liberatoire", ""), max_width=98, align="left"),

        F(x=131, y=y(422.1), text=d.get("benefices_industriels_commerciaux", ""), max_width=104, align="left"),
        F(x=131, y=y(438.0), text=d.get("benefices_non_commerciaux", ""), max_width=104, align="left"),
        F(x=131, y=y(453.9), text=d.get("revenus_agricoles", ""), max_width=104, align="left"),
        F(x=131, y=y(469.7), text=d.get("revenus_fonciers_temporaires", ""), max_width=104, align="left"),
        F(x=131, y=y(485.6), text=d.get("revenus_mobiliers_credit_impot", ""), max_width=104, align="left"),
        F(x=131, y=y(501.4), text=d.get("salaires_traitements", ""), max_width=104, align="left"),
        F(x=131, y=y(517.4), text=d.get("revenus_etranger", ""), max_width=104, align="left"),
        F(x=128, y=y(543.7), text=d.get("total_revenus_integres", ""), max_width=104, align="left"),

        F(x=133, y=y(592.4), text=d.get("interets_credit_logement", ""), max_width=96, align="left"),
        F(x=132, y=y(608.2), text=d.get("autres_deductions", ""), max_width=96, align="left"),
        F(x=136, y=y(627.8), text=d.get("total_charges_deductibles", ""), max_width=96, align="left"),

        F(x=122, y=y(660.7), text=d.get("revenu_net_global", ""), max_width=110, align="left"),
        F(x=122, y=y(692.9), text=d.get("reduction_couple_10pct", ""), max_width=110, align="left"),
        F(x=122, y=y(716.4), text=d.get("revenu_net_imposable", ""), max_width=110, align="left"),

        F(x=398, y=y(742.9), text=d.get("lieu_date_signature_p6", ""), max_width=145),
    ]

    return {0: page0, 5: page5}
