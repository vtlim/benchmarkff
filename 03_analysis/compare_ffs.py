#!/usr/bin/env python

"""
compare_ffs.py

For 2+ SDF files that are parallel in terms of molecules and their conformers,
assess them (e.g., having FF geometries) with respective to a reference SDF
file (e.g., having QM geometries). Metrics include: RMSD of conformers, TFD
(another geometric evaluation), and relative energy comparisons.

By:      Victoria T. Lim
Version: Dec 13 2019

"""

import os
import numpy as np

import openeye.oechem as oechem
import rdkit.Chem as Chem
from rdkit.Chem import TorsionFingerprints

import matplotlib.pyplot as plt
import matplotlib as mpl
import pandas as pd
import seaborn as sns

import reader

### ------------------- Functions -------------------


def calc_tfd(ref_mol, query_mol):
    """
    Calculate Torsion Fingerprint Deviation between two molecular structures.
    RDKit is required for TFD calculation.

    References
    ----------
    Modified from the following code:
    https://github.com/MobleyLab/off-ffcompare

    TFD reference:
    https://pubs.acs.org/doi/10.1021/ci2002318

    Parameters
    ----------
    ref_mol : OEMol
    query_mol : OEMol

    Returns
    -------
    tfd : float
        Torsion Fingerprint Deviation between ref and query molecules

    """
    # convert refmol to one readable by RDKit
    ref_rdmol = reader.rdmol_from_oemol(ref_mol)

    # convert querymol to one readable by RDKit
    que_rdmol = reader.rdmol_from_oemol(query_mol)

    # if there was a mistake in the conversion process, return -1
    # TODO handle differently?
    if (Chem.MolToSmiles(que_rdmol) != Chem.MolToSmiles(ref_rdmol)):
        return -1

    # else calculate the TFD
    else:
        tfd = Chem.TorsionFingerprints.GetTFDBetweenMolecules(ref_rdmol, que_rdmol)
#        try:
#            tfd = TorsionFingerprints.GetTFDBetweenMolecules(ref_rdmol, que_rdmol)
#        # TODO where does this come from and what does it mean?
#        except IndexError:
#            tfd = 0

    return tfd


