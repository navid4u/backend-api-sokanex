from django.urls import path

from .views import EconomicCalendarView, QuoteView

urlpatterns = [
    path("quotes/", QuoteView.as_view(), name="market-quotes"),
    path("economic-calendar/", EconomicCalendarView.as_view(), name="economic-calendar"),
]
