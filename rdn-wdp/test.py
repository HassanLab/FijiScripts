# @File(label="Input image") name
# @File(label="Output folder", style="directory") folder
# @Integer(label="DoG sigma",value=20) sigma
# @Float(label="DoG ratio",value=4.0) div
# @Integer(label="Local maxima radius",value=5) radius
# @ConvertService convert
# @DatasetService ds
# @OpService ops

import copy, math, os, sys, time
from ij import IJ, ImageStack, ImagePlus
from ij.measure import ResultsTable
from ij.plugin import ChannelSplitter
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
    result = ops.threshold().isoData(image)
    return result

def maxima(image, radius):
    imp = convert.convert(ops.copy().img(image), ImagePlus)
    filters = FastFilters3D()
    oimp = ImagePlus("maxima", filters.filterImageStack(imp.getImageStack(), FastFilters3D.MAXLOCAL, radius, radius, radius, Runtime.getRuntime().availableProcessors(), True))
    imp.close()
    maxima = ops.copy().img(convert.convert(oimp, Dataset))
    oimp.close()
    return ops.threshold().apply(maxima, FloatType(1))

def watershed(mask, seeds):
    mimp = convert.convert(ops.copy().img(mask), ImagePlus)
    simp = convert.convert(ops.copy().img(seeds), ImagePlus)
    water = Watershed3D(mimp.getImageStack(), simp.getImageStack(), 1.0, 1)
    water.setLabelSeeds(True)
    wimp = water.getWatershedImage3D().getImagePlus()
    mimp.close()
    simp.close()
    watershed = ops.copy().img(convert.convert(wimp, Dataset))
    wimp.close()
    return watershed
    
def segment(watershed):
    imp = convert.convert(ops.copy().img(watershed), ImagePlus)
    objects = addVoxels(readVoxels(imp), imp)
    imp.close()
    return objects

def measurements(image, watershed):
    objects = segment(watershed)
    imp = convert.convert(ops.copy().img(image), ImagePlus)
    measurements = getMeasurements(objects, imp)
    imp.close()
    return measurements


image = ds.open(str(name))
dogimage = dog(image, sigma, sigma, sigma, div)
mask = threshold(dogimage)
maxima = maxima(dogimage, radius)
watershed = watershed(mask, maxima)
dataset = ds.create(watershed)
basename = os.path.join(str(folder), "dog-water-" + str(sigma) + "_" + str(div) + "_" + str(radius))
csv = basename + ".csv"
tiff = basename + ".tif"
ds.save(watershed, tiff)
results = measurements(image, watershed)
results.save(csv)
