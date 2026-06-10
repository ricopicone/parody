# %% [markdown]
# This file is jupytext "percent" format: a plain Python file that executes
# as a notebook at build time. Cells tagged `remove_cell` are dropped from
# the output; call `autofig(caption=..., label=...)` before plotting to
# caption the captured figure.

# %%
import numpy as np

x = np.linspace(0, 2 * np.pi, 200)
print(f"sampled {x.size} points")

# %%
import matplotlib.pyplot as plt

autofig(caption="A sample figure", label="fig:sample-sine")  # noqa: F821
fig, ax = plt.subplots()
ax.plot(x, np.sin(x))
ax.set_xlabel("$x$")
ax.set_ylabel(r"$\sin x$")
plt.show()
