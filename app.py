import os
import json
import sqlite3
from datetime import datetime, date
from io import StringIO
import csv
from io import StringIO, BytesIO
from flask import send_file
from pdf_engine import fill_pdf
from field_maps.g50 import build_g50_fields
from field_maps.g1 import build_g1_fields

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, Response, g
)
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "mada.db")

app = Flask(__name__)
app.secret_key = "mada-dev-secret-key-change-in-production"

CATEGORIES_RECETTE = ["Vente de produit", "Prestation de service", "Autre recette"]
CATEGORIES_DEPENSE = ["Achat matériel", "Loyer", "Salaires", "Transport", "Marketing", "Autre dépense"]
STATUTS_DECLARATION = ["en attente", "payée", "en retard"]
SITUATIONS_FAMILIALES = ["celibataire", "marie", "veuf", "divorce"]
# ---------------------------------------------------------------------------
# Modèle des déclarations fiscales
# ---------------------------------------------------------------------------
# On distingue deux administrations :
#   - "DGI"    : déclarations fiscales (G50 mensuel, G1 annuel IRG)
#   - "CASNOS" : cotisation sociale des non-salariés (bordereau de
#                versement propre à la caisse, ce n'est PAS un formulaire
#                DGI et ne doit donc pas être assimilé au G12 ni à aucun
#                autre imprimé fiscal).
DECLARATIONS_DGI = {
    "G50": "G50 — Déclaration mensuelle (TVA / IRG / TAP / IBS)",
    "G1": "G1 — Déclaration annuelle des revenus (IRG)",
}

FORM_PDF_PATHS = {
    "G50": os.path.join(BASE_DIR, "static", "forms", "g50.pdf"),
    "G1": os.path.join(BASE_DIR, "static", "forms", "g1.pdf"),
}
FORM_BUILDERS = {
    "G50": build_g50_fields,
    "G1": build_g1_fields,
}
TYPES_DECLARATION = list(DECLARATIONS_DGI.keys()) + ["CASNOS"]

# Taux indicatif de la Taxe sur l'Activité Professionnelle. Le taux réel
# dépend de l'activité et de la loi de finances en vigueur ; il reste
# modifiable au cas par cas dans le formulaire.
TAUX_TAP_DEFAUT = 2.0

# Barème progressif indicatif de l'IRG (impôt par tranches annuelles).
# Ces tranches sont fournies à titre indicatif pour donner un ordre de
# grandeur réaliste et NE remplacent PAS les textes officiels de la DGI,
# qui doivent être vérifiés/actualisés chaque année.
BAREME_IRG = [
    (240_000, 0.00),
    (480_000, 0.23),
    (960_000, 0.27),
    (1_920_000, 0.30),
    (3_840_000, 0.33),
    (float("inf"), 0.35),
]

NATURES_VERSEMENT_CASNOS = [
    "Cotisation trimestrielle",
    "Régularisation annuelle",
    "Autre versement",
]
MODES_PAIEMENT = ["especes", "cheque", "virement"]
SITUATIONS_FAMILIALES = ["celibataire", "marie", "marie_enfants"]


