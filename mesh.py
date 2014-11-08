import numpy as np
from scipy import sparse as sp
import re
import time

from config import ad, adsparse, Logger
from parallel import pprint, Exchanger
logger = Logger(__name__)
import config, parallel

class Mesh(object):
    def __init__(self, caseDir):
        start = time.time()
        pprint('Reading mesh')

        self.case = caseDir + parallel.processorDirectory
        meshDir = self.case + 'constant/polyMesh/'
        self.faces = self.read(meshDir + 'faces', np.int32)
        self.points = self.read(meshDir + 'points', float)
        self.owner = self.read(meshDir + 'owner', np.int32).ravel()
        self.neighbour = self.read(meshDir + 'neighbour', np.int32).ravel()
        self.boundary = self.readBoundary(meshDir + 'boundary')
        self.origPatches = self.getOrigPatches()
        self.defaultBoundary = self.getDefaultBoundary()
        self.calculatedBoundary = self.getCalculatedBoundary()

        self.nInternalFaces = len(self.neighbour)
        self.nFaces = len(self.owner)
        self.nBoundaryFaces = self.nFaces-self.nInternalFaces
        self.nInternalCells = np.max(self.owner)+1
        self.nGhostCells = self.nBoundaryFaces
        self.nCells = self.nInternalCells + self.nGhostCells

        self.normals = self.getNormals()
        self.faceCentres, self.areas = self.getFaceCentresAndAreas()
        # uses neighbour
        self.cellFaces = self.getCellFaces()     # nInternalCells
        self.cellCentres, self.volumes = self.getCellCentresAndVolumes() # nCells after ghost cell mod
        # uses neighbour
        self.sumOp = self.getSumOp()             # (nInternalCells, nFaces)
        self.absSumOp = self.getAbsSumOp()             # (nInternalCells, nFaces)
        
        # ghost cell modification
        self.createGhostCells()
        self.deltas = self.getDeltas()           # nFaces
        self.weights = self.getWeights()   # nFaces

        end = time.time()
        pprint('Time for reading mesh:', end-start)
        pprint()

    def read(self, foamFile, dtype):
        logger.info('read {0}'.format(foamFile))
        content = open(foamFile).read()
        foamFileDict = re.search(re.compile('FoamFile\n{(.*?)}\n', re.DOTALL), content).group(1)
        assert re.search('format[\s\t]+(.*?);', foamFileDict).group(1) == config.fileFormat
        start = content.find('(') + 1
        end = content.rfind(')')
        if config.fileFormat == 'binary':
            if foamFile[-5:] == 'faces':
                nFaces1 = int(re.search('[0-9]+', content[start-2:0:-1]).group(0)[::-1])
                endIndices = start + nFaces1*4
                faceIndices = np.fromstring(content[start:endIndices], dtype)
                faceIndices = faceIndices[1:] - faceIndices[:-1]
                startData = content.find('(', endIndices) + 1
                data = np.fromstring(content[startData:end], dtype)
                nCellFaces = faceIndices[0] 
                return np.hstack((faceIndices.reshape(-1, 1), data.reshape(len(data)/nCellFaces, nCellFaces)))
            else:
                data = np.fromstring(content[start:end], dtype)
                if foamFile[-6:] == 'points':
                    data = data.reshape(len(data)/3, 3)
                return data
        else:
            f = lambda x: list(filter(None, re.split('[ ()\n]+', x)))
            return np.array(list(map(f, filter(None, re.split('\n', content[start:end])))), dtype)

    def readBoundary(self, boundaryFile):
        logger.info('read {0}'.format(boundaryFile))
        content = removeCruft(open(boundaryFile).read())
        patches = re.findall(re.compile('([A-Za-z0-9_]+)[\r\s\n]+{(.*?)}', re.DOTALL), content)
        boundary = {}
        for patch in patches:
            boundary[patch[0]] = dict(re.findall('\n[ \t]+([a-zA-Z]+)[ ]+(.*?);', patch[1]))
            boundary[patch[0]]['nFaces'] = int(boundary[patch[0]]['nFaces'])
            boundary[patch[0]]['startFace'] = int(boundary[patch[0]]['startFace'])
        return boundary

    def getNormals(self):
        logger.info('generated normals')
        v1 = self.points[self.faces[:,1]]-self.points[self.faces[:,2]]
        v2 = self.points[self.faces[:,2]]-self.points[self.faces[:,3]]
        normals = np.cross(v1, v2)
        return normals / config.norm(normals, axis=1).reshape(-1,1)

    def getCellFaces(self):
        logger.info('generated cell faces')
        enum = lambda x: np.column_stack((np.indices(x.shape)[0], x)) 
        combined = np.concatenate((enum(self.owner), enum(self.neighbour)))
        cellFaces = combined[combined[:,1].argsort(), 0]
        # todo: make it a list ( investigate np.diff )
        return cellFaces.reshape(self.nInternalCells, len(cellFaces)/self.nInternalCells)

    def getCellCentresAndVolumes(self):
        logger.info('generated cell centres and volumes')
        nCellFaces = self.cellFaces.shape[1]
        cellCentres = np.mean(self.faceCentres[self.cellFaces], axis=1)
        sumCentres = cellCentres*0
        sumVolumes = np.sum(sumCentres, axis=1).reshape(-1,1)
        areaNormals = self.areas * self.normals
        for index in range(0, nCellFaces):
            indices = self.cellFaces[:,index]
            height = cellCentres-self.faceCentres[indices]
            volumes = np.abs(np.sum(areaNormals[indices]*height, axis=1)).reshape(-1,1)/3
            centres = (3./4)*self.faceCentres[indices] + (1./4)*cellCentres
            sumCentres += volumes * centres
            sumVolumes += volumes
        cellCentres = sumCentres/sumVolumes
        return cellCentres, sumVolumes

    def getFaceCentresAndAreas(self):
        logger.info('generated face centres and areas')
        nFacePoints = self.faces[0, 0]
        faceCentres = np.mean(self.points[self.faces[:,1:]], axis=1)
        sumAreas = 0
        sumCentres = 0
        for index in range(1, nFacePoints+1):
            points = self.points[self.faces[:, index]]
            nextPoints = self.points[self.faces[:, (index % nFacePoints)+1]]
            centres = (points + nextPoints + faceCentres)/3
            normals = np.cross((nextPoints - points), (faceCentres - points))
            areas = (config.norm(normals, axis=1)/2).reshape(-1,1)
            sumAreas += areas
            sumCentres += areas*centres
        faceCentres = sumCentres/sumAreas
        return faceCentres, sumAreas

    def getDeltas(self):
        logger.info('generated deltas')
        P = self.cellCentres[self.owner]
        N = self.cellCentres[self.neighbour]
        return config.norm(P-N, axis=1).reshape(-1,1)

    def getWeights(self):
        logger.info('generated face deltas')
        P = self.cellCentres[self.owner]
        N = self.cellCentres[self.neighbour]
        F = self.faceCentres
        neighbourDist = np.abs(np.sum((F-N)*self.normals, axis=1))
        ownerDist = np.abs(np.sum((F-P)*self.normals, axis=1))
        weights = neighbourDist/(neighbourDist + ownerDist)
        return weights.reshape(-1,1)

    def getSumOp(self):
        logger.info('generated sum op')
        owner = sp.csc_matrix((np.ones(self.nFaces), self.owner, range(0, self.nFaces+1)), shape=(self.nInternalCells, self.nFaces))
        Nindptr = np.concatenate((range(0, self.nInternalFaces+1), self.nInternalFaces*np.ones(self.nFaces-self.nInternalFaces, int)))
        neighbour = sp.csc_matrix((-np.ones(self.nInternalFaces), self.neighbour[:self.nInternalFaces], Nindptr), shape=(self.nInternalCells, self.nFaces))
        # skip empty patches
        for patchID in self.boundary:
            patch = self.boundary[patchID]
            if patch['type'] == 'empty' and patch['nFaces'] != 0:
                pprint('Deleting empty patch ', patchID)
                startFace = patch['startFace']
                endFace = startFace + patch['nFaces']
                owner.data[startFace:endFace] = 0
        sumOp = (owner + neighbour).tocsr()
        return adsparse.CSR(sumOp.data, sumOp.indices, sumOp.indptr, sumOp.shape)

    def getAbsSumOp(self):
        logger.info('generated abs sum op')
        owner = sp.csc_matrix((np.ones(self.nFaces), self.owner, range(0, self.nFaces+1)), shape=(self.nInternalCells, self.nFaces))
        Nindptr = np.concatenate((range(0, self.nInternalFaces+1), self.nInternalFaces*np.ones(self.nFaces-self.nInternalFaces, int)))
        neighbour = sp.csc_matrix((np.ones(self.nInternalFaces), self.neighbour[:self.nInternalFaces], Nindptr), shape=(self.nInternalCells, self.nFaces))
        sumOp = (owner + neighbour).tocsr()
        return adsparse.CSR(sumOp.data, sumOp.indices, sumOp.indptr, sumOp.shape)

    def getDefaultBoundary(self):
        logger.info('generated default boundary')
        boundary = {}
        for patchID in self.boundary:
            boundary[patchID] = {}
            if self.boundary[patchID]['type'] in config.defaultPatches:
                boundary[patchID]['type'] = self.boundary[patchID]['type']
            else:
                boundary[patchID]['type'] = 'zeroGradient'
        return boundary

    def getCalculatedBoundary(self):
        logger.info('generated calculated boundary')
        boundary = {}
        for patchID in self.boundary:
            boundary[patchID] = {}
            if self.boundary[patchID]['type'] in config.coupledPatches:
                boundary[patchID]['type'] = self.boundary[patchID]['type']
            else:
                boundary[patchID]['type'] = 'calculated'
        return boundary

    def getOrigPatches(self):
        origPatches = []
        for patchID in self.boundary:
            if self.boundary[patchID]['type'] not in config.processorPatches:
                origPatches.append(patchID)
        origPatches.sort()
        return origPatches

    def createGhostCells(self):
        logger.info('generated ghost cells')
        self.neighbour = np.concatenate((self.neighbour, np.zeros(self.nBoundaryFaces, np.int32)))
        self.cellCentres = np.concatenate((self.cellCentres, np.zeros((self.nBoundaryFaces, 3))))
        mpi_Requests = []
        mpi_Data = []
        exchanger = Exchanger()
        for patchID in self.boundary:
            patch = self.boundary[patchID]
            startFace = patch['startFace']
            nFaces = patch['nFaces']
            # empty patches
            if nFaces == 0:
                continue
            endFace = startFace + nFaces
            cellStartFace = self.nInternalCells + startFace - self.nInternalFaces
            cellEndFace = self.nInternalCells + endFace - self.nInternalFaces
            # append neighbour
            self.neighbour[startFace:endFace] = range(cellStartFace, cellEndFace)
            if patch['type'] == 'cyclic': 
                neighbourPatch = self.boundary[patch['neighbourPatch']]   
                neighbourStartFace = neighbourPatch['startFace']
                neighbourEndFace = neighbourStartFace + nFaces
                # apply transformation: single value
                # append cell centres
                patch['transform'] = self.faceCentres[startFace]-self.faceCentres[neighbourStartFace]
                self.cellCentres[cellStartFace:cellEndFace] = patch['transform'] + self.cellCentres[self.owner[neighbourStartFace:neighbourEndFace]]

            elif patch['type'] == 'processor':
                patch['neighbProcNo'] = int(patch['neighbProcNo'])
                patch['myProcNo'] = int(patch['myProcNo'])
                local = patch['myProcNo']
                remote = patch['neighbProcNo']
                # exchange data
                tag = 0
                exchanger.exchange(remote, self.cellCentres[self.owner[startFace:endFace]], self.cellCentres[cellStartFace:cellEndFace], tag)

            elif patch['type'] == 'processorCyclic':
                patch['neighbProcNo'] = int(patch['neighbProcNo'])
                patch['myProcNo'] = int(patch['myProcNo'])
                local = patch['myProcNo']
                remote = patch['neighbProcNo']
                if patch['type'] == 'processorCyclic':
                    commonPatch = self.boundary[patchID]['referPatch']
                    if local > remote:
                        commonPatch = self.boundary[commonPatch]['neighbourPatch']
                    tag = 1 + self.origPatches.index(commonPatch)
                # apply transformation
                exchanger.exchange(remote, -self.faceCentres[startFace:endFace] + self.cellCentres[self.owner[startFace:endFace]], self.cellCentres[cellStartFace:cellEndFace], tag)
            else:
                # append cell centres
                self.cellCentres[cellStartFace:cellEndFace] = self.faceCentres[startFace:endFace]
        exchanger.wait()
        for patchID in self.boundary:
            patch = self.boundary[patchID]
            startFace = patch['startFace']
            nFaces = patch['nFaces']
            # empty patches
            if nFaces == 0:
                continue
            endFace = startFace + nFaces
            cellStartFace = self.nInternalCells + startFace - self.nInternalFaces
            cellEndFace = self.nInternalCells + endFace - self.nInternalFaces

            if patch['type'] == 'processorCyclic':
                self.cellCentres[cellStartFace:cellEndFace] += self.faceCentres[startFace:endFace]

