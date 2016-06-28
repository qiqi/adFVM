from field import Field, IOField
from mesh import Mesh
import sys
import os
import numpy as np
import config

case = sys.argv[1]
fields = sys.argv[2:]
mesh = Mesh.create(case)
Field.setMesh(mesh)
meshO = mesh.origMesh

times = mesh.getTimes()

for field in fields:
    # time avg: no dt
    avg = 0.
    for time in times:
        IOField.openHandle(time)
        phi = IOField.read(field)
        IOField.closeHandle()
        phi.partialComplete()
        avg += phi.field
    avg /= len(times)

    # spanwise avg: structured
    nLayers = 200
    nDims = avg.shape[1]
    #nLayers = 1
    def average(start, end):
        nCellsPerLayer = (end-start)/nLayers
        spanAvg = avg[start:end].reshape((nLayers, nCellsPerLayer, nDims)).sum(axis=0)/nLayers
        spanAvg = np.tile(spanAvg, (nLayers,1))
        avg[start:end] = spanAvg

    average(0, meshO.nInternalCells)
    for patchID in mesh.localPatches:
        patch = meshO.boundary[patchID]
        if patch['type'] != 'cyclic':
            cellStartFace = patch['startFace']-meshO.nInternalFaces + meshO.nInternalCells
            cellEndFace = cellStartFace + patch['nFaces']
            average(cellStartFace, cellEndFace)

    phi.name = field + '_avg'
    phi.field = avg
    IOField.openHandle(times[0])
    phi.write()
    IOField.closeHandle()