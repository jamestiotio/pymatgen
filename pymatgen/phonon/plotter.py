"""This module implements plotter for DOS and band structure."""

from __future__ import annotations

import logging
from collections import namedtuple
from typing import TYPE_CHECKING

import matplotlib.pyplot as plt
import numpy as np
import palettable
import scipy.constants as const
from matplotlib.collections import LineCollection
from monty.json import jsanitize

from pymatgen.electronic_structure.plotter import BSDOSPlotter, plot_brillouin_zone
from pymatgen.phonon.bandstructure import PhononBandStructureSymmLine
from pymatgen.phonon.gruneisen import GruneisenPhononBandStructureSymmLine
from pymatgen.util.plotting import add_fig_kwargs, get_ax_fig, pretty_plot

if TYPE_CHECKING:
    from collections.abc import Sequence
    from os import PathLike
    from typing import Any, Literal

    from matplotlib.axes import Axes
    from matplotlib.figure import Figure

    from pymatgen.core import Structure
    from pymatgen.phonon.dos import PhononDos
    from pymatgen.phonon.gruneisen import GruneisenParameter

logger = logging.getLogger(__name__)

FreqUnits = namedtuple("FreqUnits", ["factor", "label"])


def freq_units(units: Literal["thz", "ev", "mev", "ha", "cm-1", "cm^-1"]) -> FreqUnits:
    """
    Args:
        units: str, accepted values: thz, ev, mev, ha, cm-1, cm^-1.

    Returns:
        Conversion factor from THz to the required units and the label in the form of a namedtuple
    """
    dct = {
        "thz": FreqUnits(1, "THz"),
        "ev": FreqUnits(const.value("hertz-electron volt relationship") * const.tera, "eV"),
        "mev": FreqUnits(
            const.value("hertz-electron volt relationship") * const.tera / const.milli,
            "meV",
        ),
        "ha": FreqUnits(const.value("hertz-hartree relationship") * const.tera, "Ha"),
        "cm-1": FreqUnits(
            const.value("hertz-inverse meter relationship") * const.tera * const.centi,
            "cm^{-1}",
        ),
        "cm^-1": FreqUnits(
            const.value("hertz-inverse meter relationship") * const.tera * const.centi,
            "cm^{-1}",
        ),
    }
    try:
        return dct[units.lower().strip()]
    except KeyError:
        raise KeyError(f"Value for units `{units}` unknown\nPossible values are:\n {list(dct)}")


