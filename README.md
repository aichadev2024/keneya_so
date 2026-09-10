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

| App | Rôle | Phase (CDC 11.2) | État |
|---|---|---|---|
| `apps.core` | Socle : base horodatée, paramètres établissement, **journal d'audit** | 2 | ✅ |
| `apps.accounts` | Utilisateur personnalisé, **rôles & RBAC**, authentification | 2 | ✅ |
| `apps.patients` | Patients, dossiers médicaux, allergies | 2-3 | ✅ |
| `apps.consultations` | Consultations, constantes, **ordonnances** + alertes de prescription | 3 | ✅ |
| `apps.pharmacie` | Catalogue, **stock par lots (FEFO)**, mouvements, **dispensation** | 3 | ✅ |
| `apps.hospitalisation` | Services, **chambres/lits**, admission, **suivi quotidien**, sortie, vue d'occupation | 4 | ✅ |
| `apps.bloc_operatoire` | Salles, types d'actes, **planification + conflits**, équipes, **checklist OMS**, per-opératoire, CR, **indicateurs** (CDC section 5) | 5-6 | ✅ |
| `apps.laboratoire` | Analyses biologiques et imagerie | 7 | 🔜 |
| `apps.facturation` | Grille tarifaire, **factures auto depuis les actes**, part patient/assurance, paiements, relances, impayés | 6 | ✅ |
| `apps.assurances` | Compagnies, contrats, adhésions patient (taux + plafond), **bordereaux** | 6 | ✅ |

Les modules 🔜 sont pour l'instant des applications déclarées sans modèle : elles
fixent l'architecture et seront développées à leur phase.

### Parcours de soins (phase 3)

1. Depuis une fiche patient : **nouvelle consultation** (motif, examen, diagnostic,
   conduite à tenir) puis saisie des **constantes** (IMC, TA… calculés).
2. **Ordonnance** rattachée à la consultation : ajout de lignes (médicament du
   catalogue, posologie, durée, quantité). Des **alertes non bloquantes** (CDC 4.3)
   signalent une allergie déclarée du patient ou une interaction connue entre deux
   médicaments prescrits.
3. **Transmission** de l'ordonnance : ouvre automatiquement une dispensation dans
   la file de la pharmacie.
4. Le pharmacien **délivre** ligne par ligne ; l'allocation puise dans les lots en
   **FEFO** (premier périmé, premier sorti), décrémente le stock et journalise
   chaque mouvement. Statuts d'ordonnance/dispensation mis à jour (partielle /
   complète). Seuils d'alerte et retrait des lots périmés gérés côté catalogue.

### Hospitalisation (phase 4)

- **Services → chambres → lits** (configurés via l'administration). L'occupation
  d'un lit est **déduite des séjours en cours** — aucun champ dénormalisé à
  resynchroniser.
- **Admission** depuis la fiche patient : choix du service et d'un lit
  disponible ; contrainte base de données « un seul séjour en cours par lit ».
- **Suivi quotidien** : notes horodatées et nominatives (soin infirmier,
  observation médicale, traitement, constantes rapides).
- **Transfert de lit** tracé (`MouvementLit`) ; **sortie** avec mode
  (domicile / transfert / contre avis / décès), compte-rendu et consignes — le
  lit redevient disponible automatiquement.
- **Vue d'occupation en temps réel** par service (taux, lits libres/occupés).

### Bloc opératoire (phases 5-6, module détaillé CDC section 5)

- **Salles** (statut temps réel déduit : libre / occupée / en nettoyage / maintenance),
  **types d'acte** avec durée standard et matériel requis, **matériel** et statut
  de stérilisation, historique d'indisponibilité.
- **Cycle d'une intervention** : demande (depuis la fiche patient) → planification
  → validation anesthésique → per-opératoire → clôture → compte-rendu.
- **Règles de gestion CDC 5.4 appliquées dans `services.py`** :
  - une salle ne porte qu'une intervention par créneau — **double réservation
    bloquée**, temps de nettoyage paramétrable inséré dans le calcul de chevauchement ;
  - un membre d'équipe ne peut pas être affecté à deux interventions qui se
    chevauchent ;
  - une **extrême urgence** peut forcer le report des interventions *programmées*
    en conflit, avec motif et auteur tracés ;
  - **checklist sécurité type OMS à 3 temps** : validation nominative et horodatée,
    ordre imposé, entrée en salle / clôture bloquées tant que le temps requis
    n'est pas validé ;
  - toute annulation / déprogrammation exige un motif et est historisée.
- **Planning** par salle (vue jour) + file des demandes à planifier.
- **Indicateurs** (`stats.py`) : taux d'occupation des salles, durée moyenne par
  acte et par praticien, taux de déprogrammation + motifs, temps de rotation
  moyen. Export PDF/Excel prévu en phase 9.

### Facturation & assurances (phase 6)

- **Grille tarifaire** (`Tarif`) par catégorie (consultation, journée
  d'hospitalisation, acte de bloc, médicament, analyse).
- **Génération automatique** : à la clôture d'un acte (consultation clôturée,
  séjour terminé, intervention terminée, dispensation complète), un signal crée
  une **facture en brouillon** que le comptable émet ensuite. Désactivable par
  `FACTURATION_AUTO = False` ; génération manuelle possible depuis chaque fiche
  d'acte. Pas de double facturation d'une même source.
- **Répartition part patient / part assurance** : d'après la couverture active du
  patient (`PatientAssure` → taux du contrat ou surcharge), **plafond annuel**
  respecté (la consommation déjà facturée est décomptée).
- **Paiements** (espèces, mobile money, virement, chèque, carte) et
  **remboursements** ; le statut de la facture suit (émise → partielle → réglée).
- **Impayés** : liste des factures échues non soldées, **relances** tracées.
- **Assurances** : compagnies, contrats (taux, plafond), adhésions patient.
  **Bordereaux** regroupant les parts assurance d'une période pour un organisme
  (une facture ne figure que sur un seul bordereau).

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
