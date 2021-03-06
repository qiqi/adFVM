import numpy as np
import sys, os

from adFVM import config
from adFVM.compat import norm, intersectPlane
from adFVM.density import RCF 

config.hdf5 = True
caseDir = './'
#primal = RCF(caseDir, objective='pressureLoss', objectivePLInfo={})
#primal = RCF(caseDir, objective='heatTransfer', objectiveDragInfo="pressure|suction")
primal = RCF(caseDir, timeSeriesAppend='2', fixedTimeStep=True, objective='optim', objectivePLInfo={})
nParam = 4

# pressure loss
def getPlane(solver):
    point = np.array([0.052641,-0.1,0.005])
    normal = np.array([1.,0.,0.])
    ptin = 175158.
    interCells, interArea = intersectPlane(solver.mesh, point, normal)
    return {'cells':interCells.astype(np.int32), 
            'areas': interArea, 
            'normal': normal, 
            'ptin': ptin
           }
primal.defaultConfig["objectivePLInfo"] = getPlane(primal)
    
def makePerturb(index):
    def perturbMesh(fields, mesh, t):
        if not hasattr(perturbMesh, 'perturbation'):
            perturbMesh.perturbation = mesh.getPerturbation(caseDir + 'grad{}/'.format(index))
        return perturbMesh.perturbation
    return perturbMesh
perturb = []
for index in range(0, nParam):
    perturb.append(makePerturb(index))

parameters = 'mesh'
reportInterval = 1
nSteps = 20000
writeInterval = 1000
avgStart = 4000
#nSteps = 18000
#writeInterval = 1000
#avgStart = 3000
sampleInterval = 20
startTime = 3.001
dt = 2e-8
adjParams = [1e-3, 'abarbanel', None]
runCheckpoints = 10

# definition of 1 flow through time
# 4e-4s = (0.08m)/(200m/s)

