import numpy as np

import tensor
from func import Function
#from . import tensor as ad

#import function
#a = np.ones(4)
#print function.test_interface(a)

a = tensor.matrix()
b = tensor.col()
c = a+b
d = tensor.matrix()

#f = Function([a, b, d], [d*c])
f = Function([a, b], [2.*c], mode='c')

a = np.ones((3,4))
b = 2*np.ones((3,1))
d = 40*np.ones((3,4))
#print f(np.random.rand(2), np.random.rand(2), np.random.rand(2))
print f(a, b)