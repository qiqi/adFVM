from __future__ import print_function
from mpi4py import MPI
import numpy as np
import subprocess
import time

from .compat import add_at

mpi = MPI.COMM_WORLD
nProcessors = mpi.Get_size()
name = MPI.Get_processor_name()
rank = mpi.Get_rank()
processorDirectory = '/'
if nProcessors > 1:
    processorDirectory = '/processor{0}/'.format(rank)
temp = '/tmp'

def pprint(*args, **kwargs):
    if rank == 0:
        print(*args, **kwargs)
pprint('Running on {0} processors'.format(nProcessors))

def copyToTemp(home, coresPerNode):
    start = time.time()
    if rank % coresPerNode == 0:
        dest = temp + '/.theano'
        subprocess.call(['rm', '-rf', dest])
        subprocess.call(['cp', '-r', home + '/.theano', dest])
    mpi.Barrier()
    end = time.time()
    pprint('Time to copy to {0}: '.format(temp), end-start)
    pprint()
    return temp

def max(data):
    maxData = np.max(data)
    if nProcessors > 1:
        return mpi.allreduce(maxData, op=MPI.MAX)
    else:
        return maxData
def min(data):
    minData = np.min(data)
    if nProcessors > 1:
        return mpi.allreduce(minData, op=MPI.MIN)
    else:
        return minData

def sum(data):
    sumData = np.sum(data)
    if nProcessors > 1:
        return mpi.allreduce(sumData, op=MPI.SUM)
    else:
        return sumData
    
class Exchanger(object):
    def __init__(self):
        self.requests = []
        self.statuses = []

    def exchange(self, remote, sendData, recvData, tag):
        sendRequest = mpi.Isend(sendData, dest=remote, tag=tag)
        recvRequest = mpi.Irecv(recvData, source=remote, tag=tag)
        sendStatus = MPI.Status()
        recvStatus = MPI.Status()
        self.requests.extend([sendRequest, recvRequest])
        self.statuses.extend([sendStatus, recvStatus])

    def wait(self):
        if nProcessors == 1:
            return []
        MPI.Request.Waitall(self.requests, self.statuses)
        return self.statuses

def getRemoteCells(field, meshC):
    # mesh values required outside theano
    #logger.info('fetching remote cells')
    if nProcessors == 1:
        return field
    exchanger = Exchanger()
    mesh = meshC.origMesh
    for patchID in meshC.remotePatches:
        patch = mesh.boundary[patchID]
        local, remote, tag = meshC.getProcessorPatchInfo(patchID)
        startFace = patch['startFace']
        endFace = startFace + patch['nFaces']
        cellStartFace = mesh.nInternalCells + startFace - mesh.nInternalFaces
        cellEndFace = mesh.nInternalCells + endFace - mesh.nInternalFaces
        exchanger.exchange(remote, field[mesh.owner[startFace:endFace]], field[cellStartFace:cellEndFace], tag)
    exchanger.wait()
    return field

def getAdjointRemoteCells(field, meshC):
    if nProcessors == 1:
        return field
    mesh = meshC.origMesh
    jacobian = np.zeros_like(field)
    jacobian[:mesh.nLocalCells] = field[:mesh.nLocalCells]
    precision = field.dtype
    dimensions = field.shape[1:]
    adjointRemoteCells = {}
    exchanger = Exchanger()
    for patchID in meshC.remotePatches:
        patch = mesh.boundary[patchID]
        local, remote, tag = meshC.getProcessorPatchInfo(patchID)
        startFace = patch['startFace']
        endFace = startFace + patch['nFaces']
        cellStartFace = mesh.nInternalCells + startFace - mesh.nInternalFaces
        cellEndFace = mesh.nInternalCells + endFace - mesh.nInternalFaces
        adjointRemoteCells[patchID] = np.zeros((patch['nFaces'],) + dimensions, precision)
        exchanger.exchange(remote, field[mesh.neighbour[startFace:endFace]], adjointRemoteCells[patchID], tag)
    exchanger.wait()
    for patchID in meshC.remotePatches:
        patch = mesh.boundary[patchID]
        startFace = patch['startFace']
        endFace = startFace + patch['nFaces']
        add_at(jacobian, mesh.owner[startFace:endFace], adjointRemoteCells[patchID])
    return jacobian