class PhononDosPlotter:
    """Class for plotting phonon DOSs. The interface is extremely flexible given there are many
    different ways in which people want to view DOS.
    Typical usage is:
        # Initializes plotter with some optional args. Defaults are usually fine
        plotter = PhononDosPlotter().

        # Add DOS with a label
        plotter.add_dos("Total DOS", dos)

        # Alternatively, you can add a dict of DOSes. This is the typical form
        # returned by CompletePhononDos.get_element_dos().
    """

    def __init__(self, stack: bool = False, sigma: float | None = None) -> None:
        """
        Args:
            stack: Whether to plot the DOS as a stacked area graph
            sigma: A float specifying a standard deviation for Gaussian smearing
                the DOS for nicer looking plots. Defaults to None for no smearing.
        """
        # a likely user mistake is to try to pass a DOS as the first argument (similar to PhononBSPlotter) but
        # without the isinstance check, this would not raise an error and just silently cause a blank plot
        if not isinstance(stack, bool):
            raise ValueError(
                "The first argument stack expects a boolean. If you are trying to add a DOS, use the add_dos() method."
            )
        self.stack = stack
        self.sigma = sigma
        self._doses: dict[str, dict[Literal["frequencies", "densities"], np.ndarray]] = {}

    def add_dos(self, label: str, dos: PhononDos) -> None:
        """Adds a dos for plotting.

        Args:
            label:
                label for the DOS. Must be unique.
            dos:
                PhononDos object
        """
        densities = dos.get_smeared_densities(self.sigma) if self.sigma else dos.densities
        self._doses[label] = {"frequencies": dos.frequencies, "densities": densities}

    def add_dos_dict(self, dos_dict: dict, key_sort_func=None) -> None:
        """Add a dictionary of doses, with an optional sorting function for the
        keys.

        Args:
            dos_dict: dict of {label: Dos}
            key_sort_func: function used to sort the dos_dict keys.
        """
        keys = sorted(dos_dict, key=key_sort_func) if key_sort_func else list(dos_dict)
        for label in keys:
            self.add_dos(label, dos_dict[label])

    def get_dos_dict(self) -> dict:
        """Returns the added doses as a json-serializable dict. Note that if you
        have specified smearing for the DOS plot, the densities returned will
        be the smeared densities, not the original densities.

        Returns:
            Dict of dos data. Generally of the form, {label: {'frequencies':..,
            'densities': ...}}
        """
        return jsanitize(self._doses)

    def get_plot(
        self,
        xlim: float | None = None,
        ylim: float | None = None,
        units: Literal["thz", "ev", "mev", "ha", "cm-1", "cm^-1"] = "thz",
        legend: dict | None = None,
        ax: Axes | None = None,
    ) -> Axes:
        """Get a matplotlib plot showing the DOS.

        Args:
            xlim: Specifies the x-axis limits. Set to None for automatic
                determination.
            ylim: Specifies the y-axis limits.
            units: units for the frequencies. Accepted values thz, ev, mev, ha, cm-1, cm^-1.
            legend: dict with legend options. For example, {"loc": "upper right"}
                will place the legend in the upper right corner. Defaults to
                {"fontsize": 30}.
            ax (Axes): An existing axes object onto which the plot will be
                added. If None, a new figure will be created.
        """
        legend = legend or {"fontsize": 30}
        unit = freq_units(units)

        n_colors = max(3, len(self._doses))
        n_colors = min(9, n_colors)

        colors = palettable.colorbrewer.qualitative.Set1_9.mpl_colors

        y = None
        all_densities = []
        all_frequencies = []
        ax = pretty_plot(12, 8, ax=ax)

        # Note that this complicated processing of frequencies is to allow for
        # stacked plots in matplotlib.
        for dos in self._doses.values():
            frequencies = dos["frequencies"] * unit.factor
            densities = dos["densities"]
            if y is None:
                y = np.zeros(frequencies.shape)
            if self.stack:
                y += densities
                new_dens = y.copy()
            else:
                new_dens = densities
            all_frequencies.append(frequencies)
            all_densities.append(new_dens)

        keys = list(reversed(self._doses))
        all_densities.reverse()
        all_frequencies.reverse()
        all_pts = []
        for idx, (key, frequencies, densities) in enumerate(zip(keys, all_frequencies, all_densities)):
            all_pts.extend(list(zip(frequencies, densities)))
            if self.stack:
                ax.fill(frequencies, densities, color=colors[idx % n_colors], label=str(key))
            else:
                ax.plot(
                    frequencies,
                    densities,
                    color=colors[idx % n_colors],
                    label=str(key),
                    linewidth=3,
                )

        if xlim:
            ax.set_xlim(xlim)
        if ylim:
            ax.set_ylim(ylim)
        else:
            _xlim = ax.get_xlim()
            relevant_y = [p[1] for p in all_pts if _xlim[0] < p[0] < _xlim[1]] or ax.get_ylim()
            ax.set_ylim((min(relevant_y), max(relevant_y)))

        ax.axvline(0, linewidth=2, color="black", linestyle="--")

        ax.set_xlabel(rf"$\mathrm{{Frequencies\ ({unit.label})}}$", fontsize=legend.get("fontsize", 30))
        ax.set_ylabel(r"$\mathrm{Density\ of\ states}$", fontsize=legend.get("fontsize", 30))

        ax.legend()
        legend_text = ax.get_legend().get_texts()  # all the text.Text instance in the legend
        plt.setp(legend_text, **legend)
        plt.tight_layout()
        return ax

    def save_plot(
        self,
        filename: str | PathLike,
        img_format: str = "eps",
        xlim: float | None = None,
        ylim: float | None = None,
        units: Literal["thz", "ev", "mev", "ha", "cm-1", "cm^-1"] = "thz",
    ) -> None:
        """Save matplotlib plot to a file.

        Args:
            filename: Filename to write to.
            img_format: Image format to use. Defaults to EPS.
            xlim: Specifies the x-axis limits. Set to None for automatic
                determination.
            ylim: Specifies the y-axis limits.
            units: units for the frequencies. Accepted values thz, ev, mev, ha, cm-1, cm^-1
        """
        self.get_plot(xlim, ylim, units=units)
        plt.savefig(filename, format=img_format)
        plt.close()

    def show(
        self,
        xlim: float | None = None,
        ylim: None = None,
        units: Literal["thz", "ev", "mev", "ha", "cm-1", "cm^-1"] = "thz",
    ) -> None:
        """Show the plot using matplotlib.

        Args:
            xlim: Specifies the x-axis limits. Set to None for automatic
                determination.
            ylim: Specifies the y-axis limits.
            units: units for the frequencies. Accepted values thz, ev, mev, ha, cm-1, cm^-1.
        """
        self.get_plot(xlim, ylim, units=units)
        plt.show()


