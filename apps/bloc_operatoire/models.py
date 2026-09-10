"""
Module « Bloc opératoire » — planification, sécurité et traçabilité des
interventions chirurgicales (CDC section 5, module détaillé).

- ``SalleOperatoire``       : salle, équipement, statut temps réel, temps de nettoyage.
- ``TypeIntervention``      : référentiel des actes (durée standard, matériel requis).
- ``MaterielBloc``          : kits / instruments et leur statut de stérilisation.
- ``Intervention``          : demande → planification → per-opératoire → clôture.
- ``MembreEquipe``          : composition de l'équipe chirurgicale.
- ``EtapeChecklist``        : checklist sécurité type OMS à trois temps.
- ``CompteRenduOperatoire`` : CR rédigé par le chirurgien, rattaché au dossier.
- ``IndisponibiliteSalle``  : historique de maintenance / indisponibilité.

Référence : docs/Kenya_So_Cahier_des_charges_enrichi.docx, section 5.
"""

from __future__ import annotations

from datetime import date, timedelta

from django.conf import settings
from django.db import models
from django.db.models import Max
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel

TEMPS_NETTOYAGE_DEFAUT_MIN = 30  # CDC 5.4 : temps tampon paramétrable, défaut 30 min


class SalleOperatoire(models.Model):
    class Statut(models.TextChoices):
        DISPONIBLE = "DISPONIBLE", _("Disponible")
        MAINTENANCE = "MAINTENANCE", _("En maintenance")
        HORS_SERVICE = "HORS_SERVICE", _("Hors service")

    class StatutEffectif(models.TextChoices):
        DISPONIBLE = "DISPONIBLE", _("Libre")
        OCCUPEE = "OCCUPEE", _("Occupée")
        NETTOYAGE = "NETTOYAGE", _("En nettoyage")
        MAINTENANCE = "MAINTENANCE", _("En maintenance")
        HORS_SERVICE = "HORS_SERVICE", _("Hors service")

    nom = models.CharField(_("nom"), max_length=80, unique=True)
    code = models.CharField(_("code"), max_length=12, blank=True)
    equipement = models.TextField(_("équipement disponible"), blank=True)
    capacite = models.PositiveSmallIntegerField(_("capacité (interventions simultanées)"),
                                                default=1)
    duree_nettoyage_min = models.PositiveSmallIntegerField(
        _("temps de nettoyage (minutes)"), default=TEMPS_NETTOYAGE_DEFAUT_MIN,
        help_text=_("Temps tampon inséré automatiquement entre deux interventions."),
    )
    statut = models.CharField(_("statut"), max_length=12, choices=Statut.choices,
                              default=Statut.DISPONIBLE)
    actif = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("salle opératoire")
        verbose_name_plural = _("salles opératoires")
        ordering = ["nom"]

    def __str__(self) -> str:
        return self.nom

    @property
    def intervention_en_cours(self):
        return self.interventions.filter(
            statut=Intervention.Statut.EN_COURS
        ).select_related("patient").first()

    @property
    def statut_effectif(self) -> str:
        """Statut temps réel (CDC 5.3.2) : superpose l'activité au statut stocké."""
        if self.statut != self.Statut.DISPONIBLE:
            return self.statut
        if self.intervention_en_cours:
            return self.StatutEffectif.OCCUPEE
        derniere = (
            self.interventions.filter(
                statut=Intervention.Statut.TERMINEE, heure_sortie_salle__isnull=False,
            )
            .order_by("-heure_sortie_salle")
            .first()
        )
        if derniere and derniere.heure_sortie_salle:
            fin_nettoyage = derniere.heure_sortie_salle + timedelta(
                minutes=self.duree_nettoyage_min
            )
            if timezone.now() < fin_nettoyage:
                return self.StatutEffectif.NETTOYAGE
        return self.StatutEffectif.DISPONIBLE

    def get_statut_effectif_display(self) -> str:
        return dict(self.StatutEffectif.choices).get(self.statut_effectif,
                                                     self.statut_effectif)

    @property
    def operationnelle(self) -> bool:
        return self.actif and self.statut == self.Statut.DISPONIBLE


