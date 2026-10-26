
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import generics, serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from fusion_auth.permissions import HasPermission
from modules.elm.api.serializers import (
    LeaveDecisionSerializer,
    LeaveRequestCreateSerializer,
    LeaveRequestSerializer,
    SubstituteResponseSerializer,
)
from modules.elm.models import LeaveRequest
from modules.elm.services import workflow


@extend_schema(responses=LeaveRequestSerializer(many=True))
class LeaveRequestListView(generics.ListAPIView):
    serializer_class = LeaveRequestSerializer
    permission_classes = [
        IsAuthenticated,
        HasPermission("elm.application.view_self"),
    ]

    def get_queryset(self):
        return LeaveRequest.objects.filter(
            employee_id=self.request.principal.user_id
        ).order_by("-created_at")


class LeaveRequestCreateView(generics.CreateAPIView):
    serializer_class = LeaveRequestCreateSerializer
    permission_classes = [
        IsAuthenticated,
        HasPermission("elm.application.apply"),
    ]

    def perform_create(self, serializer):
        substitute_required = serializer.validated_data.get(
            "substitute_required", False
        )
        initial_status = (
            LeaveRequest.Status.AWAITING_SUBSTITUTE
            if substitute_required
            else LeaveRequest.Status.UNIT_HEAD_REVIEW
        )
        serializer.save(
            employee_id=self.request.principal.user_id,
            status=initial_status,
        )


class LeaveRequestActionView(APIView):
    def get_leave_request(self, pk):
        return get_object_or_404(
            LeaveRequest.objects.select_for_update(),
            pk=pk,
        )


class LeaveRequestWithdrawView(LeaveRequestActionView):
    permission_classes = [
        IsAuthenticated,
        HasPermission("elm.application.withdraw"),
    ]

    @transaction.atomic
    def post(self, request, pk):
        leave_request = self.get_leave_request(pk)
        updated = workflow.withdraw_leave(
            leave_request,
            request.principal,
        )
        return Response(
            LeaveRequestSerializer(updated).data,
            status=status.HTTP_200_OK,
        )


class SubstituteResponseView(LeaveRequestActionView):
    permission_classes = [
        IsAuthenticated,
        HasPermission("elm.substitute.respond"),
    ]

    @transaction.atomic
    def post(self, request, pk):
        serializer = SubstituteResponseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        leave_request = self.get_leave_request(pk)
        updated = workflow.respond_to_substitute(
            leave_request,
            request.principal,
            serializer.validated_data["decision"],
            serializer.validated_data.get("note", ""),
        )
        return Response(
            LeaveRequestSerializer(updated).data,
            status=status.HTTP_200_OK,
        )


class LeaveDecisionView(LeaveRequestActionView):
    permission_classes = [
        IsAuthenticated,
        HasPermission("elm.application.review"),
    ]

    @transaction.atomic
    def post(self, request, pk):
        serializer = LeaveDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        if data["stage"] == "establishment":
            if not request.principal.has_permission(
                "elm.establishment.route"
            ):
                from core.api.exceptions import PermissionDeniedError
                raise PermissionDeniedError(
                    "Establishment routing permission is required.",
                    code="permission_denied",
                )

        leave_request = self.get_leave_request(pk)
        updated = workflow.decide_leave(
            leave_request,
            request.principal,
            data["stage"],
            data["decision"],
            data.get("note", ""),
        )
        return Response(
            LeaveRequestSerializer(updated).data,
            status=status.HTTP_200_OK,
        )
