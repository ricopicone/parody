# Print Environments {#sec-env shortid="sec:envs" h="hd"}

Prose with inline math $E = mc^2$, a keyword [important term]{.keyword},
an index entry [convolution]{.index}, a code index entry [printf]{.index .cfun},
a path [/etc/hosts]{.path}, keys [Ctrl+C]{.keys}, a menu [File,Save]{.menu},
a unicode span [λ]{.unicode}, and inline code `x = 1`{.py}.

A citation [@doe2020, p. 3] and a plain cite [doe2020]{.plaincite pre="cf." post="ch. 2"}.
Cross-references: see [@fig:plot; @sec:envs] and a hashref [sec:envs]{.hashref}
and capitalized [sec:envs]{.Hashref} and a line ref [line:5]{.lref}.

A url link: [](https://example.org){.myurl h="ab"} and inline
[](https://example.org){.myurl .inline hash="cd"}.

## Working with `fgets_keypad()` and `main` {#sec-code-head shortid="sec:codehead"}

Heading code spans must not emit verbatim `\mintinline` (fragile in moving
arguments); body inline code like `x = 1`{.py} still does.

::: {.definition #def:limit title="Limit"}
A definition body with math $x \to 0$.
:::

::: {.theorem #thm:big title="Big Theorem"}
Theorem body.
:::

::: {.lemma #lem:small}
Lemma body.
:::

::: {.corollary #cor:tiny}
Corollary body.
:::

::: {.infobox #box:note title="A Note"}
Infobox body.
:::

::: {.freadinglist}
[doe2020]{.plaincite post="ch. 1, an overview"},
[doe2020]{.plaincite post="ch. 2, in depth"}
:::

::: {.exercise #exe:one h="e1" title="First Exercise"}
Exercise statement.

::: {.exercise-solution}
The solution, with display math: \(a + b\).
:::

:::

::: {.example #exm:demo h="x1"}
Example statement.

::: {.example-solution}
Example solution.
:::

:::

::: {.listing #lst:hello caption="Hello in C"}
```c
int main(void) { return 0; }
```
:::

::: {.listing #lst:script .nofloat caption="A script"}
```python
print("hi")
```
:::

::: {.output .execute_result}
    42
:::

```python
def f():
    return 1
```

```arm
MOV r0, #1
```

| Left | Right |
|------|-------|
| a    | b     |

: A caption {#tbl:demo}

<table id="tbl:htmlmath" class="notes-table">
<caption>A raw-HTML table whose cells write math as \(q(t)\).</caption>
<thead><tr><th>\(q(t)\)</th><th>\(e_\infty\)</th></tr></thead>
<tbody><tr><td>\(q^2\)</td><td>\(\dfrac{1}{K_q}\)</td></tr></tbody>
</table>

<table id="tbl:grouped" class="notes-table grouped-header">
<caption>A grouped-header table.</caption>
<thead>
<tr><th rowspan="2" class="cmid cmid-l cmid-r">Row</th><th colspan="2" class="cmid cmid-l cmid-r">Group \(A\)</th></tr>
<tr><th class="cmid cmid-l">Wide Header</th><th class="cmid cmid-r">\(y\)</th></tr>
</thead>
<tbody><tr><td>r1</td><td>\(a\)</td><td>\(b\)</td></tr></tbody>
</table>

![A figure caption naming `a.out`.](figures/plot.png){#fig:plot figwidth="3in"}

![A table that is rendered as an image.](figures/plot.png){#tbl:asimage .figure .standalone}

![A pgf figure, rtc-style extensionless src.](figures/wave){#fig:wave .pgf}

![A pgf figure, src carrying the extension.](figures/pulse.pgf){#fig:pulse .pgf}

![A bare pgf image outside a figure div, classless.](figures/spike.pgf)

::: {#fig:subs .figure .subfigures rows=1}
![Left.](figures/plot.png){#fig:sub-a .subfigure}

![Right.](figures/plot.png){#fig:sub-b .subfigure scale=0.8}

(a) The left plot and (b) the right plot.
:::

1. first
2. second
