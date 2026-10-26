
from django.urls import path

from modules.elm.api.views import (
    LeaveDecisionView,
    LeaveRequestCreateView,
    LeaveRequestListView,
    LeaveRequestWithdrawView,
    SubstituteResponseView,
)

urlpatterns = [
    path(
        "applications",
        LeaveRequestListView.as_view(),
        name="elm-applications",
    ),
    path(
        "applications/create",
        LeaveRequestCreateView.as_view(),
        name="elm-application-create",
    ),
    path(
        "applications/<int:pk>/withdraw",
        LeaveRequestWithdrawView.as_view(),
        name="elm-application-withdraw",
    ),
    path(
        "applications/<int:pk>/substitute-response",
        SubstituteResponseView.as_view(),
        name="elm-substitute-response",
    ),
    path(
        "applications/<int:pk>/review",
        LeaveDecisionView.as_view(),
        name="elm-application-review",
    ),
]
