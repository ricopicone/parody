"""Licensed third-party figures (permission=permission) must not ship their image
in the public media tree — on public pages the renderer shows a print-only
placeholder, so a staged image would be a rights leak reachable by URL."""
from parody.build import _rights_withheld_refs


def _artifact(preview, fig_html):
    return {"chapters": [{"sections": [
        {"slug": "s", "preview": preview, "html": fig_html}]}]}


SINGLE = ('<figure id="fig:x" class="figure">'
          "<img src=\"{% media 'lic-img' %}\" data-permission=\"permission\">"
          "<figcaption>Licensed.</figcaption></figure>")

SUBFIG = ('<figure id="fig:m" class="figure subfigures" data-permission="permission">'
          "<figure id=\"fig:a\" class=\"subfigure\"><img src=\"{% media 'panel-a' %}\">"
          "<figcaption>A.</figcaption></figure>"
          "<figure id=\"fig:b\" class=\"subfigure\"><img src=\"{% media 'panel-b' %}\">"
          "<figcaption>B.</figcaption></figure>"
          '<figcaption class="subfigures-caption">Both.</figcaption></figure>')


def test_single_rights_image_withheld_on_public_page():
    assert _rights_withheld_refs(_artifact(None, SINGLE)) == {"lic-img"}


def test_subfigure_rights_panels_all_withheld_on_public_page():
    assert _rights_withheld_refs(_artifact(None, SUBFIG)) == {"panel-a", "panel-b"}


def test_rights_image_kept_on_preview_page():
    # gated/preview sections show the real figure to the owner — keep the image
    assert _rights_withheld_refs(_artifact(True, SINGLE)) == set()
    assert _rights_withheld_refs(_artifact(True, SUBFIG)) == set()


def test_non_rights_figure_untouched():
    plain = ('<figure id="fig:y" class="figure">'
             "<img src=\"{% media 'free-img' %}\"><figcaption>Free.</figcaption></figure>")
    assert _rights_withheld_refs(_artifact(None, plain)) == set()
