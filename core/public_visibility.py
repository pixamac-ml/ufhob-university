from unidecode import unidecode

from .models import School


def school_code_is_hidden(code):
    """Match legacy links independently of database accent/case collation."""
    wanted = unidecode(code).upper()
    return any(
        unidecode(hidden).upper() == wanted
        for hidden in School.objects.exclude(pk__in=School.objects.public()).values_list("code", flat=True)
    )