def compare_ffs(in_dict, conf_id_tag, outprefix):
    """
    TODO

    Parameters
    ----------
    in_dict : OrderedDict
        dictionary from input file, where key is method and value is dictionary
        first entry should be reference method
        in sub-dictionary, keys are 'sdfile' and 'sdtag'

    Returns
    -------
    enes_full : 3D list
        enes_full[i][j][k] = ddE of ith method, jth mol, kth conformer.
        ddE = (dE of query method) - (dE of ref method),
        where the dE is computed as conformer M - conformer N,
        and conformer N is chosen from the lowest energy of the ref confs.
        the reference method is not present; i.e., self-comparison is skipped,
        so the max i value represents total number of files minus one.
    rmsds_full : 3D list
        same format as that of enes_full but with conformer RMSDs
    tfds_full : 3D list
        same format as that of enes_full but with conformer TFDs

    """
    # set RMSD calculation parameters
    automorph = True   # take into acct symmetry related transformations
    heavyOnly = False  # do consider hydrogen atoms for automorphisms
    overlay = True     # find the lowest possible RMSD

    # initiate final data lists
    enes_full = []
    rmsds_full = []
    tfds_full = []

    # get first filename representing the reference geometries
    sdf_ref = list(in_dict.values())[0]['sdfile']
    tag_ref = list(in_dict.values())[0]['sdtag']

    # assess each file against reference
    for ff_label, ff_dict in in_dict.items():

        # get details of queried file
        sdf_que = ff_dict['sdfile']
        tag_que = ff_dict['sdtag']

        if sdf_que == sdf_ref:
            continue

        # initiate new sublists
        enes_method = []
        rmsds_method = []
        tfds_method = []

        # open an output file to store query molecules with new SD tags
        outfile = f'{outprefix}_{sdf_que}'
        ofs = oechem.oemolostream()
        if not ofs.open(outfile):
            oechem.OEThrow.Fatal(f"Unable to open {outfile} for writing")

        # load molecules from open reference and query files
        print(f"\n\nOpening reference file {sdf_ref}")
        mols_ref = reader.read_mols(sdf_ref)

        print(f"Opening query file {sdf_que} for [ {ff_label} ] energies")
        mols_que = reader.read_mols(sdf_que)

        # loop over each molecule in reference and query files
        for rmol, qmol in zip(mols_ref, mols_que):

            # initial check that they have same title and number of confs
            rmol_name = rmol.GetTitle()
            rmol_nconfs = rmol.NumConfs()
            if (rmol_name != qmol.GetTitle()) or (rmol_nconfs != qmol.NumConfs()):
                raise ValueError("ERROR: Molecules not aligned in iteration. "
                                "Offending molecules and number of conformers:\n"
                                f"\'{rmol_name}\': {rmol_nconfs} nconfs\n"
                                f"\'{qmol.GetTitle()}\': {qmol.NumConfs()} nconfs")

            # initialize lists to store conformer energies
            enes_ref = []
            enes_que = []
            rmsds_mol = []
            tfds_mol = []

            # loop over each conformer of this mol
            for ref_conf, que_conf in zip(rmol.GetConfs(), qmol.GetConfs()):

                # check confomer match from the specified tag
                ref_id = oechem.OEGetSDData(ref_conf, conf_id_tag)
                que_id = oechem.OEGetSDData(que_conf, conf_id_tag)
                if ref_id != que_id:
                    raise ValueError("ERROR: Conformers not aligned in iteration"
                                    f" for mol: '{rmol_name}'. The conformer "
                                    f"IDs ({conf_id_tag}) for ref and query are:"
                                    f"\n{ref_id}\n{que_id}.")

                # get energies
                enes_ref.append(float(oechem.OEGetSDData(ref_conf, tag_ref)))
                enes_que.append(float(oechem.OEGetSDData(que_conf, tag_que)))

                # compute RMSD between reference and query conformers
                rmsd = oechem.OERMSD(ref_conf, que_conf, automorph,
                                     heavyOnly, overlay)
                rmsds_mol.append(rmsd)

                # compute TFD between reference and query conformers
                tfd = calc_tfd(ref_conf, que_conf)
                tfds_mol.append(tfd)

                # store data in SD tags for query conf, and write conf to file
                oechem.OEAddSDData(que_conf, f'RMSD to {sdf_ref}', str(rmsd))
                oechem.OEAddSDData(que_conf, f'TFD to {sdf_ref}', str(tfd))
                oechem.OEWriteConstMolecule(ofs, que_conf)

            # compute relative energies against lowest E reference conformer
            lowest_ref_idx = enes_ref.index(min(enes_ref))
            rel_enes_ref = np.array(enes_ref) - enes_ref[lowest_ref_idx]
            rel_enes_que = np.array(enes_que) - enes_que[lowest_ref_idx]

            # subtract them to get ddE = dE (ref method) - dE (query method)
            enes_mol = np.array(rel_enes_ref) - np.array(rel_enes_que)

            # store then move on
            enes_method.append(enes_mol)
            rmsds_method.append(np.array(rmsds_mol))
            tfds_method.append(np.array(tfds_mol))
            #print(rmsds_method, len(rmsds_method))
            #print(enes_method, len(enes_method))

        enes_full.append(enes_method)
        rmsds_full.append(rmsds_method)
        tfds_full.append(tfds_method)

    ofs.close()

    return enes_full, rmsds_full, tfds_full


def flatten(list_of_lists):
    "Flatten one level of nesting"
    return np.concatenate(list_of_lists).ravel()

def draw_scatter(xdata, ydata, method_labels, xlabel="", ylabel=""):
    """
    ydata : list of lists
        should have same shape and correspond to xdata
    """
    print(f"Number of data points in scatter plot: {len(flatten(xdata))}")
    markers = ["o", "^", "d", "x", "s", "p"]

    num_methods = len(xdata)
    for i in range(num_methods):
        plt.scatter(xdata[i], ydata[i], marker=markers[i], label=method_labels[i+1])

    plt.xlabel(xlabel)
    plt.ylabel(ylabel)

    # TODO: mv legend outside of plot
    plt.legend()
    plt.show()