class PhononBSPlotter:
    """Class to plot or get data to facilitate the plot of band structure objects."""

    def __init__(self, bs: PhononBandStructureSymmLine) -> None:
        """
        Args:
            bs: A PhononBandStructureSymmLine object.
        """
        if not isinstance(bs, PhononBandStructureSymmLine):
            raise ValueError(
                "PhononBSPlotter only works with PhononBandStructureSymmLine objects. "
                "A PhononBandStructure object (on a uniform grid for instance and "
                "not along symmetry lines won't work)"
            )
        self._bs = bs
        self._nb_bands = self._bs.nb_bands

    def _make_ticks(self, ax: Axes) -> Axes:
        """Utility private method to add ticks to a band structure."""
        ticks = self.get_ticks()
        # Sanitize only plot the uniq values
        uniq_d = []
        uniq_l = []
        temp_ticks = list(zip(ticks["distance"], ticks["label"]))
        for i, tt in enumerate(temp_ticks):
            if i == 0:
                uniq_d.append(tt[0])
                uniq_l.append(tt[1])
            else:
                uniq_d.append(tt[0])
                uniq_l.append(tt[1])

        ax.set_xticks(uniq_d)
        ax.set_xticklabels(uniq_l)

        for i in range(len(ticks["label"])):
            if ticks["label"][i] is not None:
                # don't print the same label twice
                if i != 0:
                    ax.axvline(ticks["distance"][i], color="k")
                else:
                    ax.axvline(ticks["distance"][i], color="k")
        return ax

    def bs_plot_data(self) -> dict[str, Any]:
        """Get the data nicely formatted for a plot.

        Returns:
            A dict of the following format:
            ticks: A dict with the 'distances' at which there is a qpoint (the
            x axis) and the labels (None if no label)
            frequencies: A list (one element for each branch) of frequencies for
            each qpoint: [branch][qpoint][mode]. The data is
            stored by branch to facilitate the plotting
            lattice: The reciprocal lattice.
        """
        distance = []
        frequency: list = []

        ticks = self.get_ticks()

        for b in self._bs.branches:
            frequency.append([])
            distance.append([self._bs.distance[j] for j in range(b["start_index"], b["end_index"] + 1)])

            for i in range(self._nb_bands):
                frequency[-1].append([self._bs.bands[i][j] for j in range(b["start_index"], b["end_index"] + 1)])

        return {
            "ticks": ticks,
            "distances": distance,
            "frequency": frequency,
            "lattice": self._bs.lattice_rec.as_dict(),
        }

    def get_plot(
        self, ylim: float | None = None, units: Literal["thz", "ev", "mev", "ha", "cm-1", "cm^-1"] = "thz"
    ) -> Axes:
        """Get a matplotlib object for the bandstructure plot.

        Args:
            ylim: Specify the y-axis (frequency) limits; by default None let
                the code choose.
            units: units for the frequencies. Accepted values thz, ev, mev, ha, cm-1, cm^-1.
        """
        u = freq_units(units)

        ax = pretty_plot(12, 8)

        band_linewidth = 1

        data = self.bs_plot_data()
        for d in range(len(data["distances"])):
            for i in range(self._nb_bands):
                ax.plot(
                    data["distances"][d],
                    [data["frequency"][d][i][j] * u.factor for j in range(len(data["distances"][d]))],
                    "b-",
                    linewidth=band_linewidth,
                )

        self._make_ticks(ax)

        # plot y=0 line
        ax.axhline(0, linewidth=1, color="k")

        # Main X and Y Labels
        ax.set_xlabel(r"$\mathrm{Wave\ Vector}$", fontsize=30)
        ylabel = rf"$\mathrm{{Frequencies\ ({u.label})}}$"
        ax.set_ylabel(ylabel, fontsize=30)

        # X range (K)
        # last distance point
        x_max = data["distances"][-1][-1]
        ax.set_xlim(0, x_max)

        if ylim is not None:
            ax.set_ylim(ylim)

        plt.tight_layout()

        return ax

    def _get_weight(self, vec: np.ndarray, indices: list[list[int]]) -> np.ndarray:
        """Compute the weight for each combination of sites according to the
        eigenvector.
        """
        num_atom = int(self._nb_bands / 3)
        new_vec = np.zeros(num_atom)
        for i in range(num_atom):
            new_vec[i] = np.linalg.norm(vec[i * 3 : i * 3 + 3])
        # get the projectors for each group
        gw = []
        norm_f = 0
        for comb in indices:
            projector = np.zeros(len(new_vec))
            for idx in range(len(projector)):
                if idx in comb:
                    projector[idx] = 1
            group_weight = np.dot(projector, new_vec)
            gw.append(group_weight)
            norm_f += group_weight
        return np.array(gw, dtype=float) / norm_f

    @staticmethod
    def _make_color(colors: Sequence[int]) -> Sequence[int]:
        """Convert the eigendisplacements to rgb colors."""
        # if there are two groups, use red and blue
        if len(colors) == 2:
            return [colors[0], 0, colors[1]]
        if len(colors) == 3:
            return colors
        # if there are four groups, use cyan, magenta, yellow and black
        if len(colors) == 4:
            r = (1 - colors[0]) * (1 - colors[3])
            g = (1 - colors[1]) * (1 - colors[3])
            b = (1 - colors[2]) * (1 - colors[3])
            return [r, g, b]
        raise ValueError(f"Expected 2, 3 or 4 colors, got {len(colors)}")

    def get_proj_plot(
        self,
        site_comb: str | list[list[int]] = "element",
        ylim: tuple[None | float, None | float] | None = None,
        units: Literal["thz", "ev", "mev", "ha", "cm-1", "cm^-1"] = "thz",
        rgb_labels: tuple[None | str] | None = None,
    ) -> Axes:
        """Get a matplotlib object for the bandstructure plot projected along atomic
        sites.

        Args:
            site_comb: a list of list, for example, [[0],[1],[2,3,4]];
                the numbers in each sublist represents the indices of atoms;
                the atoms in a same sublist will be plotted in a same color;
                if not specified, unique elements are automatically grouped.
            ylim: Specify the y-axis (frequency) limits; by default None let
                the code choose.
            units: units for the frequencies. Accepted values thz, ev, mev, ha, cm-1, cm^-1.
                Defaults to "thz".
            rgb_labels: a list of rgb colors for the labels; if not specified,
                the colors will be automatically generated.
        """
        assert self._bs.structure is not None, "Structure is required for get_proj_plot"
        elements = [e.symbol for e in self._bs.structure.elements]
        if site_comb == "element":
            assert 2 <= len(elements) <= 4, "the compound must have 2, 3 or 4 unique elements"
            indices: list[list[int]] = [[] for _ in range(len(elements))]
            for i, ele in enumerate(self._bs.structure.species):
                for j, unique_species in enumerate(self._bs.structure.elements):
                    if ele == unique_species:
                        indices[j].append(i)
        else:
            assert isinstance(site_comb, list)
            assert 2 <= len(site_comb) <= 4, "the length of site_comb must be 2, 3 or 4"
            all_sites = self._bs.structure.sites
            all_indices = {*range(len(all_sites))}
            for comb in site_comb:
                for idx in comb:
                    assert 0 <= idx < len(all_sites), "one or more indices in site_comb does not exist"
                    all_indices.remove(idx)
            if len(all_indices) != 0:
                raise Exception(f"not all {len(all_sites)} indices are included in site_comb")
            indices = site_comb  # type: ignore[assignment]
        assert rgb_labels is None or len(rgb_labels) == len(indices), "wrong number of rgb_labels"

        u = freq_units(units)
        fig, ax = plt.subplots(figsize=(12, 8), dpi=300)
        self._make_ticks(ax)

        data = self.bs_plot_data()
        k_dist = np.array(data["distances"]).flatten()
        for d in range(1, len(k_dist)):
            # consider 2 k points each time so they connect
            colors = []
            for idx in range(self._nb_bands):
                eigenvec_1 = self._bs.eigendisplacements[idx][d - 1].flatten()
                eigenvec_2 = self._bs.eigendisplacements[idx][d].flatten()
                colors1 = self._get_weight(eigenvec_1, indices)
                colors2 = self._get_weight(eigenvec_2, indices)
                colors.append(self._make_color((colors1 + colors2) / 2))
            seg = np.zeros((self._nb_bands, 2, 2))
            seg[:, :, 1] = self._bs.bands[:, d - 1 : d + 1] * u.factor
            seg[:, 0, 0] = k_dist[d - 1]
            seg[:, 1, 0] = k_dist[d]
            ls = LineCollection(seg, colors=colors, linestyles="-", linewidths=2.5)
            ax.add_collection(ls)
        if ylim is None:
            y_max: float = max(max(b) for b in self._bs.bands) * u.factor
            y_min: float = min(min(b) for b in self._bs.bands) * u.factor
            y_margin = (y_max - y_min) * 0.05
            ylim = (y_min - y_margin, y_max + y_margin)
        ax.set_ylim(ylim)
        xlim = [min(k_dist), max(k_dist)]
        ax.set_xlim(xlim)
        ax.set_xlabel(r"$\mathrm{Wave\ Vector}$", fontsize=28)
        ylabel = rf"$\mathrm{{Frequencies\ ({u.label})}}$"
        ax.set_ylabel(ylabel, fontsize=28)
        ax.tick_params(labelsize=28)
        # make color legend
        labels: list[str]
        if rgb_labels is not None:
            labels = rgb_labels  # type: ignore[assignment]
        elif site_comb == "element":
            labels = [e.symbol for e in self._bs.structure.elements]
        else:
            labels = [f"{i}" for i in range(len(site_comb))]
        if len(indices) == 2:
            BSDOSPlotter._rb_line(ax, labels[0], labels[1], "best")
        elif len(indices) == 3:
            BSDOSPlotter._rgb_triangle(ax, labels[0], labels[1], labels[2], "best")
        else:
            # for 4 combinations, build a color square?
            pass
        return ax

    def show(
        self, ylim: float | None = None, units: Literal["thz", "ev", "mev", "ha", "cm-1", "cm^-1"] = "thz"
    ) -> None:
        """Show the plot using matplotlib.

        Args:
            ylim (float): Specifies the y-axis limits.
            units ("thz" | "ev" | "mev" | "ha" | "cm-1" | "cm^-1"): units for the frequencies.
        """
        self.get_plot(ylim, units=units)
        plt.show()

    def save_plot(
        self,
        filename: str | PathLike,
        ylim: float | None = None,
        units: Literal["thz", "ev", "mev", "ha", "cm-1", "cm^-1"] = "thz",
    ) -> None:
        """Save matplotlib plot to a file.

        Args:
            filename (str | Path): Filename to write to.
            ylim (float): Specifies the y-axis limits.
            units ("thz" | "ev" | "mev" | "ha" | "cm-1" | "cm^-1"): units for the frequencies.
        """
        self.get_plot(ylim=ylim, units=units)
        plt.savefig(filename)
        plt.close()

    def show_proj(
        self,
        site_comb: str | list[list[int]] = "element",
        ylim: tuple[None | float, None | float] | None = None,
        units: Literal["thz", "ev", "mev", "ha", "cm-1", "cm^-1"] = "thz",
        rgb_labels: tuple[str] | None = None,
    ) -> None:
        """Show the projected plot using matplotlib.

        Args:
            site_comb: A list of list of indices of sites to combine. For example,
                [[0, 1], [2, 3]] will combine the projections of sites 0 and 1,
                and sites 2 and 3. Defaults to "element", which will combine
                sites by element.
            ylim: Specify the y-axis (frequency) limits; by default None let
                the code choose.
            units: units for the frequencies. Accepted values thz, ev, mev, ha, cm-1, cm^-1.
                Defaults to "thz".
            rgb_labels: A list of labels for the rgb triangle. Defaults to None,
                which will use the element symbols.
        """
        self.get_proj_plot(site_comb=site_comb, ylim=ylim, units=units, rgb_labels=rgb_labels)
        plt.show()

    def get_ticks(self) -> dict[str, list]:
        """Get all ticks and labels for a band structure plot.

        Returns:
            A dict with 'distance': a list of distance at which ticks should
            be set and 'label': a list of label for each of those ticks.
        """
        tick_distance = []
        tick_labels: list[str] = []
        previous_label = self._bs.qpoints[0].label
        previous_branch = self._bs.branches[0]["name"]
        for idx, point in enumerate(self._bs.qpoints):
            if point.label is not None:
                tick_distance.append(self._bs.distance[idx])
                this_branch = None
                for b in self._bs.branches:
                    if b["start_index"] <= idx <= b["end_index"]:
                        this_branch = b["name"]
                        break
                if point.label != previous_label and previous_branch != this_branch:
                    label1 = point.label
                    if label1.startswith("\\") or label1.find("_") != -1:
                        label1 = f"${label1}$"
                    label0 = previous_label or ""
                    if label0.startswith("\\") or label0.find("_") != -1:
                        label0 = f"${label0}$"
                    tick_labels.pop()
                    tick_distance.pop()
                    tick_labels.append(f"{label0}$\\mid${label1}")
                elif point.label.startswith("\\") or point.label.find("_") != -1:
                    tick_labels.append(f"${point.label}$")
                else:
                    # map atomate2 all-upper-case point.labels to pretty LaTeX
                    label = dict(GAMMA=r"$\Gamma$", DELTA=r"$\Delta$").get(point.label, point.label)
                    tick_labels.append(label)
                previous_label = point.label
                previous_branch = this_branch
        return {"distance": tick_distance, "label": tick_labels}

    def plot_compare(
        self, other_plotter: PhononBSPlotter, units: Literal["thz", "ev", "mev", "ha", "cm-1", "cm^-1"] = "thz"
    ) -> Axes:
        """Plot two band structure for comparison. One is in red the other in blue.
        The two band structures need to be defined on the same symmetry lines!
        and the distance between symmetry lines is the one of the band structure
        used to build the PhononBSPlotter.

        Args:
            other_plotter: another PhononBSPlotter object defined along the same symmetry lines
            units: units for the frequencies. Accepted values thz, ev, mev, ha, cm-1, cm^-1.
                Defaults to 'thz'.

        Returns:
            a matplotlib object with both band structures
        """
        u = freq_units(units)

        data_orig = self.bs_plot_data()
        data = other_plotter.bs_plot_data()

        if len(data_orig["distances"]) != len(data["distances"]):
            raise ValueError("The two objects are not compatible.")

        ax = self.get_plot(units=units)
        band_linewidth = 1
        for band_idx in range(other_plotter._nb_bands):
            for dist_idx in range(len(data_orig["distances"])):
                ax.plot(
                    data_orig["distances"][dist_idx],
                    [
                        data["frequency"][dist_idx][band_idx][j] * u.factor
                        for j in range(len(data_orig["distances"][dist_idx]))
                    ],
                    "r-",
                    linewidth=band_linewidth,
                )

        return ax

    def plot_brillouin(self) -> None:
        """Plot the Brillouin zone."""
        # get labels and lines
        labels = {}
        for q in self._bs.qpoints:
            if q.label:
                labels[q.label] = q.frac_coords

        lines = []
        for b in self._bs.branches:
            lines.append(
                [
                    self._bs.qpoints[b["start_index"]].frac_coords,
                    self._bs.qpoints[b["end_index"]].frac_coords,
                ]
            )

        plot_brillouin_zone(self._bs.lattice_rec, lines=lines, labels=labels)


