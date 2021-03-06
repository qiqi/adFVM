import numpy as np
import scipy as sp
import scipy.linalg
from scipy.stats import norm
#from scipy.optimize import *
import nlopt
#import matplotlib.pyplot as plt
from pyDOE import *

def _sanitize(x):
    if isinstance(x, list):
        x = np.array(x)
    if len(x.shape) == 1:
        return x.reshape(-1, x.shape[0])
    return x

def _optimize(fun, bounds, cons=None):
    #res = differential_evolution(fun, bounds)
    #return res.x, res.fun[0]
    def nlopt_fun(x, grads):
        if grads.size > 0:
            raise Exception("!")
        else:
            if cons:
                return fun(x) + 100*max(0, cons(x))
            else:
                return fun(x)

    def nlopt_constraint(x, grads):
        if grads.size > 0:
            raise Exception("!")
        else:
            return 0.5-cons(x)

    opt = nlopt.opt(nlopt.GN_DIRECT_L, bounds.shape[0])
    opt.set_min_objective(nlopt_fun)
    opt.set_lower_bounds(bounds[:,0])
    opt.set_upper_bounds(bounds[:,1])
    opt.set_maxeval(1000)
    #if cons:
    #    opt.add_inequality_constraint(nlopt_constraint)
    x = (bounds[:,0] + bounds[:,1])/2
    res = opt.optimize(x)

    opt = nlopt.opt(nlopt.LN_SBPLX, bounds.shape[0])
    #opt = nlopt.opt(nlopt.LN_COBYLA, bounds.shape[0])
    opt.set_min_objective(nlopt_fun)
    opt.set_lower_bounds(bounds[:,0])
    opt.set_upper_bounds(bounds[:,1])
    #if cons:
    #    opt.add_inequality_constraint(nlopt_constraint)
    opt.set_maxeval(100)
    res = opt.optimize(res)

    return res, opt.last_optimum_value()

class Kernel(object):
    pass

class SquaredExponentialKernel(Kernel):
    def __init__(self, L, sigma):
        self.L = np.array(L)
        self.sigma = sigma

    def evaluate(self, x, xp):
        L, sigma = self.L, self.sigma
        L = L[None,None,:]
        x = _sanitize(x)
        xp = _sanitize(xp)
        d = (x[:,None,:]-xp[None,:,:])/L
        return sigma**2*np.exp(-(d**2).sum(axis=-1)/2)

