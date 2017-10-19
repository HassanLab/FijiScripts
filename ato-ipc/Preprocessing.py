# @File(label="Directory of the images sequence", style="directory") images_sequence_dir
# @String(label="Image File Extension", required=false, value=".tif") image_extension
# @String(label="Channel identifiers") channel_ids
# @OUTPUT Dataset output

# @ConvertService convert
# @DatasetService ds
# @DisplayService display
# @LegacyService legacy
# @OpService ops

# This script takes a directory as a parameter, find all the files ending with ".tif" in the directory.
# Sort them and stack them to create a 3D dataset.

import os
import re
import sys
import HDF5ImageJ

from de.biomedical_imaging.ij.steger import LineDetector
from ij import IJ, ImagePlus
from ij.plugin import ChannelSplitter
from java.awt import Polygon;
from net.imagej import Dataset
from net.imagej.axis import Axes
from net.imglib2.view import Views
from net.imglib2.type.numeric.integer import UnsignedByteType
from net.imglib2.type.logic import BitType
from org.ilastik import IlastikHDF5Exporter

def tryint(s):
    try:
        return int(s)
    except:
        return s

def alphanum_key(s):
    """ Turn a string into a list of string and number chunks.
        "z23a" -> ["z", 23, "a"]
    """
    return [ tryint(c) for c in re.split('([0-9]+)', s) ]

def human_sort(l):
    """ Sort the given list in the way that humans expect.
    """
    l.sort(key=alphanum_key)

def make_8bit(image):
    values = ops.stats().minMax(image)
    scaled = ops.create().img(image, UnsignedByteType())
    ops.image().normalize(scaled, image, values.a, values.b,
        UnsignedByteType(int(UnsignedByteType().getMinValue())),
        UnsignedByteType(int(UnsignedByteType().getMaxValue())))
    
    return scaled

def make_binary(image):
    values = ops.stats().minMax(image)
    scaled = ops.create().img(image, BitType())
    ops.image().normalize(scaled, image, values.a, values.b,
        BitType(int(BitType().getMinValue())),
        BitType(int(BitType().getMaxValue())))
    
    return scaled

def detect_lines(image):
    pixel = image.getImgPlus().firstElement()
    # Resample image to 8-bit, preserving as much data as possible
    scaled = make_8bit(image)
    # Using legacy ImageJ methods for running RidgeDetection and drawing
    imp = convert.convert(scaled, ImagePlus)
    binary = IJ.createImage("Segments", imp.getWidth(), imp.getHeight(), imp.getStackSize(), pixel.getBitsPerPixel());
    imp_stack = imp.getStack()
    binary_stack = binary.getStack()
    detector = LineDetector()
    for s in range(1, imp_stack.getSize() + 1):
        lines = detector.detectLines(imp_stack.getProcessor(s), 5.41, 0.14, 0, 0, 0, False, False, False, True)
        ip = binary_stack.getProcessor(s)
        for c in lines:
            x = c.getXCoordinates()
            y = c.getYCoordinates()
            LineSurface = Polygon()
            ip.setLineWidth(4);
            ip.setColor(pixel.getMaxValue());
            for j in range(0, len(x)):
                if j > 0:
                    ip.drawLine(int(round(x[j-1])), int(round(y[j-1])), int(round(x[j])), int(round(y[j])))
    
    return convert.convert(binary, Dataset)

# Find image files
images_sequence_dir = str(images_sequence_dir)
channel_fnames = []
channel_names = channel_ids.split()
for channel_name in channel_names:
	channel_fnames.append([])

# Sort file names by channel
for fname in os.listdir(images_sequence_dir):
    if fname.lower().endswith(image_extension):
    	for channel, channel_name in enumerate(channel_names):
    		if channel_name in fname:
        		channel_fnames[channel].append(os.path.join(images_sequence_dir, fname))

# Compute number of channels
n_channels = len(channel_fnames)
if n_channels < 1:
    raise Exception("Not image files found in %s" % images_sequence_dir)

# Compute number of timepoints
n_timepoints = -1
for c in range(0, n_channels):
    human_sort(channel_fnames[c])
    channel_n_timepoints = len(channel_fnames[c])
    if n_timepoints != -1 and channel_n_timepoints != n_timepoints:
        raise Exception("Each channel needs to have same number of timepoints")
    n_timepoints = channel_n_timepoints

timeseries = []
ilastik = []
segmentation = []

#for t in range(0, n_timepoints):
for t in range(0, 2):
    channels = []
    schannels = []
    for c in range(0, n_channels):
        print channel_fnames[c][t]
        image = ds.open(channel_fnames[c][t])
        if (c == 0):
            binary = detect_lines(image)
            channels.append(image)
            schannels.append(binary)
            segmentation.append(make_binary(binary))
        else:
            channels.append(image)
            schannels.append(image)
    timepoint = Views.stack(channels)
    stimepoint = Views.stack(schannels)
    timeseries.append(timepoint)
    ilastik.append(stimepoint)

ilastik = ds.create(Views.stack(ilastik))
ilastik.axis(2).setType(getattr(Axes, "Z"))
ilastik.axis(3).setType(getattr(Axes, "CHANNEL"))
ilastik.axis(4).setType(getattr(Axes, "TIME"))

print "Exporting data for Ilastik " + os.path.basename(images_sequence_dir) + " - Ilastik Raw Input.h5"
exporter = IlastikHDF5Exporter(os.path.join(images_sequence_dir, os.path.basename(images_sequence_dir) + " - Ilastik Raw Input.h5"))
exporter.export(convert.convert(ilastik, ImagePlus), "segmented_timeseries")
exporter.close()
print "Ilastik export done"
ilastik = None

timeseries = ds.create(Views.stack(timeseries))
timeseries.axis(2).setType(getattr(Axes, "Z"))
timeseries.axis(3).setType(getattr(Axes, "CHANNEL"))
timeseries.axis(4).setType(getattr(Axes, "TIME"))

print "Exporting raw data " + os.path.basename(images_sequence_dir) + ".h5"
IJ.run(convert.convert(timeseries, ImagePlus), "Scriptable save HDF5 (new or replace)...",
    "save=[" + os.path.join(images_sequence_dir, os.path.basename(images_sequence_dir) + ".h5") +
    "] dsetnametemplate=/raw/t{t}/channel{c} formattime=%d formatchannel=%d compressionlevel=0");
print "Raw data export done"
timeseries = None

segmentation = ds.create(Views.stack(segmentation))
segmentation.axis(2).setType(getattr(Axes, "Z"))
segmentation.axis(3).setType(getattr(Axes, "TIME"))

print "Exporting segmented data " + os.path.basename(images_sequence_dir) + ".h5"
IJ.run(convert.convert(segmentation, ImagePlus), "Scriptable save HDF5 (append)...",
    "save=[" + os.path.join(images_sequence_dir, os.path.basename(images_sequence_dir) + ".h5") +
    "] dsetnametemplate=/segmented_membranes/t{t}/channel{c} formattime=%d formatchannel=%d compressionlevel=0");
print "Raw data export done"

output = segmentation
