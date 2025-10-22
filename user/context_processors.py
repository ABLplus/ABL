def exam_context(request):
    exam_value = request.session.get("exam", "")
    return {"exam": exam_value}