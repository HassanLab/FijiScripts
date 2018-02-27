# @File(label="Directory of the images sequence", style="directory") images_dir
# @DatasetService ds
# @DisplayService display
# @IOService io
# @OpService ops
# @ConvertService convert
# @FormatService fs

# #OUTPUT Dataset output

import math, os, re, random, string
import HDF5ImageJ
from ij import IJ, ImagePlus
from java.lang import Runtime
from java.util.concurrent import Callable
from java.util.concurrent import Executors, ExecutorCompletionService
from net.imagej import ImgPlus
from net.imagej.axis import Axes
from net.imagej.ops import Ops
from net.imglib2 import FinalInterval
from net.imglib2.view import Views
from net.imglib2.img import ImgView
from net.imglib2.img.array import ArrayImgFactory
from net.imglib2.interpolation.randomaccess import NLinearInterpolatorFactory
from net.imglib2.outofbounds import OutOfBoundsConstantValueFactory
from net.imglib2.util import Intervals
from org.yaml.snakeyaml import Yaml
from org.yaml.snakeyaml import DumperOptions

class FileNameSet():
    def __init__(self, basename, filelist, basedir):    
        self.initialized = False
        dapi = basename
        venus = basename.replace("DAPI", "Venus")
        cherry = basename.replace("DAPI", "mCherry")   
        match = re.match('^.*?(\d+)\s*[-_]?\s*?[Dd]is[ck]\s*[-_]?\s*(\d+).*$', basename)
        if match != None:
            sample = match.group(1)
            disc = match.group(2)
            if venus not in filelist:
                regex = re.compile('^.*?' + str(sample) + '.*?[Dd]is[ck]\s*[-_]?\s*[' + str(disc) + ']\s*[-_]?\s*[Vv][Ee][Nn][Uu][Ss].*$')
                match = [m.group(0) for l in filelist for m in [regex.match(l)] if m]
                venus = next(iter(match or []), None)
            if cherry not in filelist:
                regex = re.compile('^.*?' + str(sample) + '.*?[Dd]is[ck]\s*[-_]?\s*[' + str(disc) + ']\s*[-_]?\s*[Mm][Cc][Hh][Ee][Rr][Rr]?[Yy].*$')
                match = [m.group(0) for l in filelist for m in [regex.match(l)] if m]
                cherry = next(iter(match or []), None)  
            if venus and cherry:
                random_id = id_generator()
                hdf5_basename = str(sample) + "_disc_" + str(disc) + "_" + random_id + ".h5"
                yml_basename = str(sample) + "_disc_" + str(disc) + "_" + random_id + ".yml"
                hdf5 = os.path.join(basedir, hdf5_basename)
                yml = os.path.join(basedir, yml_basename)
                self.dapi = dapi
                self.venus = venus
                self.cherry = cherry
                self.hdf5 = hdf5
                self.yml = yml
                self.initialized = True
        if not self.initialized:
            print "Failed to find data for " + basename + "."

    @classmethod
    def fromSample(self, sample, disc, filelist, basedir):
        regex = re.compile('^.*?' + str(sample) + '.*?[Dd]is[ck]\s*[-_]?\s*[' + str(disc) + ']\s*[-_]?\s*[Dd][Aa][Pp][Ii].*$')
        match = [m.group(0) for l in filelist for m in [regex.match(l)] if m]
        basename = next(iter(match or []), None)
        return self(basename, filelist, basedir) if basename else None
        
    @classmethod
    def fromBasename(self, basename, filelist, basedir):
        return self(basename, filelist, basedir)
    
    def getSources(self):
        return {'DAPI': self.dapi, 'Venus': self.venus, 'mCherry': self.cherry} if self.initialized else None

    def getTarget(self):
        return self.hdf5 if self.initialized else None

    def getMetadata(self):
        return self.yml if self.initialized else None

    def id_generator(size=6, chars=string.ascii_uppercase + string.digits):
        return ''.join(random.choice(chars) for _ in range(size))

