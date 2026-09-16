from django.urls import path

from .views import AssetCatalogView, UserAssetHoldingDetailView, UserAssetHoldingListCreateView


urlpatterns = [
    path("catalog/", AssetCatalogView.as_view(), name="asset-catalog"),
    path("holdings/", UserAssetHoldingListCreateView.as_view(), name="asset-holding-list-create"),
    path("holdings/<int:pk>/", UserAssetHoldingDetailView.as_view(), name="asset-holding-detail"),
]

