# @File(label="Input folder", style="directory") in_folder
# @File(label="Output folder", style="directory") out_folder

import os
from sc.fiji.hdf5 import HDF5ImageJ

#datasets_in = [
#"/raw/DAPI/channel0", "/raw/Venus/channel0", "/raw/mCherry/channel0",
#"/raw/fused/channel0", "/raw/fused/channel1", "/raw/fused/channel2",
#"/weka/pmap0", "/weka/pmap1",
#"/watershed/dog", "/watershed/mask", "/watershed/maxima", "/watershed/objects"
#]

datasets_in = [
"/raw/dapi", "/raw/venus", "/raw/mcherry",
"/aligned/channel2", "/aligned/channel0", "/aligned/channel1",
"/weka/pmap0", "/weka/pmap1",
"/watershed/dog", "/watershed/mask", "/watershed/maxima", "/watershed/objects"
]

datasets_out = [
"/raw/DAPI", "/raw/Venus", "/raw/mCherry",
"/scaled/mCherry", "/scaled/DAPI", "/scaled/Venus",
"/weka/background", "/weka/nuclei",
"/segmentation/DoG", "/segmentation/mask", "/segmentation/maxima", "/segmentation/objects"
]


def process(h5file):
    ifile = os.path.join(str(in_folder), str(h5file))
    ofile = os.path.join(str(out_folder), str(h5file))
    print("Processing " + ifile + " -> " + ofile)
    for key, dataset in enumerate(datasets_in):
        ods = datasets_out[key]
        image = HDF5ImageJ.hdf5read(ifile, dataset, 'zyx')
        if image:
            print("\t" + dataset + " -> " + ods)
            HDF5ImageJ.hdf5write(image, ofile, ods, '%d', '%d', 0, False)
            image.close()
        else:
            print("\t" + dataset + " -> " + "null")


in_folder = str(in_folder)
for h5file in os.listdir(in_folder):
    if str(h5file).endswith(".h5"):
        if os.path.isfile(os.path.join(in_folder, h5file)):
            process(h5file)
