#include "parallel.hpp"
#include "mesh.hpp"

struct memory mem = {0, 0};

long long mil = 0;
long long current_timestamp() {
    struct timeval te; 
    gettimeofday(&te, NULL); // get current time
    long long milliseconds = te.tv_sec*1000LL + te.tv_usec/1000; // caculate milliseconds
    //printf("milliseconds: %lld\n", milliseconds);
    return milliseconds;
}

void Mesh::build() {}
void Mesh::buildBeforeWrite() {}

Mesh *meshp = NULL;
#ifdef MATOP
    #include "matop.hpp"
    Matop *matop;
#endif

#define MODULE graph
#ifdef PY3
    #define initFunc GET_MODULE(PyInit_,MODULE)
#else
    #define initFunc GET_MODULE(init,MODULE)
#endif
#define modName VALUE(MODULE)

PyObject* initialize(PyObject *self, PyObject *args) {

    PyObject *meshObject = PyTuple_GetItem(args, 0);
    Py_INCREF(meshObject);

    meshp = new Mesh(meshObject);
    meshp->init();
    meshp->localRank = PyInt_AsLong(PyTuple_GetItem(args, 1));
    parallel_init();

    #ifdef GPU
        int count;
        gpuErrorCheck(cudaGetDeviceCount(&count));
        printf("GPU devices: %d, rank: %d\n", count, meshp->rank);
        cudaSetDevice(0);
        //gpuErrorCheck(cudaSetDevice(meshp->localRank));
    #endif

    #ifdef MATOP
        integer argc = 0;
        PetscInitialize(&argc, NULL, NULL, NULL);
        matop = new Matop();
    #endif

    return Py_None;
}

PyObject* viscositySolver(PyObject *self, PyObject *args) {

    //cout << "forward 1" << endl;
    PyObject *uObject, *DTObject;
    scalar dt;
    PyArg_ParseTuple(args, "OOd", &uObject, &DTObject, &dt);

    arrType<scalar, 5> u;
    vec DT;
    getArray((PyArrayObject *)uObject, u);
    getArray((PyArrayObject *)DTObject, DT);

    const Mesh& mesh = *meshp;
    arrType<scalar, 5> un(mesh.nInternalCells, true);
    #ifdef MATOP
        matop->heat_equation(u, DT, dt, un);
    #endif
    
    return putArray(un);
}



PyMethodDef StaticMethods[] = {
    {"initialize",  initialize, METH_VARARGS, "Execute a shell command."},
    {"viscositySolver",  viscositySolver, METH_VARARGS, "Execute a shell command."},
};
extern PyMethodDef ExtraMethods[];
static PyMethodDef* Methods;

void interface_exit() {
    parallel_exit();
    delete meshp;
    #ifdef MATOP
        PetscFinalize();
        delete matop;
    #endif
    free(Methods);
}

PyMODINIT_FUNC
initFunc(void)
{
    PyObject *m;
    int n = 0;
    while(1) {
        if (ExtraMethods[n].ml_name == NULL) 
            break;
        n++;
    }
    n++;
    Methods = (PyMethodDef*) malloc(sizeof(PyMethodDef)*(2+n));
    memcpy(Methods, StaticMethods, sizeof(PyMethodDef)*2);
    memcpy(Methods + 2, ExtraMethods, sizeof(PyMethodDef)*n);

    #ifdef PY3
        static struct PyModuleDef moduledef = {
            PyModuleDef_HEAD_INIT,  /* m_base */
            modName,                 /* m_name */
            NULL,                   /* m_doc */
            -1,                     /* m_size */
            Methods            /* m_methods */
        };
        m = PyModule_Create(&moduledef);
    #else
        m = Py_InitModule(modName, Methods);
        if (m == NULL)
            return;
    #endif
    import_array();
    Py_AtExit(interface_exit);

    //SpamError = PyErr_NewException("spam.error", NULL, NULL);
    //Py_INCREF(SpamError);
    //PyModule_AddObject(m, "error", SpamError);
    #ifdef PY3
        return m;
    #endif
}

