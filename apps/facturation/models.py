"""
Module « Facturation et paiements » (CDC 4.8).

- ``Tarif``       : grille tarifaire par catégorie d'acte.
- ``Facture`` / ``LigneFacture`` : facture d'un patient agrégeant des actes de
  plusieurs modules ; répartition part patient / part assurance.
- ``Paiement``   : encaissements et remboursements (espèces, mobile money, …).
- ``Relance``    : relances sur factures impayées.

Référence : docs/Kenya_So_Cahier_des_charges_enrichi.docx, section 4.8.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Max, Sum
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel

DELAI_ECHEANCE_JOURS = 30


class CategorieTarif(models.TextChoices):
    CONSULTATION = "CONSULTATION", _("Consultation")
    HOSPITALISATION_JOUR = "HOSPIT_JOUR", _("Hospitalisation (par jour)")
    ACTE_BLOC = "ACTE_BLOC", _("Acte de bloc opératoire")
    MEDICAMENT = "MEDICAMENT", _("Médicament")
    ANALYSE = "ANALYSE", _("Analyse / imagerie")
    AUTRE = "AUTRE", _("Autre")


class TypeSource(models.TextChoices):
    CONSULTATION = "CONSULTATION", _("Consultation")
    HOSPITALISATION = "HOSPITALISATION", _("Hospitalisation")
    INTERVENTION = "INTERVENTION", _("Intervention chirurgicale")
    DISPENSATION = "DISPENSATION", _("Dispensation pharmacie")
    AUTRE = "AUTRE", _("Autre")


class Tarif(models.Model):
    code = models.CharField(_("code"), max_length=40, unique=True)
    libelle = models.CharField(_("libellé"), max_length=150)
    categorie = models.CharField(_("catégorie"), max_length=16,
                                 choices=CategorieTarif.choices)
    montant = models.DecimalField(_("montant (FCFA)"), max_digits=12, decimal_places=2)
    reference_externe = models.CharField(
        _("référence externe"), max_length=40, blank=True,
        help_text=_("Ex. : identifiant d'un type d'intervention pour un tarif d'acte."),
    )
    actif = models.BooleanField(_("actif"), default=True)

    class Meta:
        verbose_name = _("tarif")
        verbose_name_plural = _("grille tarifaire")
        ordering = ["categorie", "libelle"]

    def __str__(self) -> str:
        return f"{self.libelle} — {self.montant} FCFA"

    @classmethod
    def montant_pour(cls, categorie: str, reference_externe: str = "") -> Decimal | None:
        qs = cls.objects.filter(categorie=categorie, actif=True)
        if reference_externe:
            specifique = qs.filter(reference_externe=str(reference_externe)).first()
            if specifique:
                return specifique.montant
        generique = qs.filter(reference_externe="").first()
        return generique.montant if generique else None


class Facture(TimeStampedModel):
    class Statut(models.TextChoices):
        BROUILLON = "BROUILLON", _("Brouillon")
        EMISE = "EMISE", _("Émise")
        PARTIELLE = "PARTIELLE", _("Partiellement réglée")
        REGLEE = "REGLEE", _("Réglée")
        ANNULEE = "ANNULEE", _("Annulée")

    reference = models.CharField(_("référence"), max_length=20, unique=True,
                                 editable=False)
    patient = models.ForeignKey("patients.Patient", on_delete=models.PROTECT,
                                related_name="factures", verbose_name=_("patient"))
    patient_assure = models.ForeignKey(
        "assurances.PatientAssure", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="factures", verbose_name=_("couverture appliquée"),
    )
    date_emission = models.DateField(_("date d'émission"), default=date.today)
    date_echeance = models.DateField(_("échéance"), null=True, blank=True)
    statut = models.CharField(_("statut"), max_length=10, choices=Statut.choices,
                              default=Statut.BROUILLON)

    montant_total = models.DecimalField(_("montant total"), max_digits=12,
                                        decimal_places=2, default=0)
    taux_couverture_applique = models.DecimalField(
        _("taux de couverture appliqué (%)"), max_digits=5, decimal_places=2, default=0)
    part_assurance = models.DecimalField(_("part assurance"), max_digits=12,
                                         decimal_places=2, default=0)
    part_patient = models.DecimalField(_("part patient"), max_digits=12,
                                       decimal_places=2, default=0)
    notes = models.CharField(_("notes"), max_length=255, blank=True)
    motif_annulation = models.CharField(_("motif d'annulation"), max_length=255, blank=True)

    class Meta:
        verbose_name = _("facture")
        verbose_name_plural = _("factures")
        ordering = ["-date_emission", "-cree_le"]
        indexes = [
            models.Index(fields=["statut", "date_echeance"]),
            models.Index(fields=["patient", "-date_emission"]),
        ]

    def __str__(self) -> str:
        return f"{self.reference} — {self.patient.nom_complet}"

    def save(self, *args, **kwargs):
        if not self.reference:
            annee = date.today().year
            base = f"FACT-{annee}-"
            dernier = (Facture.objects.filter(reference__startswith=base)
                       .aggregate(m=Max("reference")).get("m"))
            seq = int(dernier.split("-")[-1]) + 1 if dernier else 1
            self.reference = f"{base}{seq:06d}"
        if not self.date_echeance:
            self.date_echeance = (self.date_emission
                                  + timedelta(days=DELAI_ECHEANCE_JOURS))
        super().save(*args, **kwargs)

    # -- montants ---------------------------------------------------------
    @property
    def montant_regle(self) -> Decimal:
        total = Decimal("0")
        for p in self.paiements.all():
            total += -p.montant if p.est_remboursement else p.montant
        return total

    @property
    def reste_a_payer(self) -> Decimal:
        return max(Decimal("0"), self.montant_total - self.montant_regle)

    @property
    def regle_par_patient(self) -> Decimal:
        return sum((p.montant for p in self.paiements.all()
                    if p.payeur == Paiement.Payeur.PATIENT and not p.est_remboursement),
                   Decimal("0"))

    @property
    def reste_patient(self) -> Decimal:
        return max(Decimal("0"), self.part_patient - self.regle_par_patient)

    @property
    def en_retard(self) -> bool:
        return (self.statut in {self.Statut.EMISE, self.Statut.PARTIELLE}
                and self.date_echeance is not None
                and self.date_echeance < date.today())

    def recalculer_totaux(self, *, sauvegarder=True):
        self.montant_total = (self.lignes.aggregate(s=Sum("montant")).get("s")
                              or Decimal("0"))
        assure = self.patient_assure
        if assure and assure.couvert_a(self.date_emission):
            taux = assure.taux_effectif
            brute = (self.montant_total * taux / Decimal("100")).quantize(Decimal("1."))
            restant = assure.plafond_restant(self.date_emission.year)
            if restant is not None:
                # on exclut la part déjà comptée pour cette facture
                restant += self.part_assurance
                brute = min(brute, max(Decimal("0"), restant))
            self.taux_couverture_applique = taux
            self.part_assurance = brute
        else:
            self.taux_couverture_applique = Decimal("0")
            self.part_assurance = Decimal("0")
        self.part_patient = self.montant_total - self.part_assurance
        if sauvegarder:
            self.save(update_fields=["montant_total", "taux_couverture_applique",
                                     "part_assurance", "part_patient", "modifie_le"])

    def rafraichir_statut(self, *, sauvegarder=True):
        if self.statut in {self.Statut.BROUILLON, self.Statut.ANNULEE}:
            return
        regle = self.montant_regle
        if regle >= self.montant_total and self.montant_total > 0:
            self.statut = self.Statut.REGLEE
        elif regle > 0:
            self.statut = self.Statut.PARTIELLE
        else:
            self.statut = self.Statut.EMISE
        if sauvegarder:
            self.save(update_fields=["statut", "modifie_le"])


class LigneFacture(models.Model):
    facture = models.ForeignKey(Facture, on_delete=models.CASCADE, related_name="lignes",
                                verbose_name=_("facture"))
    type_source = models.CharField(_("origine"), max_length=16,
                                   choices=TypeSource.choices, default=TypeSource.AUTRE)
    source_id = models.PositiveIntegerField(_("identifiant de l'acte"), null=True,
                                            blank=True)
    libelle = models.CharField(_("libellé"), max_length=200)
    quantite = models.DecimalField(_("quantité"), max_digits=10, decimal_places=2,
                                   default=1)
    prix_unitaire = models.DecimalField(_("prix unitaire"), max_digits=12,
                                        decimal_places=2)
    montant = models.DecimalField(_("montant"), max_digits=12, decimal_places=2,
                                  default=0)

    class Meta:
        verbose_name = _("ligne de facture")
        verbose_name_plural = _("lignes de facture")
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.libelle} — {self.montant}"

    def save(self, *args, **kwargs):
        self.montant = (self.quantite * self.prix_unitaire).quantize(Decimal("1."))
        super().save(*args, **kwargs)


class Paiement(models.Model):
    class Mode(models.TextChoices):
        ESPECES = "ESPECES", _("Espèces")
        MOBILE_MONEY = "MOBILE_MONEY", _("Mobile money")
        VIREMENT = "VIREMENT", _("Virement bancaire")
        CHEQUE = "CHEQUE", _("Chèque")
        CARTE = "CARTE", _("Carte bancaire")

    class Payeur(models.TextChoices):
        PATIENT = "PATIENT", _("Patient")
        ASSURANCE = "ASSURANCE", _("Assurance")

    reference = models.CharField(_("référence"), max_length=20, unique=True,
                                 editable=False)
    facture = models.ForeignKey(Facture, on_delete=models.PROTECT,
                                related_name="paiements", verbose_name=_("facture"))
    montant = models.DecimalField(_("montant"), max_digits=12, decimal_places=2)
    mode = models.CharField(_("mode"), max_length=14, choices=Mode.choices,
                            default=Mode.ESPECES)
    payeur = models.CharField(_("payeur"), max_length=10, choices=Payeur.choices,
                              default=Payeur.PATIENT)
    est_remboursement = models.BooleanField(_("remboursement"), default=False)
    reference_transaction = models.CharField(_("référence de transaction"), max_length=80,
                                             blank=True)
    date_paiement = models.DateTimeField(_("date"), default=timezone.now)
    encaisse_par = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                     null=True, blank=True, related_name="+")
    commentaire = models.CharField(_("commentaire"), max_length=255, blank=True)

    class Meta:
        verbose_name = _("paiement")
        verbose_name_plural = _("paiements")
        ordering = ["-date_paiement"]

    def __str__(self) -> str:
        signe = "-" if self.est_remboursement else "+"
        return f"{self.reference} {signe}{self.montant} ({self.get_mode_display()})"

    def save(self, *args, **kwargs):
        if not self.reference:
            annee = date.today().year
            base = f"PAY-{annee}-"
            dernier = (Paiement.objects.filter(reference__startswith=base)
                       .aggregate(m=Max("reference")).get("m"))
            seq = int(dernier.split("-")[-1]) + 1 if dernier else 1
            self.reference = f"{base}{seq:06d}"
        super().save(*args, **kwargs)


class Relance(models.Model):
    class Canal(models.TextChoices):
        TELEPHONE = "TELEPHONE", _("Téléphone")
        SMS = "SMS", _("SMS")
        COURRIER = "COURRIER", _("Courrier")
        EMAIL = "EMAIL", _("Courriel")
        GUICHET = "GUICHET", _("Au guichet")

    facture = models.ForeignKey(Facture, on_delete=models.CASCADE, related_name="relances")
    date_relance = models.DateTimeField(_("date"), default=timezone.now)
    canal = models.CharField(_("canal"), max_length=10, choices=Canal.choices,
                             default=Canal.TELEPHONE)
    commentaire = models.CharField(_("commentaire"), max_length=255, blank=True)
    par = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                            null=True, blank=True, related_name="+")

    class Meta:
        verbose_name = _("relance")
        verbose_name_plural = _("relances")
        ordering = ["-date_relance"]

    def __str__(self) -> str:
        return f"{self.facture.reference} — {self.get_canal_display()} ({self.date_relance:%d/%m/%Y})"
