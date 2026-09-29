"""Invitation d'un membre du personnel : e-mail avec identifiant et lien de première connexion.

Le mot de passe n'est jamais envoyé par e-mail (une boîte mail est trop souvent
partagée, transférée ou piratée) : l'e-mail contient l'identifiant et un lien à
usage unique qui permet à la personne de choisir elle-même son mot de passe,
puis la connecte directement.
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import translation
from django.utils.crypto import constant_time_compare
from django.utils.encoding import force_bytes
from django.utils.http import base36_to_int, urlsafe_base64_encode

VALIDITE_INVITATION_JOURS = 7


class InvitationTokenGenerator(PasswordResetTokenGenerator):
    """Jeton d'invitation : même mécanique que la réinitialisation, mais valable 7 jours.

    Un nouvel employé n'ouvre pas forcément son e-mail dans l'heure. Le jeton est
    invalidé dès que le mot de passe est choisi (ou l'adresse e-mail modifiée),
    et un jeton de réinitialisation ne peut pas servir d'invitation (sel distinct).
    """

    key_salt = "apps.accounts.invitation"

    def check_token(self, user, token):
        if not (user and token):
            return False
        try:
            ts_b36, _ = token.split("-")
            ts = base36_to_int(ts_b36)
        except ValueError:
            return False
        for secret in [self.secret, *self.secret_fallbacks]:
            if constant_time_compare(self._make_token_with_timestamp(user, ts, secret), token):
                break
        else:
            return False
        return (self._num_seconds(self._now()) - ts) <= VALIDITE_INVITATION_JOURS * 86400


generateur_invitation = InvitationTokenGenerator()


def envoyer_invitation(utilisateur, request) -> None:
    """Envoie l'e-mail d'invitation (lève une exception si l'envoi échoue)."""
    uid = urlsafe_base64_encode(force_bytes(utilisateur.pk))
    jeton = generateur_invitation.make_token(utilisateur)
    langue = utilisateur.langue_preferee or settings.LANGUAGE_CODE
    with translation.override(langue):
        contexte = {
            "utilisateur": utilisateur,
            "hopital": utilisateur.etablissement.nom if utilisateur.etablissement_id else "Kènèya Sô",
            "lien": request.build_absolute_uri(reverse("accounts:invitation", args=[uid, jeton])),
            "lien_connexion": request.build_absolute_uri(reverse("accounts:login")),
            "validite_jours": VALIDITE_INVITATION_JOURS,
        }
        sujet = " ".join(render_to_string("registration/invitation_objet.txt", contexte).split())
        corps = render_to_string("registration/invitation_email.txt", contexte)
    send_mail(sujet, corps, None, [utilisateur.email])


def tenter_invitation(utilisateur, request) -> bool:
    """Comme ``envoyer_invitation``, mais n'échoue jamais : journalise et renvoie False si
    l'envoi a échoué (SMTP indisponible, adresse refusée…) au lieu de laisser l'exception
    remonter — le compte reste créé, l'appelant décide comment prévenir l'utilisateur."""
    try:
        envoyer_invitation(utilisateur, request)
    except Exception:
        logging.getLogger(__name__).exception("Échec d'envoi de l'invitation à %s", utilisateur.pk)
        return False
    return True
