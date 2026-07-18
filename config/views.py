from django.http import JsonResponse

def home(request):
    return JsonResponse({
        "status": "ok",
        "project": "Trading API",
        "version": "1.0"
    })