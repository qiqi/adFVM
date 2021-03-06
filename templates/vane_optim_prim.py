from adFVM.density import RCF 
import sys
import os
sys.path.append(os.path.expanduser('~/adFVM/templates'))
from adFVM.objectives.vane import objective, getPlane, getWeights

#config.hdf5 = True
nParam = 4

primal = RCF('./', objective=objective, fixedTimeStep=True)
#primal = RCF('/home/talnikar/adFVM/cases/vane/3d_10/', objective=objective)
#primal = RCF('/home/talnikar/adFVM/cases/vane/les/', objective=objective)
getPlane(primal)
getWeights(primal)

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
reportInterval = 1000
nSteps = 300000
writeInterval = 100000
avgStart = 0
sampleInterval = 100
#nSteps = 10
#writeInterval = 5
#avgStart = 0
#sampleInterval = 1
startTime = 3.001
dt = 2e-8

# definition of 1 flow through time
# 4e-4s = (0.08m)/(200m/s)

