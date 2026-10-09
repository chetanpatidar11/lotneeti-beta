"""Resolve current GMP from fresh enabled source observations."""

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from statistics import median

from django.utils import timezone

from ipos.gmp_policy import current_gmp_policy
from ipos.models import GMPObservation, GMPProviderState
from ipos.overrides import effective_ipo_values
from ipos.provider_health import active_provider_override


@dataclass(frozen=True)
class EffectiveGMP:
    observation: GMPObservation
    value_per_share: Decimal
    source_count: int = 1
    source_conflict: bool = False
    corrected: bool = False

    @property
    def observed_at(self):
        return self.observation.observed_at

    @property
    def fetched_at(self):
        return self.observation.fetched_at

    @property
    def source_key(self):
        return (
            self.observation.source_key if self.corrected or self.source_count == 1 else "consensus"
        )

    @property
    def source_url(self):
        return self.observation.source_url if self.source_count == 1 else ""


@dataclass(frozen=True)
class GMPResolution:
    effective: EffectiveGMP | None
    fresh_observations: tuple[GMPObservation, ...]
    stale_source_keys: tuple[str, ...]
    source_conflict: bool

    @property
    def source_count(self) -> int:
        return len(self.fresh_observations)

    @property
    def minimum(self) -> Decimal | None:
        return min((item.value_per_share for item in self.fresh_observations), default=None)

    @property
    def maximum(self) -> Decimal | None:
        return max((item.value_per_share for item in self.fresh_observations), default=None)

    @property
    def median(self) -> Decimal | None:
        values = [item.value_per_share for item in self.fresh_observations]
        return median(values) if values else None

    @property
    def latest_observed_at(self):
        return max((item.observed_at for item in self.fresh_observations), default=None)


def effective_observation_value(observation: GMPObservation, *, at=None):
    now = at or timezone.now()
    correction = (
        observation.overrides.filter(resumed_at__isnull=True, expires_at__gt=now)
        .order_by("-created_at", "-id")
        .first()
    )
    if correction is not None:
        return correction.value_per_share
    state = GMPProviderState.objects.filter(provider_key=observation.source_key).first()
    if state is not None:
        override = active_provider_override(state, at=now)
        if override is not None:
            return override
    return observation.value_per_share


def resolve_gmp(ipo, *, at=None) -> GMPResolution:
    now = at or timezone.now()
    policy = current_gmp_policy()
    states = {state.provider_key: state for state in GMPProviderState.objects.all()}
    latest_by_source = {}
    for observation in ipo.gmp_observations.all():
        latest_by_source.setdefault(observation.source_key, observation)

    fresh = []
    stale = []
    limit = timedelta(hours=policy.freshness_hours)
    for source_key, observation in sorted(latest_by_source.items()):
        state = states.get(source_key)
        if state is not None and not state.enabled:
            continue
        age = now - observation.observed_at
        if timedelta(0) <= age < limit:
            fresh.append(observation)
        else:
            stale.append(source_key)

    if not fresh:
        return GMPResolution(None, (), tuple(stale), False)

    raw_values = [observation.value_per_share for observation in fresh]
    upper_price = effective_ipo_values(ipo)["upper_price"]
    source_conflict = (
        len(fresh) >= 2
        and (max(raw_values) - min(raw_values)) * Decimal("100") / upper_price
        >= policy.conflict_threshold_percent_points
    )

    # Founder corrections take precedence; source disagreement still uses immutable raw values.
    observation_corrections = []
    provider_corrections = []
    for observation in fresh:
        correction = (
            observation.overrides.filter(resumed_at__isnull=True, expires_at__gt=now)
            .order_by("-created_at", "-id")
            .first()
        )
        if correction is not None:
            observation_corrections.append(
                (
                    correction.created_at,
                    observation.source_key,
                    correction.value_per_share,
                    observation,
                )
            )
        state = states.get(observation.source_key)
        provider_value = active_provider_override(state, at=now) if state is not None else None
        if provider_value is not None:
            provider_corrections.append(
                (state.updated_at, observation.source_key, provider_value, observation)
            )
    corrections = observation_corrections or provider_corrections
    if corrections:
        _, _, value, representative = max(corrections)
    else:
        value = median(raw_values)
        representative = min(fresh, key=lambda item: (item.observed_at, str(item.pk)))

    effective = EffectiveGMP(
        observation=representative,
        value_per_share=value,
        source_count=len(fresh),
        source_conflict=source_conflict,
        corrected=bool(corrections),
    )
    return GMPResolution(effective, tuple(fresh), tuple(stale), source_conflict)


def latest_effective_gmp(ipo, *, at=None):
    return resolve_gmp(ipo, at=at).effective