class MaterielBloc(models.Model):
    class Sterilisation(models.TextChoices):
        STERILISE = "STERILISE", _("Stérilisé")
        EN_STERILISATION = "EN_STERILISATION", _("En stérilisation")
        NON_STERILISE = "NON_STERILISE", _("Non stérilisé")
        PERIME = "PERIME", _("Péremption de stérilité dépassée")

    designation = models.CharField(_("désignation"), max_length=150, unique=True)
    reference = models.CharField(_("référence"), max_length=60, blank=True)
    quantite_disponible = models.PositiveIntegerField(_("quantité disponible"), default=0)
    quantite_totale = models.PositiveIntegerField(_("quantité totale"), default=0)
    statut_sterilisation = models.CharField(
        _("statut de stérilisation"), max_length=16, choices=Sterilisation.choices,
        default=Sterilisation.NON_STERILISE,
    )
    date_sterilisation = models.DateField(_("date de stérilisation"), null=True, blank=True)
    actif = models.BooleanField(_("actif"), default=True)

    class Meta:
        verbose_name = _("matériel de bloc")
        verbose_name_plural = _("matériels de bloc")
        ordering = ["designation"]

    def __str__(self) -> str:
        return self.designation

    @property
    def disponible_pour_intervention(self) -> bool:
        return (
            self.actif
            and self.quantite_disponible > 0
            and self.statut_sterilisation == self.Sterilisation.STERILISE
        )


class TypeIntervention(models.Model):
    libelle = models.CharField(_("libellé de l'acte"), max_length=150, unique=True)
    specialite = models.CharField(_("spécialité"), max_length=100, blank=True)
    duree_standard_min = models.PositiveSmallIntegerField(_("durée standard (minutes)"),
                                                          default=60)
    description = models.TextField(_("description"), blank=True)
    materiels = models.ManyToManyField(MaterielBloc, through="MaterielRequis",
                                       related_name="types_intervention", blank=True)
    actif = models.BooleanField(_("actif"), default=True)

    class Meta:
        verbose_name = _("type d'intervention")
        verbose_name_plural = _("types d'intervention")
        ordering = ["libelle"]

    def __str__(self) -> str:
        return self.libelle


class MaterielRequis(models.Model):
    """Matériel requis pour un type d'intervention (CDC 5.3.4)."""

    type_intervention = models.ForeignKey(TypeIntervention, on_delete=models.CASCADE,
                                          related_name="materiels_requis")
    materiel = models.ForeignKey(MaterielBloc, on_delete=models.CASCADE,
                                 related_name="requis_par")
    quantite = models.PositiveSmallIntegerField(_("quantité"), default=1)

    class Meta:
        verbose_name = _("matériel requis")
        verbose_name_plural = _("matériels requis")
        constraints = [
            models.UniqueConstraint(fields=["type_intervention", "materiel"],
                                    name="materiel_requis_unique"),
        ]

    def __str__(self) -> str:
        return f"{self.materiel} ×{self.quantite}"


