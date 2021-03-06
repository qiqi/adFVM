## Introduction

adFVM is an explicit unsteady compressible fluid dynamics package with adjoint capability
using automatic differentiation provided by the library adpy.

## Installation
adFVM requires the adpy library. To install it,
after cloning, execute the following
```
git submodule update --init --recursive
```
Next build and install it using the following (using python2)
```
cd adpy
python setup.py build
python setup.py install --prefix=/path/you/want
cd ..
```

adFVM requires the following python packages, they
will be automatically installed when you execute the python install script or
you can install them separately if you want.
```
numpy
scipy
mpi4py
cython
matplotlib
```
Build and install adFVM
```
python setup.py build
python setup.py install --prefix=/path/you/want
```

Additionally for HDF5 capability parallel h5py needs to be
installed. For running the adjoint solver using artificial
viscosity PETSc and lapack need to be installed. For computing
statistics of long-time averaged quantities in the primal
and adjoint solvers the library [ar](https://github.com/RhysU/ar) needs to be installed.
For handling meshes OpenFOAM and Metis need to be installed.
For Ubuntu, the following script can be used to install
all these packages. 
```
./install_deps.sh
```
Edit the variable PYTHONPREFIX to change the python libraries installation location.

## Testing
To run unit tests for adpy
```
cd adpy/tests
./run_tests.sh
cd ../..
```
To run unit tests for adFVM
```
cd tests
./setup_tests.sh
./run_tests.sh
cd ..
```

## Usage
To use adFVM on a flow problem, a python case
file needs to be defined that contains information about
the details of the problem, like case folder, thermodynamic constants,
design objective, simulation length, etc. Many example case files
can be found in the templates folder. For a short explanation
of the various options read the templates/vane.py file.
To run the primal flow solver, use the following
```
./apps/problem.py templates/vane.py -c
```
To run the adjoint flow solver,
```
./apps/adjoint.py templates/vane.py -c
```
The sensitivities obtained using the adjoint solver can be found
in the "objective.txt" file in the case folder. The "-c" option
is not needed if running a flow solver multiple times.

In order to run the flow solver on multiple cores, first
the mesh needs to be decomposed. Edit the "system/decomposeParDict"
file in the case folder to set the number of processors, for example 4. Then,
execute
```
decomposePar
```
To run the flow solver on 4 cores,
```
mpirun -np 4 ./apps/problem.py templates/vane.py 
```
The "objective.txt" for parallel runs is in the "processor0"
directory in the case folder.

## Contributors

Chaitanya Talnikar and Professor Qiqi Wang