class ThermoPlotter:
    """Plotter for thermodynamic properties obtained from phonon DOS.
    If the structure corresponding to the DOS, it will be used to extract the formula unit and provide
    the plots in units of mol instead of mole-cell.
    """

    def __init__(self, dos: PhononDos, structure: Structure = None) -> None:
        """
        Args:
            dos: A PhononDos object.
            structure: A Structure object corresponding to the structure used for the calculation.
        """
        self.dos = dos
        self.structure = structure

    def _plot_thermo(
        self,
        func,
        temperatures: Sequence,
        factor: float = 1,
        ax: Axes = None,
        ylabel: str | None = None,
        label: str | None = None,
        ylim: float | None = None,
        **kwargs,
    ) -> Figure:
        """Plots a thermodynamic property for a generic function from a PhononDos instance.

        Args:
            func: the thermodynamic function to be used to calculate the property
            temperatures: a list of temperatures
            factor: a multiplicative factor applied to the thermodynamic property calculated. Used to change
                the units.
            ax: matplotlib Axes or None if a new figure should be created.
            ylabel: label for the y axis
            label: label of the plot
            ylim: tuple specifying the y-axis limits.
            kwargs: kwargs passed to the matplotlib function 'plot'.

        Returns:
            plt.figure: matplotlib figure
        """
        ax, fig = get_ax_fig(ax)

        values = []

        for t in temperatures:
            values.append(func(t, structure=self.structure) * factor)

        ax.plot(temperatures, values, label=label, **kwargs)

        if ylim:
            ax.set_ylim(ylim)

        ax.set_xlim((np.min(temperatures), np.max(temperatures)))
        _ylim = plt.ylim()
        if _ylim[0] < 0 < _ylim[1]:
            plt.plot(plt.xlim(), [0, 0], "k-", linewidth=1)

        ax.set_xlabel(r"$T$ (K)")
        if ylabel:
            ax.set_ylabel(ylabel)

        return fig

    @add_fig_kwargs
    def plot_cv(self, tmin: float, tmax: float, ntemp: int, ylim: float | None = None, **kwargs) -> Figure:
        """Plots the constant volume specific heat C_v in a temperature range.

        Args:
            tmin: minimum temperature
            tmax: maximum temperature
            ntemp: number of steps
            ylim: tuple specifying the y-axis limits.
            kwargs: kwargs passed to the matplotlib function 'plot'.

        Returns:
            plt.figure: matplotlib figure
        """
        temperatures = np.linspace(tmin, tmax, ntemp)

        ylabel = "$C_v$ (J/K/mol)" if self.structure else "$C_v$ (J/K/mol-c)"

        return self._plot_thermo(self.dos.cv, temperatures, ylabel=ylabel, ylim=ylim, **kwargs)

    @add_fig_kwargs
    def plot_entropy(self, tmin: float, tmax: float, ntemp: int, ylim: float | None = None, **kwargs) -> Figure:
        """Plots the vibrational entrpy in a temperature range.

        Args:
            tmin: minimum temperature
            tmax: maximum temperature
            ntemp: number of steps
            ylim: tuple specifying the y-axis limits.
            kwargs: kwargs passed to the matplotlib function 'plot'.

        Returns:
            plt.figure: matplotlib figure
        """
        temperatures = np.linspace(tmin, tmax, ntemp)

        ylabel = "$S$ (J/K/mol)" if self.structure else "$S$ (J/K/mol-c)"

        return self._plot_thermo(self.dos.entropy, temperatures, ylabel=ylabel, ylim=ylim, **kwargs)

    @add_fig_kwargs
    def plot_internal_energy(self, tmin: float, tmax: float, ntemp: int, ylim: float | None = None, **kwargs) -> Figure:
        """Plots the vibrational internal energy in a temperature range.

        Args:
            tmin: minimum temperature
            tmax: maximum temperature
            ntemp: number of steps
            ylim: tuple specifying the y-axis limits.
            kwargs: kwargs passed to the matplotlib function 'plot'.

        Returns:
            plt.figure: matplotlib figure
        """
        temperatures = np.linspace(tmin, tmax, ntemp)

        ylabel = "$\\Delta E$ (kJ/mol)" if self.structure else "$\\Delta E$ (kJ/mol-c)"

        return self._plot_thermo(
            self.dos.internal_energy, temperatures, ylabel=ylabel, ylim=ylim, factor=1e-3, **kwargs
        )

    @add_fig_kwargs
    def plot_helmholtz_free_energy(
        self, tmin: float, tmax: float, ntemp: int, ylim: float | None = None, **kwargs
    ) -> Figure:
        """Plots the vibrational contribution to the Helmoltz free energy in a temperature range.

        Args:
            tmin: minimum temperature
            tmax: maximum temperature
            ntemp: number of steps
            ylim: tuple specifying the y-axis limits.
            kwargs: kwargs passed to the matplotlib function 'plot'.

        Returns:
            plt.figure: matplotlib figure
        """
        temperatures = np.linspace(tmin, tmax, ntemp)

        ylabel = "$\\Delta F$ (kJ/mol)" if self.structure else "$\\Delta F$ (kJ/mol-c)"

        return self._plot_thermo(
            self.dos.helmholtz_free_energy, temperatures, ylabel=ylabel, ylim=ylim, factor=1e-3, **kwargs
        )

    @add_fig_kwargs
    def plot_thermodynamic_properties(
        self, tmin: float, tmax: float, ntemp: int, ylim: float | None = None, **kwargs
    ) -> Figure:
        """Plots all the thermodynamic properties in a temperature range.

        Args:
            tmin: minimum temperature
            tmax: maximum temperature
            ntemp: number of steps
            ylim: tuple specifying the y-axis limits.
            kwargs: kwargs passed to the matplotlib function 'plot'.

        Returns:
            plt.figure: matplotlib figure
        """
        temperatures = np.linspace(tmin, tmax, ntemp)

        mol = "" if self.structure else "-c"

        fig = self._plot_thermo(
            self.dos.cv,
            temperatures,
            ylabel="Thermodynamic properties",
            ylim=ylim,
            label=rf"$C_v$ (J/K/mol{mol})",
            **kwargs,
        )
        self._plot_thermo(
            self.dos.entropy, temperatures, ylim=ylim, ax=fig.axes[0], label=rf"$S$ (J/K/mol{mol})", **kwargs
        )
        self._plot_thermo(
            self.dos.internal_energy,
            temperatures,
            ylim=ylim,
            ax=fig.axes[0],
            factor=1e-3,
            label=rf"$\Delta E$ (kJ/mol{mol})",
            **kwargs,
        )
        self._plot_thermo(
            self.dos.helmholtz_free_energy,
            temperatures,
            ylim=ylim,
            ax=fig.axes[0],
            factor=1e-3,
            label=rf"$\Delta F$ (kJ/mol{mol})",
            **kwargs,
        )

        fig.axes[0].legend(loc="best")

        return fig