def gatherCells(field, mesh, axis=0):
    if nProcessors == 1:
        return field
    #nCells = np.array(mpi.gather(mesh.nCells))
    #nCellsPos = np.cumsum(nCells)-nCells[0]
    #if rank == 0:
    #    totalField = np.zeros((np.sum(nCells),) + field.shape[1:])
    #else:
    #    totalField = None
    #mpi.Gatherv(field, [totalField, nCells, nCellsPos])
    #return totalField
    totalField = mpi.gather(field)
    if totalField is not None:
        totalField = np.concatenate(totalField, axis=axis)
    return totalField

def scatterCells(totalField, mesh, axis=0):
    if nProcessors == 1:
        return totalField
    nCells = np.array(mpi.gather(mesh.nCells))
    if totalField is not None:
        nCellsPos = np.cumsum(nCells)[:-1]
        #field = np.zeros((mesh.nCells,) + totalField.shape[1:])
        #mpi.Scatterv([totalField, nCells, nCellsPos], field)
        #return field
        totalField = np.split(totalField, nCellsPos, axis=axis)
    field = mpi.scatter(totalField)
    return field

#def getRemoteCells(stackedFields, mesh):
#    # mesh values required outside theano
#    #logger.info('fetching remote cells')
#    if nProcessors == 1:
#        return stackedFields
#
#    meshC = mesh
#    origMesh = mesh.origMesh
#    meshP = mesh.paddedMesh 
#    mesh = meshP.origMesh
#    precision = stackedFields.dtype
#
#    paddedStackedFields = np.zeros((mesh.nCells, ) + stackedFields.shape[1:], precision)
#    paddedStackedFields[:origMesh.nInternalCells] = stackedFields[:origMesh.nInternalCells]
#    nLocalBoundaryFaces = origMesh.nLocalCells - origMesh.nInternalCells
#    paddedStackedFields[mesh.nInternalCells:mesh.nInternalCells + nLocalBoundaryFaces] = stackedFields[origMesh.nInternalCells:origMesh.nLocalCells]
#
#    exchanger = Exchanger()
#    internalCursor = origMesh.nInternalCells
#    boundaryCursor = origMesh.nCells
#    for patchID in meshC.remotePatches:
#        nInternalCells = len(meshP.remoteCells['internal'][patchID])
#        nBoundaryCells = len(meshP.remoteCells['boundary'][patchID])
#        local, remote, tag = meshC.getProcessorPatchInfo(patchID)
#        exchanger.exchange(remote, stackedFields[meshP.localRemoteCells['internal'][patchID]], paddedStackedFields[internalCursor:internalCursor+nInternalCells], tag)
#        tag += meshC.nLocalPatches + 1
#        exchanger.exchange(remote, stackedFields[meshP.localRemoteCells['boundary'][patchID]], paddedStackedFields[boundaryCursor:boundaryCursor+nBoundaryCells], tag)
#        internalCursor += nInternalCells
#        boundaryCursor += nBoundaryCells
#    exchanger.wait()
#
#    # second round of transferring: does not matter which processor
#    # the second layer belongs to, in previous transfer the correct values have been put in 
#    # the extra remote ghost cells, transfer that portion
#    exchanger = Exchanger()
#    boundaryCursor = origMesh.nCells
#    for patchID in meshC.remotePatches:
#        nBoundaryCells = len(meshP.remoteCells['boundary'][patchID])
#        boundaryCursor += nBoundaryCells
#        nExtraRemoteBoundaryCells = len(meshP.remoteCells['extra'][patchID])
#        nLocalBoundaryCells = origMesh.nLocalCells - origMesh.nInternalCells
#        local, remote, tag = meshC.getProcessorPatchInfo(patchID)
#        # does it work if sendData/recvData is empty
#        exchanger.exchange(remote, paddedStackedFields[-nLocalBoundaryCells + meshP.localRemoteCells['extra'][patchID]], paddedStackedFields[boundaryCursor-nExtraRemoteBoundaryCells:boundaryCursor], tag)
#    exchanger.wait()
#
#    return paddedStackedFields
#
#def getAdjointRemoteCells(paddedJacobian, mesh):
#    # mesh values required outside theano
#    #logger.info('fetching adjoint remote cells')
#    if nProcessors == 1:
#        return paddedJacobian
#
#    meshC = mesh
#    meshP = mesh.paddedMesh 
#    origMesh = mesh.origMesh
#    mesh = meshP.origMesh
#    precision = paddedJacobian.dtype
#    dimensions = paddedJacobian.shape[1:]
#
#    jacobian = np.zeros(((origMesh.nCells,) + dimensions), precision)
#    jacobian[:origMesh.nInternalCells] = paddedJacobian[:origMesh.nInternalCells]
#    nLocalBoundaryFaces = origMesh.nLocalCells - origMesh.nInternalCells
#    jacobian[origMesh.nInternalCells:origMesh.nLocalCells] = paddedJacobian[mesh.nInternalCells:mesh.nInternalCells+nLocalBoundaryFaces]
#
#    exchanger = Exchanger()
#    internalCursor = origMesh.nInternalCells
#    boundaryCursor = origMesh.nCells
#    adjointRemoteCells = {'internal':{}, 'boundary':{}, 'extra':{}}
#    for patchID in meshC.remotePatches:
#        nInternalCells = len(meshP.remoteCells['internal'][patchID])
#        nBoundaryCells = len(meshP.remoteCells['boundary'][patchID])
#        local, remote, tag = meshC.getProcessorPatchInfo(patchID)
#        
#        size = (len(meshP.localRemoteCells['internal'][patchID]), ) + dimensions
#        adjointRemoteCells['internal'][patchID] = np.zeros(size, precision)
#        exchanger.exchange(remote, paddedJacobian[internalCursor:internalCursor+nInternalCells], adjointRemoteCells['internal'][patchID], tag)
#        internalCursor += nInternalCells
#        tag += meshC.nLocalPatches + 1
#
#        size = (len(meshP.localRemoteCells['boundary'][patchID]), ) + dimensions
#        adjointRemoteCells['boundary'][patchID] = np.zeros(size, precision)
#        exchanger.exchange(remote, paddedJacobian[boundaryCursor:boundaryCursor+nBoundaryCells], adjointRemoteCells['boundary'][patchID], tag)
#        boundaryCursor += nBoundaryCells
#        tag += meshC.nLocalPatches + 1
#
#    exchanger.wait()
#    for patchID in meshC.remotePatches:
#        add_at(jacobian, meshP.localRemoteCells['internal'][patchID], adjointRemoteCells['internal'][patchID])
#        add_at(jacobian, meshP.localRemoteCells['boundary'][patchID], adjointRemoteCells['boundary'][patchID])
#
#    # code for second layer: transfer to remote jacobians again and add up
#    exchanger = Exchanger()
#    internalCursor = origMesh.nLocalCells
#    for patchID in meshC.remotePatches:
#        nInternalCells = len(meshP.localRemoteCells['internal'][patchID])
#        local, remote, tag = meshC.getProcessorPatchInfo(patchID)
#        
#        size = (nInternalCells, ) + dimensions
#        adjointRemoteCells['extra'][patchID] = np.zeros(size, precision)
#        exchanger.exchange(remote, jacobian[internalCursor:internalCursor+nInternalCells], adjointRemoteCells['extra'][patchID], tag)
#        internalCursor += nInternalCells
#
#    exchanger.wait()
#    for patchID in meshC.remotePatches:
#        add_at(jacobian, meshP.localRemoteCells['internal'][patchID], adjointRemoteCells['extra'][patchID])
#
#    # make processor cells zero again
#    jacobian[origMesh.nLocalCells:] = 0.
#
#    return jacobian
#
#