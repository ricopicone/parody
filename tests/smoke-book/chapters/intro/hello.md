---
title: Hello
slug: hello
id: hello
---

# Hello {#hello}

A minimal section that exercises the print toolchain end to end: **bold** text,
display math
$$E = mc^2,$$
and inline code `printf()`.

A short code listing drives minted (shell-escape + pygmentize):

```python
def greet(name):
    print(f"hello, {name}")
```

Fill-in-the-blank markup, so the cloze macros are exercised by a real
lualatex run: the damping ratio is [0.707]{.cloze}, and $\tau = \cloze{RC}$.
Sketch the response: []{.blank size=lg}
