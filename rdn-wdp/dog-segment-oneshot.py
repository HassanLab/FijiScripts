# @File(label="Input image") inputfile
# @Integer(label="DoG sigma",value=18) sigma
# @Float(label="DoG ratio",value=4.0) div
# @Integer(label="Local maxima radius",value=3) radius
# @ConvertService convert
# @DatasetService ds
# @DisplayService display
# @OpService ops

import copy, math, os, sys, time
from ij import IJ, ImageStack, ImagePlus
from ij.measure import ResultsTable
from ij.plugin import ChannelSplitter, RGBStackMerge, Commands
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
from sc.fiji.hdf5 import HDF5ImageJ


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

def threshold(image, value = 1):
    result = ops.threshold().apply(image, FloatType(value))
    return result

def maxima(image, radius):
    imp = convert.convert(ops.copy().img(image), ImagePlus)
    filters = FastFilters3D()
    oimp = ImagePlus("maxima", filters.filterImageStack(imp.getImageStack(), FastFilters3D.MAXLOCAL, radius, radius, radius, Runtime.getRuntime().availableProcessors(), True))
    imp.close()
    maxima = ops.copy().img(convert.convert(oimp, Dataset))
    oimp.close()
    return ops.threshold().apply(maxima, FloatType(0))

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


#hdf5 = str(inputfile)
#csv = hdf5.replace(".h5", ".csv")
#print "Datasets will be loaded from and saved to HDF5 file: " + hdf5
#print "Opening dataset: " + dsegm
#imp = HDF5ImageJ.hdf5read(hdf5, dsegm)
#image = convert.convert(imp, Dataset)
image = ds.open(str(inputfile))
imp = convert.convert(image, ImagePlus)

dogimage = dog(image, sigma, sigma, sigma, div)
display.createDisplay(dogimage)
mask = threshold(dogimage, 0)
mask = convert.convert(mask, ImagePlus)
#method = "Scriptable save HDF5 (append)..."
#options = "save=[" +  hdf5 + "] dsetnametemplate=/watershed/mask formatchannel=%d compressionlevel=0"
#print "Saving mask to dataset: /watershed/mask"
#IJ.run(mask, method, options)
display.createDisplay(mask)

maxima = maxima(dogimage, radius)
maxima = convert.convert(maxima, ImagePlus)
maxima.copyScale(imp)
#options = "save=[" +  hdf5 + "] dsetnametemplate=/watershed/maxima formatchannel=%d compressionlevel=0"
#print "Saving local maxima to dataset: /watershed/maxima"
#IJ.run(maxima, method, options)
display.createDisplay(mask)

watershed = watershed(mask, maxima)
#mask.close()
#maxima.close()
watershed.copyScale(imp)
#imp.close()
#options = "save=[" +  hdf5 + "] dsetnametemplate=/watershed/objects formatchannel=%d compressionlevel=0"
#print "Saving watershed to dataset: /watershed/objects"
#IJ.run(watershed, method, options)
display.createDisplay(watershed)

#channels = []

#for dataset in dmeas.split(","):
#    print "Opening dataset: " + dataset.strip()
#    channel = HDF5ImageJ.hdf5read(hdf5, dataset.strip())
#    channels.append(channel)
#image = RGBStackMerge.mergeChannels(channels, False)
#for channel in channels:
#    channel.close()

#results = measurements(image, watershed)
#print "Saving point cloud to file: " + csv
#results.save(csv)
#watershed.close()
#image.close()

#IJ.run("Quit")