class GruneisenPlotter:
    """Class to plot Gruneisenparameter Object."""

    def __init__(self, gruneisen: GruneisenParameter) -> None:
        """Class to plot information from Gruneisenparameter Object.

        Args:
            gruneisen: GruneisenParameter Object.
        """
        self._gruneisen = gruneisen

    def get_plot(
        self,
        marker: str = "o",
        markersize: float | None = None,
        units: Literal["thz", "ev", "mev", "ha", "cm-1", "cm^-1"] = "thz",
    ) -> Axes:
        """Will produce a plot.

        Args:
            marker: marker for the depiction
            markersize: size of the marker
            units: unit for the plots, accepted units: thz, ev, mev, ha, cm-1, cm^-1.

        Returns:
            plt.Axes: matplotlib axes object
        """
        u = freq_units(units)

        xs = self._gruneisen.frequencies.flatten() * u.factor
        ys = self._gruneisen.gruneisen.flatten()

        ax = pretty_plot(12, 8)

        ax.set_xlabel(rf"$\mathrm{{Frequency\ ({u.label})}}$")
        ax.set_ylabel(r"$\mathrm{Grüneisen\ parameter}$")

        n = len(ys) - 1
        for idx, (xi, yi) in enumerate(zip(xs, ys)):
            color = (1.0 / n * idx, 0, 1.0 / n * (n - idx))

            ax.plot(xi, yi, marker, color=color, markersize=markersize)

        plt.tight_layout()
        return ax

    def show(self, units: Literal["thz", "ev", "mev", "ha", "cm-1", "cm^-1"] = "thz") -> None:
        """Will show the plot.

        Args:
            units: units for the plot, accepted units: thz, ev, mev, ha, cm-1, cm^-1.
        """
        self.get_plot(units=units)
        plt.show()

    def save_plot(
        self,
        filename: str | PathLike,
        img_format: str = "pdf",
        units: Literal["thz", "ev", "mev", "ha", "cm-1", "cm^-1"] = "thz",
    ) -> None:
        """Will save the plot to a file.

        Args:
            filename: name of the filename
            img_format: format of the saved plot
            units: accepted units: thz, ev, mev, ha, cm-1, cm^-1.
        """
        self.get_plot(units=units)
        plt.savefig(filename, format=img_format)
        plt.close()


