# Entropy, Coarse-Graining, and the Conditional Emergence of Arrows

An entropy computed from observations depends on what you group together. If a task records only which room contains a key, all positions within that room produce the same observation. Recording the exact position would make different distinctions. That choice of which detailed states share one observation is the coarse-graining. [MONAD’s formal reference](https://github.com/getHarshOnline/MONAD/blob/main/formal/README.md#contents) locates its entropy-conservation result and hypotheses. An entropy of macrostates depends on the coarse-graining, and any direction of increase needs the boundary conditions and typicality assumptions of the declared model.

## What the laboratory needs, and no more

If you claim that entropy must increase, state the coarse-graining and boundary conditions that make the claim apply. Reckon also has a [spectral-entropy helper](../src/reckon/metrics/spectral.py), which measures a different object: the spectrum of a graph Laplacian. Its edge-list entry builds an undirected graph, computes the selected Laplacian and normalises eigenvalues above its numerical cutoff before taking their entropy. Report the graph, Laplacian choice, cutoff and logarithm base with the value. This graph statistic does not by itself show that physical entropy increased or that an arrow of time emerged.

## Implementation

- [Core module README](../src/reckon/core/README.md): the `CoarseGraining` abstract base class in `channels.py`
