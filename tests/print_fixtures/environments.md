# Print Environments {#sec-env shortid="sec:envs"}

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

![A figure caption naming `a.out`.](figures/plot.png){#fig:plot figwidth="3in"}

![A pgf figure, rtc-style extensionless src.](figures/wave){#fig:wave .pgf}

![A pgf figure, src carrying the extension.](figures/pulse.pgf){#fig:pulse .pgf}

![A bare pgf image outside a figure div, classless.](figures/spike.pgf)

::: {#fig:subs .figure .subfigures rows=1}
![Left.](figures/plot.png){#fig:sub-a .subfigure}

![Right.](figures/plot.png){#fig:sub-b .subfigure}

(a) The left plot and (b) the right plot.
:::

1. first
2. second