class GruneisenPhononBSPlotter(PhononBSPlotter):
    """Class to plot or get data to facilitate the plot of band structure objects."""

    def __init__(self, bs: GruneisenPhononBandStructureSymmLine) -> None:
        """
        Args:
            bs: A GruneisenPhononBandStructureSymmLine object.
        """
        if not isinstance(bs, GruneisenPhononBandStructureSymmLine):
            raise ValueError(
                "GruneisenPhononBSPlotter only works with GruneisenPhononBandStructureSymmLine objects. "
                "A GruneisenPhononBandStructure object (on a uniform grid for instance and "
                "not along symmetry lines won't work)"
            )
        super().__init__(bs)

    def bs_plot_data(self) -> dict[str, Any]:
        """Get the data nicely formatted for a plot.

        Returns:
            A dict of the following format:
            ticks: A dict with the 'distances' at which there is a qpoint (the
            x axis) and the labels (None if no label)
            frequencies: A list (one element for each branch) of frequencies for
            each qpoint: [branch][qpoint][mode]. The data is
            stored by branch to facilitate the plotting
            gruneisen: GruneisenPhononBandStructureSymmLine
            lattice: The reciprocal lattice.
        """
        distance: list = []
        frequency: list[list[list[float]]] = []
        gruneisen: list = []

        ticks = self.get_ticks()

        for b in self._bs.branches:
            frequency.append([])
            gruneisen.append([])
            distance.append([self._bs.distance[j] for j in range(b["start_index"], b["end_index"] + 1)])

            for i in range(self._nb_bands):
                frequency[-1].append([self._bs.bands[i][j] for j in range(b["start_index"], b["end_index"] + 1)])
                gruneisen[-1].append([self._bs.gruneisen[i][j] for j in range(b["start_index"], b["end_index"] + 1)])

        return {
            "ticks": ticks,
            "distances": distance,
            "frequency": frequency,
            "gruneisen": gruneisen,
            "lattice": self._bs.lattice_rec.as_dict(),
        }

    def get_plot_gs(self, ylim: float | None = None) -> Axes:
        """Get a matplotlib object for the gruneisen bandstructure plot.

        Args:
            ylim: Specify the y-axis (gruneisen) limits; by default None let
                the code choose.
        """
        ax = pretty_plot(12, 8)

        # band_linewidth = 1

        data = self.bs_plot_data()
        for d in range(len(data["distances"])):
            for i in range(self._nb_bands):
                ax.plot(
                    data["distances"][d],
                    [data["gruneisen"][d][i][j] for j in range(len(data["distances"][d]))],
                    "b-",
                    # linewidth=band_linewidth)
                    marker="o",
                    markersize=2,
                    linewidth=2,
                )

        self._make_ticks(ax)

        # plot y=0 line
        ax.axhline(0, linewidth=1, color="k")

        # Main X and Y Labels
        ax.set_xlabel(r"$\mathrm{Wave\ Vector}$", fontsize=30)
        ax.set_ylabel(r"$\mathrm{Grüneisen\ Parameter}$", fontsize=30)

        # X range (K)
        # last distance point
        x_max = data["distances"][-1][-1]
        ax.set_xlim(0, x_max)

        if ylim is not None:
            ax.set_ylim(ylim)

        plt.tight_layout()

        return ax

    def show_gs(self, ylim: float | None = None) -> None:
        """Show the plot using matplotlib.

        Args:
            ylim: Specifies the y-axis limits.
        """
        self.get_plot_gs(ylim)
        plt.show()

    def save_plot_gs(self, filename: str | PathLike, img_format: str = "eps", ylim: float | None = None) -> None:
        """Save matplotlib plot to a file.

        Args:
            filename: Filename to write to.
            img_format: Image format to use. Defaults to EPS.
            ylim: Specifies the y-axis limits.
        """
        self.get_plot_gs(ylim=ylim)
        plt.savefig(filename, format=img_format)
        plt.close()

    def plot_compare_gs(self, other_plotter: GruneisenPhononBSPlotter) -> Axes:
        """Plot two band structure for comparison. One is in red the other in blue.
        The two band structures need to be defined on the same symmetry lines!
        and the distance between symmetry lines is
        the one of the band structure used to build the PhononBSPlotter.

        Args:
            other_plotter (GruneisenPhononBSPlotter): another phonon DOS plotter defined along
                the same symmetry lines.

        Raises:
            ValueError: if the two plotters are incompatible (due to different data lengths)

        Returns:
            a matplotlib object with both band structures
        """
        data_orig = self.bs_plot_data()
        data = other_plotter.bs_plot_data()

        len_orig = len(data_orig["distances"])
        len_other = len(data["distances"])
        if len_orig != len_other:
            raise ValueError(
                f"The two plotters are incompatible, plotting data have different lengths ({len_orig} vs {len_other})."
            )

        ax = self.get_plot()
        band_linewidth = 1
        for band_idx in range(other_plotter._nb_bands):
            for dist_idx in range(len(data_orig["distances"])):
                ax.plot(
                    data_orig["distances"][dist_idx],
                    [data["gruneisen"][dist_idx][band_idx][j] for j in range(len(data_orig["distances"][dist_idx]))],
                    "r-",
                    linewidth=band_linewidth,
                )

        return ax
