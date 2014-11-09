import numpy as np

from field import Field, CellField, IOField
from mesh import Mesh

from config import ad, Logger, T
import config
from parallel import pprint
logger = Logger(__name__)
import time

class Solver(object):
    defaultConfig = {
                        'timeIntegrator': 'euler',
                        'source': None
                    }
    def __init__(self, case, **userConfig):
        logger.info('initializing solver for {0}'.format(case))
        fullConfig = self.__class__.defaultConfig.copy()
        fullConfig.update(userConfig)
        for key in fullConfig:
            setattr(self, key, fullConfig[key])

        self.mesh = Mesh(case)
        self.timeIntegrator = globals()[self.timeIntegrator]
        Field.setSolver(self)

    def setDt(self):
        self.dtc = config.smin(self.dtc, self.endTime-self.t)

    def run(self, endTime=np.inf, writeInterval=config.LARGE, startTime=0.0, dt=1e-3, nSteps=config.LARGE, 
            mode='simulation', initialFields=None, objective=lambda x: 0, perturb=None):

        logger.info('running solver for {0}'.format(nSteps))
        mesh = self.mesh
        #initialize
        if initialFields is not None:
            fields = initialFields
        else:
            fields = self.initFields(startTime)
        if perturb is not None:
            perturb(fields)
        pprint()

        if mode == 'simulation':
            timeSteps = []
            result = objective(fields)
        else:
            solutions = [copy(fields)]
        self.t = T.shared(startTime)
        t = startTime
        self.dt = T.shared(dt)
        self.endTime = endTime
        timeIndex = 0
        stackedFields = np.hstack([phi.field for phi in fields])

        unstack = lambda X, mod: [mod('rho', X[:, 0].reshape((-1,1)), (1,)), mod('rhoU', X[:,1:4], (3,)), mod('rhoE', X[:, 4].reshape((-1,1)), (1,))]
        X = ad.dmatrix()
        X.tag.test_value = (np.random.rand(mesh.nCells, 5))
        phis = unstack(X, CellField)
        #ars, tech = self.equation(*phis, exit=True)
        phis = self.timeIntegrator(self.equation, self.boundary, phis, self)
        Y = ad.concatenate([phi.field for phi in phis], axis=1)
        func = T.function([X], [Y, self.dtc], on_unused_input='warn')#, mode=T.compile.MonitorMode(pre_func=config.inspect_inputs, post_func=config.inspect_outputs))
        #Z = ad.concatenate([phi.field for phi in ars], axis=1)
        #func2 = T.function([X], [Z, tech], on_unused_input='warn')#, mode=T.compile.MonitorMode(pre_func=config.inspect_inputs, post_func=config.inspect_outputs))

        while t < endTime and timeIndex < nSteps:
            start = time.time()

            pprint('Time marching for', ' '.join(self.names))
            for index in range(0, len(fields)):
                fields[index].info()
     
            pprint('Time step', timeIndex)
            stackedFields, dtc = func(stackedFields)
            print(stackedFields)
            print(stackedFields.min())
            print(stackedFields.max())
            print(dtc)
            #stackedFields, tech = func2(stackedFields)
            #print(stackedFields)
            #print(stackedFields[569])
            #print(stackedFields.min(axis=0), stackedFields.argmin(axis=0))
            #print(stackedFields.max(axis=0), stackedFields.argmax(axis=0))
            #print(tech)
            fields = unstack(stackedFields, IOField)

            end = time.time()
            end = time.time()
            pprint('Time for iteration:', end-start)
            
            self.dt.set_value(dtc)
            dt, t = self.dt.get_value(), self.t.get_value()
            if mode == 'simulation':
                result += objective(fields)
                timeSteps.append([t, dt])
            elif mode == 'forward':
                self.clearFields(fields)
                solutions.append(copy(fields))
            elif mode == 'adjoint':
                assert nSteps == 1
                solutions = fields
            else:
                raise Exception('mode not recognized', mode)

            self.t.set_value(round(t + dt, 9))
            t = self.t.get_value()
            timeIndex += 1
            pprint('Simulation Time:', t, 'Time step:', dt)
            if timeIndex % writeInterval == 0:
                self.writeFields(fields, t)
            pprint()

        if mode == 'simulation':
            self.writeFields(fields, t)
            return timeSteps, result
        else:
            return solutions

def euler(equation, boundary, fields, solver):
    LHS = equation(*fields)
    internalFields = [(fields[index].getInternalField() - LHS[index].field*solver.dtc) for index in range(0, len(fields))]
    newFields = boundary(*internalFields)
    return newFields

def RK(equation, boundary, fields, solver):
    start = time.time()

    names = [phi.name for phi in fields]
    pprint('Time marching for', ' '.join(names))
    for phi in fields:
        phi.info()

    def NewFields(a, LHS):
        internalFields = [phi.getInternalField().copy() for phi in fields]
        for termIndex in range(0, len(a)):
            for index in range(0, len(fields)):
                internalFields[index] -= a[termIndex]*LHS[termIndex][index].field*solver.dt
        return boundary(*internalFields)

    def f(a, *LHS):
        pprint('RK step ', f.rk)
        f.rk += 1
        if len(LHS) != 0:
            newFields = NewFields(a, LHS)
        else:
            newFields = fields
        for phi in newFields:
            phi.old = phi
        return equation(*newFields)
    f.rk = 1

    k1 = f([0.])
    k2 = f([0.5], k1)
    k3 = f([0.5], k2)
    k4 = f([1.], k3)
    newFields = NewFields([1./6, 1./3, 1./3, 1./6], [k1, k2, k3, k4])

    for index in range(0, len(fields)):
        newFields[index].name = fields[index].name
    end = time.time()
    pprint('Time for iteration:', end-start)
    return newFields

def implicit(equation, boundary, fields, garbage):
    assert ad.__name__ == 'numpad'
    start = time.time()

    names = [phi.name for phi in fields]
    pprint('Solving for', ' '.join(names))
    for index in range(0, len(fields)):
        fields[index].old = CellField.copy(fields[index])
        fields[index].info()
    nDimensions = np.concatenate(([0], np.cumsum(np.array([phi.dimensions[0] for phi in fields]))))
    nDimensions = zip(nDimensions[:-1], nDimensions[1:])
    def setInternalFields(stackedInternalFields):
        internalFields = []
        # range creates a copy on the array
        for index in range(0, len(fields)):
            internalFields.append(stackedInternalFields[:, range(*nDimensions[index])])
        return boundary(*internalFields)
    def solver(internalFields):
        newFields = setInternalFields(internalFields)
        for index in range(0, len(fields)):
            newFields[index].old = fields[index].old
        return ad.hstack([phi.field for phi in equation(*newFields)])

    internalFields = ad.hstack([phi.getInternalField() for phi in fields])
    solution = ad.solve(solver, internalFields)
    newFields = setInternalFields(solution)
    for index in range(0, len(fields)):
        newFields[index].name = fields[index].name

    end = time.time()
    pprint('Time for iteration:', end-start)
    return newFields

def derivative(newField, oldFields):
    names = [phi.name for phi in oldFields]
    logger.info('computing derivative with respect to {0}'.format(names))
    diffs = [newField.diff(phi.field).toarray().reshape(phi.field.shape) for phi in oldFields]
    result = np.hstack(diffs)
    return result

def copy(fields):
    newFields = [CellField.copy(phi) for phi in fields]
    return newFields

def forget(fields):
    if ad.__name__ != 'numpad':
        return
    for phi in fields:
        phi.field.obliviate()