class Intervention(TimeStampedModel):
    class Urgence(models.TextChoices):
        PROGRAMMEE = "PROGRAMMEE", _("Programmée")
        URGENTE = "URGENTE", _("Urgente")
        EXTREME_URGENCE = "EXTREME_URGENCE", _("Extrême urgence")

    class Statut(models.TextChoices):
        DEMANDEE = "DEMANDEE", _("Demandée")
        PLANIFIEE = "PLANIFIEE", _("Planifiée")
        EN_COURS = "EN_COURS", _("En cours")
        TERMINEE = "TERMINEE", _("Terminée")
        REPORTEE = "REPORTEE", _("Reportée")
        ANNULEE = "ANNULEE", _("Annulée")

    STATUTS_ACTIFS = {Statut.PLANIFIEE, Statut.EN_COURS}

    reference = models.CharField(_("référence"), max_length=20, unique=True, editable=False)
    patient = models.ForeignKey("patients.Patient", on_delete=models.PROTECT,
                                related_name="interventions", verbose_name=_("patient"))
    type_intervention = models.ForeignKey(TypeIntervention, on_delete=models.PROTECT,
                                          related_name="interventions",
                                          verbose_name=_("type d'acte"))
    hospitalisation = models.ForeignKey("hospitalisation.Hospitalisation",
                                        on_delete=models.SET_NULL, null=True, blank=True,
                                        related_name="interventions")
    salle = models.ForeignKey(SalleOperatoire, on_delete=models.SET_NULL, null=True,
                              blank=True, related_name="interventions",
                              verbose_name=_("salle"))
    chirurgien_principal = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="interventions_operees", verbose_name=_("chirurgien principal"),
    )
    demandeur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                  null=True, blank=True, related_name="+",
                                  verbose_name=_("demandeur"))

    motif_operation = models.TextField(_("motif de l'intervention"))
    diagnostic_preop = models.TextField(_("diagnostic préopératoire"), blank=True)
    materiel_specifique = models.TextField(_("matériel spécifique requis"), blank=True)

    date_demande = models.DateTimeField(_("date de la demande"), default=timezone.now)
    date_heure_debut_prevue = models.DateTimeField(_("début prévu"), null=True, blank=True)
    duree_estimee_min = models.PositiveSmallIntegerField(_("durée estimée (minutes)"),
                                                         default=60)
    niveau_urgence = models.CharField(_("niveau d'urgence"), max_length=16,
                                      choices=Urgence.choices, default=Urgence.PROGRAMMEE)
    statut = models.CharField(_("statut"), max_length=12, choices=Statut.choices,
                              default=Statut.DEMANDEE)

    # Validation anesthésique (CDC 5.2 / 5.3.5)
    faisabilite_anesthesique_validee = models.BooleanField(
        _("faisabilité anesthésique validée"), default=False)
    protocole_anesthesie = models.TextField(_("protocole d'anesthésie"), blank=True)
    anesthesiste_validateur = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+", verbose_name=_("anesthésiste"),
    )

    # Suivi per-opératoire (CDC 5.3.6)
    heure_entree_salle = models.DateTimeField(_("entrée en salle"), null=True, blank=True)
    heure_debut_intervention = models.DateTimeField(_("début (incision)"), null=True,
                                                    blank=True)
    heure_fin_intervention = models.DateTimeField(_("fin d'intervention"), null=True,
                                                  blank=True)
    heure_sortie_salle = models.DateTimeField(_("sortie de salle"), null=True, blank=True)
    incidents_peroperatoires = models.TextField(_("incidents / complications"), blank=True)

    # Annulation / report (CDC 5.4 : motif obligatoire et historisé)
    motif_annulation = models.TextField(_("motif d'annulation / de report"), blank=True)
    annule_par = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                   null=True, blank=True, related_name="+")
    annule_le = models.DateTimeField(_("annulée / reportée le"), null=True, blank=True)

    class Meta:
        verbose_name = _("intervention")
        verbose_name_plural = _("interventions")
        ordering = ["-date_heure_debut_prevue", "-date_demande"]
        indexes = [
            models.Index(fields=["statut", "date_heure_debut_prevue"]),
            models.Index(fields=["salle", "date_heure_debut_prevue"]),
        ]

    def __str__(self) -> str:
        return f"{self.reference} — {self.patient.nom_complet}"

    def save(self, *args, **kwargs):
        if not self.reference:
            annee = date.today().year
            base = f"BLOC-{annee}-"
            dernier = (
                Intervention.objects.filter(reference__startswith=base)
                .aggregate(m=Max("reference")).get("m")
            )
            seq = int(dernier.split("-")[-1]) + 1 if dernier else 1
            self.reference = f"{base}{seq:06d}"
        super().save(*args, **kwargs)

    # -- créneaux -----------------------------------------------------------
    @property
    def duree_reelle_min(self):
        if self.heure_debut_intervention and self.heure_fin_intervention:
            delta = self.heure_fin_intervention - self.heure_debut_intervention
            return round(delta.total_seconds() / 60)
        return None

    @property
    def fin_prevue(self):
        if not self.date_heure_debut_prevue:
            return None
        return self.date_heure_debut_prevue + timedelta(minutes=self.duree_estimee_min)

    def fin_creneau_avec_nettoyage(self):
        fin = self.fin_prevue
        if fin is None:
            return None
        minutes = self.salle.duree_nettoyage_min if self.salle else TEMPS_NETTOYAGE_DEFAUT_MIN
        return fin + timedelta(minutes=minutes)

    @property
    def est_active(self) -> bool:
        return self.statut in self.STATUTS_ACTIFS

    @property
    def checklist_sortie_validee(self) -> bool:
        return self.checklist.filter(
            temps=EtapeChecklist.Temps.AVANT_SORTIE_SALLE, valide=True
        ).exists()


class MembreEquipe(models.Model):
    class Role(models.TextChoices):
        CHIRURGIEN = "CHIRURGIEN", _("Chirurgien")
        CHIRURGIEN_AIDE = "CHIRURGIEN_AIDE", _("Chirurgien aide")
        ANESTHESISTE = "ANESTHESISTE", _("Anesthésiste")
        IBODE = "IBODE", _("IBODE")
        AIDE_OPERATOIRE = "AIDE_OPERATOIRE", _("Aide-opératoire")
        AUTRE = "AUTRE", _("Autre")

    intervention = models.ForeignKey(Intervention, on_delete=models.CASCADE,
                                     related_name="equipe", verbose_name=_("intervention"))
    utilisateur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                    related_name="participations_bloc",
                                    verbose_name=_("membre"))
    role = models.CharField(_("rôle"), max_length=16, choices=Role.choices)
    notifie_le = models.DateTimeField(_("notifié le"), null=True, blank=True)

    class Meta:
        verbose_name = _("membre d'équipe")
        verbose_name_plural = _("équipe chirurgicale")
        constraints = [
            models.UniqueConstraint(fields=["intervention", "utilisateur"],
                                    name="membre_equipe_unique"),
        ]

    def __str__(self) -> str:
        return f"{self.utilisateur.get_full_name() or self.utilisateur} — {self.get_role_display()}"


