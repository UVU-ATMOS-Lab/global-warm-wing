"""
ln_e_fit.py

!! only for the airframe pipeline !!
do not need to touch unless adding aircraft
look at "procedure to add new airframe.txt"


Fit a flat, hand-writable curve to (x, y) data points using PyTorch + GPU.

No neural networks: the coefficients (a, k, o) are plain leaf tensors and we
solve for them with backpropagation (autograd) + Adam minimizing MSE loss.

Two candidate formulas are fit every run and compared:
    1) logarithmic:  y = a * ln(x + k) + o
    2) exponential:  y = a * e^(k * x) + o

Data source: pre_curve.json5 -> models[<name>][<elevation>], e.g. "e0",
which is a list of [x, y] pairs.

Results (coefficients, metrics, plain + Desmos formulas) are printed and also
written back into the same model object under a new "<elevation>_results" attr.
"""

import math
import time

import json5
import torch


# ------------------------------------------------------------------------------
# TOP-LEVEL CONTROLS  --  change these by hand per run
# ------------------------------------------------------------------------------
JSON5_PATH = "pre_curve.json5"
MODEL_NAME = "a330-200"   # which aircraft "name" to fit
ELEVATION  = "d4000"         # which elevation data array to fit
# e refers to isa standard, d to isa+15
# the trailing number reps feet altitude

DEVICE     = "cuda:0"     # your GPU; falls back to CPU if unavailable
ITERS      = 40_000       # Adam iterations per formula
LR         = 0.02         # Adam learning rate
SEED       = 0            # for reproducible inits
WRITE_BACK = True         # write "<ELEVATION>_results" back into the json5
FIT_EXP    = False        # exp fit DISABLED (ln chosen as best); code kept, just
                          #   not run.  Set True to re-enable the e^(kx) fit.
# ------------------------------------------------------------------------------


def fmt(v: float, sig: int = 10) -> str:
    """Compact numeric formatting for formula strings."""
    return f"{v:.{sig}g}"


def fmt_d(v: float, sig: int = 10) -> str:
    """Plain-decimal formatting (never scientific notation) for Desmos, which
    rejects exponent syntax like '8.076e-3'.  Keeps `sig` significant figures."""
    from decimal import Decimal
    return format(Decimal(f"{v:.{sig}g}"), "f")


# ------------------------------------------------------------------------------
# Model definitions.
#
# Each is fit in a normalized x-space (xn = (x - xm) / xs) for numerical
# stability, then the coefficients are converted back EXACTLY to raw-x units so
# the final formula takes raw x.  y is left in raw units (its range is small).
# ------------------------------------------------------------------------------
class LnModel:
    # form: y = -a * ln(k - x) + o
    name = "ln"

    def __init__(self, xn: torch.Tensor, y: torch.Tensor, device):
        # Domain constraint for ln(K - xn): need K - xn > 0 for every point,
        # i.e. K > max(xn).  We enforce K = max(xn) + softplus(p) + eps, so
        # (K - xn) >= eps always and log of a non-positive number is impossible.
        self._max_xn = float(xn.max())
        self._eps = 1e-4
        # init so that the smallest (K - xn) ~= 1
        self.p = torch.tensor(_inv_softplus(1.0), device=device, requires_grad=True)
        self.a = torch.tensor(float(y.std()), device=device, requires_grad=True)
        self.o = torch.tensor(float(y.mean()), device=device, requires_grad=True)

    def params(self):
        return [self.a, self.p, self.o]

    def _K(self):
        return torch.nn.functional.softplus(self.p) + self._max_xn + self._eps

    def predict(self, xn: torch.Tensor) -> torch.Tensor:
        return -self.a * torch.log(self._K() - xn) + self.o

    def to_raw(self, xm: float, xs: float) -> dict:
        # y = -A*ln(K - xn) + O,  xn = (x - xm)/xs
        #   K - xn = ((K*xs + xm) - x) / xs
        #   = -A*ln(k - x) + (O + A*ln(xs)),   k = K*xs + xm
        A = float(self.a)
        K = float(self._K())
        O = float(self.o)
        a = A
        k = K * xs + xm
        o = O + A * math.log(xs)
        return {"a": a, "k": k, "o": o}

    @staticmethod
    def formula(c: dict) -> str:
        return f"y = -{fmt(c['a'])} * ln({fmt(c['k'])} - x) + {fmt(c['o'])}"

    @staticmethod
    def desmos(c: dict) -> str:
        # self-contained expression: leading minus folded into the coefficient
        # template: -a\ln\left(k-x\right)+o
        return rf"{fmt_d(-c['a'])}\ln\left({fmt_d(c['k'])}-x\right)+{fmt_d(c['o'])}"


