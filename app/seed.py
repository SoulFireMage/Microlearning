r"""Curated seed units: a small, deliberately cross-linked slice of ML maths.

Chosen so the graph has real lateral links across domains (softmax is the
Boltzmann distribution; cross-entropy is entropy plus a KL gap; gradient
descent speed is set by a condition number). References are to real,
canonical works only.
"""
from __future__ import annotations

import sqlite3

from . import services as S

UNITS: list[dict] = [
    {
        "slug": "backprop-chain-rule",
        "title": "Backpropagation is the chain rule, run backwards",
        "domain": "ML Mathematics",
        "l0": r"""Backprop is not a learning rule; it is bookkeeping. A network is a composition $f = f_n \circ \dots \circ f_1$, so by the chain rule $\partial L/\partial x$ is a product of local Jacobians. Multiplying that product **right-to-left from the loss** means one backward pass costs about the same as one forward pass, however many parameters there are.""",
        "l1": r"""**Inputs.** A computation graph of differentiable operations, a scalar loss $L$, and the intermediate values cached during the forward pass.

**Mechanics.** Each node knows only its *local* derivative. Going backwards, every node receives an upstream gradient $\bar{y} = \partial L/\partial y$ and passes $\bar{x} = \bar{y}\,\partial y/\partial x$ to its inputs (a vector–Jacobian product). Where a value feeds several consumers, the incoming gradients **add** (multivariate chain rule).

**Why backwards?** For $L: \mathbb{R}^n \to \mathbb{R}$ with $n$ huge, reverse mode gets the whole gradient in one sweep. Forward mode would need $n$ sweeps (one per input direction). The asymmetry is purely about the shape of the output: one scalar out, millions of parameters in.

**Cost.** Time is a small constant multiple of the forward pass. Memory is the catch: activations must be kept for the backward pass (gradient checkpointing trades recomputation for memory).

**Failure modes.**
- *Vanishing/exploding gradients:* the product of many Jacobians can shrink or blow up geometrically with depth (motivating residual connections, normalisation, careful initialisation).
- *Non-differentiable points* (ReLU at 0): frameworks pick a subgradient by convention.
- *It computes the gradient exactly* (up to floating point); it does not decide what to do with it. That is the optimiser's job.""",
        "l1_pattern": r"""**Shape:** credit assignment as a flow on a graph, run against the arrows.

- Forward pass = values flow from inputs to loss. Backward pass = *sensitivity* flows from loss to inputs, along the same edges reversed.
- Every node is a local exchange rate: "a nudge here becomes this much nudge there." Chain the exchange rates along a path and you get the end-to-end sensitivity; sum over paths where edges fan out.
- **Structural parallel:** dynamic programming. The gradient at a node is reused by everything upstream of it, so you compute it once and cache it, exactly like memoised shortest-path costs. This is why it is cheap.
- **Second parallel:** adjoint methods in optimal control and PDE-constrained optimisation are the same trick for continuous-time systems (Neural ODEs make this explicit).
- **Where the analogy breaks:** DP usually takes a min over paths; backprop takes a *sum* over paths, because derivatives of sums of contributions add.""",
        "l1_steps": r"""1. **Define the composition.** Let $h_1 = f_1(x)$, $h_2 = f_2(h_1)$, $L = f_3(h_2)$. All scalars for now.
2. **Chain rule.** $\dfrac{dL}{dx} = \dfrac{dL}{dh_2}\cdot\dfrac{dh_2}{dh_1}\cdot\dfrac{dh_1}{dx}$.
3. **Order of multiplication.** Compute from the left: start with $\bar h_2 = dL/dh_2$, then $\bar h_1 = \bar h_2 \cdot dh_2/dh_1$, then $\bar x = \bar h_1 \cdot dh_1/dx$. Each "bar" quantity means "derivative of the loss with respect to this".
4. **Worked example.** $x = 2$, $h_1 = x^2 = 4$, $h_2 = 3h_1 = 12$, $L = h_2 + 1 = 13$.
   - $\bar h_2 = 1$.
   - $\bar h_1 = 1 \cdot 3 = 3$.
   - $\bar x = 3 \cdot 2x = 3 \cdot 4 = 12$.
   - Check directly: $L = 3x^2 + 1$, $dL/dx = 6x = 12$. ✓
5. **Vectors.** With vectors, each $dh_{k+1}/dh_k$ is a Jacobian matrix. Starting from the scalar loss means we only ever multiply a *row vector* by a matrix, never matrix by matrix. That is the saving.
6. **Branching.** If $x$ is used twice, e.g. $L = g(x) + k(x)$, then $\bar x = \bar g\,g'(x) + \bar k\,k'(x)$: gradients from each use are added.""",
        "l2": r"""### Formal statement

Let the forward computation be a DAG with nodes $v_1,\dots,v_N$ (inputs first, scalar output $v_N = L$), each $v_j = \phi_j(\{v_i : i \in \mathrm{pa}(j)\})$. Define the *adjoint* $\bar v_i = \partial L/\partial v_i$. Then $\bar v_N = 1$ and, in reverse topological order,

$$\bar v_i = \sum_{j \in \mathrm{ch}(i)} \bar v_j \,\frac{\partial \phi_j}{\partial v_i}.$$

For vector-valued nodes the product is a vector–Jacobian product $\bar{\mathbf v}_i^\top = \sum_j \bar{\mathbf v}_j^\top J_{\phi_j}(\mathbf v_i)$, which is usually computed **without** materialising $J$ (e.g. for $y = Wx$: $\bar x = W^\top \bar y$, $\bar W = \bar y\, x^\top$).

### Forward vs reverse mode

For $F:\mathbb R^n\to\mathbb R^m$, forward mode computes Jacobian–vector products $J\dot x$ (one column-ish per pass, $n$ passes for the full Jacobian); reverse mode computes $\bar y^\top J$ (one row per pass, $m$ passes). Training has $m = 1$, so reverse mode wins by a factor of roughly $n$. The cost of one reverse pass is bounded by a small constant times the forward cost (the "cheap gradient principle"; see Griewank & Walther).

### A minimal reverse-mode engine

```python
class V:
    def __init__(self, val, parents=()):
        self.val, self.parents, self.grad = val, parents, 0.0
    def __add__(s, o): return V(s.val + o.val, [(s, 1.0), (o, 1.0)])
    def __mul__(s, o): return V(s.val * o.val, [(s, o.val), (o, s.val)])
    def backward(self):
        order, seen = [], set()
        def topo(v):
            if id(v) in seen: return
            seen.add(id(v)); [topo(p) for p, _ in v.parents]; order.append(v)
        topo(self); self.grad = 1.0
        for v in reversed(order):
            for p, local in v.parents:
                p.grad += v.grad * local   # sum over consumers

x = V(2.0); L = x * x * V(3.0) + V(1.0); L.backward(); print(x.grad)  # 12.0
```

### Edge cases and practicalities

- **Gradient magnitude through depth:** with $h_{k+1} = \sigma(W_k h_k)$, $\bar h_k = W_k^\top \mathrm{diag}(\sigma'(\cdot))\,\bar h_{k+1}$. The norm of the product of these factors behaves roughly geometrically in depth unless the singular values of each factor sit near 1, which is the motivation for orthogonal/variance-preserving initialisation, normalisation layers and residual connections ($h_{k+1} = h_k + F(h_k)$ adds an identity path to every Jacobian).
- **Memory:** naive reverse mode stores all intermediates: $O(\text{depth})$ memory. Checkpointing stores a subset and recomputes the rest; $O(\sqrt{\text{depth}})$ memory for one extra forward pass is a classic trade-off.
- **Non-smooth ops:** ReLU, max, abs have kinks; autodiff returns a (Clarke) subgradient-like value by convention, which is fine almost everywhere.
- **Numerical checks:** compare against central finite differences $\frac{f(x+\epsilon)-f(x-\epsilon)}{2\epsilon}$ with $\epsilon\approx 10^{-5}$ in float64.

### History

Reverse-mode automatic differentiation predates its neural-network use (Linnainmaa's 1970 thesis is usually cited); its popularisation for training multi-layer networks is Rumelhart, Hinton & Williams (1986).""",
        "probe": (
            "Why is reverse-mode differentiation (backprop) dramatically cheaper than forward mode for training a neural network? Answer in terms of the shapes of inputs and outputs.",
            "Training differentiates a scalar loss with respect to n parameters (n huge). Reverse mode propagates a single row vector (dL/d·) backwards through vector–Jacobian products, getting all n partial derivatives in one pass whose cost is a constant multiple of the forward pass. Forward mode propagates one input direction per pass, so it would need n passes. The asymmetry comes from having one output and many inputs.",
        ),
        "sources": [
            ("reference", "Rumelhart, Hinton & Williams (1986), Learning representations by back-propagating errors, Nature 323", "https://doi.org/10.1038/323533a0"),
            ("reference", "Baydin et al. (2018), Automatic Differentiation in Machine Learning: a Survey, JMLR 18", "https://arxiv.org/abs/1502.05767"),
        ],
    },
    {
        "slug": "gradient-descent",
        "title": "Gradient descent and the condition number",
        "domain": "ML Mathematics",
        "l0": r"""Gradient descent steps against the gradient: $x_{k+1} = x_k - \eta \nabla f(x_k)$. The non-obvious part: its speed is governed less by how far you are from the minimum than by the **shape** of the bowl. A long thin valley (high condition number $\kappa$) forces a small step and zig-zagging, however close you start.""",
        "l1": r"""**Inputs.** A differentiable objective $f$, a starting point, a step size (learning rate) $\eta$.

**Mechanics.** $-\nabla f$ is the direction of steepest local decrease. Take a step of size $\eta$ in that direction and repeat. Near a minimum, $f$ looks like a quadratic $\tfrac12 (x-x^*)^\top H (x-x^*)$ with Hessian $H$.

**The condition number.** Let $H$ have eigenvalues $\mu = \lambda_{\min} \le \dots \le \lambda_{\max} = L$. Stability requires $\eta < 2/L$ (otherwise the steepest direction overshoots and diverges). But progress along the flattest direction is proportional to $\eta\mu$. So the number of steps scales roughly with $\kappa = L/\mu$.

**Trade-offs.**
- *Too large $\eta$:* oscillation or divergence. *Too small:* glacial progress.
- *Stochastic (SGD):* using mini-batch gradients makes each step cheap and noisy; the noise needs a decaying learning rate or averaging to converge, and is often argued to help generalisation (an active research question, not settled).
- *Momentum / Adam:* momentum damps the zig-zag across a valley; Adam rescales per coordinate, which helps when the valley is axis-aligned, and less when it is not.

**Failure modes.** Saddle points and plateaus (gradient ≈ 0 without being at a minimum), ill-conditioning, and non-convex landscapes where only local guarantees hold.""",
        "l2": r"""### Convergence on smooth, strongly convex functions

Assume $f$ is $L$-smooth ($\|\nabla f(x)-\nabla f(y)\| \le L\|x-y\|$) and $\mu$-strongly convex. With $\eta = 1/L$:

$$f(x_k) - f^* \le \left(1 - \frac{\mu}{L}\right)^k \big(f(x_0) - f^*\big).$$

So reaching accuracy $\varepsilon$ takes $O(\kappa \log(1/\varepsilon))$ iterations, $\kappa = L/\mu$. With the best fixed step $\eta = 2/(\mu+L)$ the iterates satisfy $\|x_k - x^*\| \le \left(\frac{\kappa-1}{\kappa+1}\right)^k \|x_0 - x^*\|$.

### Why the quadratic case tells the whole story

For $f(x) = \tfrac12 x^\top H x$ with eigen-decomposition $H = Q\Lambda Q^\top$, write $z = Q^\top x$. Then each coordinate evolves independently:

$$z_i^{(k+1)} = (1 - \eta\lambda_i)\, z_i^{(k)}.$$

Every mode contracts by its own factor $|1-\eta\lambda_i|$. You need $|1-\eta\lambda_{\max}| < 1$, i.e. $\eta < 2/\lambda_{\max}$; then the slowest mode contracts by about $1 - \eta\lambda_{\min} \approx 1 - 1/\kappa$. That single picture explains divergence, zig-zag and slow convergence.

### Momentum fixes the dependence on κ (partially)

Heavy-ball / Nesterov acceleration improves the rate to $O(\sqrt{\kappa}\log(1/\varepsilon))$ on strongly convex smooth problems, which is optimal for first-order methods in the worst case (Nesterov's lower bound).

### Code sketch

```python
import numpy as np
H = np.diag([1.0, 100.0])          # kappa = 100
x = np.array([1.0, 1.0]); eta = 1.9 / 100
for k in range(500):
    x = x - eta * (H @ x)
print(x)  # the lambda=100 mode oscillates in sign but dies fast; the lambda=1 mode crawls
```

### Edge cases

- **Non-convex objectives:** guarantees weaken to reaching a point with small gradient norm, $\min_k \|\nabla f(x_k)\|^2 = O(1/k)$ for $L$-smooth $f$.
- **Saddles:** gradient descent with random initialisation almost surely avoids strict saddles asymptotically (Lee et al., 2016), but can still be slowed by them.
- **Deep nets:** the Hessian changes along the trajectory; observed phenomena such as the sharpness hovering near $2/\eta$ ("edge of stability", Cohen et al., 2021) are empirical findings still being explained.

### Canonical references

Boyd & Vandenberghe, *Convex Optimization* (2004), ch. 9. Nesterov, *Introductory Lectures on Convex Optimization* (2004).""",
        "probe": (
            "On a quadratic bowl with Hessian eigenvalues from μ to L, explain why gradient descent's step size is limited by L but its speed is limited by μ.",
            "In the eigenbasis each coordinate evolves as z ← (1 − ηλ)z. Stability needs |1 − ηL| < 1, so η < 2/L. The flattest direction then shrinks only by about (1 − η μ) ≈ (1 − μ/L) per step. So the number of steps scales with κ = L/μ: the steep direction caps η, the shallow direction sets the pace.",
        ),
        "sources": [
            ("reference", "Boyd & Vandenberghe (2004), Convex Optimization, Cambridge University Press (free PDF from the authors)", "https://web.stanford.edu/~boyd/cvxbook/"),
        ],
    },
    {
        "slug": "softmax",
        "title": "Softmax",
        "domain": "ML Mathematics",
        "l0": r"""Softmax turns arbitrary scores into probabilities: $\sigma(z)_i = e^{z_i}/\sum_j e^{z_j}$. Only **differences** between scores matter (add a constant to all, nothing changes). It is a smooth stand-in for argmax, and it is exactly the Boltzmann distribution from physics with scores playing the role of negative energies.""",
        "l1": r"""**Inputs.** A vector of real scores (logits) $z \in \mathbb R^K$, optionally a temperature $T > 0$.

**Mechanics.** $\sigma(z/T)_i = \exp(z_i/T) / \sum_j \exp(z_j/T)$. Outputs are positive and sum to 1.

**Key properties.**
- *Shift invariance:* $\sigma(z + c\mathbf 1) = \sigma(z)$. Used for numerical stability: subtract $\max_j z_j$ before exponentiating.
- *Temperature:* $T \to 0$ approaches a one-hot argmax (when the max is unique); $T \to \infty$ approaches uniform.
- *Gradient:* $\partial \sigma_i / \partial z_j = \sigma_i(\delta_{ij} - \sigma_j)$. Combined with cross-entropy loss against a target distribution $y$, the gradient with respect to the logits collapses to $\sigma(z) - y$.

**Trade-offs and failure modes.**
- *Overconfidence:* exponentials amplify gaps; modern networks are often poorly calibrated (temperature scaling after training is a standard fix).
- *Saturation:* when one logit dominates, gradients for the others become tiny.
- *Cost:* the normaliser sums over all $K$ classes, which is expensive for huge vocabularies (hence sampled/hierarchical softmax variants).
- *It is not a measure of certainty* in any rigorous sense; it is a normalised exponential of whatever the network learned.""",
        "l1_pattern": r"""**Shape:** exponentiate, then normalise. Turn additive scores into multiplicative odds, then share out a fixed budget of probability.

- **Physics isomorph:** $p_i \propto e^{-E_i/kT}$. Logits are negative energies; temperature is temperature. Low $T$ freezes into the ground state (argmax); high $T$ melts into uniform. Same function, same limits.
- **Invariant:** only score *differences* matter, just as only energy differences matter physically. The normaliser $Z$ is the partition function.
- **Log-space view:** $\log \sigma_i = z_i - \log\sum_j e^{z_j}$. The log-sum-exp is a smooth max, so softmax is "how far below the smooth max is each score".
- **Max-entropy view:** softmax is the distribution of highest entropy given fixed expected scores. It assumes nothing beyond the scores.
- **Where the analogy breaks:** physical energies come from a real Hamiltonian; logits are learned and carry no conserved meaning. Calibration is not guaranteed.""",
        "l1_steps": r"""1. **Start with scores.** $z = (2, 1, 0)$.
2. **Exponentiate** to make them positive: $e^2 \approx 7.389$, $e^1 \approx 2.718$, $e^0 = 1$.
3. **Sum:** $Z \approx 11.107$.
4. **Normalise:** $\sigma \approx (0.665, 0.245, 0.090)$. These sum to 1.
5. **Check shift invariance:** use $z = (102, 101, 100)$. Each exponential gains the same factor $e^{100}$, which cancels in the ratio. Same answer. In code, subtract the max first so you never compute $e^{102}$.
6. **Temperature.** Divide scores by $T = 0.5$: $z/T = (4, 2, 0)$, giving $\approx (0.867, 0.117, 0.016)$: sharper. With $T = 2$: $(1, 0.5, 0)$, giving $\approx (0.506, 0.307, 0.186)$: flatter.
7. **Gradient with cross-entropy.** If the true class is the first one, $y = (1,0,0)$ and the loss is $-\log\sigma_1$. Its gradient with respect to $z$ is $\sigma - y \approx (-0.335, 0.245, 0.090)$: raise the right logit, lower the others in proportion to how much probability they stole.""",
        "l2": r"""### Definition and derivatives

$$\sigma(z)_i = \frac{e^{z_i}}{\sum_{j=1}^K e^{z_j}}, \qquad \frac{\partial \sigma_i}{\partial z_j} = \sigma_i(\delta_{ij} - \sigma_j), \quad J = \mathrm{diag}(\sigma) - \sigma\sigma^\top.$$

$J$ is symmetric positive semi-definite with $J\mathbf 1 = 0$: the null direction is exactly the shift invariance.

With cross-entropy $\ell = -\sum_i y_i \log \sigma_i$ (where $\sum_i y_i = 1$): $\nabla_z \ell = \sigma - y$.

### Log-sum-exp and stable computation

$\log \sigma_i = z_i - \mathrm{LSE}(z)$ with $\mathrm{LSE}(z) = \log\sum_j e^{z_j}$. LSE is convex, satisfies $\max_j z_j \le \mathrm{LSE}(z) \le \max_j z_j + \log K$, and $\nabla \mathrm{LSE} = \sigma$. Compute it as $m + \log\sum_j e^{z_j - m}$ with $m = \max_j z_j$.

```python
import numpy as np
def log_softmax(z):
    m = z.max(axis=-1, keepdims=True)
    return z - m - np.log(np.exp(z - m).sum(axis=-1, keepdims=True))
```

### Variational characterisation

Softmax solves
$$\sigma(z) = \arg\max_{p \in \Delta^{K-1}} \Big( \langle p, z\rangle + H(p) \Big), \quad H(p) = -\sum_i p_i\log p_i,$$
and the optimal value is $\mathrm{LSE}(z)$. With temperature, maximise $\langle p, z\rangle + T H(p)$. As $T\to 0$ the entropy bonus vanishes and the solution becomes the argmax vertex. This is the same Lagrangian that yields the Boltzmann distribution (maximise entropy at fixed mean energy), up to sign conventions.

### Edge cases

- **Ties at $T\to0$:** the limit splits mass uniformly among the tied maxima.
- **Gumbel-max trick:** $\arg\max_i (z_i + g_i)$ with iid standard Gumbel $g_i$ samples exactly from $\sigma(z)$; the Gumbel-softmax relaxation replaces argmax by a tempered softmax for differentiable sampling.
- **Sparsemax / entmax** replace the entropy regulariser with others and can output exact zeros.

### Origins

The name and probabilistic interpretation for network outputs are due to Bridle (1990). The functional form is Boltzmann/Gibbs (19th century) and appears in economics as the multinomial logit (McFadden).""",
        "probe": (
            "Why can you subtract the maximum logit before computing softmax, and what does temperature do in the limits T→0 and T→∞?",
            "Softmax is invariant to adding a constant to every logit, because the common factor e^c cancels between numerator and denominator; subtracting the max avoids overflow. Dividing logits by T: as T→0 the distribution concentrates on the argmax (one-hot if unique), as T→∞ it tends to uniform.",
        ),
        "sources": [
            ("reference", "Bridle (1990), Probabilistic Interpretation of Feedforward Classification Network Outputs, with Relationships to Statistical Pattern Recognition", None),
        ],
    },
    {
        "slug": "shannon-entropy",
        "title": "Shannon entropy",
        "domain": "Information Theory",
        "l0": r"""Entropy $H(X) = -\sum_x p(x)\log_2 p(x)$ is the average number of yes/no questions needed to pin down an outcome, if you ask the best possible questions. It measures **uncertainty in a distribution**, not meaning or disorder in a thing. It is maximal ($\log_2 n$) when all $n$ outcomes are equally likely.""",
        "l1": r"""**Inputs.** A probability distribution $p$ over outcomes. Entropy is a property of the distribution, not of any single outcome.

**Mechanics.** The *surprisal* of an outcome is $-\log p(x)$: rare events carry more information. Entropy is the expected surprisal. Units: bits for $\log_2$, nats for $\ln$.

**Operational meaning (source coding theorem).** The best achievable average code length for symbols drawn iid from $p$ is $H(X)$ bits per symbol in the limit of long blocks; any uniquely decodable code needs at least $H$ on average, and a Huffman code achieves within 1 bit per symbol.

**Properties.**
- $H \ge 0$, with equality iff the outcome is certain.
- $H \le \log n$ for $n$ outcomes, with equality iff uniform.
- Independent variables: $H(X,Y) = H(X) + H(Y)$. In general $H(X,Y) \le H(X)+H(Y)$, the gap being the mutual information.

**Pitfalls.**
- Entropy depends on how outcomes are carved up; for continuous variables, *differential* entropy can be negative and is not invariant to change of variables.
- Estimating entropy from samples is biased (plug-in estimates underestimate it for small samples).
- "Information" here is purely statistical; a random string has maximal entropy and no meaning.""",
        "l2": r"""### Definitions

$$H(X) = -\sum_{x} p(x)\log p(x), \qquad H(Y\mid X) = -\sum_{x,y} p(x,y)\log p(y\mid x),$$
$$I(X;Y) = H(X) - H(X\mid Y) = H(X) + H(Y) - H(X,Y) \ge 0.$$

### Why this formula? (Uniqueness)

Shannon (1948) showed that, up to the choice of logarithm base, $H$ is the unique function satisfying continuity, monotonic growth in $n$ for uniform distributions, and the *grouping* (chain) rule: splitting a choice into successive choices gives the weighted sum of their uncertainties.

### Maximum entropy, derived

Maximise $-\sum_i p_i\log p_i$ subject to $\sum_i p_i = 1$. Lagrangian stationarity gives $-\log p_i - 1 - \lambda = 0$, so all $p_i$ are equal: the uniform distribution. Add a constraint $\sum_i p_i E_i = \bar E$ and the same calculation gives $p_i \propto e^{-\beta E_i}$: the Boltzmann distribution. This is Jaynes's (1957) bridge between information theory and statistical mechanics.

### Worked example

A biased coin with $p = 0.9$: $H = -(0.9\log_2 0.9 + 0.1\log_2 0.1) \approx 0.469$ bits. So long runs of such flips compress to under half a bit per flip.

```python
import numpy as np
def entropy(p, base=2):
    p = np.asarray(p, float); p = p[p > 0]
    return -(p * np.log(p)).sum() / np.log(base)
entropy([0.9, 0.1])  # 0.469
```

### Relation to thermodynamic entropy

Gibbs entropy $S = -k_B\sum_i p_i\ln p_i$ is Shannon entropy in nats times Boltzmann's constant. Whether this formal identity reflects a deep identity of concepts is a long-running debate in the philosophy of physics; the mathematics is not in dispute.

### Canonical references

Shannon (1948), *A Mathematical Theory of Communication*. Cover & Thomas, *Elements of Information Theory* (2nd ed., 2006).""",
        "probe": (
            "What does entropy measure, operationally, and why is the uniform distribution the maximum-entropy one?",
            "Entropy is the expected surprisal −log p(x), operationally the minimum average number of bits (best yes/no questions) needed to encode outcomes drawn from p. Maximising −Σ p log p subject only to Σp = 1 gives equal p_i by Lagrange multipliers, so with n outcomes the maximum is log n, attained by the uniform distribution: no outcome is more predictable than another.",
        ),
        "sources": [
            ("reference", "Shannon (1948), A Mathematical Theory of Communication, Bell System Technical Journal 27", "https://doi.org/10.1002/j.1538-7305.1948.tb01338.x"),
        ],
    },
    {
        "slug": "cross-entropy-kl",
        "title": "Cross-entropy and KL divergence",
        "domain": "Information Theory",
        "l0": r"""Cross-entropy $H(p,q)$ is the average code length when reality follows $p$ but you encode as if it were $q$. It splits exactly: $H(p,q) = H(p) + D_{\mathrm{KL}}(p\,\|\,q)$. Since $H(p)$ is fixed by the data, minimising cross-entropy loss **is** minimising the KL gap, which is also maximum-likelihood estimation.""",
        "l1": r"""**Definitions.** $H(p,q) = -\sum_x p(x)\log q(x)$ and $D_{\mathrm{KL}}(p\|q) = \sum_x p(x)\log\frac{p(x)}{q(x)}$.

**Mechanics.** KL is the *excess* bits paid for using the wrong model. Gibbs' inequality gives $D_{\mathrm{KL}} \ge 0$, with equality iff $p = q$ (almost everywhere).

**In ML.** With one-hot labels, cross-entropy reduces to $-\log q(\text{true class})$: the negative log-likelihood. Averaged over a dataset, minimising it over model parameters is maximum likelihood.

**Asymmetry matters.** $D_{\mathrm{KL}}(p\|q) \ne D_{\mathrm{KL}}(q\|p)$ and KL is not a metric.
- *Forward KL* $D(p\|q)$ (what MLE minimises) punishes $q$ for putting low mass where $p$ has mass: **mass-covering**, tends to over-spread.
- *Reverse KL* $D(q\|p)$ (common in variational inference) punishes $q$ for putting mass where $p$ has little: **mode-seeking**, tends to lock onto one mode.

**Failure modes.**
- If $q(x) = 0$ where $p(x) > 0$, forward KL is infinite (hence label smoothing, clipping, $\epsilon$ in logs).
- KL can be large while samples look fine, and vice versa; it is one lens among several divergences.""",
        "l2": r"""### Decomposition

$$H(p,q) = -\sum_x p\log q = -\sum_x p\log p + \sum_x p\log\frac{p}{q} = H(p) + D_{\mathrm{KL}}(p\|q).$$

### Gibbs' inequality (proof via Jensen)

Since $\log$ is concave, $-D_{\mathrm{KL}}(p\|q) = \sum_x p\log\frac{q}{p} \le \log\sum_x p\frac{q}{p} = \log\sum_{x: p>0} q \le \log 1 = 0$. Equality requires $q/p$ constant on the support of $p$, i.e. $p = q$.

### Cross-entropy as maximum likelihood

With empirical distribution $\hat p = \frac1N\sum_n \delta_{x_n}$ and model $q_\theta$:
$$H(\hat p, q_\theta) = -\frac1N\sum_{n=1}^N \log q_\theta(x_n),$$
the average negative log-likelihood. So $\arg\min_\theta H(\hat p, q_\theta) = \arg\max_\theta \prod_n q_\theta(x_n)$.

### Forward vs reverse, concretely

Let $p$ be an equal mixture of two well-separated Gaussians and $q$ a single Gaussian. Minimising $D(p\|q)$ places $q$ between the modes with large variance (to cover both). Minimising $D(q\|p)$ places $q$ on one mode (to avoid low-$p$ regions). The ELBO in variational inference, $\log p(x) - D_{\mathrm{KL}}(q(z)\,\|\,p(z\mid x))$, uses the reverse direction, which is one reason VI posteriors tend to underestimate variance.

### Softmax + cross-entropy gradient

For logits $z$, $q = \mathrm{softmax}(z)$ and target $y$: $\nabla_z H(y,q) = q - y$. The Jacobian of softmax and the derivative of the log cancel almost perfectly, which is why this pair is the default classifier head.

```python
import numpy as np
def cross_entropy(logits, y):  # y one-hot
    m = logits.max(); lse = m + np.log(np.exp(logits - m).sum())
    return -(y * (logits - lse)).sum()
```

### Canonical references

Kullback & Leibler (1951), *On Information and Sufficiency*, Annals of Mathematical Statistics 22. Cover & Thomas, *Elements of Information Theory*, ch. 2.""",
        "probe": (
            "Show why minimising cross-entropy loss is equivalent to minimising KL divergence from the data distribution, and say which direction of KL that is.",
            "H(p,q) = H(p) + KL(p‖q). The data entropy H(p) does not depend on the model q, so minimising H(p,q) over q minimises KL(p‖q). That is forward KL, which is mass-covering, and with the empirical distribution it equals average negative log-likelihood, i.e. maximum likelihood.",
        ),
        "sources": [
            ("reference", "Kullback & Leibler (1951), On Information and Sufficiency, Annals of Mathematical Statistics 22(1)", "https://doi.org/10.1214/aoms/1177729694"),
        ],
    },
    {
        "slug": "boltzmann-distribution",
        "title": "The Boltzmann distribution",
        "domain": "Statistical Physics",
        "l0": r"""A system in contact with a heat bath at temperature $T$ occupies state $i$ with probability $p_i = e^{-E_i/k_BT}/Z$. Low-energy states are favoured, exponentially, and temperature sets how strongly. It is also the **maximum-entropy** distribution when only the average energy is known: physics and inference giving the same answer.""",
        "l1": r"""**Inputs.** A set of microstates with energies $E_i$, a temperature $T$ (or inverse temperature $\beta = 1/k_BT$).

**Mechanics.** $p_i = e^{-\beta E_i}/Z$ with partition function $Z = \sum_i e^{-\beta E_i}$. Everything thermodynamic falls out of $Z$:
- mean energy $\langle E\rangle = -\partial \ln Z/\partial\beta$,
- free energy $F = -k_BT\ln Z$,
- energy fluctuations $\mathrm{Var}(E) = \partial^2 \ln Z/\partial\beta^2$.

**Two derivations, one answer.**
1. *Physical:* a small system exchanging energy with a much larger reservoir; the reservoir's number of accessible states falls off exponentially with the energy the small system takes.
2. *Inferential (Jaynes):* maximise entropy subject to a fixed mean energy. The Lagrange multiplier for the energy constraint is $\beta$.

**Limits.** $T\to 0$: all probability in the ground state. $T\to\infty$: uniform over states.

**Where it fails.** Systems not in equilibrium; systems not weakly coupled to a bath; quantum indistinguishability at low temperature (Bose–Einstein and Fermi–Dirac statistics replace the classical counting for occupation numbers).

**ML echoes.** Softmax is this distribution with logits as $-\beta E$. Energy-based models, Boltzmann machines, simulated annealing and temperature sampling in language models all borrow it directly.""",
        "l2": r"""### Maximum-entropy derivation

Maximise $S = -\sum_i p_i \ln p_i$ subject to $\sum_i p_i = 1$ and $\sum_i p_i E_i = U$. Lagrangian:
$$\mathcal L = -\sum_i p_i\ln p_i - \alpha\Big(\sum_i p_i - 1\Big) - \beta\Big(\sum_i p_i E_i - U\Big).$$
Setting $\partial\mathcal L/\partial p_i = 0$: $-\ln p_i - 1 - \alpha - \beta E_i = 0 \Rightarrow p_i = e^{-\beta E_i}/Z$. The multiplier $\beta$ is identified with $1/k_BT$ by matching to thermodynamics ($\partial S/\partial U = 1/T$, with $S$ in units of $k_B$).

### Partition function as generating function

$$\frac{\partial \ln Z}{\partial \beta} = -\frac{\sum_i E_i e^{-\beta E_i}}{Z} = -\langle E\rangle, \qquad \frac{\partial^2\ln Z}{\partial\beta^2} = \langle E^2\rangle - \langle E\rangle^2.$$
$\ln Z$ is a cumulant generating function, which is why it is convex in $\beta$. In ML, the same object appears as log-sum-exp.

### Free energy as a variational principle

For any distribution $q$, define $F[q] = \langle E\rangle_q - T S[q]$. Then $F[q] = F + k_BT\, D_{\mathrm{KL}}(q\,\|\,p_{\text{Boltz}})$, so the Boltzmann distribution minimises free energy and the gap is a KL divergence. Variational inference minimises exactly this kind of objective (the negative ELBO is a variational free energy).

### Two-level example

States $E_0 = 0$, $E_1 = \epsilon$. $p_1 = 1/(1 + e^{\beta\epsilon})$, a logistic sigmoid in $-\beta\epsilon$. The sigmoid is the two-class softmax for the same reason.

### Sampling

Metropolis (1953): propose a move, accept with probability $\min(1, e^{-\beta\Delta E})$. The resulting Markov chain has the Boltzmann distribution as its stationary distribution, with no need to compute $Z$. Simulated annealing slowly raises $\beta$ to find low-energy states.

### Canonical references

Jaynes (1957), *Information Theory and Statistical Mechanics*, Physical Review 106. Any standard text, e.g. Reif, *Fundamentals of Statistical and Thermal Physics*.""",
        "probe": (
            "Derive (in outline) why maximising entropy with a fixed average energy gives the Boltzmann distribution. What is the temperature, from this point of view?",
            "Maximise −Σ p ln p subject to Σp = 1 and Σ p E = U with Lagrange multipliers α, β. Stationarity gives ln p_i = −1 − α − βE_i, so p_i ∝ e^{−βE_i}, normalised by Z. The inverse temperature β is the Lagrange multiplier on the energy constraint: how strongly the fixed mean energy constrains the distribution.",
        ),
        "sources": [
            ("reference", "Jaynes (1957), Information Theory and Statistical Mechanics, Physical Review 106", "https://doi.org/10.1103/PhysRev.106.620"),
        ],
    },
    {
        "slug": "scaled-dot-product-attention",
        "title": "Scaled dot-product attention",
        "domain": "ML Mathematics",
        "l0": r"""Attention is a **soft, differentiable dictionary lookup**: each query scores every key by dot product, softmax turns the scores into weights, and the output is the weighted average of the values. $\mathrm{softmax}(QK^\top/\sqrt{d_k})\,V$. The $\sqrt{d_k}$ stops dot products growing with dimension and saturating the softmax.""",
        "l1": r"""**Inputs.** Queries $Q \in \mathbb R^{n\times d_k}$, keys $K \in \mathbb R^{m\times d_k}$, values $V\in\mathbb R^{m\times d_v}$, each a learned linear projection of token representations.

**Mechanics.**
1. Scores $S = QK^\top/\sqrt{d_k}$: how well each query matches each key.
2. Weights $A = \mathrm{softmax}(S)$, row-wise: each query distributes one unit of attention.
3. Output $AV$: each query receives a convex combination of the values.

**Why $\sqrt{d_k}$?** If query and key components are independent with mean 0 and variance 1, their dot product has variance $d_k$. Dividing by $\sqrt{d_k}$ keeps scores at unit variance, so softmax stays in a regime with useful gradients rather than collapsing to near one-hot.

**Multi-head.** Several attention operations run in parallel on lower-dimensional projections, then are concatenated. Different heads can specialise in different relations.

**Trade-offs and failure modes.**
- *Cost:* $O(n^2 d)$ time and $O(n^2)$ memory for $n$ tokens (IO-aware kernels such as FlashAttention avoid materialising the full matrix but not the quadratic compute).
- *Order-blind:* attention is permutation-equivariant; position must be injected (positional encodings, RoPE).
- *Causal masking* is required for autoregressive models so a token cannot attend to the future.
- Attention weights are often read as explanations; that reading is contested.""",
        "l2": r"""### Definition

$$\mathrm{Attn}(Q,K,V) = \mathrm{softmax}\!\left(\frac{QK^\top}{\sqrt{d_k}} + M\right)V,$$
where $M$ is a mask ($-\infty$ for disallowed positions, e.g. $j>i$ in causal attention).

### The variance argument

If $q, k \in \mathbb R^{d_k}$ have iid components with mean 0 and variance 1, then $q\cdot k = \sum_{t=1}^{d_k} q_t k_t$ has mean 0 and variance $d_k$. Unscaled, typical score gaps grow like $\sqrt{d_k}$; softmax of large-gap inputs is nearly one-hot and its Jacobian $\mathrm{diag}(a) - aa^\top$ nearly vanishes. Scaling restores unit variance at initialisation. (This is an initialisation-time argument; trained representations need not satisfy the iid assumption.)

### Kernel-smoother view

Each output row is $\sum_j \frac{\kappa(q_i,k_j)}{\sum_{j'}\kappa(q_i,k_{j'})} v_j$ with $\kappa(q,k) = \exp(q\cdot k/\sqrt{d_k})$: a Nadaraya–Watson kernel regression with a learned, asymmetric exponential kernel. Linear-attention methods replace $\kappa$ by a feature-map inner product $\phi(q)^\top\phi(k)$, which allows $O(n)$ computation by reassociating $(\phi(Q)\phi(K)^\top)V = \phi(Q)(\phi(K)^\top V)$.

### Rank structure

$QK^\top = XW_QW_K^\top X^\top$ has rank at most $d_k$: the score matrix is a low-rank bilinear form in token space, before the softmax's nonlinearity.

### Minimal implementation

```python
import numpy as np
def attention(Q, K, V, causal=False):
    d = Q.shape[-1]
    S = Q @ K.T / np.sqrt(d)
    if causal:
        S = S + np.triu(np.full(S.shape, -np.inf), k=1)
    S = S - S.max(axis=-1, keepdims=True)
    A = np.exp(S); A /= A.sum(axis=-1, keepdims=True)
    return A @ V
```

### History

Additive attention for alignment in translation: Bahdanau, Cho & Bengio (2014). The scaled dot-product form and the all-attention Transformer: Vaswani et al. (2017).""",
        "probe": (
            "Explain what attention computes as a 'soft dictionary lookup', and give the statistical reason for dividing by √d_k.",
            "Each query is compared with every key by dot product; softmax turns those scores into non-negative weights summing to 1; the output is the weighted average of the values: a differentiable lookup that blends entries by match quality. If query and key components are independent with mean 0 and variance 1, the dot product has variance d_k, so dividing by √d_k keeps the scores at unit variance and stops the softmax saturating (which would kill gradients).",
        ),
        "sources": [
            ("arxiv", "Vaswani et al. (2017), Attention Is All You Need", "https://arxiv.org/abs/1706.03762"),
            ("arxiv", "Bahdanau, Cho & Bengio (2014), Neural Machine Translation by Jointly Learning to Align and Translate", "https://arxiv.org/abs/1409.0473"),
        ],
    },
    {
        "slug": "singular-value-decomposition",
        "title": "Singular value decomposition",
        "domain": "Linear Algebra",
        "l0": r"""Every matrix, of any shape, is a **rotation, then an axis-aligned stretch, then another rotation**: $A = U\Sigma V^\top$. The stretch factors (singular values) tell you everything about how much the map amplifies, squashes or annihilates directions, and keeping only the largest few gives the best possible low-rank approximation.""",
        "l1": r"""**Inputs.** Any real $m\times n$ matrix $A$.

**Output.** $A = U\Sigma V^\top$ with $U$ ($m\times m$) and $V$ ($n\times n$) orthogonal and $\Sigma$ diagonal with $\sigma_1\ge\sigma_2\ge\dots\ge 0$.

**Mechanics / geometry.** $V^\top$ rotates the input so the special input directions $v_i$ line up with the axes; $\Sigma$ scales axis $i$ by $\sigma_i$ (and drops or pads dimensions); $U$ rotates into output space so $Av_i = \sigma_i u_i$. The unit sphere maps to an ellipsoid with semi-axes $\sigma_i u_i$.

**Connections.**
- $\sigma_i^2$ are the eigenvalues of $A^\top A$ (and of $AA^\top$); $v_i$ and $u_i$ are their eigenvectors.
- Rank = number of non-zero singular values.
- $\|A\|_2 = \sigma_1$ (largest stretch); condition number $\kappa = \sigma_1/\sigma_r$.
- PCA is the SVD of the centred data matrix.

**Eckart–Young.** Truncating to the top $k$ terms, $A_k = \sum_{i\le k}\sigma_i u_i v_i^\top$, gives the best rank-$k$ approximation in both spectral and Frobenius norms.

**Trade-offs.** Full SVD costs $O(mn\min(m,n))$; randomised and iterative methods get the top $k$ cheaply. Singular vectors are not unique when singular values repeat, and they can be sensitive when gaps between singular values are small.""",
        "l2": r"""### Existence (sketch)

$A^\top A$ is symmetric positive semi-definite, so by the spectral theorem $A^\top A = V\Lambda V^\top$ with $\lambda_i\ge0$. Set $\sigma_i = \sqrt{\lambda_i}$ and, for $\sigma_i>0$, $u_i = Av_i/\sigma_i$. Then $u_i^\top u_j = v_i^\top A^\top A v_j/(\sigma_i\sigma_j) = \delta_{ij}$, so the $u_i$ are orthonormal; extend them to a basis. By construction $AV = U\Sigma$.

### Eckart–Young–Mirsky

For $k < \mathrm{rank}(A)$:
$$\min_{\mathrm{rank}(B)\le k}\|A - B\|_2 = \sigma_{k+1}, \qquad \min_{\mathrm{rank}(B)\le k}\|A - B\|_F = \Big(\sum_{i>k}\sigma_i^2\Big)^{1/2},$$
both attained by $A_k$.

### Variational characterisation

$\sigma_1 = \max_{\|x\|=1}\|Ax\|$, attained at $v_1$; then $\sigma_2$ is the max over $x\perp v_1$, and so on (Courant–Fischer for $A^\top A$).

### Why ML keeps meeting it

- **Optimisation:** for least squares $\tfrac12\|Ax-b\|^2$, the Hessian is $A^\top A$, with eigenvalues $\sigma_i^2$. Gradient descent's rate depends on $\kappa(A^\top A) = (\sigma_1/\sigma_n)^2$: squaring the condition number is why normal equations are numerically worse than QR.
- **Low-rank adaptation:** fine-tuning updates constrained to $\Delta W = BA$ with small inner dimension (LoRA) bet that useful updates are approximately low rank.
- **Signal propagation:** in deep nets, products of layer Jacobians are well-behaved when their singular values cluster near 1 (dynamical isometry).
- **Embeddings:** classic latent semantic analysis is a truncated SVD of a term–document matrix.

### Code

```python
import numpy as np
A = np.random.randn(100, 40)
U, s, Vt = np.linalg.svd(A, full_matrices=False)
k = 5
A_k = (U[:, :k] * s[:k]) @ Vt[:k]
print(np.linalg.norm(A - A_k, 2), s[k])   # equal: Eckart–Young (spectral)
```

### Canonical references

Eckart & Young (1936), *The approximation of one matrix by another of lower rank*, Psychometrika 1. Trefethen & Bau, *Numerical Linear Algebra* (1997), lectures 4–5. Strang, *Linear Algebra and Learning from Data* (2019).""",
        "probe": (
            "Describe the SVD geometrically, and state what the truncated SVD is optimal for.",
            "Any matrix acts as a rotation/reflection (V^T), then scaling along coordinate axes by the singular values (Σ), then another rotation/reflection (U); the unit sphere maps to an ellipsoid whose semi-axes are σ_i u_i. Keeping the top k singular triplets gives the best rank-k approximation in spectral and Frobenius norm (Eckart–Young), with spectral error σ_{k+1}.",
        ),
        "sources": [
            ("reference", "Eckart & Young (1936), The approximation of one matrix by another of lower rank, Psychometrika 1", "https://doi.org/10.1007/BF02288367"),
        ],
    },
]

