"""SMS behind a service interface. The mock stores the message and sends nothing; the real provider is used
automatically once its credentials are in .env (SMS_PROVIDER=africastalking, AT_USERNAME, AT_API_KEY).
WhatsApp, email templates and per-organization credentials are added in phase 2."""

from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request

from django.conf import settings

from .models import OutboundMessage

logger = logging.getLogger(__name__)


class SMSService:
    name = "base"
    is_live = False

    def send(self, to: str, body: str, organization=None) -> OutboundMessage:
        msg = OutboundMessage.objects.create(channel=OutboundMessage.Channel.SMS, to=to, body=body, provider=self.name,
                                             organization=organization)
        try:
            msg.provider_ref = self._deliver(to, body) or ""
            msg.status = OutboundMessage.Status.SENT
        except Exception as exc:  # noqa: BLE001 - recorded on the message
            msg.status, msg.error = OutboundMessage.Status.FAILED, str(exc)[:255]
            logger.warning("SMS to %s failed: %s", to, exc)
        msg.save(update_fields=["status", "provider_ref", "error"])
        return msg

    def _deliver(self, to: str, body: str) -> str:
        raise NotImplementedError


class MockSMS(SMSService):
    name = "mock"
    is_live = False

    def _deliver(self, to, body):
        logger.info("[mock SMS] to %s: %s", to, body)
        return "mock"


class AfricasTalkingSMS(SMSService):
    name = "africastalking"
    is_live = True
    URL = "https://api.africastalking.com/version1/messaging"

    def __init__(self, username: str, api_key: str, sender_id: str = ""):
        self.username, self.api_key, self.sender_id = username, api_key, sender_id

    def _deliver(self, to, body):
        data = {"username": self.username, "to": to, "message": body}
        if self.sender_id:
            data["from"] = self.sender_id
        req = urllib.request.Request(self.URL, data=urllib.parse.urlencode(data).encode(), headers={
            "apiKey": self.api_key, "Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"})
        with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310 - fixed https URL
            payload = json.loads(resp.read().decode())
        recipients = payload.get("SMSMessageData", {}).get("Recipients", [])
        if not recipients or recipients[0].get("status") != "Success":
            raise RuntimeError(f"Africa's Talking: {payload}")
        return recipients[0].get("messageId", "")


def sms() -> SMSService:
    cfg = settings.INTEGRATIONS
    if cfg.get("SMS_PROVIDER") == "africastalking" and cfg.get("AT_USERNAME") and cfg.get("AT_API_KEY"):
        return AfricasTalkingSMS(cfg["AT_USERNAME"], cfg["AT_API_KEY"], cfg.get("AT_SENDER_ID", ""))
    return MockSMS()
