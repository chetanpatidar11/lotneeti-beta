import json
from datetime import datetime
from uuid import UUID

from django.contrib import admin
from django.contrib.admin import AdminSite, ModelAdmin
from django.contrib.auth import authenticate, login
from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import path, reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect

from accounts.models import User, Workspace, WorkspaceMembership
from applications.models import Application
from core.audit import record_event
from core.models import AuditEvent, BetaEvent
from funding.models import BankAccount
from ipos.content import publish_content_revision
from ipos.gmp_effective import effective_observation_value, resolve_gmp
from ipos.gmp_overrides import resume_observation_auto, set_observation_override
from ipos.gmp_policy import current_gmp_policy, update_gmp_policy
from ipos.models import (
    IPO,
    GMPObservation,
    GMPProviderState,
    IPOContentVersion,
    IPOFeedBatch,
    IPOFeedObservation,
    IPOFieldOverride,
    IPOProviderSyncState,
    SEBIFiling,
)
from ipos.overrides import (
    OVERRIDABLE_FIELDS,
    effective_ipo_resolution,
    published_ipos,
    resume_ipo_auto,
    set_ipo_override,
)
from ipos.provider_health import (
    clear_provider_override,
    set_provider_enabled,
    set_provider_override,
)
from ipos.tasks import run_ipo_sync
from planner.models import PlannerPolicy, PlanRun
from planner.policies import platform_policy, set_policy
from platform_admin.totp import verify_admin_code