class ExpModel:
    name = "exp"

    def __init__(self, xn: torch.Tensor, y: torch.Tensor, device):
        self.a = torch.tensor(float(y.std()), device=device, requires_grad=True)
        self.k = torch.tensor(0.1, device=device, requires_grad=True)
        self.o = torch.tensor(float(y.mean()), device=device, requires_grad=True)

    def params(self):
        return [self.a, self.k, self.o]

    def predict(self, xn: torch.Tensor) -> torch.Tensor:
        return self.a * torch.exp(self.k * xn) + self.o

    def to_raw(self, xm: float, xs: float) -> dict:
        # y = A*e^(K*xn) + O,  xn = (x - xm)/xs
        #   = A*e^(-K*xm/xs) * e^((K/xs)*x) + O
        #   = a*e^(k*x) + o
        A = float(self.a)
        K = float(self.k)
        O = float(self.o)
        a = A * math.exp(-K * xm / xs)
        k = K / xs
        o = O
        return {"a": a, "k": k, "o": o}

    @staticmethod
    def formula(c: dict) -> str:
        return f"y = {fmt(c['a'])} * e^({fmt(c['k'])} * x) + {fmt(c['o'])}"

    @staticmethod
    def desmos(c: dict) -> str:
        return rf"{fmt_d(c['a'])}e^{{{fmt_d(c['k'])}x}}+{fmt_d(c['o'])}"


def _inv_softplus(y: float) -> float:
    """Inverse of softplus, for choosing an initial raw param p."""
    # softplus(p) = log(1 + e^p); invert:
    return math.log(math.expm1(max(y, 1e-6)))


# ------------------------------------------------------------------------------
# Fitting
# ------------------------------------------------------------------------------
def fit(model_cls, xn, y, xm, xs, device):
    torch.manual_seed(SEED)
    model = model_cls(xn, y, device)
    opt = torch.optim.Adam(model.params(), lr=LR)

    best_loss = float("inf")
    best_raw = None
    for _ in range(ITERS):
        opt.zero_grad()
        pred = model.predict(xn)
        loss = torch.mean((pred - y) ** 2)          # MSE
        loss.backward()
        opt.step()

        lv = loss.item()
        if lv < best_loss and math.isfinite(lv):
            best_loss = lv
            with torch.no_grad():
                best_raw = model.to_raw(xm, xs)

    return best_raw


def raw_metrics(model_cls, coeffs, x_raw, y_raw):
    """Evaluate the converted raw-x formula against the raw data (numpy-free)."""
    a, k, o = coeffs["a"], coeffs["k"], coeffs["o"]
    n = len(x_raw)
    if model_cls is LnModel:
        pred = [-a * math.log(k - x) + o for x in x_raw]
    else:
        pred = [a * math.exp(k * x) + o for x in x_raw]
    ss_res = sum((p - y) ** 2 for p, y in zip(pred, y_raw))
    ymean = sum(y_raw) / n
    ss_tot = sum((y - ymean) ** 2 for y in y_raw)
    mse = ss_res / n
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    return {"mse": mse, "rmse": math.sqrt(mse), "r2": r2}