def removeCruft(content, keepHeader=False):
    # remove comments and newlines
    content = re.sub(re.compile('/\*.*\*/',re.DOTALL ) , '' , content)
    content = re.sub(re.compile('//.*\n' ) , '' , content)
    content = re.sub(re.compile('\n\n' ) , '\n' , content)
    # remove header
    if not keepHeader:
        content = re.sub(re.compile('FoamFile\n{(.*?)}\n', re.DOTALL), '', content)
    return content


def extractField(data, size, vector):
    extractScalar = lambda x: re.findall('[0-9\.Ee\-]+', x)
    if vector:
        extractor = lambda y: list(map(extractScalar, re.findall('\(([0-9\.Ee\-\r\n\s\t]+)\)', y)))
    else:
        extractor = extractScalar
    nonUniform = re.search('nonuniform', data)
    data = re.search(re.compile('[A-Za-z<>\s\r\n]+(.*)', re.DOTALL), data).group(1)
    if nonUniform is not None:
        start = data.find('(') + 1
        end = data.rfind(')')
        if config.fileFormat == 'binary':
            internalField = ad.array(np.fromstring(data[start:end], dtype=float))
            if vector:
                internalField = internalField.reshape((len(internalField)/3, 3))
        else:
            internalField = ad.array(np.array(extractor(data[start:end]), dtype=float))
        if not vector:
            internalField = internalField.reshape((-1, 1))
    else:
        internalField = ad.array(np.tile(np.array(extractor(data)), (size, 1)))
    return internalField

def writeField(handle, field, dtype, initial):
    handle.write(initial + ' nonuniform List<'+ dtype +'>\n')
    handle.write('{0}\n('.format(len(field)))
    if config.fileFormat == 'binary':
        handle.write(ad.value(field).tostring())
    else:
        handle.write('\n')
        for value in ad.value(field):
            if dtype == 'scalar':
                handle.write(str(value[0]) + '\n')
            else:
                handle.write('(' + ' '.join(np.char.mod('%f', value)) + ')\n')
    handle.write(')\n;\n')