class FounderAdminSite(AdminSite):
    site_header = "LotNeeti staff"
    site_title = "LotNeeti staff"
    index_title = "Platform overview"
    index_template = "platform_admin/index.html"

    def get_urls(self):
        return [
            path("live-data/", self.admin_view(self.live_data), name="live-data"),
            path("ipo-exceptions/", self.admin_view(self.ipo_exceptions), name="ipo-exceptions"),
            path("gmp-policy/", self.admin_view(self.gmp_policy), name="gmp-policy"),
            path("gmp-providers/", self.admin_view(self.gmp_providers), name="gmp-providers"),
            path(
                "gmp-providers/<str:provider_key>/",
                self.admin_view(self.gmp_provider_detail),
                name="gmp-provider-detail",
            ),
            path(
                "gmp-observations/",
                self.admin_view(self.gmp_observations),
                name="gmp-observations",
            ),
            path(
                "gmp-observations/<uuid:observation_id>/",
                self.admin_view(self.gmp_observation_detail),
                name="gmp-observation-detail",
            ),
            path("ai-content/", self.admin_view(self.ai_content), name="ai-content"),
            path(
                "ai-content/<uuid:version_id>/",
                self.admin_view(self.ai_content_detail),
                name="ai-content-detail",
            ),
            path(
                "planner-policies/",
                self.admin_view(self.planner_policies),
                name="planner-policies",
            ),
            path("ipo-overrides/", self.admin_view(self.ipo_overrides), name="ipo-overrides"),
            path(
                "ipo-overrides/<uuid:ipo_id>/",
                self.admin_view(self.ipo_override_detail),
                name="ipo-override-detail",
            ),
            path(
                "support/workspaces/",
                self.admin_view(self.support_workspaces),
                name="support-workspaces",
            ),
            *super().get_urls(),
        ]

    def live_data(self, request):
        sync_result = None
        if request.method == "POST":
            action = request.POST.get("action")
            if action == "sync_investorgain":
                provider = "investorgain"
                sync_result = run_ipo_sync(provider=provider, manual=True)
                record_event(
                    action="admin.provider_manual_refresh",
                    target=request.user,
                    actor=request.user,
                    metadata={"provider": provider},
                )
            else:
                sync_result = {
                    "status": "UNAVAILABLE",
                    "reason": "Provider access is not configured",
                }
        latest = SEBIFiling.objects.order_by("-fetched_at").first()
        sebi_state, _ = IPOProviderSyncState.objects.get_or_create(source_key="sebi")
        return render(
            request,
            "platform_admin/live_data.html",
            {
                "title": "Live data",
                "sync_result": sync_result,
                "latest": latest,
                "sebi_state": sebi_state,
                "nse_state": IPOProviderSyncState.objects.filter(source_key="nse").first(),
                "bse_state": IPOProviderSyncState.objects.filter(source_key="bse").first(),
                "filings": SEBIFiling.objects.all()[:25],
                "published_count": published_ipos().count(),
                "gmp_states": GMPProviderState.objects.all(),
                "gmp_sync_state": IPOProviderSyncState.objects.filter(
                    source_key="investorgain"
                ).first(),
                "gmp_count": GMPObservation.objects.count(),
                "nse_batch_count": IPOFeedBatch.objects.filter(source_key="nse").count(),
                "bse_batch_count": IPOFeedBatch.objects.filter(source_key="bse").count(),
            },
        )

    def gmp_policy(self, request):
        error = ""
        if request.method == "POST":
            try:
                update_gmp_policy(
                    freshness_hours=request.POST.get("freshness_hours"),
                    conflict_threshold_percent_points=request.POST.get(
                        "conflict_threshold_percent_points"
                    ),
                    reason=request.POST.get("reason", ""),
                    actor=request.user,
                )
            except ValidationError as exc:
                error = "; ".join(exc.messages)
            else:
                return HttpResponseRedirect(reverse("founder_admin:gmp-policy"))
        return render(
            request,
            "platform_admin/gmp_policy.html",
            {"title": "GMP policy", "policy": current_gmp_policy(), "error": error},
        )

    def ipo_exceptions(self, request):
        now = timezone.now()
        rows = []
        for ipo in IPO.objects.filter(publication_state=IPO.PublicationState.PUBLISHED).order_by(
            "issuer_name", "id"
        ):
            resolution = resolve_gmp(ipo, at=now)
            ipo_resolution = effective_ipo_resolution(ipo)
            issues = []
            if resolution.effective is None:
                issues.append("GMP stale" if resolution.stale_source_keys else "GMP missing")
            if resolution.stale_source_keys and resolution.effective is not None:
                issues.append("Stale GMP source")
            if resolution.source_conflict:
                issues.append("GMP source conflict")
            if ipo_resolution.exchange_conflict_fields:
                issues.append(
                    "IPO source conflict: " + ", ".join(ipo_resolution.exchange_conflict_fields)
                )
            if ipo_resolution.document_disagreement_fields:
                issues.append(
                    "RHP value differs: " + ", ".join(ipo_resolution.document_disagreement_fields)
                )
            if ipo_resolution.validation_blocked:
                issues.append("IPO source values need review")
            if issues:
                rows.append({"ipo": ipo, "resolution": resolution, "issues": issues})
        return render(
            request,
            "platform_admin/ipo_exceptions.html",
            {"title": "IPO data exceptions", "rows": rows, "policy": current_gmp_policy()},
        )

    def gmp_providers(self, request):
        states = GMPProviderState.objects.order_by("provider_key")
        return render(
            request,
            "platform_admin/gmp_providers.html",
            {"title": "GMP provider health", "states": states},
        )

    def gmp_provider_detail(self, request, provider_key):
        state = get_object_or_404(GMPProviderState, provider_key=provider_key)
        error = ""
        if request.method == "POST":
            try:
                action = request.POST.get("action")
                if action in {"enable", "disable"}:
                    set_provider_enabled(
                        provider_key=provider_key,
                        enabled=action == "enable",
                        reason=request.POST.get("reason", ""),
                        actor=request.user,
                    )
                elif action == "override":
                    expires_at = timezone.make_aware(
                        datetime.fromisoformat(request.POST.get("expires_at", ""))
                    )
                    set_provider_override(
                        provider_key=provider_key,
                        value_per_share=request.POST.get("value_per_share", ""),
                        expires_at=expires_at,
                        reason=request.POST.get("reason", ""),
                        actor=request.user,
                    )
                elif action == "clear":
                    clear_provider_override(provider_key=provider_key, actor=request.user)
                else:
                    raise ValidationError("Choose a provider action")
            except (ValidationError, ValueError) as exc:
                error = "; ".join(exc.messages) if isinstance(exc, ValidationError) else str(exc)
            else:
                return HttpResponseRedirect(
                    reverse("founder_admin:gmp-provider-detail", args=[provider_key])
                )
            state.refresh_from_db()
        return render(
            request,
            "platform_admin/gmp_provider_detail.html",
            {"title": f"GMP provider: {provider_key}", "state": state, "error": error},
        )

    def gmp_observations(self, request):
        query = request.GET.get("q", "").strip()[:100]
        observations = GMPObservation.objects.select_related("ipo").order_by("-observed_at", "-id")
        if query:
            observations = observations.filter(
                Q(ipo__issuer_name__icontains=query) | Q(source_key__icontains=query)
            )
        return render(
            request,
            "platform_admin/gmp_observations.html",
            {
                "title": "GMP source observations",
                "observations": observations[:100],
                "query": query,
            },
        )

    def gmp_observation_detail(self, request, observation_id):
        observation = get_object_or_404(
            GMPObservation.objects.select_related("ipo"), pk=observation_id
        )
        error = ""
        if request.method == "POST":
            try:
                action = request.POST.get("action")
                if action == "set":
                    expires_at = timezone.make_aware(
                        datetime.fromisoformat(request.POST.get("expires_at", ""))
                    )
                    set_observation_override(
                        observation=observation,
                        value_per_share=request.POST.get("value_per_share", ""),
                        expires_at=expires_at,
                        reason=request.POST.get("reason", ""),
                        actor=request.user,
                    )
                elif action == "resume":
                    resume_observation_auto(observation=observation, actor=request.user)
                else:
                    raise ValidationError("Choose an observation action")
            except (ValidationError, ValueError) as exc:
                error = "; ".join(exc.messages) if isinstance(exc, ValidationError) else str(exc)
            else:
                return HttpResponseRedirect(
                    reverse("founder_admin:gmp-observation-detail", args=[observation.pk])
                )
        effective = effective_observation_value(observation)
        active = observation.overrides.filter(resumed_at__isnull=True).first()
        history = observation.overrides.select_related("created_by", "resumed_by")
        freshness_seconds = max(0, int((timezone.now() - observation.observed_at).total_seconds()))
        return render(
            request,
            "platform_admin/gmp_observation_detail.html",
            {
                "title": f"GMP observation: {observation.ipo.issuer_name}",
                "observation": observation,
                "effective": effective,
                "active": active,
                "history": history,
                "freshness_seconds": freshness_seconds,
                "error": error,
            },
        )

    def ai_content(self, request):
        query = request.GET.get("q", "").strip()[:100]
        versions = IPOContentVersion.objects.select_related("ipo").order_by(
            "ipo__issuer_name", "content_type", "-generated_at"
        )
        if query:
            versions = versions.filter(
                Q(ipo__issuer_name__icontains=query)
                | Q(source_document_id__icontains=query)
                | Q(content_type__icontains=query)
            )
        return render(
            request,
            "platform_admin/ai_content.html",
            {"title": "AI content review", "versions": versions[:100], "query": query},
        )

    def ai_content_detail(self, request, version_id):
        version = get_object_or_404(
            IPOContentVersion.objects.select_related("ipo", "reviewed_by"), pk=version_id
        )
        error = ""
        if request.method == "POST":
            try:
                if request.POST.get("action") != "publish":
                    raise ValidationError("Choose a content action")
                publish_content_revision(
                    version=version,
                    text=request.POST.get("text", ""),
                    reason=request.POST.get("reason", ""),
                    actor=request.user,
                )
            except ValidationError as exc:
                error = "; ".join(exc.messages)
            else:
                return HttpResponseRedirect(
                    reverse("founder_admin:ai-content-detail", args=[version.pk])
                )
        return render(
            request,
            "platform_admin/ai_content_detail.html",
            {
                "title": f"AI content: {version.ipo.issuer_name}",
                "version": version,
                "revisions": version.revisions.select_related("created_by"),
                "error": error,
            },
        )

    def planner_policies(self, request):
        error = ""
        if request.method == "POST":
            try:
                scope = request.POST.get("scope", "")
                bank = None
                if scope == PlannerPolicy.Scope.BANK:
                    bank = BankAccount.objects.filter(pk=request.POST.get("bank_id")).first()
                    if bank is None:
                        raise ValidationError("Select a bank for a bank policy")
                effective_from = timezone.make_aware(
                    datetime.fromisoformat(request.POST.get("effective_from", ""))
                )
                until_text = request.POST.get("effective_until", "").strip()
                effective_until = (
                    timezone.make_aware(datetime.fromisoformat(until_text)) if until_text else None
                )
                set_policy(
                    scope=scope,
                    policy=request.POST.get("policy", ""),
                    bank=bank,
                    effective_from=effective_from,
                    effective_until=effective_until,
                    reason=request.POST.get("reason", ""),
                    actor=request.user,
                )
            except (ValidationError, ValueError) as exc:
                error = "; ".join(exc.messages) if isinstance(exc, ValidationError) else str(exc)
            else:
                return HttpResponseRedirect(reverse("founder_admin:planner-policies"))
        try:
            current_global = platform_policy()
        except Exception:
            current_global = "Not configured"
        return render(
            request,
            "platform_admin/planner_policies.html",
            {
                "title": "Planner policies",
                "policies": PlannerPolicy.objects.select_related("bank", "created_by"),
                "banks": BankAccount.objects.select_related("owner").order_by("bank_name", "id"),
                "current_global": current_global,
                "error": error,
            },
        )

    def ipo_overrides(self, request):
        query = request.GET.get("q", "").strip()[:100]
        ipos = IPO.objects.order_by("issuer_name", "id")
        if query:
            ipos = ipos.filter(Q(issuer_name__icontains=query) | Q(symbol__icontains=query))
        return render(
            request,
            "platform_admin/ipo_overrides.html",
            {"title": "IPO field corrections", "ipos": ipos[:50], "query": query},
        )

    def ipo_override_detail(self, request, ipo_id):
        ipo = get_object_or_404(IPO, pk=ipo_id)
        error = ""
        if request.method == "POST":
            field_name = request.POST.get("field_name", "")
            try:
                if request.POST.get("action") == "set":
                    set_ipo_override(
                        ipo=ipo,
                        field_name=field_name,
                        value=request.POST.get("value", ""),
                        reason=request.POST.get("reason", ""),
                        actor=request.user,
                    )
                elif request.POST.get("action") == "resume":
                    resume_ipo_auto(ipo=ipo, field_name=field_name, actor=request.user)
                else:
                    raise ValidationError("Choose a correction action")
            except ValidationError as exc:
                error = "; ".join(exc.messages)
            else:
                return HttpResponseRedirect(
                    reverse("founder_admin:ipo-override-detail", args=[ipo.pk])
                )

        ipo_resolution = effective_ipo_resolution(ipo)
        effective = ipo_resolution.values
        active = {
            item.field_name: item
            for item in IPOFieldOverride.objects.filter(ipo=ipo, resumed_at__isnull=True)
            .select_related("created_by")
            .order_by("field_name")
        }
        fields = [
            {
                "name": name,
                "label": IPO._meta.get_field(name).verbose_name,
                "source": getattr(ipo, name),
                "sources": [
                    {"key": key, "value": value}
                    for key, value in ipo_resolution.fields[name].source_values.items()
                ]
                if name in ipo_resolution.fields
                else [],
                "provenance": ipo_resolution.fields[name].provenance_source
                if name in ipo_resolution.fields
                else ipo.source_key,
                "conflict": ipo_resolution.fields[name].exchange_conflict
                if name in ipo_resolution.fields
                else False,
                "document_disagreement": ipo_resolution.fields[name].document_disagreement
                if name in ipo_resolution.fields
                else False,
                "effective": effective[name],
                "override": active.get(name),
            }
            for name in sorted(OVERRIDABLE_FIELDS)
        ]
        history = IPOFieldOverride.objects.filter(ipo=ipo).select_related(
            "created_by", "resumed_by"
        )
        source_rows = []
        for link in ipo.source_links.order_by("source_key", "source_record_id"):
            snapshot = link.snapshots.first()
            if snapshot is not None:
                source_rows.append(
                    {
                        "link": link,
                        "snapshot": snapshot,
                        "payload": json.dumps(snapshot.payload, indent=2, sort_keys=True),
                    }
                )
        return render(
            request,
            "platform_admin/ipo_override_detail.html",
            {
                "title": f"IPO corrections: {ipo.issuer_name}",
                "ipo": ipo,
                "fields": fields,
                "history": history,
                "source_rows": source_rows,
                "error": error,
            },
        )

    def support_workspaces(self, request):
        query = request.GET.get("q", "").strip()
        results = []
        error = ""
        if query:
            if not 3 <= len(query) <= 100:
                error = "Search with 3 to 100 characters."
            else:
                lookup = Q(name__icontains=query)
                try:
                    lookup |= Q(pk=UUID(query))
                except ValueError:
                    pass
                for workspace in Workspace.objects.filter(lookup).order_by("created_at", "id")[:20]:
                    applications = dict(
                        Application.objects.filter(workspace=workspace)
                        .values_list("status")
                        .annotate(total=Count("id"))
                    )
                    latest_plan = PlanRun.objects.filter(workspace=workspace).first()
                    results.append(
                        {
                            "id": workspace.pk,
                            "name": workspace.name,
                            "created_at": workspace.created_at,
                            "members": workspace.memberships.count(),
                            "investors": workspace.investors.count(),
                            "banks": workspace.banks.count(),
                            "plans": workspace.plan_runs.count(),
                            "applications": sum(applications.values()),
                            "blocked": applications.get(Application.Status.BLOCKED, 0),
                            "allotted": applications.get(Application.Status.ALLOTTED, 0),
                            "latest_plan_status": latest_plan.status if latest_plan else "None",
                        }
                    )
                record_event(
                    action="admin.support_lookup",
                    target=request.user,
                    actor=request.user,
                    metadata={"result_count": len(results)},
                )
        return render(
            request,
            "platform_admin/support_workspaces.html",
            {
                "title": "Workspace support lookup",
                "query": query,
                "results": results,
                "error": error,
            },
        )

    def has_permission(self, request):
        user = request.user
        return (
            user.is_active
            and user.is_staff
            and user.is_founder_admin
            and request.session.get("admin_mfa_verified", False)
        )

    @method_decorator(csrf_protect)
    @method_decorator(never_cache)
    def login(self, request, extra_context=None):
        if self.has_permission(request):
            return HttpResponseRedirect(reverse("founder_admin:index"))

        error = False
        if request.method == "POST":
            email = request.POST.get("email", "").strip().lower()
            password = request.POST.get("password", "")
            code = request.POST.get("code", "")
            user = authenticate(request, username=email, password=password)
            if (
                user is not None
                and user.is_staff
                and user.is_founder_admin
                and verify_admin_code(user, code)
            ):
                login(request, user)
                request.session["admin_mfa_verified"] = True
                request.session.set_expiry(8 * 60 * 60)
                record_event(
                    action="admin.login",
                    target=user,
                    actor=user,
                    metadata={"method": "PASSWORD_TOTP"},
                )
                return HttpResponseRedirect(reverse("founder_admin:index"))
            error = True

        return render(request, "platform_admin/login.html", {"error": error})


