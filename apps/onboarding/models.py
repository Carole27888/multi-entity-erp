from django.conf import settings
from django.db import models
from django.utils import timezone


class OnboardingSession(models.Model):
    """Progress through the set-up wizard, so it can be resumed on any device.

    Global (the organization is only created at the first step); always read through the signed-in user.
    """

    STEPS = ["business", "industry", "niche", "team", "modules", "sample", "invite"]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="onboarding_sessions")
    organization = models.OneToOneField("tenancy.Organization", null=True, blank=True, on_delete=models.CASCADE,
                                        related_name="onboarding")
    step = models.CharField(max_length=20, default="business")
    data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user} · {self.step}"

    @property
    def step_index(self) -> int:
        return self.STEPS.index(self.step) if self.step in self.STEPS else 0

    def reached(self, step: str) -> bool:
        return step in self.STEPS and self.STEPS.index(step) <= self.data.get("_furthest", 0)

    def go_to(self, step: str) -> None:
        self.step = step
        idx = self.STEPS.index(step)
        self.data["_furthest"] = max(self.data.get("_furthest", 0), idx)
