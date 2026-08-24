from django.urls import path

from .views import (
    AdminUpgradePlanListView, AdminUpgradePlanUpdateView,
    PaymentCreateView, PaymentProviderListView, PaymentProviderUpdateView,
    PaymentVerifyView, UpgradePlanListView,
)

urlpatterns = [
    path("admin/platform/payment-providers/", PaymentProviderListView.as_view()),
    path("admin/platform/payment-providers/<int:pk>/", PaymentProviderUpdateView.as_view()),
    path("admin/platform/upgrade-plans/", AdminUpgradePlanListView.as_view()),
    path("admin/platform/upgrade-plans/<int:pk>/", AdminUpgradePlanUpdateView.as_view()),
    path("billing/payments/", PaymentCreateView.as_view()),
    path("billing/payments/verify/", PaymentVerifyView.as_view()),
    path("billing/upgrade-plans/", UpgradePlanListView.as_view()),
]
