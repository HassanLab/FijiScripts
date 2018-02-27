# @OpService ops

from java.lang import Runtime

ncpus = Runtime.getRuntime().availableProcessors()
print "CPU number detected is " + str(ncpus)
