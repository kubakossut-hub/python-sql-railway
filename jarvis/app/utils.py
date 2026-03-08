"""
Wspólne narzędzia – importowane przez wiele modułów.
"""

import re

# ---------------------------------------------------------------------------
# Wzorce do czyszczenia maili
# Używane przez: python 3 (email_labels), python 4 (email_todo), python 7 (email_clean)
# ---------------------------------------------------------------------------

_QUOTED = [
    re.compile(r"On .+? wrote:.*",                re.DOTALL),
    re.compile(r"^>.*$",                           re.MULTILINE),
    re.compile(r"-{5,}Original Message-{5,}.*",   re.DOTALL | re.IGNORECASE),
    re.compile(r"_{5,}.*",                         re.DOTALL),
    re.compile(r"From:.*?Sent:.*?To:.*?Subject:.*?(?=\n\n)", re.DOTALL | re.IGNORECASE),
]

_FOOTERS = [
    re.compile(r"Sent from (my|the) .+",           re.IGNORECASE),
    re.compile(
        r"(Best regards|Kind regards|Regards|Pozdrawiam|Z poważaniem"
        r"|Dziękuję|Thank you|Thanks)[,.\s].*",
        re.DOTALL | re.IGNORECASE,
    ),
    re.compile(r"\n--\s*\n.*",                     re.DOTALL),
    re.compile(r"\n_{3,}\s*$",                     re.DOTALL),
]


def clean_body(body: str) -> str:
    """
    Czyści treść maila:
    - usuwa cytowane odpowiedzi ('On X wrote:', linie zaczynające się od '>', itd.)
    - usuwa typowe stopki ('Best regards', 'Sent from my iPhone', itd.)
    - przycina nadmiarowe puste linie i whitespace
    """
    for pat in _QUOTED:
        body = pat.sub("", body)
    for pat in _FOOTERS:
        body = pat.sub("", body)
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    return body
