"""How each language is typeset in a twin (task #825).

Per language:
- ``preamble``: the language package. babel with ``shorthands=off`` for
  de/fr/es, since active characters would break key-value options. ctex for
  Chinese, luatexko for Korean.
- ``names``: the words parody's boxes and problems print.
- ``cref``: the words a cross-reference prints.
- ``notes``: the two markers for text that is untranslated or stale.

``twin_preamble`` turns one entry into LaTeX for the twin document.
"""

import shutil
import subprocess

_BOXES = ("parodydefinitionname", "parodytheoremname", "parodylemmaname",
          "parodycorollaryname", "parodypropositionname", "parodyexamplename",
          "parodyboxname", "parodyproblemname", "parodylabexercisename",
          "parodylabsolutionname")


def _names(*words):
    return dict(zip(_BOXES, words))


def _cref(**pairs):
    return pairs


TWIN_LANGUAGES = {
    "de": {
        "preamble": "\\usepackage[ngerman,shorthands=off]{babel}",
        "names": _names("Definition", "Satz", "Lemma", "Korollar", "Proposition",
                        "Beispiel", "Kasten", "Aufgabe", "Laborübung", "Laborlösung"),
        "extra_names": {},
        "cref": _cref(figure=("Abbildung", "Abbildungen"), table=("Tabelle", "Tabellen"),
                      equation=("Gleichung", "Gleichungen"), section=("Abschnitt", "Abschnitte"),
                      chapter=("Kapitel", "Kapitel"), definition=("Definition", "Definitionen"),
                      theorem=("Satz", "Sätze"), lemma=("Lemma", "Lemmata"),
                      corollary=("Korollar", "Korollare"), proposition=("Proposition", "Propositionen"),
                      examplectr=("Beispiel", "Beispiele"), infoboxctr=("Kasten", "Kästen"),
                      exercise=("Aufgabe", "Aufgaben"), labexercise=("Aufgabe", "Aufgaben"),
                      listingctr=("Listing", "Listings"), algorithmctr=("Algorithmus", "Algorithmen")),
        "capitalised": True,
        "notes": {"untranslated": "Englisch: noch nicht übersetzt",
                  "stale": "kann vom Englischen abweichen"},
    },
    "fr": {
        "preamble": "\\usepackage[french,shorthands=off]{babel}",
        "names": _names("Définition", "Théorème", "Lemme", "Corollaire", "Proposition",
                        "Exemple", "Encadré", "Problème", "Exercice de laboratoire",
                        "Solution de laboratoire"),
        "extra_names": {},
        "cref": _cref(figure=("figure", "figures"), table=("tableau", "tableaux"),
                      equation=("équation", "équations"), section=("section", "sections"),
                      chapter=("chapitre", "chapitres"), definition=("définition", "définitions"),
                      theorem=("théorème", "théorèmes"), lemma=("lemme", "lemmes"),
                      corollary=("corollaire", "corollaires"), proposition=("proposition", "propositions"),
                      examplectr=("exemple", "exemples"), infoboxctr=("encadré", "encadrés"),
                      exercise=("problème", "problèmes"), labexercise=("problème", "problèmes"),
                      listingctr=("listing", "listings"), algorithmctr=("algorithme", "algorithmes")),
        "capitalised": False,
        "notes": {"untranslated": "anglais : pas encore traduit",
                  "stale": "peut différer de l’anglais"},
    },
    "es": {
        "preamble": "\\usepackage[spanish,es-noshorthands,shorthands=off]{babel}",
        "names": _names("Definición", "Teorema", "Lema", "Corolario", "Proposición",
                        "Ejemplo", "Recuadro", "Problema", "Ejercicio de laboratorio",
                        "Solución de laboratorio"),
        "extra_names": {},
        "cref": _cref(figure=("figura", "figuras"), table=("tabla", "tablas"),
                      equation=("ecuación", "ecuaciones"), section=("sección", "secciones"),
                      chapter=("capítulo", "capítulos"), definition=("definición", "definiciones"),
                      theorem=("teorema", "teoremas"), lemma=("lema", "lemas"),
                      corollary=("corolario", "corolarios"), proposition=("proposición", "proposiciones"),
                      examplectr=("ejemplo", "ejemplos"), infoboxctr=("recuadro", "recuadros"),
                      exercise=("problema", "problemas"), labexercise=("problema", "problemas"),
                      listingctr=("listado", "listados"), algorithmctr=("algoritmo", "algoritmos")),
        "capitalised": False,
        "notes": {"untranslated": "inglés: aún sin traducir",
                  "stale": "puede diferir del inglés"},
    },
    "zh": {
        "preamble": ("\\usepackage[fontset=none,heading=false,scheme=plain]{ctex}\n"
                     "\\setCJKmainfont{%(font)s}\n\\setCJKsansfont{%(font)s}\n\\setCJKmonofont{%(font)s}"),
        "fonts": ("Noto Serif CJK SC", "Source Han Serif SC", "Songti SC"),
        "names": _names("定义", "定理", "引理", "推论", "命题", "例", "框", "习题",
                        "实验练习", "实验解答"),
        "extra_names": {"figurename": "图", "tablename": "表", "chaptername": "章",
                        "contentsname": "目录"},
        "cref": _cref(figure=("图", "图"), table=("表", "表"), equation=("式", "式"),
                      section=("节", "节"), chapter=("章", "章"), definition=("定义", "定义"),
                      theorem=("定理", "定理"), lemma=("引理", "引理"), corollary=("推论", "推论"),
                      proposition=("命题", "命题"), examplectr=("例", "例"), infoboxctr=("框", "框"),
                      exercise=("习题", "习题"), labexercise=("习题", "习题"),
                      listingctr=("代码", "代码"), algorithmctr=("算法", "算法")),
        "capitalised": True,
        "notes": {"untranslated": "英文：尚未翻译", "stale": "可能与英文不一致"},
    },
    "ko": {
        "preamble": "\\usepackage{luatexko}\n\\setmainhangulfont{%(font)s}\n\\setsanshangulfont{%(font)s}",
        "fonts": ("Noto Serif CJK KR", "Noto Serif KR", "Source Han Serif K", "AppleMyungjo",
                  "Apple SD Gothic Neo"),
        "names": _names("정의", "정리", "보조정리", "따름정리", "명제", "예제", "상자", "문제",
                        "실험 연습", "실험 풀이"),
        "extra_names": {"figurename": "그림", "tablename": "표", "chaptername": "장",
                        "contentsname": "차례"},
        "cref": _cref(figure=("그림", "그림"), table=("표", "표"), equation=("식", "식"),
                      section=("절", "절"), chapter=("장", "장"), definition=("정의", "정의"),
                      theorem=("정리", "정리"), lemma=("보조정리", "보조정리"),
                      corollary=("따름정리", "따름정리"), proposition=("명제", "명제"),
                      examplectr=("예제", "예제"), infoboxctr=("상자", "상자"),
                      exercise=("문제", "문제"), labexercise=("문제", "문제"),
                      listingctr=("코드", "코드"), algorithmctr=("알고리즘", "알고리즘")),
        "capitalised": True,
        "notes": {"untranslated": "영어: 아직 번역되지 않음", "stale": "영어 원문과 다를 수 있음"},
    },
}


