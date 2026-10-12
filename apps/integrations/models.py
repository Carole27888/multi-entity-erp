from django.db import models
from django.utils import timezone


class OutboundMessage(models.Model):
    """Every SMS / WhatsApp message the platform sends (or would send, with the mock provider).

    organization is empty for platform messages such as sign-up codes. Tenant screens filter by organization.
    """

    class Channel(models.TextChoices):
        SMS = "sms", "SMS"
        WHATSAPP = "whatsapp", "WhatsApp"

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"

    organization = models.ForeignKey("tenancy.Organization", null=True, blank=True, on_delete=models.CASCADE, related_name="+")
    channel = models.CharField(max_length=10, choices=Channel.choices)
    to = models.CharField(max_length=20)
    body = models.TextField()
    provider = models.CharField(max_length=30)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.QUEUED)
    provider_ref = models.CharField(max_length=100, blank=True)
    error = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.channel} → {self.to}"
