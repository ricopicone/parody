---
title: Voltage dividers
slug: voltage-dividers
id: lec:voltage_dividers
hash: o5
---

# Voltage dividers {#lec:voltage_dividers h="o5"}

In [uy]{.hashref} we'll learn about how to approach circuit
analysis in a systematic way. For now, we'll limp along unsystematically
with our toolbelt of concepts and equations in order to introduce some
more circuit elements, concepts, and theorems. But we can't resist just
a bit of circuit analysis now.

The [voltage divider]{.keyword} is a ubiquitous and useful circuit. In a
sense, it's less of a circuit and more of concept. For resistors, that
concept can be stated as the following.

> The voltage across resistors in series is [divided among the resistors]{.cloze}.

An immediately useful result is that we can "divide voltage" into any
smaller voltage we like by putting in a couple resistors.

![a simple voltage divider
circuit.](notebooks/electronics/voltage-dividers-voltage_divider_demo.pdf){#fig:voltage_divider_demo
width="60%"}

In order to show *how* the voltage divider "divides up" the voltage, we
must do some basic circuit analysis. Consider the circuit in
[@fig:voltage_divider_demo]. The input voltage $v_\text{in}$ is divided
into $v_{R_1}$ and $v_{R_2} = v_\text{out}$. We want to know
$v_\text{out}$ as a function of $v_\text{in}$ and parameters $R_1$ and
$R_2$. Let's write down the equations we know from the laws of Kirchhoff
and Ohm: $$\begin{aligned}
  v_{R_1} &= i_{R_1} R_1, \\
  v_{R_2} &= i_{R_2} R_2, \\
  v_\text{in} &= \cloze{v_{R_1} + v_{R_2}},\text{ and} \\
  i_{R_1} &= \cloze{i_{R_2}}.\end{aligned}$$
We've already established that $v_\text{out} = v_{R_2}$, so we can solve
for $v_{R_2}$ in ($*$). We want to eliminate the three "unknown"
variables $v_{R_1}$, $i_{R_1}$, and $i_{R_2}$, so it is good that we
have four equations.[^3] We begin with ($*$b) and proceed by
substitution of the others of ($*$): $$\begin{aligned}
  v_{R_2} &= i_{R_2} R_2 \\
  &= i_{R_1} R_2 \\
  &= \cloze{\frac{R_2} {R_1} v_{R_1}} \\
  &= \cloze{\frac{R_2} {R_1} \left( v_\text{in} - v_{R_2} \right)} \ \Rightarrow \\
  v_{R_2} + \frac{R_2} {R_1} v_{R_2} &= \frac{R_2} {R_1} v_\text{in} \ \Rightarrow \\
  v_{R_2} &= \cloze{\frac{R_2/R_1} {1+R_2/R_1} v_\text{in}} \ \Rightarrow \\
  &= \cloze{\frac{R_2} {R_1+R_2} v_\text{in}}.\end{aligned}$$

[^3]: Alternatively, we could solve for all four unknown variables with
    our four equations.

Nice! So we can now write the input-output relationship for a
two-resistor voltage divider.

::: definition

For a voltage $v_\text{in}$ split across two resistors $R_1$ and $R_2$ in series, the voltage divider equation is
$$v_{R_2} = \cloze{\frac{R_2}{R_1+R_2}} v_\text{in}$$
for $R_2$ or
$$v_{R_1} = \cloze{\frac{R_1}{R_1+R_2}} v_\text{in}$$
for $R_1$.

:::

So the voltage divider had the effect of dividing the input voltage into
a fraction governed by the relationship between [the relative resistances]{.cloze}
of the two resistors. This fraction takes values in the interval
[$[0,1]$]{.cloze}. Now, whenever we see the voltage divider circuit, we can just
remember this easy formula!

Similarly, for $n$ resistors in series, it can be shown that the voltage
divider relationship is as follows.

::: definition

For a voltage $v_\text{in}$ split across $n$ resistors $R_1$, $R_2$, $\cdots$, $R_n$ in series, the voltage divider equation is
$$v_{R_m} = \left( R_m \middle/ \cloze{\sum_{k=1}^n R_k} \right) v_\text{in}$$
for resistor $R_m$.

:::