def _installed_families():
    """Font family names fontconfig knows (what luaotfload can find by name)."""
    if not shutil.which("fc-list"):
        return set()
    out = subprocess.run(["fc-list", ":", "family"], capture_output=True, text=True).stdout
    return {name.strip() for line in out.splitlines() for name in line.split(",") if name.strip()}


def cjk_font(language):
    """The first installed font for a CJK language; RuntimeError naming them otherwise."""
    candidates = TWIN_LANGUAGES[language]["fonts"]
    installed = _installed_families()
    for name in candidates:
        if name in installed:
            return name
    raise RuntimeError(
        f"no font for {language} twins: install one of {', '.join(candidates)} "
        "(Noto CJK: https://github.com/notofonts/noto-cjk; not part of TeX Live)")


def _cap(word):
    return word[:1].upper() + word[1:]


def twin_preamble(language):
    """LaTeX for a twin document's preamble in ``language``, after the profile's own."""
    spec = TWIN_LANGUAGES[language]
    preamble = spec["preamble"]
    if "fonts" in spec:
        preamble = preamble % {"font": cjk_font(language)}
    lines = [preamble, "\\usepackage{parody-twin}"]
    for macro, word in spec["names"].items():
        lines.append(f"\\renewcommand{{\\{macro}}}{{{word}}}")
    lines.append("\\xsimsetup{exercise/name=\\parodyproblemname, labexercise/name=\\parodyproblemname}")
    for macro, word in spec["extra_names"].items():
        lines.append(f"\\AtBeginDocument{{\\renewcommand{{\\{macro}}}{{{word}}}}}")
    for counter, (one, many) in spec["cref"].items():
        lines.append(f"\\crefname{{{counter}}}{{{one}}}{{{many}}}")
        lines.append(f"\\Crefname{{{counter}}}{{{_cap(one)}}}{{{_cap(many)}}}")
    notes = spec["notes"]
    lines.append(f"\\renewcommand{{\\parodytwinuntranslatedtext}}{{{notes['untranslated']}}}")
    lines.append(f"\\renewcommand{{\\parodytwinstaletext}}{{{notes['stale']}}}")
    return "\n".join(lines)
