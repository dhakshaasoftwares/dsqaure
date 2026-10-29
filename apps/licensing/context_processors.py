def licence(request):
    return {"licence": getattr(request, "licence", None)}