class SourceImageSet():
    def __init__(self, names):
        self.dapi = io.open(names.dapi)
        self.venus = io.open(names.venus)
        self.cherry = io.open(names.cherry)
        self.initialized = self.sanityCheck()

    def sanityCheck(self):
        for image in [self.dapi, self.venus, self.cherry]:
            if image:
                d = image.dimensionIndex(Axes.Z)
                if d >= 0 and image.max(d) > 20:
                    return True
        return False

    def getImages(self):
        return {'DAPI': self.dapi, 'Venus': self.venus, 'mCherry': self.cherry} if self.initialized else None

    def getReference(self):
        return self.dapi if self.initialized else None


class MetadataSet():
    def __init__(self, names):
        self.dapi = self.readMetadata(names.dapi)
        self.venus = self.readMetadata(names.venus)
        self.cherry = self.readMetadata(names.cherry)
        self.initialized = True
        for metadata in [self.dapi, self.venus, self.cherry]:
            if metadata is None:
                self.initialized = False

    def readMetadata(self, image):
        if image:
            metadict = {}
            format = fs.getFormat(image)
            metadata = format.createParser().parse(image)
            for entry in metadata.getTable().entrySet():
                key = entry.key
                value = entry.value
                match = re.match('^\[(.*?)\]\s*(.*)$', key)
                if match:
                    group = match.group(1)
                    key = match.group(2)
                    if not group in metadict:
                        metadict[group] = {}
                    metadict[group][key] = value
                else: 
                    metadict[key] = value
            return metadict
        else:
            return None        

    def getMedatada(self):
        return {'DAPI': self.dapi, 'Venus': self.venus, 'mCherry': self.cherry}

    def getYaml(self):
        options = DumperOptions()
        options.setDefaultFlowStyle(DumperOptions.FlowStyle.FLOW)
        options.setPrettyFlow(True)
        options.setIndent(4)
        yaml = Yaml(options)
        return yaml.dump(self.getMedatada())

    
class ImageFusion():
    def __init__(self, sources):
        if sources.initialized:
            images = sources.getImages()
            self.reference = sources.getReference()
            self.images = []
            for key, image in images.items():
                d = image.dimensionIndex(Axes.CHANNEL)
                scaled = self.__scaleImage(image)
                if d >= 0:
                    for c in range(scaled.min(d), scaled.max(d) + 1):
                        channel = Views.hyperSlice(scaled, d, c)
                        self.images.append(channel)
                else:
                    self.images.append(scaled)
            self.initialized = True
        else:
            self.initialized = False

    def __scaleImage(self, image):
        axes = []
        scales = []
        resize = False
        for d in range(0, image.numDimensions()):
            axis = image.axis(d)
            if axis.type().isSpatial():
                bd = self.reference.dimensionIndex(axis.type())
                scale = (self.reference.max(bd) - self.reference.min(bd) + 1.0) / (image.max(d) - image.min(d) + 1.0)
                resize = resize or (scale != 1.0)
                scales.append(scale)
            else:
                scales.append(1.0)
        d = image.dimensionIndex(Axes.CHANNEL)
        return ops.transform().scale(image, scales, NLinearInterpolatorFactory()) if resize else image

    def getAlignedImage(self, offsets):
        if not self.initialized:
            return None
        zidx = self.reference.dimensionIndex(Axes.Z)
        zaxis = self.reference.axis(zidx)
        if len(offsets) == len(self.images):
            zshifts = [round(zaxis.rawValue(offset)) for offset in offsets]
        else:
            zshifts = [0 for x in range(0, len(self.images))]
        zsmin = min(zshifts) if min(zshifts) < 0 else 0
        zsmax = max(zshifts) if max(zshifts) > 0 else 0
        zslices = self.reference.max(zidx) + zsmax - zsmin
        
        stack = []
        zero = self.reference.firstElement().createVariable()
        zero.setZero()
        for i, image in enumerate(self.images):
            imin = []
            imax = [] 
            image = Views.extendValue(image, zero)
            for d in range(0, image.numDimensions()):
                if d == (self.reference.dimensionIndex(Axes.Z) - 1):
                    dmin = self.reference.min(d) + zshifts[i] - zsmax
                    dmax = dmin + zslices
                else:
                    dmin = self.reference.min(d)
                    dmax = self.reference.max(d)
                imin.append(long(dmin))
                imax.append(long(dmax))
            stack.append(Views.offsetInterval(image, FinalInterval(imin, imax)))
        
        result = ds.create(Views.stack(stack))
        result.setAxis(self.reference.axis(self.reference.dimensionIndex(Axes.X)), 0)
        result.setAxis(self.reference.axis(self.reference.dimensionIndex(Axes.Y)), 1)
        result.setAxis(self.reference.axis(self.reference.dimensionIndex(Axes.Z)), 2)
        result.axis(3).setType(Axes.CHANNEL)
        return result

    def getImage(self):
        if not self.initialized:
            return None
        result = ds.create(Views.stack(self.images))
        result.setAxis(self.reference.axis(self.reference.dimensionIndex(Axes.X)), 0)
        result.setAxis(self.reference.axis(self.reference.dimensionIndex(Axes.Y)), 1)
        result.setAxis(self.reference.axis(self.reference.dimensionIndex(Axes.Z)), 2)
        result.axis(3).setType(Axes.CHANNEL)
        return result


