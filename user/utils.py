# user/utils.py

def set_exam_session(request, profile):
    """
    Sets request.session['exam'] in the format 'EXAMNAME YEAR'
    Logic:
      - If both exam_date and exam_year exist → take year from exam_date.
      - If only exam_year → use that.
      - If only exam_date → derive year from it.
    """
    exam_display = ""

    if profile and profile.exam:
        exam_name = getattr(profile.exam, "name", str(profile.exam))

        # --- Derive the correct year ---
        year = None
        if profile.exam_date and profile.exam_year:
            year = profile.exam_date.year  # prefer exam_date's year
        elif profile.exam_date:
            year = profile.exam_date.year
        elif profile.exam_year:
            year = profile.exam_year

        # --- Build display string ---
        exam_display = f"{exam_name} {year}" if year else exam_name

    request.session["exam"] = exam_display.upper() if exam_display else ""
