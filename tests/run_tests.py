#!/usr/bin/python2

from test_adjoint import *
from test_parallel import *
from test_interp import *
from test_op import *
from test_field import *
from test_timestep import *
from test_CFD import *

unittest.main(verbosity=2, buffer=True)