class GaussianProcess(object):
    def __init__(self, kernel, bounds, noise=None, noiseGP=False, cons=None):
        self.kernel = kernel
        self.x = []
        self.y = []
        self.yn = []
        self.bounds = np.array(bounds)
        self.noise = noise
        self.ndim = self.bounds.shape[0]
        self.cons = cons
        if noise is None:
            self.noise = [0., np.zeros(self.ndim)]
        self.noiseGP = None
        if noiseGP:
            kernel = SquaredExponentialKernel(kernel.L, 1.)
            self.noiseGP = GaussianProcess(kernel, bounds, noise=0.1)
    
    def evaluate(self, xs):
        xs = _sanitize(xs)
        x, y = np.array(self.x), np.array(self.y)
        Ki = self.kernel.evaluate(xs, x)

        K = self.kernel.evaluate(xs, xs)
        Kd = self.Kd
        Kd = Kd + 1e-30*np.diag(np.ones_like(np.diag(Kd)))
        L = sp.linalg.cho_factor(Kd)
        mu = np.dot(Ki, sp.linalg.cho_solve(L, y))
        cov = K - np.dot(Ki, sp.linalg.cho_solve(L, Ki.T))
        return mu.flatten(), cov

    def exponential(self, xs):
        mu, cov = self.evaluate(xs)
        emu = np.exp(mu + np.diag(cov)/2)
        ecov = np.outer(emu, emu)*(np.exp(cov)-1)
        return emu, ecov

    def explore(self, n, func):
        assert len(self.x) == 0

        bounds = self.bounds.T
        if x is None:
            if self.cons:
                xa = []
                while len(xa) < n:
                    x = lhs(self.ndim, samples=n, criterion='maximin')
                    x = bounds[[0]] + x*(bounds[[1]]-bounds[[0]])
                    xa.extend(filter(lambda y: self.cons(y) <= 0., x))
                x = xa[:n]
            else:
                x = lhs(self.ndim, samples=n, criterion='maximin')
                x = bounds[[0]] + x*(bounds[[1]]-bounds[[0]])
        res = func(x)
        if len(res) > 2:
            y, _, yn, _ = res
            if not isinstance(yn, float):
                yn = list(yn)
            self.train(list(x), list(y), yn)
        else:
            y, _ = res
            self.train(list(x), list(y))

    def train(self, x, y, yn=0.):
        if len(np.array(x).shape) == 1:
            x = [x]
            y = [y]
            if not isinstance(yn, float):
                yn = [yn]
        self.x.extend(x)
        self.y.extend(y)
        self.Kd = self.kernel.evaluate(self.x, self.x)
        if self.noiseGP is None:
            yn = self.noise
        if isinstance(yn, float):
            yn = list(yn*np.ones_like(np.array(y)))
        yn = np.array(yn)
        if self.noiseGP is None:
            if len(self.x) != len(yn):
                yn = np.tile(yn[0], len(self.x))
        else: 
            self.noiseGP.train(x, np.log(yn/self.noise))
            indices = np.indices((len(self.x), len(self.x)))
            yn = self.noiseGP.exponential(self.x)[0]*self.noise
        self.Kd += np.diag(np.array(yn))
        # do noise analysis.

    def posterior_min(self):
        res = _optimize(lambda x: self.evaluate(x)[0][0], self.bounds, cons=self.cons)
        return res + (self.evaluate(res[0])[1][0,0],)

    def data_min(self):
        ys = np.array(self.y).flatten()
        i = np.argmin(ys)
        return self.x[i], self.y[i]

class AcquisitionFunction(object):
    def __init__(self, gp):
        self.gp = gp

class ExpectedImprovement(AcquisitionFunction):
    def evaluate(self, xs):
        fmin = self.fmin
        mu, cov = self.gp.evaluate(xs)
        std = np.diag(cov)**0.5
        delta = fmin-mu
        Z = delta/std
        return (delta*norm.cdf(Z) + std*norm.pdf(Z))

    def optimize(self):
        res = self.gp.posterior_min()
        self.fmin = res[1]# + 1.*self.gp.evaluate(res[0])[1][0][0]**0.5
        res = _optimize(lambda x: -self.evaluate(x)[0], self.gp.bounds, cons=self.gp.cons)
        return res[0]

sig = 0.4
def test_func(x):
    x = _sanitize(x)
    return np.sin(x).reshape((x.shape[0])) + sig*np.random.randn(),\
           np.cos(x).reshape((x.shape[0])) + sig*np.random.randn(),\
           sig**2, \
           sig**2

def _test_main():
    kernel = SquaredExponentialKernel([3.], 1.)
    bounds = [[0, 4*2*np.pi]]
    gp = GaussianProcess(kernel, bounds)
    gp.explore(3, test_func)
    xs = np.linspace(gp.bounds[0,0], gp.bounds[0,1], 500).reshape(-1,1)

    ei = ExpectedImprovement(gp)
    for i in range(0, 100):
        x = ei.optimize()
        y, _, yn, _ = test_func(x)
        gp.train(x, y, yn=yn)

        plt.ylim([-2,2])
        #plt.plot(xs, expected_improvement(xs))

        mu, cov = gp.evaluate(xs)
        std = np.diag(cov)**0.5
        plt.plot(xs.flatten(), mu)
        plt.fill_between(xs.flatten(), mu-std, mu + std, facecolor='gray')
        plt.scatter(gp.x, gp.y, c='k')

        plt.show()

if __name__ == "__main__":
    _test_main()