def draw_ridgeplot(mydata, datalabel, method_labels):
    """
    Modified from the following code:
    https://seaborn.pydata.org/examples/kde_ridgeplot.html

    Parameters
    ----------
    mydata : list of lists
    datalabel : string

    """
    # Define and use a simple function to label the plot in axes coordinates
    def label(x, color, label):
        ax = plt.gca()
        ax.text(0, .2, label, fontweight="bold", color=color,
                ha="left", va="center", transform=ax.transAxes)

    num_methods = len(mydata)

    # convert data to dataframes for ridge plot
    temp = []
    for i in range(num_methods):
        df = pd.DataFrame(mydata[i], columns = [datalabel])
        df['method'] = method_labels[i+1]
        temp.append(df)

    # list of dataframes concatenated to single dataframe
    df = pd.concat(temp, ignore_index = True)

    # Initialize the FacetGrid object
    pal = sns.palplot(sns.color_palette("tab10"))
    g = sns.FacetGrid(df, row="method", hue="method", aspect=15, height=1.0, palette=pal)

    # draw filled-in densities
    g.map(sns.kdeplot, datalabel, clip_on=False, shade=True, alpha=0.5, lw=1.5, bw=.2)

    # draw outline around densities; can also single outline color: color="k"
    g.map(sns.kdeplot, datalabel, clip_on=False, lw=1.5, bw=.2)

    # draw horizontal line below densities
    g.map(plt.axhline, y=0, lw=1.5, clip_on=False)

    # draw a vertical line at x=0 for visual reference
    g.map(plt.axvline, x=0, lw=0.5, ls='--', color='gray', clip_on=False)

    # add labels to each level and to whole x-axis
    g.map(label, datalabel)

    # Set the subplots to overlap
    #g.fig.subplots_adjust(hspace=0.05)
    g.fig.subplots_adjust(hspace=-.45)

    # Remove axes details that don't play well with overlap
    g.set_titles("")
    g.set(yticks=[])
    g.despine(bottom=True, left=True)

    # save with transparency for overlapping plots
    # TODO generalize
    plt.savefig('test.png', transparent=True)
    plt.show()


def main(in_dict, conf_id_tag, plot):
    """

    Parameter
    ---------
    in_dict : OrderedDict
        dictionary from input file, where key is method and value is dictionary
        first entry should be reference method
        in sub-dictionary, keys are 'sdfile' and 'sdtag'
    plot : Boolean
        generate line plots of conformer energies

    """
    method_labels = list(in_dict.keys())

    # enes_full[i][j][k] = ddE of ith method, jth mol, kth conformer.
    enes_full, rmsds_full, tfds_full = compare_ffs(in_dict, conf_id_tag, 'refdata')

    energies = []
    rmsds = []
    tfds = []

    # flatten all confs/molecules into same list but keep methods distinct
    # energies and rmsds are now 2d lists
    for a, b, c in zip(enes_full, rmsds_full, tfds_full):
        energies.append(flatten(a))
        rmsds.append(flatten(b))
        tfds.append(flatten(c))

    if plot:
        draw_scatter(rmsds, energies, method_labels, "RMSD ($\mathrm{\AA}$)", "ddE (kcal/mol)")
        draw_scatter(tfds, energies, method_labels, "TFD", "ddE (kcal/mol)")
        draw_ridgeplot(energies, 'ddE (kcal/mol)', method_labels)
        draw_ridgeplot(rmsds, 'RMSD ($\mathrm{\AA}$)', method_labels)


### ------------------- Parser -------------------

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()

    parser.add_argument("-i", "--infile",
        help="Name of text file with force field in first column and molecule "
             "file in second column. Columns separated by commas.")

    parser.add_argument("-t", "--conftag",
        help="Name of the SD tag that distinguishes conformers. Within the "
             "same SDF file, no other conformer should have the same tag value."
             " Between two SDF files, the matching conformers should have the "
             "same SD tag and value.")

    parser.add_argument("--plot", action="store_true", default=False,
        help="Generate line plots for every molecule with the conformer "
             "relative energies.")

    # parse arguments
    args = parser.parse_args()
    if not os.path.exists(args.infile):
        parser.error(f"Input file {args.infile} does not exist.")

    # read main input file and check that files within exist
    in_dict = reader.read_check_input(args.infile)

    # run main
    main(in_dict, args.conftag, args.plot)
