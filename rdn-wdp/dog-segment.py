# @File(label="Input image") inputfile
# @File(label="Output HDF5 name", value="") outputfile
# @File(label="Training data (specify to run ML)", value="") model
# @Integer(label="Probability map index", value=1) pmapidx
# @String(label="Segmentation dataset", value="/raw/fused/channel1") dsegm
# @String(label="Measurement datasets", value="/raw/fused/channel0, /raw/fused/channel2, /raw/fused/channel1") dmeas
# @Integer(label="DoG sigma",value=18) sigma
# @Float(label="DoG ratio",value=4.0) div
# @Integer(label="Local maxima radius",value=3) radius
# @Float(label="Maxima cutoff",value=0.0) cutoff
# @ConvertService convert
# @DatasetService ds
# @DisplayService display
# @OpService ops

import copy, math, os, sys, time
from ij import IJ, ImageStack, ImagePlus
from ij.measure import ResultsTable
from ij.plugin import ChannelSplitter, HyperStackConverter, RGBStackMerge, Commands
from java.lang import Runtime
from java.util import ArrayList
from mcib3d.image3d import ImageHandler, ImageInt
from mcib3d.image3d.processing import FastFilters3D
from mcib3d.image3d.regionGrowing import Watershed3D
from mcib3d.geom import Voxel3D
from mcib3d.geom import Object3DVoxels
from mcib3d.geom import Objects3DPopulation
from net.imagej import Dataset, ImgPlus
from net.imglib2.algorithm.gauss import Gauss
from net.imglib2.img.array import ArrayImgFactory
from net.imglib2.type.numeric.real import FloatType
from net.imglib2.type.numeric.integer import UnsignedShortType
from sc.fiji.hdf5 import HDF5ImageJ
from trainableSegmentation import WekaSegmentation


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

def getMeasurements(objects, image):
    imageChannels = []
    print image
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

def dog(image, sigmaX, sigmaY, sigmaZ, div):
    sigmaA = [sigmaX, sigmaY, sigmaZ]
    sigmaB = [sigmaX / div, sigmaY / div, sigmaZ / div]
    image32 = ops.convert().float32(image)
    dogFormula = "gauss(image, " + str(sigmaB) + ") - gauss(image, " + str(sigmaA) + ")"
    result = ops.eval(dogFormula, {"image": image32})
    return result

def threshold(image):
    result = ops.threshold().apply(image, FloatType(0))
    return result

def maxima(image, radius, cutoff):
    #image16 = ops.convert().uint16(image)
    imp = convert.convert(ops.copy().img(image), ImagePlus)
    filters = FastFilters3D()
    oimp = ImagePlus("maxima", filters.filterImageStack(imp.getImageStack(), FastFilters3D.MAXLOCAL, radius, radius, radius, Runtime.getRuntime().availableProcessors(), True))
    imp.close()
    maxima = ops.copy().img(convert.convert(oimp, Dataset))
    oimp.close()
    return ops.threshold().apply(maxima, FloatType(cutoff))

def watershed(mask, seeds):
    water = Watershed3D(mask.getImageStack(), seeds.getImageStack(), 1.0, 1)
    water.setLabelSeeds(True)
    watershed = water.getWatershedImage3D().getImagePlus()
    return watershed

def segment(watershed):
    objects = addVoxels(readVoxels(watershed), watershed)
    return objects

def measurements(image, watershed):
    objects = segment(watershed)
    measurements = getMeasurements(objects, image)
    return measurements

def weka(imp, model):
    weka = WekaSegmentation(True)
    weka.setTrainingImage(imp)
    print "Loading training data from: " + str(model)
    weka.loadTrainingData(str(model))
    print "Training classifier..."
    weka.trainClassifier()
    print "Classifying image..."
    weka.applyClassifier(True)
    pmap = weka.getClassifiedImage()
    result = HyperStackConverter.toHyperStack(pmap, weka.getNumOfClasses(), imp.getNSlices(), 1, "default", "Color")
    pmap.close()
    return result
    
def weka_extract(pmap, pmapidx):
    splitter = ChannelSplitter()
    return ImagePlus("nuclei", splitter.getChannel(pmap, pmapidx + 1))


inhdf5 = str(inputfile)

if str(outputfile):
    hdf5 = str(outputfile)
else:
    hdf5 = str(inputfile)

csv = hdf5.replace(".h5", ".csv")
print "Datasets will be loaded from: " + inhdf5 +  " and saved to: " + hdf5
print "Opening dataset: " + dsegm
imp = HDF5ImageJ.hdf5read(inhdf5, dsegm)
image = convert.convert(imp, Dataset)

if str(model):
    pmap = weka(imp, model)
    method = "Scriptable save HDF5 (append)..."
    options = "save=[" +  hdf5 + "] dsetnametemplate=/watershed/pmap/label{c} formatchannel=%d compressionlevel=0"
    print "Saving probability maps to dataset: /watershed/pmap/label{c}"
    IJ.run(pmap, method, options)
    nuclei = weka_extract(pmap, pmapidx)
    pmap.close()
    dogimage = dog(convert.convert(nuclei, Dataset), sigma, sigma, sigma, div)
    nuclei.close()
else:
    dogimage = dog(image, sigma, sigma, sigma, div)

dog = convert.convert(dogimage, ImagePlus)
dog.copyScale(imp)
method = "Scriptable save HDF5 (append)..."
options = "save=[" +  hdf5 + "] dsetnametemplate=/watershed/dog formatchannel=%d compressionlevel=0"
print "Saving difference of gaussians to dataset: /watershed/dog"
IJ.run(dog, method, options)

mask = threshold(dogimage)
mask = convert.convert(mask, ImagePlus)
mask.copyScale(imp)
method = "Scriptable save HDF5 (append)..."
options = "save=[" +  hdf5 + "] dsetnametemplate=/watershed/mask formatchannel=%d compressionlevel=0"
print "Saving mask to dataset: /watershed/mask"
IJ.run(mask, method, options)
dog.close()

maxima = maxima(dogimage, radius, cutoff)
maxima = convert.convert(maxima, ImagePlus)
maxima.copyScale(imp)
method = "Scriptable save HDF5 (append)..."
options = "save=[" +  hdf5 + "] dsetnametemplate=/watershed/maxima formatchannel=%d compressionlevel=0"
print "Saving local maxima to dataset: /watershed/maxima"
IJ.run(maxima, method, options)

watershed = watershed(mask, maxima)
mask.close()
maxima.close()
watershed.copyScale(imp)
imp.close()
method = "Scriptable save HDF5 (append)..."
options = "save=[" +  hdf5 + "] dsetnametemplate=/watershed/objects formatchannel=%d compressionlevel=0"
print "Saving watershed to dataset: /watershed/objects"
IJ.run(watershed, method, options)

channels = []

for dataset in dmeas.split(","):
    print "Opening dataset: " + dataset.strip()
    channel = HDF5ImageJ.hdf5read(inhdf5, dataset.strip())
    channels.append(channel)
image = RGBStackMerge.mergeChannels(channels, False)
if image is None:
    image = channels.pop()
else:
    for channel in channels:
        channel.close()

results = measurements(image, watershed)
print "Saving point cloud to file: " + csv
results.save(csv)
watershed.close()
image.close()

#IJ.run("Quit")
