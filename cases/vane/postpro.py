import numpy as np
import sys
from match import *

from adFVM import config
from adFVM.field import IOField
from adFVM.parallel import pprint
from pyRCF import RCF
from compute import getHTC, getIsentropicMa, getPressureLoss, getYPlus

def postprocess(solver, time, suffix=''):
    mesh = solver.mesh.origMesh

    T0 = 420.
    p0 = 175158
    point = np.array([0.052641,-0.1,0.005])
    normal = np.array([1.,0.,0.])
    patches = ['pressure', 'suction']

    pprint('postprocessing', time)
    rho, rhoU, rhoE = solver.initFields(time, suffix=suffix)
    U, T, p = solver.U, solver.T, solver.p
    
    htc = getHTC(T, T0, patches)
    Ma = getIsentropicMa(p, p0, patches)
    wakeCells, pl = getPressureLoss(p, T, U, p0, point, normal)
    uplus, yplus, _, _ = getYPlus(U, T, rho, patches)

    htc = IOField.boundaryField('htc' + suffix, htc, (1,))
    Ma = IOField.boundaryField('Ma' + suffix, Ma, (1,))
    uplus = IOField.boundaryField('uplus' + suffix, uplus, (3,))
    yplus = IOField.boundaryField('yplus' + suffix, yplus, (1,))
    with IOField.handle(time):
        htc.write()
        Ma.write()
        uplus.write()
        yplus.write()

if __name__ == '__main__':
    case = sys.argv[1]
    times = [float(x) for x in sys.argv[2:]]

    solver = RCF(case)
    if len(times) == 0:
        times = solver.mesh.getTimes()
    solver.readFields(times[0])

    # plot over surface normals
    #for patchID in patches:
    #    startFace = mesh.boundary[patchID]['startFace']
    #    endFace = startFace + mesh.boundary[patchID]['nFaces']
    #    index = 0
    #    mult = np.logspace(0, 2, 100)
    #    points = mesh.faceCentres[startFace + index] \
    #           - mesh.normals[startFace + index]*yplus1[patchID][index]*mult.reshape(-1,1)
    #    field = U.interpolate(points)/ustar[patchID][index]
    #    field = ((field**2).sum(axis=1))**0.5
    #    plt.plot(mult, field)
    #    plt.show()

    # average
    time = times[0]
    postprocess(solver, time, suffix='_avg')
    pprint()

    # instantaneous
    #for index, time in enumerate(times):
    #    postprocess(solver, time)
    #    pprint()