# ---------------------------------------------------------------------------
# Base de données
# ---------------------------------------------------------------------------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DB_PATH)
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS user (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nom TEXT NOT NULL,
            entreprise TEXT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            date_creation TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS operation (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            type TEXT NOT NULL CHECK(type IN ('recette','depense')),
            categorie TEXT NOT NULL,
            montant REAL NOT NULL,
            description TEXT,
            date_operation TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES user(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS declaration (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            type TEXT NOT NULL,
            formulaire TEXT NOT NULL DEFAULT '',
            periode TEXT NOT NULL,
            montant REAL NOT NULL DEFAULT 0,
            statut TEXT NOT NULL DEFAULT 'en attente',
            date_echeance TEXT NOT NULL,
            nif TEXT,
            raison_sociale TEXT,
            adresse TEXT,
            numero_article TEXT,
            details TEXT,
            FOREIGN KEY (user_id) REFERENCES user(id) ON DELETE CASCADE
        );
        """
    )
    db.commit()

    _migrer_schema_declaration(db)
    db.close()


def _migrer_schema_declaration(db):
    """Ajoute les colonnes manquantes et met à jour les anciennes déclarations
    (créées avant l'introduction du modèle G50 / G1 / CASNOS) sans perdre de
    données.
    """
    existing_cols = {row[1] for row in db.execute("PRAGMA table_info(declaration)")}
    new_cols = {
        "formulaire": "TEXT NOT NULL DEFAULT ''",
        "administration": "TEXT NOT NULL DEFAULT 'DGI'",
        "nif": "TEXT",
        "raison_sociale": "TEXT",
        "adresse": "TEXT",
        "numero_article": "TEXT",
        "details": "TEXT",
    }
    for col, coltype in new_cols.items():
        if col not in existing_cols:
            db.execute(f"ALTER TABLE declaration ADD COLUMN {col} {coltype}")
    db.commit()

    # Compatibilité ascendante : les anciennes déclarations utilisaient les
    # libellés "TVA" / "IRG" / "CASNOS" comme valeur de `type`, avec CASNOS
    # associé (à tort) au formulaire "G12". On aligne les données existantes
    # sur le nouveau modèle sans les supprimer.
    db.execute("UPDATE declaration SET type='G50', formulaire='G50' "
               "WHERE type='TVA'")
    db.execute("UPDATE declaration SET type='G1', formulaire='G1' "
               "WHERE type='IRG'")
    db.execute("UPDATE declaration SET administration='CASNOS', formulaire='' "
               "WHERE type='CASNOS'")
    db.commit()


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------
def login_required(view):
    from functools import wraps

    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            flash("Veuillez vous connecter pour accéder à cette page.", "error")
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped


def current_user():
    if "user_id" not in session:
        return None
    db = get_db()
    return db.execute("SELECT * FROM user WHERE id = ?", (session["user_id"],)).fetchone()


@app.context_processor
def inject_user():
    return {"current_user": current_user()}


# ---------------------------------------------------------------------------
# Routes - Auth
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        nom = request.form.get("nom", "").strip()
        entreprise = request.form.get("entreprise", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")

        errors = []
        if not nom or not email or not password:
            errors.append("Tous les champs obligatoires doivent être remplis.")
        if password != confirm:
            errors.append("Les mots de passe ne correspondent pas.")
        if len(password) < 6:
            errors.append("Le mot de passe doit contenir au moins 6 caractères.")

        db = get_db()
        if not errors:
            existing = db.execute("SELECT id FROM user WHERE email = ?", (email,)).fetchone()
            if existing:
                errors.append("Un compte existe déjà avec cet email.")

        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("register.html", nom=nom, entreprise=entreprise, email=email)

        db.execute(
            "INSERT INTO user (nom, entreprise, email, password_hash, date_creation) VALUES (?, ?, ?, ?, ?)",
            (nom, entreprise, email, generate_password_hash(password), datetime.now().isoformat()),
        )
        db.commit()
        flash("Compte créé avec succès. Vous pouvez vous connecter.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        db = get_db()
        user = db.execute("SELECT * FROM user WHERE email = ?", (email,)).fetchone()

        if user is None or not check_password_hash(user["password_hash"], password):
            flash("Email ou mot de passe incorrect.", "error")
            return render_template("login.html", email=email)

        session.clear()
        session["user_id"] = user["id"]
        flash(f"Bienvenue, {user['nom']} !", "success")
        return redirect(url_for("dashboard"))

    return render_template("login.html")


@app.route("/logout", methods=["GET", "POST"])
def logout():
    session.clear()
    flash("Vous avez été déconnecté.", "success")
    return redirect(url_for("index"))


# ---------------------------------------------------------------------------
# Routes - Dashboard
# ---------------------------------------------------------------------------
@app.route("/dashboard")
@login_required
def dashboard():
    db = get_db()
    uid = session["user_id"]

    total_recettes = db.execute(
        "SELECT COALESCE(SUM(montant),0) s FROM operation WHERE user_id=? AND type='recette'", (uid,)
    ).fetchone()["s"]
    total_depenses = db.execute(
        "SELECT COALESCE(SUM(montant),0) s FROM operation WHERE user_id=? AND type='depense'", (uid,)
    ).fetchone()["s"]
    solde = total_recettes - total_depenses

    dernieres_operations = db.execute(
        "SELECT * FROM operation WHERE user_id=? ORDER BY date_operation DESC, id DESC LIMIT 6", (uid,)
    ).fetchall()

    depenses_par_categorie = db.execute(
        """SELECT categorie, COALESCE(SUM(montant),0) total FROM operation
           WHERE user_id=? AND type='depense' GROUP BY categorie ORDER BY total DESC""",
        (uid,),
    ).fetchall()

    evolution = db.execute(
        """SELECT substr(date_operation,1,7) mois,
                  SUM(CASE WHEN type='recette' THEN montant ELSE 0 END) recettes,
                  SUM(CASE WHEN type='depense' THEN montant ELSE 0 END) depenses
           FROM operation WHERE user_id=?
           GROUP BY mois ORDER BY mois DESC LIMIT 6""",
        (uid,),
    ).fetchall()
    evolution = list(reversed(evolution))

    prochaines_declarations = db.execute(
        """SELECT * FROM declaration WHERE user_id=? AND statut != 'payée'
           ORDER BY date_echeance ASC LIMIT 4""",
        (uid,),
    ).fetchall()

    nb_declarations_retard = db.execute(
        "SELECT COUNT(*) c FROM declaration WHERE user_id=? AND statut='en retard'", (uid,)
    ).fetchone()["c"]

    return render_template(
        "dashboard.html",
        total_recettes=total_recettes,
        total_depenses=total_depenses,
        solde=solde,
        dernieres_operations=dernieres_operations,
        depenses_par_categorie=depenses_par_categorie,
        evolution=evolution,
        prochaines_declarations=prochaines_declarations,
        nb_declarations_retard=nb_declarations_retard,
    )


# ---------------------------------------------------------------------------
# Routes - Opérations (recettes / dépenses)
# ---------------------------------------------------------------------------
@app.route("/operations", methods=["GET", "POST"])
@login_required
def operations():
    db = get_db()
    uid = session["user_id"]

    if request.method == "POST":
        type_op = request.form.get("type")
        categorie = request.form.get("categorie", "").strip()
        montant = request.form.get("montant", "0").replace(",", ".")
        description = request.form.get("description", "").strip()
        date_operation = request.form.get("date_operation") or date.today().isoformat()

        try:
            montant_val = float(montant)
            if montant_val <= 0:
                raise ValueError
        except ValueError:
            flash("Le montant doit être un nombre positif.", "error")
            return redirect(url_for("operations"))

        if type_op not in ("recette", "depense") or not categorie:
            flash("Formulaire invalide.", "error")
            return redirect(url_for("operations"))

        db.execute(
            """INSERT INTO operation (user_id, type, categorie, montant, description, date_operation)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (uid, type_op, categorie, montant_val, description, date_operation),
        )
        db.commit()
        flash("Opération enregistrée.", "success")
        return redirect(url_for("operations"))

    filtre_type = request.args.get("type", "")
    query = "SELECT * FROM operation WHERE user_id=?"
    params = [uid]
    if filtre_type in ("recette", "depense"):
        query += " AND type=?"
        params.append(filtre_type)
    query += " ORDER BY date_operation DESC, id DESC"

    liste_operations = db.execute(query, params).fetchall()

    return render_template(
        "operations.html",
        operations=liste_operations,
        filtre_type=filtre_type,
        categories_recette=CATEGORIES_RECETTE,
        categories_depense=CATEGORIES_DEPENSE,
        today=date.today().isoformat(),
    )


@app.route("/operations/<int:op_id>/delete", methods=["POST"])
@login_required
def delete_operation(op_id):
    db = get_db()
    db.execute("DELETE FROM operation WHERE id=? AND user_id=?", (op_id, session["user_id"]))
    db.commit()
    flash("Opération supprimée.", "success")
    return redirect(url_for("operations"))


# ---------------------------------------------------------------------------
# Déclarations fiscales - helpers de calcul
# ---------------------------------------------------------------------------
def calculer_irg_progressif(revenu_imposable):
    """Calcule l'IRG dû selon un barème progressif par tranches (indicatif,
    voir BAREME_IRG). Fourni à titre d'ordre de grandeur, pas comme valeur
    officielle.
    """
    impot = 0.0
    borne_precedente = 0
    for borne, taux in BAREME_IRG:
        tranche = max(0.0, min(revenu_imposable, borne) - borne_precedente)
        impot += tranche * taux
        if revenu_imposable <= borne:
            break
        borne_precedente = borne
    return round(impot, 2)


def calculer_g50(donnees):
    """Calcule la TVA nette, la TAP et le total à payer pour une
    déclaration G50, à partir des montants saisis par l'utilisateur.
    """
    tva_nette = round(donnees["tva_collectee"] - donnees["tva_deductible"], 2)
    tva_a_payer = tva_nette if tva_nette > 0 else 0.0
    credit_tva = -tva_nette if tva_nette < 0 else 0.0

    tap_montant = round(donnees["tap_base"] * donnees["taux_tap"] / 100, 2)

    total = round(tva_a_payer + donnees["irg_retenue"] + tap_montant + donnees["acompte_ibs"], 2)

    resultats = dict(donnees)
    resultats.update(
        tva_nette=tva_nette,
        tva_a_payer=tva_a_payer,
        credit_tva=credit_tva,
        tva_due=tva_nette > 0,
        tap_montant=tap_montant,
        total=total,
    )
    return resultats


def calculer_g1(donnees):
    """Calcule le revenu net imposable et l'IRG dû pour une déclaration
    annuelle G1, à partir des catégories de revenus intégrées au revenu
    global (les revenus soumis au prélèvement libératoire ne rentrent
    pas dans ce calcul — voir le commentaire dans lire_champs_g1).
    """
    categories_integrees = [
        "benefices_industriels_commerciaux",
        "benefices_non_commerciaux",
        "revenus_agricoles",
        "revenus_fonciers_temporaires",
        "revenus_mobiliers_credit_impot",
        "salaires_traitements",
        "revenus_etranger",
    ]
    total_revenus_integres = round(sum(donnees[c] for c in categories_integrees), 2)

    total_charges_deductibles = round(
        donnees["interets_credit_logement"] + donnees["autres_deductions"], 2
    )

    revenu_net_global = round(max(total_revenus_integres - total_charges_deductibles, 0.0), 2)

    # Réduction de 10% (imposition commune des époux) — indicatif, comme
    # BAREME_IRG plus haut : à vérifier contre le texte en vigueur.
    reduction_couple_10pct = (
        round(revenu_net_global * 0.10, 2) if donnees["situation_familiale"] == "marie" else 0.0
    )

    revenu_net_imposable = round(max(revenu_net_global - reduction_couple_10pct, 0.0), 2)
    irg_du = calculer_irg_progressif(revenu_net_imposable)

    resultats = dict(donnees)
    resultats.update(
        total_revenus_integres=total_revenus_integres,
        total_charges_deductibles=total_charges_deductibles,
        revenu_net_global=revenu_net_global,
        reduction_couple_10pct=reduction_couple_10pct,
        revenu_net_imposable=revenu_net_imposable,
        irg_du=irg_du,
        total=irg_du,
    )
    return resultats

def calculer_casnos(donnees):
    """Le bordereau CASNOS n'a pas de calcul dérivé : le montant à verser
    est saisi directement par le cotisant. On le renvoie tel quel pour
    conserver une interface homogène avec les autres helpers.
    """
    resultats = dict(donnees)
    resultats["total"] = donnees["montant_versement"]
    return resultats


# ---------------------------------------------------------------------------
# Déclarations fiscales - helpers de lecture / validation du formulaire
# ---------------------------------------------------------------------------
def to_float(form, name, default=0.0):
    """Convertit un champ du formulaire en float. Renvoie None si la valeur
    saisie n'est pas un nombre valide (à distinguer d'un champ vide, qui
    reçoit `default`).
    """
    valeur_brute = form.get(name, "")
    valeur_brute = valeur_brute.strip().replace(",", ".") if valeur_brute else ""
    if not valeur_brute:
        return default
    try:
        return float(valeur_brute)
    except ValueError:
        return None


def valider_infos_contribuable(nif, raison_sociale, adresse):
    erreurs = []
    if not nif or len(nif) != 15 or not nif.isdigit():
        erreurs.append("Le NIF doit contenir exactement 15 chiffres.")
    if not raison_sociale:
        erreurs.append("Le nom / raison sociale est obligatoire.")
    if not adresse:
        erreurs.append("L'adresse fiscale est obligatoire.")
    return erreurs


def valider_montants(donnees, champs, erreurs):
    """Vérifie que chaque champ monétaire de `champs` est un nombre valide
    et non négatif.
    """
    for champ in champs:
        valeur = donnees.get(champ)
        if valeur is None:
            erreurs.append(f"Le champ « {champ} » doit être un nombre valide.")
        elif valeur < 0:
            erreurs.append(f"Le champ « {champ} » ne peut pas être négatif.")


def lire_champs_g50(form):
    return {
        "ca_imposable": to_float(form, "ca_imposable"),
        "tva_collectee": to_float(form, "tva_collectee"),
        "tva_deductible": to_float(form, "tva_deductible"),
        "irg_retenue": to_float(form, "irg_retenue"),
        "tap_base": to_float(form, "tap_base"),
        "taux_tap": to_float(form, "taux_tap", default=TAUX_TAP_DEFAUT),
        "acompte_ibs": to_float(form, "acompte_ibs"),
    }


def lire_champs_g1(form):
    try:
        nb_enfants_charge = int(form.get("nb_enfants_charge", 0) or 0)
    except ValueError:
        nb_enfants_charge = 0
    return {
        # -- identification, reportée telle quelle sur le PDF --
        "nom_prenoms": form.get("nom_prenoms", "").strip(),
        "date_lieu_naissance": form.get("date_lieu_naissance", "").strip(),
        "profession": form.get("profession", "").strip(),
        "adresse_residence": form.get("adresse_residence", "").strip(),
        "commune_residence": form.get("commune_residence", "").strip(),
        "wilaya_residence": form.get("wilaya_residence", "").strip(),
        "code_postal_residence": form.get("code_postal_residence", "").strip(),
        "nin": form.get("nin", "").strip(),
        "compte_bancaire": form.get("compte_bancaire", "").strip(),
        "compte_postal": form.get("compte_postal", "").strip(),
        "telephone": form.get("telephone", "").strip(),
        "email": form.get("email", "").strip(),
        "fax": form.get("fax", "").strip(),
        "situation_familiale": form.get("situation_familiale", ""),
        "conjoint_nom": form.get("conjoint_nom", "").strip(),
        "conjoint_naissance": form.get("conjoint_naissance", "").strip(),
        "nb_enfants_charge": max(nb_enfants_charge, 0),
        "lieu_date_signature": form.get("lieu_date_signature", "").strip(),

        # -- revenus soumis au prélèvement libératoire (imposés à part,
        #    non intégrés au barème IRG progressif ci-dessous ; reportés
        #    sur le PDF à titre informatif, non totalisés) --
        "revenus_fonciers_liberatoire": to_float(form, "revenus_fonciers_liberatoire"),
        "plus_values_cession": to_float(form, "plus_values_cession"),
        "revenus_mobiliers_liberatoire": to_float(form, "revenus_mobiliers_liberatoire"),

        # -- revenus intégrés au revenu global (soumis au barème IRG) --
        "benefices_industriels_commerciaux": to_float(form, "benefices_industriels_commerciaux"),
        "benefices_non_commerciaux": to_float(form, "benefices_non_commerciaux"),
        "revenus_agricoles": to_float(form, "revenus_agricoles"),
        "revenus_fonciers_temporaires": to_float(form, "revenus_fonciers_temporaires"),
        "revenus_mobiliers_credit_impot": to_float(form, "revenus_mobiliers_credit_impot"),
        "salaires_traitements": to_float(form, "salaires_traitements"),
        "revenus_etranger": to_float(form, "revenus_etranger"),

        # -- charges déductibles --
        "interets_credit_logement": to_float(form, "interets_credit_logement"),
        "autres_deductions": to_float(form, "autres_deductions"),
    }

def lire_champs_casnos(form):
    return {
        "nature_versement": form.get("nature_versement", ""),
        "base_cotisation": to_float(form, "base_cotisation"),
        "montant_versement": to_float(form, "montant_versement"),
        "mode_paiement": form.get("mode_paiement", ""),
    }


def traiter_declaration_g50(form, erreurs):
    donnees = lire_champs_g50(form)
    valider_montants(
        donnees,
        ["ca_imposable", "tva_collectee", "tva_deductible", "irg_retenue",
         "tap_base", "taux_tap", "acompte_ibs"],
        erreurs,
    )
    if erreurs:
        return None, None, None
    resultats = calculer_g50(donnees)
    return resultats, resultats["total"], ("DGI", "G50")


def traiter_declaration_g1(form, erreurs):
    donnees = lire_champs_g1(form)
    valider_montants(
        donnees,
        ["revenus_fonciers_liberatoire", "plus_values_cession", "revenus_mobiliers_liberatoire",
         "benefices_industriels_commerciaux", "benefices_non_commerciaux", "revenus_agricoles",
         "revenus_fonciers_temporaires", "revenus_mobiliers_credit_impot", "salaires_traitements",
         "revenus_etranger", "interets_credit_logement", "autres_deductions"],
        erreurs,
    )
    if not donnees["situation_familiale"]:
        erreurs.append("La situation familiale est obligatoire.")
    if erreurs:
        return None, None, None
    resultats = calculer_g1(donnees)
    return resultats, resultats["total"], ("DGI", "G1")

def traiter_declaration_casnos(form, erreurs):
    donnees = lire_champs_casnos(form)
    valider_montants(donnees, ["base_cotisation", "montant_versement"], erreurs)
    if erreurs:
        return None, None, None
    resultats = calculer_casnos(donnees)
    return resultats, resultats["total"], ("CASNOS", "")


TRAITEMENTS_PAR_TYPE = {
    "G50": traiter_declaration_g50,
    "G1": traiter_declaration_g1,
    "CASNOS": traiter_declaration_casnos,
}

LIBELLES_DECLARATION = dict(DECLARATIONS_DGI, CASNOS="CASNOS — Bordereau de versement (cotisation sociale)")


# ---------------------------------------------------------------------------
# Déclarations fiscales - libellés d'affichage pour le récapitulatif HTML
# ---------------------------------------------------------------------------
# Le fallback HTML (CASNOS, ou tout type dont le PDF officiel n'est pas
# encore calibré) affiche les valeurs saisies. On ne veut PAS afficher le
# dict `details` brut : ses clés sont des noms de variables Python, pas des
# libellés lisibles, et il peut contenir des valeurs vides ou des champs
# internes sans intérêt pour le contribuable. FIELD_LABELS fixe donc,
# pour chaque type de déclaration, la liste ordonnée des champs à montrer
# et leur libellé en français ; build_detail_rows() filtre et traduit.
SITUATION_LABELS = {
    "celibataire": "Célibataire",
    "marie": "Marié(e)",
    "marie_enfants": "Marié(e) avec enfants",
    "veuf": "Veuf(ve)",
    "divorce": "Divorcé(e)",
}
MODE_PAIEMENT_LABELS = {"especes": "Espèces", "cheque": "Chèque", "virement": "Virement"}

FIELD_LABELS = {
    "G50": [
        ("ca_imposable", "Chiffre d'affaires imposable"),
        ("tva_collectee", "TVA collectée"),
        ("tva_deductible", "TVA déductible"),
        ("tva_nette", "TVA nette"),
        ("credit_tva", "Crédit de TVA reporté"),
        ("tva_a_payer", "TVA à payer"),
        ("irg_retenue", "IRG — retenue à la source"),
        ("tap_base", "Base TAP"),
        ("taux_tap", "Taux TAP (%)"),
        ("tap_montant", "Montant TAP"),
        ("acompte_ibs", "Acompte IBS"),
        ("total", "TOTAL À PAYER"),
    ],
    "G1": [
        ("nom_prenoms", "Nom et prénoms"),
        ("date_lieu_naissance", "Date et lieu de naissance"),
        ("profession", "Profession"),
        ("adresse_residence", "Adresse de résidence"),
        ("commune_residence", "Commune de résidence"),
        ("wilaya_residence", "Wilaya de résidence"),
        ("code_postal_residence", "Code postal"),
        ("nin", "NIN"),
        ("compte_bancaire", "Compte bancaire"),
        ("compte_postal", "Compte postal (CCP)"),
        ("telephone", "Téléphone"),
        ("email", "Email"),
        ("situation_familiale", "Situation familiale"),
        ("conjoint_nom", "Nom du conjoint"),
        ("nb_enfants_charge", "Enfants à charge"),
        ("revenus_fonciers_liberatoire", "Revenus fonciers (prélèvement libératoire)"),
        ("plus_values_cession", "Plus-values de cession"),
        ("revenus_mobiliers_liberatoire", "Revenus mobiliers (prélèvement libératoire)"),
        ("benefices_industriels_commerciaux", "Bénéfices industriels et commerciaux"),
        ("benefices_non_commerciaux", "Bénéfices non commerciaux"),
        ("revenus_agricoles", "Revenus agricoles"),
        ("revenus_fonciers_temporaires", "Revenus fonciers temporaires"),
        ("revenus_mobiliers_credit_impot", "Revenus mobiliers (crédit d'impôt)"),
        ("salaires_traitements", "Salaires et traitements"),
        ("revenus_etranger", "Revenus de source étrangère"),
        ("total_revenus_integres", "Total des revenus intégrés"),
        ("interets_credit_logement", "Intérêts crédit logement"),
        ("autres_deductions", "Autres déductions"),
        ("total_charges_deductibles", "Total des charges déductibles"),
        ("revenu_net_global", "Revenu net global"),
        ("reduction_couple_10pct", "Réduction 10 % (couple)"),
        ("revenu_net_imposable", "Revenu net imposable"),
        ("total", "IRG DÛ"),
    ],
    "CASNOS": [
        ("nature_versement", "Nature du versement"),
        ("base_cotisation", "Base de cotisation"),
        ("montant_versement", "Montant du versement"),
        ("mode_paiement", "Mode de paiement"),
        ("total", "TOTAL"),
    ],
}


def build_detail_rows(type_decl, details):
    """Transforme le dict brut `details` en liste ordonnée de tuples
    (label, valeur, is_total) prête à afficher : seules les clés
    pertinentes pour ce type sont gardées, dans un ordre lisible, avec
    les valeurs codées (situation familiale, mode de paiement) traduites
    en libellé humain, et les champs vides écartés.
    """
    rows = []
    for key, label in FIELD_LABELS.get(type_decl, []):
        val = details.get(key, "")
        if val in ("", None):
            continue
        if key == "situation_familiale":
            val = SITUATION_LABELS.get(val, val)
        elif key == "mode_paiement":
            val = MODE_PAIEMENT_LABELS.get(val, val)
        rows.append((label, val, key == "total"))
    return rows


# ---------------------------------------------------------------------------
# Routes - Déclarations fiscales
# ---------------------------------------------------------------------------
@app.route("/declarations", methods=["GET", "POST"])
@login_required
def declarations():
    db = get_db()
    uid = session["user_id"]

    if request.method == "POST":
        return _enregistrer_declaration(db, uid)

    _actualiser_statuts_en_retard(db, uid)

    liste = db.execute(
        "SELECT * FROM declaration WHERE user_id=? ORDER BY date_echeance ASC", (uid,)
    ).fetchall()

    return render_template(
        "declarations.html",
        declarations=liste,
        declarations_dgi=DECLARATIONS_DGI,
        today=date.today().isoformat(),
        taux_tap_defaut=TAUX_TAP_DEFAUT,
        situations_familiales=SITUATIONS_FAMILIALES,
        natures_versement_casnos=NATURES_VERSEMENT_CASNOS,
        modes_paiement=MODES_PAIEMENT,
    )


def _actualiser_statuts_en_retard(db, uid):
    db.execute(
        """UPDATE declaration SET statut='en retard'
           WHERE user_id=? AND statut='en attente' AND date_echeance < ?""",
        (uid, date.today().isoformat()),
    )
    db.commit()


def _enregistrer_declaration(db, uid):
    form = request.form
    type_decl = form.get("type", "")
    periode = form.get("periode", "").strip()
    date_echeance = form.get("date_echeance")
    nif = form.get("nif", "").strip()
    raison_sociale = form.get("raison_sociale", "").strip()
    adresse = form.get("adresse", "").strip()
    numero_article = form.get("numero_article", "").strip()

    erreurs = []
    if type_decl not in TRAITEMENTS_PAR_TYPE:
        erreurs.append("Type de déclaration invalide.")
    if not periode:
        erreurs.append("La période concernée est obligatoire.")
    if not date_echeance:
        erreurs.append("La date d'échéance est obligatoire.")
    erreurs.extend(valider_infos_contribuable(nif, raison_sociale, adresse))

    if erreurs:
        for e in erreurs:
            flash(e, "error")
        return redirect(url_for("declarations"))

    resultats, montant_total, meta = TRAITEMENTS_PAR_TYPE[type_decl](form, erreurs)

    if erreurs or resultats is None:
        for e in erreurs:
            flash(e, "error")
        return redirect(url_for("declarations"))

    administration, formulaire = meta

    db.execute(
        """INSERT INTO declaration
           (user_id, type, formulaire, administration, periode, montant, statut,
            date_echeance, nif, raison_sociale, adresse, numero_article, details)
           VALUES (?, ?, ?, ?, ?, ?, 'en attente', ?, ?, ?, ?, ?, ?)""",
        (uid, type_decl, formulaire, administration, periode, montant_total, date_echeance,
         nif, raison_sociale, adresse, numero_article, json.dumps(resultats)),
    )
    db.commit()
    flash(f"Déclaration ajoutée ({LIBELLES_DECLARATION.get(type_decl, type_decl)}).", "success")
    return redirect(url_for("declarations"))


@app.route("/declarations/<int:decl_id>/statut", methods=["POST"])
@login_required
def update_statut_declaration(decl_id):
    statut = request.form.get("statut")
    if statut not in STATUTS_DECLARATION:
        flash("Statut invalide.", "error")
        return redirect(url_for("declarations"))
    db = get_db()
    db.execute(
        "UPDATE declaration SET statut=? WHERE id=? AND user_id=?",
        (statut, decl_id, session["user_id"]),
    )
    db.commit()
    flash("Statut mis à jour.", "success")
    return redirect(url_for("declarations"))


@app.route("/declarations/<int:decl_id>/delete", methods=["POST"])
@login_required
def delete_declaration(decl_id):
    db = get_db()
    db.execute("DELETE FROM declaration WHERE id=? AND user_id=?", (decl_id, session["user_id"]))
    db.commit()
    flash("Déclaration supprimée.", "success")
    return redirect(url_for("declarations"))


@app.route("/declarations/<int:decl_id>/generate")
@login_required
def generate_declaration_form(decl_id):
    db = get_db()
    decl = db.execute(
        "SELECT * FROM declaration WHERE id=? AND user_id=?", (decl_id, session["user_id"])
    ).fetchone()

    if decl is None:
        flash("Déclaration introuvable.", "error")
        return redirect(url_for("declarations"))

    details = json.loads(decl["details"]) if decl["details"] else {}
    contribuable = current_user()

    builder = FORM_BUILDERS.get(decl["type"])
    pdf_path = FORM_PDF_PATHS.get(decl["type"])

    if builder and pdf_path and os.path.exists(pdf_path):
        # The contribuable identity fields live on the declaration row,
        # not in `details` (which only holds the calcul-specific inputs).
        data = dict(details)
        data.setdefault("nif", decl["nif"])
        data.setdefault("raison_sociale", decl["raison_sociale"])
        data.setdefault("adresse", decl["adresse"])
        data.setdefault("numero_article", decl["numero_article"])

        pdf_bytes = fill_pdf(pdf_path, builder(data))
        return send_file(
            BytesIO(pdf_bytes),
            mimetype="application/pdf",
            as_attachment=False,
            download_name=f"{decl['type']}_{decl['periode']}.pdf",
        )

    # CASNOS (no official DGI form) and any type without a calibrated
    # field map fall back to the HTML recap.
    detail_rows = build_detail_rows(decl["type"], details)
    return render_template(
        "declaration_form.html",
        d=decl,
        detail_rows=detail_rows,
        contribuable=contribuable,
        date_edition=date.today().isoformat(),
    )

# ---------------------------------------------------------------------------
# Routes - Rapports
# ---------------------------------------------------------------------------
@app.route("/reports")
@login_required
def reports():
    db = get_db()
    uid = session["user_id"]

    date_debut = request.args.get("date_debut", "")
    date_fin = request.args.get("date_fin", "")

    query = "SELECT * FROM operation WHERE user_id=?"
    params = [uid]
    if date_debut:
        query += " AND date_operation >= ?"
        params.append(date_debut)
    if date_fin:
        query += " AND date_operation <= ?"
        params.append(date_fin)
    query += " ORDER BY date_operation ASC"

    liste_operations = db.execute(query, params).fetchall()

    total_recettes = sum(o["montant"] for o in liste_operations if o["type"] == "recette")
    total_depenses = sum(o["montant"] for o in liste_operations if o["type"] == "depense")

    par_categorie = {}
    for o in liste_operations:
        key = (o["type"], o["categorie"])
        par_categorie[key] = par_categorie.get(key, 0) + o["montant"]

    return render_template(
        "reports.html",
        operations=liste_operations,
        total_recettes=total_recettes,
        total_depenses=total_depenses,
        solde=total_recettes - total_depenses,
        par_categorie=par_categorie,
        date_debut=date_debut,
        date_fin=date_fin,
    )


@app.route("/reports/export")
@login_required
def export_csv():
    db = get_db()
    uid = session["user_id"]

    date_debut = request.args.get("date_debut", "")
    date_fin = request.args.get("date_fin", "")

    query = "SELECT * FROM operation WHERE user_id=?"
    params = [uid]
    if date_debut:
        query += " AND date_operation >= ?"
        params.append(date_debut)
    if date_fin:
        query += " AND date_operation <= ?"
        params.append(date_fin)
    query += " ORDER BY date_operation ASC"

    liste_operations = db.execute(query, params).fetchall()

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["Date", "Type", "Catégorie", "Montant (DZD)", "Description"])
    for o in liste_operations:
        writer.writerow([o["date_operation"], o["type"], o["categorie"], o["montant"], o["description"] or ""])

    response = Response(output.getvalue(), mimetype="text/csv")
    response.headers["Content-Disposition"] = "attachment; filename=rapport_mada.csv"
    return response


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    init_db()  # idempotent : crée le schéma ou migre une base existante
    app.run(debug=True, host="0.0.0.0", port=5000)