# MADA — MVP

Plateforme numérique de gestion comptable, fiscale et administrative pour startups,
micro-entreprises et freelances en Algérie.

## Stack
- **Backend** : Flask + SQLite (sqlite3 natif, sans ORM)
- **Frontend** : HTML / CSS / JS (aucun framework, Chart.js via CDN pour les graphiques)
- **Auth** : sessions Flask + mots de passe hashés (werkzeug)

## Fonctionnalités du MVP
- Création de compte / connexion / déconnexion
- Tableau de bord : solde, totaux, graphique d'évolution, répartition des dépenses,
  dernières opérations, prochaines échéances fiscales
- Gestion des recettes et dépenses (ajout, filtrage, suppression)
- Gestion des déclarations fiscales : IRG, TVA, CASNOS (statut en attente / payée / en retard,
  détection automatique du retard)
- Rapports : filtrage par période, répartition par catégorie, export CSV

## Installation

```bash
cd mada
python3 -m venv venv
source venv/bin/activate      # Windows : venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

L'application est accessible sur **http://localhost:5000**.
La base de données SQLite (`mada.db`) est créée automatiquement au premier lancement.

## Structure du projet

```
mada/
├── app.py                  # Application Flask (routes + logique métier)
├── mada.db                 # Base SQLite (générée au 1er lancement)
├── requirements.txt
├── templates/
│   ├── base.html            # Layout commun (sidebar, flash messages)
│   ├── login.html / register.html
│   ├── dashboard.html
│   ├── operations.html      # Recettes & dépenses
│   ├── declarations.html    # IRG / TVA / CASNOS
│   └── reports.html
└── static/
    ├── css/style.css
    └── js/script.js
```

## Modèle de données

- **user** : id, nom, entreprise, email, password_hash, date_creation
- **operation** : id, user_id, type (recette/depense), categorie, montant, description, date_operation
- **declaration** : id, user_id, type (IRG/TVA/CASNOS), periode, montant, statut, date_echeance

## Limites du prototype (pistes d'évolution)
- Calcul automatique des montants d'IRG/TVA (actuellement saisie manuelle)
- Rappels par email/SMS avant échéance
- Génération de rapports PDF
- Rôles multi-utilisateurs (comptable ↔ client)
- Migration vers PostgreSQL pour la production
