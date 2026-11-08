"""Supplied information-relaxation policy, not a model of human forgetting.

RLS stores a ridge-regularized sufficient statistic. Observed information s
relaxes by ds/dt = -s / (tau * (1+s)); reinforced directions therefore persist
longer. Cross-statistics relax by the same factor, preserving the estimate while
its support declines. No observations or reconstructed targets are replayed.
"""
import torch

RIDGE = .001
RULE = 'information-relaxation-v1'
DEFAULT_SECONDS = 86400.


@torch.no_grad()
def spectrum(precision):
    eigenvalues, basis = torch.linalg.eigh(precision)
    if eigenvalues.min() <= 0 or eigenvalues.max() > 1000.00001:
        raise ValueError('Semantic retention requires an RLS information covariance.')
    return (eigenvalues.reciprocal() - RIDGE).clamp_min(0.), basis


@torch.no_grad()
def relaxed_information(information, elapsed, seconds):
    if elapsed == 0:
        return information.clone()
    # Solve log(s_new)+s_new = log(s_old)+s_old-elapsed/tau.
    # Log-space Newton avoids overflow/underflow for arbitrarily long gaps.
    positive = information > 0
    old_log = information.clamp_min(torch.finfo(torch.float64).tiny).log()
    rhs = old_log + information - elapsed / seconds
    value = torch.minimum(old_log, rhs)
    for _ in range(20):
        exponential = value.exp()
        value -= (value + exponential - rhs) / (1. + exponential)
    return torch.where(positive, torch.minimum(value.exp(), information), torch.zeros_like(information))


@torch.no_grad()
def view(weights, information, basis, elapsed, seconds):
    remaining = relaxed_information(information, elapsed, seconds)
    ratio = torch.where(information > 0,
        remaining * (RIDGE + information) / (information.clamp_min(torch.finfo(torch.float64).tiny) * (RIDGE + remaining)),
        torch.ones_like(information))
    aged_weights = ((weights @ basis) * ratio) @ basis.T
    precision = (basis * (RIDGE + remaining).reciprocal()) @ basis.T
    return aged_weights, (precision + precision.T) * .5
