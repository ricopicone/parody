---
title: Overview
slug: overview
id: sec-overview
---

Welcome to *$title*. This sample section demonstrates the core authoring
constructs; replace it with real content.

## Prose, math, and cross-references {#getting-started}

Inline math like $$E = mc^2$$ and display math both render via MathJax on
the web and LaTeX in print:

$$\frac{d}{dt}\left(\frac{\partial L}{\partial \dot{q}}\right) - \frac{\partial L}{\partial q} = 0$$ {#eq:euler-lagrange}

## Executed code

Jupytext Python files execute at build time; their output (including
figures) is captured into the document:

```{.include-py path="example_code.py"}
```

## Exercises and solutions

Solutions live alongside exercises in the source and are extracted into a
separate, access-controlled part of the artifact at build time:

::: {.exercise #exe:sample title="A sample exercise"}
Show that the sample exercise machinery works.

::: {.exercise-solution}
It does: this solution is stripped from the public section body and carried
separately in the artifact (`parody build --help` for visibility options).
:::

:::
