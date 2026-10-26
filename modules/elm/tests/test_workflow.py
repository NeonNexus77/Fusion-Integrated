
from datetime import date, timedelta

import pytest
from django.core.exceptions import ValidationError

from conftest import make_principal
from core.api.exceptions import PermissionDeniedError
from modules.directory.models import UserRef
from modules.elm.models import LeaveDecision, LeaveRequest, SubstituteResponse
from modules.elm.services import workflow

pytestmark = pytest.mark.django_db

EMPLOYEE_ID = 1001
SUBSTITUTE_ID = 1002
APPROVER_ID = 1003


def make_user(user_id, kind="staff"):
    return UserRef.objects.create(
        user_id=user_id,
        username=f"u{user_id}",
        display_name=f"User {user_id}",
        kind=kind,
    )


def make_leave(employee, substitute=None, status=None, category="EL"):
    data = {
        "employee": employee,
        "category": category,
        "start_date": date.today() + timedelta(days=5),
        "end_date": date.today() + timedelta(days=6),
        "reason": "Personal reasons",
        "substitute": substitute,
        "substitute_required": substitute is not None,
    }
    if status is not None:
        data["status"] = status
    return LeaveRequest.objects.create(**data)


def actor(user_id, *permissions):
    return make_principal(
        user_id=user_id,
        kind="staff",
        roles=("staff",),
        active_role="staff",
        modules=("elm",),
        permissions=permissions,
    )


def test_substitute_acceptance_moves_request_to_unit_head_review():
    employee = make_user(EMPLOYEE_ID)
    substitute = make_user(SUBSTITUTE_ID)
    leave = make_leave(
        employee,
        substitute,
        LeaveRequest.Status.AWAITING_SUBSTITUTE,
    )

    result = workflow.respond_to_substitute(
        leave,
        actor(SUBSTITUTE_ID, "elm.substitute.respond"),
        SubstituteResponse.Decision.ACCEPTED,
    )

    leave.refresh_from_db()
    assert result.pk == leave.pk
    assert leave.status == LeaveRequest.Status.UNIT_HEAD_REVIEW
    assert SubstituteResponse.objects.filter(
        leave_request=leave,
        substitute=substitute,
        decision=SubstituteResponse.Decision.ACCEPTED,
    ).count() == 1


def test_substitute_rejection_returns_request_to_applicant_action():
    employee = make_user(EMPLOYEE_ID)
    substitute = make_user(SUBSTITUTE_ID)
    leave = make_leave(
        employee,
        substitute,
        LeaveRequest.Status.AWAITING_SUBSTITUTE,
    )

    workflow.respond_to_substitute(
        leave,
        actor(SUBSTITUTE_ID, "elm.substitute.respond"),
        SubstituteResponse.Decision.DECLINED,
        "Unable to substitute",
    )

    leave.refresh_from_db()
    assert leave.status == LeaveRequest.Status.APPLICANT_ACTION


def test_another_user_cannot_respond_for_the_substitute():
    employee = make_user(EMPLOYEE_ID)
    substitute = make_user(SUBSTITUTE_ID)
    leave = make_leave(
        employee,
        substitute,
        LeaveRequest.Status.AWAITING_SUBSTITUTE,
    )

    with pytest.raises(ValidationError):
        workflow.respond_to_substitute(
            leave,
            actor(APPROVER_ID, "elm.substitute.respond"),
            SubstituteResponse.Decision.ACCEPTED,
        )

    assert SubstituteResponse.objects.filter(leave_request=leave).count() == 0


def test_substitute_response_requires_permission():
    employee = make_user(EMPLOYEE_ID)
    substitute = make_user(SUBSTITUTE_ID)
    leave = make_leave(
        employee,
        substitute,
        LeaveRequest.Status.AWAITING_SUBSTITUTE,
    )

    with pytest.raises(PermissionDeniedError):
        workflow.respond_to_substitute(
            leave,
            actor(SUBSTITUTE_ID),
            SubstituteResponse.Decision.ACCEPTED,
        )

    assert SubstituteResponse.objects.filter(leave_request=leave).count() == 0


def test_employee_can_withdraw_own_pending_application():
    employee = make_user(EMPLOYEE_ID)
    leave = make_leave(
        employee,
        status=LeaveRequest.Status.UNIT_HEAD_REVIEW,
    )

    workflow.withdraw_leave(
        leave,
        actor(EMPLOYEE_ID, "elm.application.withdraw"),
    )

    leave.refresh_from_db()
    assert leave.status == LeaveRequest.Status.WITHDRAWN


def test_employee_cannot_withdraw_another_employees_application():
    employee = make_user(EMPLOYEE_ID)
    make_user(APPROVER_ID)
    leave = make_leave(
        employee,
        status=LeaveRequest.Status.UNIT_HEAD_REVIEW,
    )

    with pytest.raises(PermissionDeniedError):
        workflow.withdraw_leave(
            leave,
            actor(APPROVER_ID, "elm.application.withdraw"),
        )

    leave.refresh_from_db()
    assert leave.status == LeaveRequest.Status.UNIT_HEAD_REVIEW


def test_withdrawal_requires_permission():
    employee = make_user(EMPLOYEE_ID)
    leave = make_leave(
        employee,
        status=LeaveRequest.Status.UNIT_HEAD_REVIEW,
    )

    with pytest.raises(PermissionDeniedError):
        workflow.withdraw_leave(leave, actor(EMPLOYEE_ID))

    leave.refresh_from_db()
    assert leave.status == LeaveRequest.Status.UNIT_HEAD_REVIEW


def test_invalid_unit_head_decision_does_not_create_audit_record():
    employee = make_user(EMPLOYEE_ID)
    approver = make_user(APPROVER_ID)
    leave = make_leave(
        employee,
        status=LeaveRequest.Status.UNIT_HEAD_REVIEW,
        category="CL",
    )

    with pytest.raises(ValidationError):
        workflow.decide_leave(
            leave,
            actor(APPROVER_ID, "elm.application.review"),
            "unit_head",
            "recommend",
        )

    assert LeaveDecision.objects.filter(leave_request=leave).count() == 0
    leave.refresh_from_db()
    assert leave.status == LeaveRequest.Status.UNIT_HEAD_REVIEW