# ------------------------------------------------------------------------------
# JSON5 read / write (compact leaf arrays preserved on write)
# ------------------------------------------------------------------------------
_IDENT = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_")


def _qstr(s: str) -> str:
    """Quote a string but keep backslashes LITERAL (single) so Desmos LaTeX
    like \\ln\\left(...\\right) is paste-ready straight from the file.
    Note: this makes the file intentionally non-round-trippable for such
    values, which is fine because they are regenerated every run."""
    out = (s.replace('"', '\\"')
            .replace("\n", "\\n")
            .replace("\r", "\\r")
            .replace("\t", "\\t"))
    return '"' + out + '"'


def _key(k: str) -> str:
    if k and k[0] not in "0123456789" and all(c in _IDENT for c in k):
        return k
    return _qstr(k)


def _is_leaf_list(v) -> bool:
    """A list of numbers, or a list of lists-of-numbers -> keep inline."""
    if not isinstance(v, list):
        return False
    for e in v:
        if isinstance(e, (int, float, bool)):
            continue
        if isinstance(e, list) and all(isinstance(x, (int, float, bool)) for x in e):
            continue
        return False
    return True


def _dump(v, indent: int) -> str:
    pad = "    " * indent
    pad2 = "    " * (indent + 1)
    if isinstance(v, dict):
        if not v:
            return "{}"
        items = [f"{pad2}{_key(k)}: {_dump(val, indent + 1)}" for k, val in v.items()]
        return "{\n" + ",\n".join(items) + f",\n{pad}}}"
    if isinstance(v, list):
        if _is_leaf_list(v) or not v:
            return "[" + ", ".join(_dump(e, indent + 1) for e in v) + "]"
        items = [f"{pad2}{_dump(e, indent + 1)}" for e in v]
        return "[\n" + ",\n".join(items) + f",\n{pad}]"
    if isinstance(v, bool):
        return "true" if v else "false"
    if v is None:
        return "null"
    if isinstance(v, float):
        return fmt(v, 12)
    if isinstance(v, int):
        return str(v)
    return _qstr(v)


def write_json5(path: str, data: dict):
    with open(path, "w", encoding="utf-8") as f:
        f.write(_dump(data, 0) + "\n")


_MODELS_BY_NAME = {"ln": LnModel, "exp": ExpModel}


def repair_results(data: dict):
    """Regenerate every result's `formula`/`desmos` from its stored numeric
    coefficients (a, k, o) before writing.

    Necessary because the Desmos strings are stored with literal single
    backslashes (paste-ready) which json5.load mangles on read (\\ln -> ln).
    Without this, each run would silently corrupt the Desmos strings of every
    elevation OTHER than the one being fit.  The coefficients themselves are
    plain numbers and round-trip cleanly, so we rebuild the strings from them.
    """
    for model in data.get("models", {}).values():
        if not isinstance(model, dict):
            continue
        for elev in model.values():
            res = elev.get("results") if isinstance(elev, dict) else None
            if not isinstance(res, dict):
                continue
            for name, cls in _MODELS_BY_NAME.items():
                sub = res.get(name)
                if isinstance(sub, dict) and all(c in sub for c in ("a", "k", "o")):
                    coeffs = {c: sub[c] for c in ("a", "k", "o")}
                    sub["formula"] = cls.formula(coeffs)
                    sub["desmos"] = cls.desmos(coeffs)


