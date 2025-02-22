"""
This module implements a EnergyModel abstract class and some basic
implementations. Basically, an EnergyModel is any model that returns an
"energy" for any given structure.
"""

from __future__ import annotations

import abc
from typing import TYPE_CHECKING

from monty.json import MSONable

from pymatgen.analysis.ewald import EwaldSummation
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer

if TYPE_CHECKING:
    from pymatgen.core import Structure

__version__ = "0.1"


class EnergyModel(MSONable, metaclass=abc.ABCMeta):
    """Abstract structure filter class."""

    @abc.abstractmethod
    def get_energy(self, structure) -> float:
        """
        :param structure: Structure

        Returns:
            Energy value
        """
        return 0.0

    @classmethod
    def from_dict(cls, dct):
        """
        Args:
            dct (dict): Dict representation.

        Returns:
            EnergyModel
        """
        return cls(**dct["init_args"])


class EwaldElectrostaticModel(EnergyModel):
    """Wrapper around EwaldSum to calculate the electrostatic energy."""

    def __init__(self, real_space_cut=None, recip_space_cut=None, eta=None, acc_factor=8.0):
        """
        Initializes the model. Args have the same definitions as in
        pymatgen.analysis.ewald.EwaldSummation.

        Args:
            real_space_cut (float): Real space cutoff radius dictating how
                many terms are used in the real space sum. Defaults to None,
                which means determine automatically using the formula given
                in gulp 3.1 documentation.
            recip_space_cut (float): Reciprocal space cutoff radius.
                Defaults to None, which means determine automatically using
                the formula given in gulp 3.1 documentation.
            eta (float): Screening parameter. Defaults to None, which means
                determine automatically.
            acc_factor (float): No. of significant figures each sum is
                converged to.
        """
        self.real_space_cut = real_space_cut
        self.recip_space_cut = recip_space_cut
        self.eta = eta
        self.acc_factor = acc_factor

    def get_energy(self, structure: Structure):
        """
        :param structure: Structure

        Returns:
            Energy value
        """
        e = EwaldSummation(
            structure,
            real_space_cut=self.real_space_cut,
            recip_space_cut=self.recip_space_cut,
            eta=self.eta,
            acc_factor=self.acc_factor,
        )
        return e.total_energy

    def as_dict(self):
        """MSONable dict"""
        return {
            "version": __version__,
            "@module": type(self).__module__,
            "@class": type(self).__name__,
            "init_args": {
                "real_space_cut": self.real_space_cut,
                "recip_space_cut": self.recip_space_cut,
                "eta": self.eta,
                "acc_factor": self.acc_factor,
            },
        }


class SymmetryModel(EnergyModel):
    """
    Sets the energy to the negative of the spacegroup number. Higher symmetry =>
    lower "energy".

    Args have same meaning as in pymatgen.symmetry.SpacegroupAnalyzer.
    """

    def __init__(self, symprec: float = 0.1, angle_tolerance=5):
        """
        Args:
            symprec (float): Symmetry tolerance. Defaults to 0.1.
            angle_tolerance (float): Tolerance for angles. Defaults to 5 degrees.
        """
        self.symprec = symprec
        self.angle_tolerance = angle_tolerance

    def get_energy(self, structure: Structure):
        """
        :param structure: Structure

        Returns:
            Energy value
        """
        spg_analyzer = SpacegroupAnalyzer(structure, symprec=self.symprec, angle_tolerance=self.angle_tolerance)
        return -spg_analyzer.get_space_group_number()

    def as_dict(self):
        """MSONable dict"""
        return {
            "version": __version__,
            "@module": type(self).__module__,
            "@class": type(self).__name__,
            "init_args": {
                "symprec": self.symprec,
                "angle_tolerance": self.angle_tolerance,
            },
        }


class IsingModel(EnergyModel):
    """A very simple Ising model, with r^2 decay."""

    def __init__(self, j, max_radius):
        """
        Args:
            j (float): The interaction parameter. E = J * spin1 * spin2.
            radius (float): max_radius for the interaction.
        """
        self.j = j
        self.max_radius = max_radius

    def get_energy(self, structure: Structure):
        """
        :param structure: Structure

        Returns:
            Energy value
        """
        all_nn = structure.get_all_neighbors(r=self.max_radius)
        energy = 0
        for idx, nns in enumerate(all_nn):
            s1 = getattr(structure[idx].specie, "spin", 0)
            for nn in nns:
                energy += self.j * s1 * getattr(nn.specie, "spin", 0) / (nn.nn_distance**2)
        return energy

    def as_dict(self):
        """MSONable dict"""
        return {
            "version": __version__,
            "@module": type(self).__module__,
            "@class": type(self).__name__,
            "init_args": {"j": self.j, "max_radius": self.max_radius},
        }


class NsitesModel(EnergyModel):
    """
    Sets the energy to the number of sites. More sites => higher "energy".
    Used to rank structures from smallest number of sites to largest number
    of sites after enumeration.
    """

    def get_energy(self, structure: Structure):
        """
        :param structure: Structure

        Returns:
            Energy value
        """
        return len(structure)

    def as_dict(self):
        """MSONable dict"""
        return {
            "version": __version__,
            "@module": type(self).__module__,
            "@class": type(self).__name__,
            "init_args": {},
        }