# (source, target, type, description): read as "source TYPE target".
RELATIONS = [
    ("gradient-descent", "backprop-chain-rule", "REQUIRES",
     "In neural networks, the gradient that gradient descent follows is computed by backprop."),
    ("gradient-descent", "singular-value-decomposition", "REQUIRES",
     "Convergence speed is set by the Hessian's spectrum: κ = λmax/λmin (for least squares, (σ1/σn)²)."),
    ("softmax", "boltzmann-distribution", "ANALOGOUS_TO",
     "Identical functional form: logits ↔ −E/kT, softmax temperature ↔ physical temperature, normaliser ↔ partition function."),
    ("shannon-entropy", "boltzmann-distribution", "ANALOGOUS_TO",
     "Boltzmann is the maximum-entropy distribution at fixed mean energy (Jaynes); Gibbs entropy is Shannon entropy × k_B."),
    ("cross-entropy-kl", "shannon-entropy", "EXTENDS",
     "Cross-entropy = entropy + KL gap: the cost of coding with the wrong distribution."),
    ("cross-entropy-kl", "softmax", "REQUIRES",
     "The standard classifier head is softmax + cross-entropy; together their gradient is simply q − y."),
    ("scaled-dot-product-attention", "softmax", "REQUIRES",
     "Attention weights are a row-wise softmax over query–key scores."),
    ("scaled-dot-product-attention", "singular-value-decomposition", "EXTENDS",
     "The score matrix XW_QW_Kᵀ Xᵀ has rank ≤ d_k: a low-rank bilinear form."),
    ("backprop-chain-rule", "singular-value-decomposition", "EXTENDS",
     "Vanishing/exploding gradients are about singular values of products of layer Jacobians."),
    ("softmax", "cross-entropy-kl", "CONTRASTS_WITH",
     "Softmax produces a distribution; cross-entropy scores one. Easy to conflate because they are fused in code (log_softmax + NLL)."),
]


def seed(conn: sqlite3.Connection) -> int:
    """Insert seed units if the knowledge base is empty. Returns units added."""
    if conn.execute("SELECT COUNT(*) FROM knowledge_units").fetchone()[0]:
        return 0
    ids: dict[str, str] = {}
    for u in UNITS:
        unit = S.create_unit(conn, u["title"], u["domain"], slug=u["slug"])
        ids[u["slug"]] = unit["id"]
        S.set_layer(conn, unit["id"], 0, u["l0"])
        S.set_layer(conn, unit["id"], 1, u["l1"])
        S.set_layer(conn, unit["id"], 2, u["l2"])
        if "l1_pattern" in u:
            S.set_layer(conn, unit["id"], 1, u["l1_pattern"], lens="pattern")
        if "l1_steps" in u:
            S.set_layer(conn, unit["id"], 1, u["l1_steps"], lens="steps")
        S.set_probe(conn, unit["id"], *u["probe"])
        for kind, title, url in u.get("sources", []):
            S.add_source(conn, unit["id"], kind, title, url)
    for src, tgt, typ, desc in RELATIONS:
        S.add_relation(conn, ids[src], ids[tgt], typ, desc)
    return len(UNITS)
