"""Gaussian field adapter; smoothing numerics remain in vendor/CPS_A source."""
from vendor.CPS_A.Conflict_Field_Updater import ConflictFieldUpdater

def make_gaussian_field(grid, tickets, config):
    return ConflictFieldUpdater(
        grid, tickets,
        delta=config.delta,
        k_space=config.L,
        m_time=config.T,
        sigma_space=config.sigma_l,
        sigma_time=config.sigma_t,
    )
