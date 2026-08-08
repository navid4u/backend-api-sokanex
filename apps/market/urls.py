from django.urls import path

from .views import EconomicCalendarView, MarketNewsView, QuoteView

urlpatterns = [
    path("quotes/", QuoteView.as_view(), name="market-quotes"),
    path("economic-calendar/", EconomicCalendarView.as_view(), name="economic-calendar"),
    path("news/", MarketNewsView.as_view(), name="market-news"),
]
