"""
Aide à la décision du suivi prénatal : signes de danger relevés lors d'une visite.

Les alertes sont **non bloquantes** et ne remplacent pas le jugement clinique : elles
rappellent à la sage-femme les seuils usuels (OMS / protocoles nationaux) et la conduite
attendue — orienter vers un médecin ou vers la structure de référence.
"""

from __future__ import annotations

from decimal import Decimal

from django.utils.translation import gettext_lazy as _

from apps.consultations.services import NIVEAU_ATTENTION, NIVEAU_DANGER, NIVEAU_INFO

from .models import ConsultationPrenatale as CPN

# Seuils usuels
TA_SYSTOLIQUE_HTA, TA_DIASTOLIQUE_HTA = 140, 90            # hypertension gravidique
TA_SYSTOLIQUE_SEVERE, TA_DIASTOLIQUE_SEVERE = 160, 110     # hypertension sévère
HB_ANEMIE, HB_ANEMIE_SEVERE = Decimal("11"), Decimal("7")  # g/dL
BCF_MIN, BCF_MAX = 110, 160                                # battements par minute
FIEVRE = Decimal("38")
SA_ECOUTE_BCF = 20        # avant ce terme, l'absence de BCF au stéthoscope n'a rien d'anormal
SA_PRESENTATION = 36      # au-delà, une présentation non céphalique se prépare
BANDELETTE_POSITIVE = {CPN.Bandelette.PLUS1, CPN.Bandelette.PLUS2, CPN.Bandelette.PLUS3}
BANDELETTE_FORTE = {CPN.Bandelette.PLUS2, CPN.Bandelette.PLUS3}

_ORDRE = {NIVEAU_DANGER: 0, NIVEAU_ATTENTION: 1, NIVEAU_INFO: 2}


def _alerte(niveau: str, message) -> dict:
    return {"niveau": niveau, "message": message}


def alertes_visite(visite) -> list[dict]:
    """Signes de danger d'une visite, du plus grave au moins grave."""
    alertes: list[dict] = []
    constantes = visite.constantes

    systolique = getattr(constantes, "tension_systolique", None)
    diastolique = getattr(constantes, "tension_diastolique", None)
    hta_severe = bool((systolique and systolique >= TA_SYSTOLIQUE_SEVERE)
                      or (diastolique and diastolique >= TA_DIASTOLIQUE_SEVERE))
    hta = hta_severe or bool((systolique and systolique >= TA_SYSTOLIQUE_HTA)
                             or (diastolique and diastolique >= TA_DIASTOLIQUE_HTA))
    proteinurie = visite.albuminurie in BANDELETTE_POSITIVE

    if hta and proteinurie:
        alertes.append(_alerte(NIVEAU_DANGER, _("Tension élevée avec albuminurie : suspicion de pré-éclampsie. Orienter d'urgence vers un médecin ou la structure de référence.")))
    elif hta_severe:
        alertes.append(_alerte(NIVEAU_DANGER, _("Hypertension sévère (≥ 160/110). Orienter d'urgence vers un médecin.")))
    elif hta:
        alertes.append(_alerte(NIVEAU_ATTENTION, _("Tension élevée (≥ 140/90) : recontrôler après repos, rechercher albuminurie et œdèmes, avis médical.")))
    elif visite.albuminurie in BANDELETTE_FORTE:
        alertes.append(_alerte(NIVEAU_ATTENTION, _("Albuminurie ≥ ++ : rechercher une infection urinaire ou une pré-éclampsie.")))

    if visite.hemoglobine_g_dl is not None:
        if visite.hemoglobine_g_dl < HB_ANEMIE_SEVERE:
            alertes.append(_alerte(NIVEAU_DANGER, _("Anémie sévère (Hb < 7 g/dL) : référer, envisager une transfusion.")))
        elif visite.hemoglobine_g_dl < HB_ANEMIE:
            alertes.append(_alerte(NIVEAU_ATTENTION, _("Anémie (Hb < 11 g/dL) : fer + acide folique, rechercher paludisme et parasitoses, contrôle de l'hémoglobine.")))

    if visite.terme_sa >= SA_ECOUTE_BCF and visite.bruits_coeur_foetal == CPN.BruitsCoeur.ABSENTS:
        alertes.append(_alerte(NIVEAU_DANGER, _("Bruits du cœur fœtal absents : suspicion de mort fœtale in utero. Référer pour échographie.")))
    if visite.frequence_bcf and not BCF_MIN <= visite.frequence_bcf <= BCF_MAX:
        alertes.append(_alerte(NIVEAU_ATTENTION, _("Fréquence cardiaque fœtale hors de 110–160 bpm : recontrôler, avis médical si elle persiste.")))

    if visite.terme_sa >= SA_PRESENTATION and visite.presentation in {
            CPN.Presentation.SIEGE, CPN.Presentation.TRANSVERSE}:
        alertes.append(_alerte(NIVEAU_ATTENTION, _("Présentation non céphalique à terme : avis médical pour le choix du mode d'accouchement.")))

    temperature = getattr(constantes, "temperature_c", None)
    if temperature is not None and temperature >= FIEVRE:
        alertes.append(_alerte(NIVEAU_ATTENTION, _("Fièvre (≥ 38 °C) : rechercher paludisme et infection urinaire.")))

    if visite.glycosurie in BANDELETTE_POSITIVE:
        alertes.append(_alerte(NIVEAU_ATTENTION, _("Glycosurie positive : dépister un diabète gestationnel (glycémie).")))
    if visite.oedemes and not (hta or proteinurie):
        alertes.append(_alerte(NIVEAU_INFO, _("Œdèmes du visage ou des mains : surveiller la tension et l'albuminurie.")))

    if visite.depistage_vih == CPN.Depistage.POSITIF:
        alertes.append(_alerte(NIVEAU_ATTENTION, _("Dépistage VIH positif : prise en charge PTME, orienter vers le service de référence.")))
    if visite.depistage_syphilis == CPN.Depistage.POSITIF:
        alertes.append(_alerte(NIVEAU_ATTENTION, _("Dépistage de la syphilis positif : traitement de la patiente et du partenaire.")))

    return sorted(alertes, key=lambda a: _ORDRE[a["niveau"]])


def alertes_dossier(dossier) -> list[dict]:
    """Alertes de la dernière visite + celles qui tiennent au dossier lui-même."""
    alertes: list[dict] = []
    derniere = dossier.derniere_visite
    if derniere:
        alertes.extend(alertes_visite(derniere))
    if dossier.dpa_depassee:
        alertes.append(_alerte(NIVEAU_ATTENTION, _("Date prévue d'accouchement dépassée : avis médical, surveillance du terme dépassé.")))
    if dossier.rdv_manque:
        alertes.append(_alerte(NIVEAU_ATTENTION, _("Rendez-vous manqué : relancer la patiente.")))
    return sorted(alertes, key=lambda a: _ORDRE[a["niveau"]])
