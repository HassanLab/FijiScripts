# @File(label="Input image") name
# @File(label="Output folder", style="directory") folder
# @Float(label="Median XY sigma", value=2) msigma
# @Float(label="Median Z sigma", value=2) msigmaz
# @Float(label="Local maxima XY sigma", value=2) lsigma
# @Float(label="Local maxima Z sigma", value=2) lsigmaz
# @Float(label="Seed diameter", value=2) sd
# @String(label="Threshold Method", required=true, choices={'otsu', 'huang'}) method_threshold
# @Integer(label="Theads", value=2) ncpus
# @ConvertService convert
# @DatasetService ds
# @DisplayService display
# @LegacyService legacy
# @OpService ops

import os, HDF5ImageJ
from ij import IJ, ImageStack, ImagePlus
from ij.measure import ResultsTable
from ij.plugin import ChannelSplitter
from inra.ijpb.morphology import Morphology
from inra.ijpb.morphology.strel import BallStrel
from java.lang import Runtime
from java.util import ArrayList
from mcib3d.image3d import ImageHandler
from mcib3d.image3d import ImageInt
from mcib3d.image3d import Segment3DSpots
from mcib3d.image3d.processing import FastFilters3D
from mcib3d.image3d.regionGrowing import Watershed3D
from mcib3d.geom import Voxel3D
from mcib3d.geom import Object3DVoxels
from mcib3d.geom import Objects3DPopulation
from net.imagej import Dataset
from net.imglib2.type.numeric.integer import UnsignedShortType
from net.imglib2.algorithm.morphology import Dilation


def threshold(imp):
    image = convert.convert(imp, Dataset)
    histo = ops.run("image.histogram", image)
    threshold_value = ops.run("threshold.%s" % method_threshold, histo)
    threshold_value = UnsignedShortType(int(threshold_value.get()))    
    thresholded = ops.run("threshold.apply", image, threshold_value)
    return convert.convert(thresholded, ImagePlus)

def threshold_maxima(imp):
    image = convert.convert(imp, Dataset)
    thresholded = ops.run("threshold.apply", image, UnsignedShortType(128))
    return convert.convert(thresholded, ImagePlus)
    
def dilate(imp, radius):
    return ImagePlus("seeds", Morphology.dilation(imp.getImageStack(), BallStrel.fromDiameter(radius)))

def readVoxels(imp):
    image = ImageInt.wrap(imp)
    minX = 0
    maxX = image.sizeX
    minY = 0
    maxY = image.sizeY
    minZ = 0
    maxZ = image.sizeZ
    minV = int(image.getMinAboveValue(0))
    maxV = int(image.getMax())
    voxels = []
    for i in range(0, maxV - minV + 1):
        vlist = ArrayList()
        voxels.append(vlist)
    for k in range(minZ, maxZ):
        for j in range(minY, maxY):
            for i in range(minX, maxX):
                pixel = image.getPixel(i, j, k)
                if pixel > 0:
                    voxel = Voxel3D(i, j, k, pixel)
                    oid = int(pixel) - minV
                    voxels[oid].add(voxel)
    objectVoxels = []
    for i in range(0, maxV - minV + 1):
        if voxels[i]:
            objectVoxels.append(voxels[i])
    return objectVoxels

### Create objects from label image voxels
def addVoxels(objectVoxels, imagePlus):
    objects = Objects3DPopulation()
    image = ImageInt.wrap(imagePlus)
    calibration = image.getCalibration();
    for voxels in objectVoxels:
        if voxels:
            objectV = Object3DVoxels(voxels)
            objectV.setCalibration(calibration)
            objectV.setLabelImage(image)
            objectV.computeContours()
            objectV.setLabelImage(None)
            objects.addObject(objectV)
    return objects

### Return 3D measurements
def getMeasurements(objects, image):
        imageChannels = []
        splitter = ChannelSplitter()
        for channel in range (0, image.getNChannels()):
            channelStack = splitter.getChannel(image, channel + 1)
            imageChannels.append(ImageHandler.wrap(channelStack))
    
        results = ResultsTable()
        results.showRowNumbers(False)
        
        for index, objectV in enumerate(objects.getObjectsList()):
            results.incrementCounter()
            results.addValue("Particle", index + 1)
            results.addValue("cx", objectV.getCenterX())
            results.addValue("cy", objectV.getCenterY())
            results.addValue("cz", objectV.getCenterZ())
            results.addValue("Volume", objectV.getVolumePixels())

            for channel, channelImage in enumerate(imageChannels):
                results.addValue("Integral " + "%i" % channel,  objectV.getIntegratedDensity(channelImage))
                results.addValue("Mean " + "%i" % channel, objectV.getPixMeanValue(channelImage))

        return results

# Convert to 8-bit binary
# Run Thresholding (Stack histogram)
# Convert to 8-bit binary
# Run 3D Watershed Split

if ncpus == 0:
    ncpus = Runtime.getRuntime().availableProcessors()

# Open Image
image = ds.open(str(name))

# Initialize 3D Filters
filters = FastFilters3D()

# Run 3D Median Filter
imp = convert.convert(image, ImagePlus)
stack = imp.getImageStack()
median = ImagePlus("median", filters.filterImageStack(stack, FastFilters3D.MEDIAN, msigma, msigma, msigmaz, ncpus, True))

# Run 3D Local Maxima Filter
maxima = ImagePlus("maxima", filters.filterImageStack(stack, FastFilters3D.MAXLOCAL, lsigma, lsigma, lsigmaz, ncpus, True))

# Threshold images
mask = threshold(median)
mask.setTitle("mask")
maxima = dilate(threshold_maxima(maxima), sd)

# Compute watershed
water = Watershed3D(mask.getImageStack(), maxima.getImageStack(), 1.0, 1)
water.setLabelSeeds(True)
watershed = water.getWatershedImage3D().getImagePlus()
watershed.setTitle("watershed")

objects = addVoxels(readVoxels(watershed), imp)
results = getMeasurements(objects, imp)

folder = str(folder)
basename = os.path.join(folder, method_threshold + "-" + str(msigma) + "_" + str(msigmaz) + "_" + str(lsigma) + "_" + str(lsigmaz) + "_" + str(sd))
csv = basename + ".csv"
hdf5 = basename + ".hdf5"

print csv 
print hdf5

results.save(csv)

for image in [median, mask, maxima, watershed]:
    if not os.path.isfile(hdf5):
        method = "Scriptable save HDF5 (new or replace)..."
    else:
        method = "Scriptable save HDF5 (append)..."
    options = "save=[" +  hdf5 + "] dsetnametemplate=/" + image.getTitle() + " compressionlevel=9"
    IJ.run(image, method, options)
