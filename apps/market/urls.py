from django.urls import path

from .views import CryptoSnapshotView, EconomicCalendarView, MarketChartView, MarketNewsView, QuoteView

urlpatterns = [
    path("quotes/", QuoteView.as_view(), name="market-quotes"),
    path("crypto-snapshot/", CryptoSnapshotView.as_view(), name="crypto-snapshot"),
    path("charts/", MarketChartView.as_view(), name="market-charts"),
    path("economic-calendar/", EconomicCalendarView.as_view(), name="economic-calendar"),
    path("news/", MarketNewsView.as_view(), name="market-news"),
]