# ------------------------------------------------------------------------------
# Main
# ------------------------------------------------------------------------------
def main():
    if DEVICE.startswith("cuda") and not torch.cuda.is_available():
        device = torch.device("cpu")
        print(f"[warn] {DEVICE} unavailable, using CPU")
    else:
        device = torch.device(DEVICE)

    with open(JSON5_PATH, "r", encoding="utf-8") as f:
        data = json5.load(f)

    models = data["models"]
    if MODEL_NAME not in models:
        raise SystemExit(f"model {MODEL_NAME!r} not found in {JSON5_PATH}")
    model_obj = models[MODEL_NAME]
    if ELEVATION not in model_obj:
        raise SystemExit(f"elevation {ELEVATION!r} not found for {MODEL_NAME!r}")
    elev_obj = model_obj[ELEVATION]

    points = elev_obj["data"]
    x_raw = [float(p[0]) for p in points]
    y_raw = [float(p[1]) for p in points]

    x = torch.tensor(x_raw, dtype=torch.float64, device=device)
    y = torch.tensor(y_raw, dtype=torch.float64, device=device)
    xm = float(x.mean())
    xs = float(x.std())
    xn = (x - xm) / xs

    print(f"Fitting {MODEL_NAME!r} / {ELEVATION!r}: {len(x_raw)} points on {device}")
    print(f"  x range [{min(x_raw):.3f}, {max(x_raw):.3f}]   "
          f"y range [{min(y_raw):.3f}, {max(y_raw):.3f}]\n")

    fit_classes = [LnModel] + ([ExpModel] if FIT_EXP else [])
    results = {}
    for cls in fit_classes:
        t0 = time.time()
        coeffs = fit(cls, xn, y, xm, xs, device)
        metrics = raw_metrics(cls, coeffs, x_raw, y_raw)
        entry = {
            **{k: coeffs[k] for k in ("a", "k", "o")},
            **metrics,
            "formula": cls.formula(coeffs),
            "desmos": cls.desmos(coeffs),
        }
        results[cls.name] = entry

        print(f"[{cls.name}]  ({time.time() - t0:.1f}s)")
        print(f"  a = {coeffs['a']}")
        print(f"  k = {coeffs['k']}")
        print(f"  o = {coeffs['o']}")
        print(f"  MSE = {metrics['mse']:.6g}   RMSE = {metrics['rmse']:.6g}"
              f"   R^2 = {metrics['r2']:.8f}")
        print(f"  formula: {entry['formula']}")
        print(f"  desmos : {entry['desmos']}\n")

    best = min(results, key=lambda n: results[n]["mse"])
    print(f"==> best fit (lowest MSE): {best.upper()}\n")

    # --- Evaluate the ln fit at x = mtow (max takeoff weight) --------------
    # The ln form y = -a*ln(k - x) + o has a vertical asymptote at x = k and is
    # only real for x < k.  If mtow >= k the result would not exist in reality,
    # so for human output we shortcut to the string "not possible".  Computed in
    # Python double.
    NOT_POSSIBLE = "not possible"
    mtow_eval = None
    mtow = model_obj.get("mtow")
    if mtow is None:
        print("[mtow] no 'mtow' on model; skipping evaluation")
    else:
        c = results["ln"]
        x = float(mtow)
        margin = c["k"] - x
        if margin > 0.0:
            mtow_eval = -c["a"] * math.log(margin) + c["o"]
            print(f"[mtow] ln at x={fmt(x)}:  y = {fmt(mtow_eval)}")
        else:
            mtow_eval = NOT_POSSIBLE
            print(f"[mtow] ln at x={fmt(x)}:  {NOT_POSSIBLE} "
                  f"(past asymptote k={fmt(c['k'])})")
    print()

    if WRITE_BACK:
        res = {
            "device": str(device),
            "iters": ITERS,
            "best": best,
            "ln": results["ln"],
        }
        if FIT_EXP:
            res["exp"] = results["exp"]
        if mtow_eval is not None:
            res["mtowFit"] = mtow_eval
        elev_obj["results"] = res
        repair_results(data)  # heal any strings mangled by json5.load on read
        write_json5(JSON5_PATH, data)
        print(f"wrote {MODEL_NAME!r}.{ELEVATION}.results in {JSON5_PATH}")


if __name__ == "__main__":
    main()
