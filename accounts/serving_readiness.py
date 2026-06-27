"""Read-only serving-readiness evaluator (SERVING-READINESS.1B).

Computes, on demand, whether a user's `ChurchMemberRecord` facts satisfy a
configurable `ServingReadinessPolicy`. The result is warning-only and advisory:

- It is never stored as a boolean (no `eligible_for_formal_serving`).
- It never creates a `ChurchMemberRecord` or any assignment.
- It never reads `ChurchStructureMembership` (or any legacy small-group /
  district / ministry-context model) to infer facts.
- It never grants permissions or capabilities.

Belonging stays `ChurchStructureMembership`; serving stays
`TeamAssignmentMember` / `BibleStudyMeetingRole`. This module only reads policy
rows, requirement rows, and the user's global member record.
"""

from dataclasses import dataclass, field
from typing import List, Optional

from accounts.models import (
    ChurchMemberRecord,
    ServingReadinessPolicy,
    ServingReadinessRequirement,
)

# Result status labels.
STATUS_READY = "ready"
STATUS_PENDING = "pending"
STATUS_NO_RECORD = "no_record"
STATUS_NO_POLICY = "no_policy"
STATUS_INACTIVE_USER = "inactive_user"

# Bilingual operational, non-shaming overall warnings.
NO_RECORD_WARNING = {
    "en": (
        "No church member record is on file yet, so serving readiness cannot be "
        "confirmed."
    ),
    "zh": "尚未建立教会成员记录，暂时无法确认服事预备情况。",
}
INACTIVE_USER_WARNING = {
    "en": "This account is inactive, so serving readiness was not evaluated.",
    "zh": "该账号未启用，暂不评估服事预备情况。",
}


@dataclass
class ServingReadinessCheck:
    """One evaluated requirement within a readiness result."""

    requirement_type: str
    severity: str
    accepted_statuses: List[str]
    current_status: Optional[str]
    passed: bool
    label: str
    message: str

    @property
    def is_required(self):
        return self.severity == ServingReadinessRequirement.SEVERITY_REQUIRED


@dataclass
class ServingReadinessResult:
    """Structured, warning-only readiness outcome (never a stored boolean)."""

    is_ready: bool
    status: str
    warnings: List[str] = field(default_factory=list)
    missing_requirements: List[ServingReadinessCheck] = field(default_factory=list)
    passed_requirements: List[ServingReadinessCheck] = field(default_factory=list)
    policy_used: Optional[ServingReadinessPolicy] = None
    record: Optional[ChurchMemberRecord] = None


def _normalize_language(language):
    return "en" if language == "en" else "zh"


def _resolve_default_policy():
    return (
        ServingReadinessPolicy.objects.filter(is_default=True, is_active=True)
        .order_by("sort_order", "code")
        .first()
    )


def _current_status_for(record, requirement_type):
    if record is None:
        return None
    if requirement_type == ServingReadinessRequirement.REQUIREMENT_FAITH_STATEMENT:
        return record.faith_statement_status
    if requirement_type == ServingReadinessRequirement.REQUIREMENT_BAPTISM:
        return record.baptism_status
    return None


def _requirement_warning(check, language):
    if check.message:
        return check.message
    # Operational fallback when a requirement has no configured message.
    if language == "en":
        return f"{check.label}: not yet satisfied."
    return f"{check.label}：尚未满足。"


def get_serving_readiness(user, context=None, policy=None, language="en"):
    """Resolve the applicable policy and evaluate readiness for ``user``.

    ``context`` is accepted for forward compatibility (future per-ministry or
    per-unit-type policy selection) but is not used to select a policy in V1.

    When ``policy`` is not supplied, the active default policy is resolved. If
    none exists, a neutral ``no_policy`` result is returned (``is_ready=True``,
    no warnings) so unconfigured churches are never spammed.

    An explicitly passed ``policy`` is honored even if inactive (the caller has
    explicitly requested it); auto-resolution only ever selects active defaults.
    """
    language = _normalize_language(language)

    if policy is None:
        policy = _resolve_default_policy()

    if policy is None:
        return ServingReadinessResult(
            is_ready=True,
            status=STATUS_NO_POLICY,
            policy_used=None,
            record=None,
        )

    return evaluate_serving_readiness(user, policy, language=language)


def evaluate_serving_readiness(user, policy, language="en"):
    """Evaluate ``user`` against ``policy`` and return a structured result.

    Read-only: never creates a member record or assignment, never reads
    membership, never grants permissions.
    """
    language = _normalize_language(language)

    if policy is None:
        return ServingReadinessResult(
            is_ready=True,
            status=STATUS_NO_POLICY,
            policy_used=None,
            record=None,
        )

    # Inactive / unauthenticated users short-circuit to a neutral, non-shaming
    # result without evaluating facts.
    is_active = bool(user) and bool(getattr(user, "is_active", False))
    if not is_active:
        return ServingReadinessResult(
            is_ready=False,
            status=STATUS_INACTIVE_USER,
            warnings=[INACTIVE_USER_WARNING[language]],
            policy_used=policy,
            record=None,
        )

    requirements = [
        requirement
        for requirement in policy.requirements.filter(is_active=True).order_by(
            "sort_order", "id"
        )
        # Defensive: only evaluate supported fact types.
        if ServingReadinessRequirement.valid_status_codes_for_type(
            requirement.requirement_type
        )
        is not None
    ]

    record = ChurchMemberRecord.objects.filter(user=user).first()

    warnings = []
    missing_requirements = []
    passed_requirements = []
    required_unmet = 0

    for requirement in requirements:
        accepted = sorted(requirement.accepted_status_set())
        current_status = _current_status_for(record, requirement.requirement_type)
        passed = current_status is not None and current_status in accepted

        check = ServingReadinessCheck(
            requirement_type=requirement.requirement_type,
            severity=requirement.severity,
            accepted_statuses=accepted,
            current_status=current_status,
            passed=passed,
            label=requirement.display_label(language),
            message=requirement.display_message(language),
        )

        if passed:
            passed_requirements.append(check)
            continue

        missing_requirements.append(check)
        warnings.append(_requirement_warning(check, language))
        if check.is_required:
            required_unmet += 1

    if record is None:
        # Lead with an operational, non-shaming overall warning.
        warnings.insert(0, NO_RECORD_WARNING[language])
        has_required = any(
            requirement.severity == ServingReadinessRequirement.SEVERITY_REQUIRED
            for requirement in requirements
        )
        return ServingReadinessResult(
            is_ready=not has_required,
            status=STATUS_NO_RECORD,
            warnings=warnings,
            missing_requirements=missing_requirements,
            passed_requirements=passed_requirements,
            policy_used=policy,
            record=None,
        )

    is_ready = required_unmet == 0
    status = STATUS_READY if is_ready else STATUS_PENDING

    return ServingReadinessResult(
        is_ready=is_ready,
        status=status,
        warnings=warnings,
        missing_requirements=missing_requirements,
        passed_requirements=passed_requirements,
        policy_used=policy,
        record=record,
    )