founder_admin_site = FounderAdminSite(name="founder_admin")


class ReadOnlyModelAdmin(ModelAdmin):
    def has_view_permission(self, request, obj=None):
        return founder_admin_site.has_permission(request)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(User, site=founder_admin_site)
class UserAdmin(ReadOnlyModelAdmin):
    list_display = ("email", "is_active", "is_staff", "is_founder_admin")
    search_fields = ("email",)


@admin.register(Workspace, site=founder_admin_site)
class WorkspaceAdmin(ReadOnlyModelAdmin):
    list_display = ("name", "owner", "created_at")
    search_fields = ("name", "owner__email")


@admin.register(WorkspaceMembership, site=founder_admin_site)
class WorkspaceMembershipAdmin(ReadOnlyModelAdmin):
    list_display = ("workspace", "user", "role", "created_at")
    search_fields = ("workspace__name", "user__email")


@admin.register(AuditEvent, site=founder_admin_site)
class AuditEventAdmin(ReadOnlyModelAdmin):
    list_display = ("created_at", "action", "actor", "workspace", "object_type", "object_id")
    list_filter = ("action", "created_at")


@admin.register(BetaEvent, site=founder_admin_site)
class BetaEventAdmin(ReadOnlyModelAdmin):
    list_display = ("created_at", "event_type", "workspace")
    list_filter = ("event_type", "created_at")


