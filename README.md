# Kènèya Sô — plateforme de gestion hospitalière

Application de gestion hospitalière intelligente pour le contexte malien.
Mémoire de fin de cycle en ingénierie biomédicale — Alpha Boubacar Touré.

Cahier des charges complet : [`docs/Kenya_So_Cahier_des_charges_enrichi.docx`](docs/Kenya_So_Cahier_des_charges_enrichi.docx).
Diagrammes UML et d'architecture : [`docs/diagrammes/`](docs/diagrammes/).

## Pile technique (CDC section 8)

| Couche | Choix |
|---|---|
| Backend | Django 5.2 + Django REST Framework |
| Base de données | PostgreSQL (repli SQLite en développement) |
| Frontend | Django Templates + Bootstrap 5 |
| Internationalisation | Django i18n — 6 langues (fr, en, ar, bm, ff, snk) |
| Documentation d'API | drf-spectacular (`/api/docs/`) |
| Déploiement | Render / Railway (Gunicorn + WhiteNoise) |

## Architecture

Une application Django par module métier (CDC 7.5) :

| App | Rôle | Phase (CDC 11.2) |
|---|---|---|
| `apps.core` | Socle : base horodatée, paramètres établissement, **journal d'audit** | 2 |
| `apps.accounts` | Utilisateur personnalisé, **rôles & RBAC**, authentification | 2 |
| `apps.patients` | Patients, dossiers médicaux, allergies | 2-3 |
| `apps.consultations` | Consultations, constantes, diagnostics | 3 |
| `apps.pharmacie` | Dispensation, stocks | 3 |
| `apps.hospitalisation` | Admission, lits, sortie | 4 |
| `apps.bloc_operatoire` | Planning salles, équipes, checklist, CR opératoire (CDC section 5) | 5-6 |
| `apps.laboratoire` | Analyses biologiques et imagerie | 7 |
| `apps.facturation` | Factures, paiements, part patient/assurance | 6 |
| `apps.assurances` | Compagnies, contrats, bordereaux | 6 |

Les modules au-delà de `patients` sont pour l'instant des applications déclarées
sans modèle : ils fixent l'architecture et seront développés à leur phase.

### Contrôle d'accès (RBAC)

`apps/accounts/roles.py` est la **source de vérité** : il associe chaque rôle
métier à ses permissions Django. Un groupe `role:<ROLE>` est recalculé à chaque
migration (`post_migrate`) et l'appartenance de chaque utilisateur est
synchronisée sur son rôle courant. Principe du moindre privilège (CDC 7.1).

## Démarrage

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows
# source .venv/bin/activate       # Linux/macOS
pip install -r requirements.txt

copy .env.example .env            # puis adapter (SECRET_KEY, DATABASE_URL…)

python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

- Application : http://127.0.0.1:8000/
- Administration : http://127.0.0.1:8000/admin/
- Documentation de l'API : http://127.0.0.1:8000/api/docs/

## Tests

```bash
python manage.py test
```

Les tests couvrent en priorité les règles de gestion critiques (CDC 7.5) :
génération des numéros de dossier, création automatique du dossier médical,
et application du RBAC (qui peut créer / consulter un patient).

## Internationalisation

```bash
python manage.py makemessages -l bm -l ff -l snk -l ar -l en
# traduire les fichiers locale/<lang>/LC_MESSAGES/django.po (locuteurs natifs)
python manage.py compilemessages
```

Le bambara, le peulh (fulfulde) et le soninké n'ont pas de catalogue Django
préexistant : la traduction est une tâche à part entière, à mener en parallèle
du développement (CDC 4.11 / 12.5).
