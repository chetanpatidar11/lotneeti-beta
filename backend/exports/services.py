"""Authorize and map a saved plan before any adapter sees sensitive values."""

from django.core.exceptions import ValidationError

from accounts.models import WorkspaceMembership
from core.crypto import decrypt_value
from exports.adapters import ExportArtifact, ExportRegistry, ExportRow
from exports.generic_csv import GenericCSVAdapter
from funding.models import BankAccount, UPIHandle
from investors.models import DematAccount, Investor
from ipos.models import IPO
from planner.export_readiness import assert_exportable_plan
from planner.models import PlanRun

DEFAULT_EXPORT_REGISTRY = ExportRegistry((GenericCSVAdapter(),))


def export_saved_plan(
    *,
    plan_run: PlanRun,
    actor,
    format_id: str = "generic_csv",
    registry: ExportRegistry = DEFAULT_EXPORT_REGISTRY,
) -> ExportArtifact:
    if not WorkspaceMembership.objects.filter(
        workspace=plan_run.workspace,
        user=actor,
        role__in=(WorkspaceMembership.Role.OWNER, WorkspaceMembership.Role.OPERATOR),
    ).exists():
        raise ValidationError("This member cannot export the plan")
    assert_exportable_plan(plan_run)
    plan_rows = list(plan_run.rows.all())
    ipo_ids = {row.ipo_ref for row in plan_rows}
    applicant_ids = {row.applicant_ref for row in plan_rows}
    demat_ids = {row.demat_ref for row in plan_rows}
    bank_ids = {row.bank_ref for row in plan_rows}
    upi_ids = {row.upi_ref for row in plan_rows}
    ipos = {str(item.pk): item for item in IPO.objects.filter(pk__in=ipo_ids)}
    applicants = {
        str(item.pk): item
        for item in Investor.objects.filter(workspace=plan_run.workspace, pk__in=applicant_ids)
    }
    demats = {
        str(item.pk): item
        for item in DematAccount.objects.filter(
            investor__workspace=plan_run.workspace, pk__in=demat_ids
        )
    }
    banks = {
        str(item.pk): item
        for item in BankAccount.objects.filter(workspace=plan_run.workspace, pk__in=bank_ids)
    }
    upis = {
        str(item.pk): item
        for item in UPIHandle.objects.filter(bank__workspace=plan_run.workspace, pk__in=upi_ids)
    }
    output = []
    for row in plan_rows:
        ipo = ipos.get(row.ipo_ref)
        applicant = applicants.get(row.applicant_ref)
        demat = demats.get(row.demat_ref)
        bank = banks.get(row.bank_ref)
        upi = upis.get(row.upi_ref)
        if any(item is None for item in (ipo, applicant, demat, bank, upi)):
            raise ValidationError("A plan mapping is no longer available for export")
        if demat.investor_id != applicant.pk or upi.bank_id != bank.pk:
            raise ValidationError("A plan mapping does not match its applicant or bank")
        output.append(
            ExportRow(
                position=row.position,
                ipo_id=row.ipo_ref,
                ipo_name=ipo.issuer_name,
                applicant_id=row.applicant_ref,
                applicant_name=applicant.name,
                pan=decrypt_value(applicant.pan_ciphertext, purpose="pan"),
                category=row.category,
                lots=row.lots,
                amount=row.amount,
                depository=demat.depository,
                dp_id=decrypt_value(demat.dp_id_ciphertext, purpose="demat"),
                client_id=decrypt_value(demat.client_id_ciphertext, purpose="demat"),
                bank_name=bank.bank_name,
                bank_account_number=decrypt_value(bank.account_ciphertext, purpose="bank-account"),
                upi_handle=decrypt_value(upi.handle_ciphertext, purpose="upi"),
            )
        )
    return registry.render(format_id, tuple(output))