@admin.register(IPO, site=founder_admin_site)
class IPOAdmin(ReadOnlyModelAdmin):
    list_display = ("issuer_name", "status", "publication_state", "open_date", "close_date")
    list_filter = ("status", "publication_state", "issue_type")
    search_fields = ("issuer_name", "symbol", "source_record_id")


@admin.register(IPOFeedObservation, site=founder_admin_site)
class IPOFeedObservationAdmin(ReadOnlyModelAdmin):
    list_display = ("source_key", "source_record_id", "observed_at", "fetched_at")
    list_filter = ("source_key", "observed_at")
    search_fields = ("source_record_id",)


@admin.register(IPOFeedBatch, site=founder_admin_site)
class IPOFeedBatchAdmin(ReadOnlyModelAdmin):
    list_display = ("source_key", "observed_at", "fetched_at", "payload_hash")
    list_filter = ("source_key", "observed_at")


@admin.register(SEBIFiling, site=founder_admin_site)
class SEBIFilingAdmin(ReadOnlyModelAdmin):
    list_display = ("issuer_name", "document_type", "filing_date", "review_state", "fetched_at")
    search_fields = ("issuer_name", "document_type")


@admin.register(GMPObservation, site=founder_admin_site)
class GMPObservationAdmin(ReadOnlyModelAdmin):
    list_display = ("ipo", "value_per_share", "source_key", "observed_at", "fetched_at")
    list_filter = ("source_key", "observed_at")
    search_fields = ("ipo__issuer_name", "source_record_id")


@admin.register(PlanRun, site=founder_admin_site)
class PlanRunAdmin(ReadOnlyModelAdmin):
    list_display = ("workspace", "status", "planner_version", "planned_total", "generated_at")
    list_filter = ("status", "planner_version")
    search_fields = ("workspace__name",)
