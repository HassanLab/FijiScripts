# @File(label="Input image") name
# @File(label="Output folder", style="directory") outfolder
# @Integer(label="Minimum sigma",value=10) smin
# @Integer(label="Maximum sigma",value=40) smax
# @Integer(label="Step size",value=2) step
# @ConvertService convert
# @DatasetService ds
# @OpService ops

import copy, math, os, sys, time
from ij import IJ, ImageStack, ImagePlus
from ij.plugin import Duplicator, GaussianBlur3D, ImageCalculator
from java.lang import Runtime
from java.util.concurrent import Callable
from java.util.concurrent import Executors, ExecutorCompletionService
from net.imagej import Dataset
from net.imglib2.algorithm.gauss import Gauss
from net.imglib2.img.array import ArrayImgFactory


class DogProcessor(Callable):
    def __init__(self, image, sigma, folder):
        self.image = image
        self.sigma = sigma
        self.folder = folder

    def dog(self, sigmaX, sigmaY, sigmaZ, div):
        sigmaA = [sigmaX, sigmaY, sigmaZ]
        sigmaB = [sigmaX / div, sigmaY / div, sigmaZ / div]
        image32 = ops.convert().float32(self.image)
        dogFormula = "gauss(image, " + str(sigmaB) + ") - gauss(image, " + str(sigmaA) + ")"
        result = ops.eval(dogFormula, {"image": image32})
        return result

    def call(self):  
        (sxy, foo, sz, div) = self.sigma
        try:
            result = self.dog(*self.sigma)
        except Exception as e:
            print("Error applying DOG filter: " + str(e))
            return -1
        basename = os.path.join(self.folder, "dog-" + str(sxy) + "_" + str(sz) + "_" + str(div))
        tiff = basename + ".tiff"
        try:
            dataset = ds.create(result)
            ds.save(dataset, tiff)
        except Exception as e:
            print("Error saving result image: " + str(e))
        return self

def main():
    try:
        image = ds.open(str(name))
        folder = str(outfolder)
    except Exception as e:
        print("Error opening image: " + str(e))
        return -1
    
    pool = Executors.newFixedThreadPool(Runtime.getRuntime().availableProcessors() - 2)
    ecs = ExecutorCompletionService(pool)
    sigmas = []
    for sxy in range(smin, smax+1, step):
        for sz in [sxy, sxy/2]:
            for div in [1.5, 2, 3, 4]:
                sigma = (sxy, sxy, sz, div)
                sigmas.append(sigma)
    
    submitted = 0   
    for sigma in sigmas:
        ecs.submit(DogProcessor(image, sigma, folder))
        submitted += 1
    
    while submitted > 0:
        result = ecs.take().get()
        submitted -= 1
    
    pool.shutdown()
    return 0

if __name__ == "__main__" or __name__ == "__builtin__":
    print "BEGIN: " + time.strftime("%c")
    main()
    print "END: " + time.strftime("%c")