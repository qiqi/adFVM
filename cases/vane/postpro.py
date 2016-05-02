from pyRCF import RCF
from compute import getHTC, getIsentropicMa
import config

from match import match_htc, match_velocity
import argparse
parser = argparse.ArgumentParser()
parser.add_argument('case')
parser.add_argument('time', nargs='+', type=float)
user = parser.parse_args(config.args)

solver = RCF(user.case)
mesh = solver.mesh.origMesh
solver.initialize(user.time[0])

nLayers = 1
#nLayers = 200
for time in user.time:
    rho, rhoU, rhoE = solver.initFields(time)
    U, T, p = solver.U, solver.T, solver.p

    patches = ['pressure', 'suction']
    htc = getHTC(T, 420., patches)
    #Ma = getIsentropicMa(p, 171325., patches)
    Ma = getIsentropicMa(p, 1.4e5, patches)
    htc_args = []
    Ma_args = []
    for patchID in patches:
        startFace = mesh.boundary[patchID]['startFace']
        endFace = startFace + mesh.boundary[patchID]['nFaces']
        x = mesh.faceCentres[startFace:endFace, 0]
        nFaces = x.shape[0]
        nFacesPerLayer = nFaces/nLayers
        x = x[:nFacesPerLayer]

        y = htc[patchID].reshape((nLayers, nFacesPerLayer))
        y = y.sum(axis=0)/nLayers
        htc_args.extend([y, x])
        y = Ma[patchID].reshape((nLayers, nFacesPerLayer))
        y = y.sum(axis=0)/nLayers
        print y
        Ma_args.extend([y, x])

    match_htc(*htc_args)
    match_velocity(*Ma_args)
    