class EtapeChecklist(models.Model):
    """Checklist sécurité type OMS à trois temps (CDC 5.3.5)."""

    class Temps(models.TextChoices):
        AVANT_INDUCTION = "AVANT_INDUCTION", _("Avant l'induction anesthésique")
        AVANT_INCISION = "AVANT_INCISION", _("Avant l'incision")
        AVANT_SORTIE_SALLE = "AVANT_SORTIE_SALLE", _("Avant la sortie de salle")

    ORDRE = [Temps.AVANT_INDUCTION, Temps.AVANT_INCISION, Temps.AVANT_SORTIE_SALLE]

    intervention = models.ForeignKey(Intervention, on_delete=models.CASCADE,
                                     related_name="checklist")
    temps = models.CharField(_("temps"), max_length=20, choices=Temps.choices)
    valide = models.BooleanField(_("validé"), default=False)
    valide_par = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                   null=True, blank=True, related_name="+",
                                   verbose_name=_("validé par"))
    valide_le = models.DateTimeField(_("validé le"), null=True, blank=True)
    commentaire = models.CharField(_("réserves / commentaire"), max_length=255, blank=True)

    class Meta:
        verbose_name = _("étape de checklist")
        verbose_name_plural = _("checklist de sécurité")
        ordering = ["intervention", "temps"]
        constraints = [
            models.UniqueConstraint(fields=["intervention", "temps"],
                                    name="checklist_temps_unique"),
        ]

    def __str__(self) -> str:
        return f"{self.get_temps_display()} — {'OK' if self.valide else '...'}"


class CompteRenduOperatoire(TimeStampedModel):
    """CR opératoire rédigé par le chirurgien, rattaché au dossier (CDC 5.3.6)."""

    intervention = models.OneToOneField(Intervention, on_delete=models.CASCADE,
                                        related_name="compte_rendu",
                                        verbose_name=_("intervention"))
    technique_operatoire = models.TextField(_("technique opératoire"))
    constatations = models.TextField(_("constatations peropératoires"), blank=True)
    complications = models.TextField(_("complications"), blank=True)
    suites_a_prevoir = models.TextField(_("suites à prévoir"), blank=True)
    prescription_postoperatoire = models.TextField(_("prescription postopératoire"),
                                                   blank=True)
    redige_par = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                   null=True, blank=True, related_name="+",
                                   verbose_name=_("rédigé par"))
    redige_le = models.DateTimeField(_("rédigé le"), default=timezone.now)

    class Meta:
        verbose_name = _("compte-rendu opératoire")
        verbose_name_plural = _("comptes-rendus opératoires")

    def __str__(self) -> str:
        return _("CR — %(ref)s") % {"ref": self.intervention.reference}

    @property
    def patient(self):
        return self.intervention.patient


class IndisponibiliteSalle(models.Model):
    """Historique de maintenance / indisponibilité d'une salle (CDC 5.3.2)."""

    class Motif(models.TextChoices):
        MAINTENANCE = "MAINTENANCE", _("Maintenance planifiée")
        PANNE = "PANNE", _("Panne d'équipement")
        TRAVAUX = "TRAVAUX", _("Travaux")
        AUTRE = "AUTRE", _("Autre")

    salle = models.ForeignKey(SalleOperatoire, on_delete=models.CASCADE,
                              related_name="indisponibilites")
    motif = models.CharField(_("motif"), max_length=12, choices=Motif.choices,
                             default=Motif.MAINTENANCE)
    date_debut = models.DateTimeField(_("début"), default=timezone.now)
    date_fin = models.DateTimeField(_("fin"), null=True, blank=True)
    description = models.CharField(_("description"), max_length=255, blank=True)
    cree_par = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                 null=True, blank=True, related_name="+")

    class Meta:
        verbose_name = _("indisponibilité de salle")
        verbose_name_plural = _("indisponibilités de salle")
        ordering = ["-date_debut"]

    def __str__(self) -> str:
        return f"{self.salle} — {self.get_motif_display()} ({self.date_debut:%d/%m/%Y})"