class ImagePreprocessor(Callable):
    def __init__(self, files, offsets):
        self.offsets = offsets
        self.files = files
        self.initialized = False
        self.sources = None
        self.metadata = None
        self.processed = None
        self.called = False

    def initialize(self):
        if self.files:
            self.sources = SourceImageSet(self.files)
            self.metadata = MetadataSet(self.files)
            if self.sources and self.metadata:
                self.processed = ImageFusion(self.sources)
                self.initialized = True

    def destroy(self):
        if self.sources:
            del self.sources
        if self.metadata:
            del self.metadata
        if self.processed:
            del self.processed
        self.initialized = False

    def saveMetadata(self):
        if self.initialized:
            filename = self.files.yml
            print "Exporting metadata " +  filename
            metafile = open(filename, "w")
            metafile.write(self.metadata.getYaml())
            metafile.close()
            print "Metadata export done"
        
    def saveRaw(self):
        if self.initialized:
            filename = self.files.hdf5
            print "Exporting raw data " +  filename
            images = self.sources.getImages()
            if images:
                for name, image in images.items():
                    if not os.path.isfile(filename):
                        method = "Scriptable save HDF5 (new or replace)..."
                    else:
                        method = "Scriptable save HDF5 (append)..."
                    options = "save=[" +  filename + "] dsetnametemplate=/raw/" + name + "/channel{c} formatchannel=%d compressionlevel=9"
                    IJ.run(convert.convert(image, ImagePlus), method, options)
                print "Raw data export done"
            else:
                print "There were no images to export"

    def saveAligned(self):
        if self.initialized:
            filename = self.files.hdf5
            print "Exporting aligned data " +  filename
            image = self.processed.getAlignedImage(self.offsets)
            if image:
                if not os.path.isfile(filename):
                    method = "Scriptable save HDF5 (new or replace)..."
                else:
                    method = "Scriptable save HDF5 (append)..."
                options = "save=[" +  filename + "] dsetnametemplate=/raw/aligned/channel{c} formatchannel=%d compressionlevel=0"
                IJ.run(convert.convert(image, ImagePlus), method, options)
                print "Aligned data export done"

    def call(self):
        self.initialize()
        
        self.saveMetadata()
        self.saveRaw()
        self.saveAligned()
        self.destroy()
        self.called = True
        return self

filelist = []
for path, subdirs, files in os.walk(str(images_dir)):
    for name in files:
        if name.endswith(".oif"):
            filelist.append(os.path.join(path, name))

samples = []
for name in filelist:
    if "dapi" in name.lower():
        sample = FileNameSet(name, filelist, str(images_dir))
        if sample.initialized:
            samples.append(sample)

offsets = [0, 1, 1]
#pool = Executors.newFixedThreadPool(Runtime.getRuntime().availableProcessors() - 2)
pool = Executors.newFixedThreadPool(2)
ecs = ExecutorCompletionService(pool)

for sample in samples:
    ecs.submit(ImagePreprocessor(sample, offsets))

submitted = len(samples)
while submitted > 0:
    result = ecs.take().get()
    submitted -= 1

pool.shutdown()
