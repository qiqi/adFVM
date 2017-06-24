#define timeIntegrator euler

class RCF {
    public:

    void* req;
    integer reqIndex;
    integer reqField;
    Boundary boundaries[3];
    scalar* reqBuf[3];
    integer stage;

    void equation(const vec& rho, const mat& rhoU, const vec& rhoE, vec& drho, mat& drhoU, vec& drhoE, scalar& objective, scalar& minDtc);
    void boundaryInit(integer startField);
    void boundaryEnd();

    template <typename dtype, integer shape1, integer shape2>
    void boundary(const Boundary& boundary, arrType<dtype, shape1, shape2>& phi);
};

RCF *rcf;

void RCF::equation(const vec& rho, const mat& rhoU, const vec& rhoE, vec& drho, mat& drhoU, vec& drhoE, scalar& objective, scalar& minDtc) {
    // make decision between 1 and 3 a template
    // optimal memory layout? combine everything?
    //cout << "c++: equation 1" << endl;
    const Mesh& mesh = *meshp;

    mat U(mesh.nCells);
    vec T(mesh.nCells);
    vec p(mesh.nCells);

    Function_primitive(mesh.nInternalCells, &rho(0), &rhoU(0), &rhoE(0), &U(0), &T(0), &p(0));

    for (auto& patch: this->boundaries[2]) {
        string patchType = patch.second.at("type");
        string patchID = patch.first;
        integer startFace, nFaces;
        tie(startFace, nFaces) = mesh.boundaryFaces.at(patchID);
        integer cellStartFace = mesh.nInternalCells + startFace - mesh.nInternalFaces;

        if (patchType == "CBC_UPT") {
            mat Uval(nFaces, patch.second.at("_U0"));
            vec Tval(nFaces, patch.second.at("_T0"));
            vec pval(nFaces, patch.second.at("_p0"));
            for (integer i = 0; i < nFaces; i++) {
                integer c = cellStartFace + i;
                for (integer j = 0; j < 3; j++) {
                    U(c, j) = Uval(i, j);
                }
                T(c) = Tval(i);
                p(c) = pval(i);
            }
        } else if (patchType == "CBC_TOTAL_PT") {
            cout << "implement this" << endl;
        }
    }
    this->boundaryInit(0);    
    boundary(this->boundaries[0], U);
    boundary(this->boundaries[1], T);
    boundary(this->boundaries[2], p);
    this->boundaryEnd();    
    U.info();
    T.info();
    p.info();

    arrType<scalar, 3, 3> gradU(mesh.nCells);
    arrType<scalar, 1, 3> gradT(mesh.nCells);
    arrType<scalar, 1, 3> gradp(mesh.nCells);
    gradU.zero();
    gradT.zero();
    gradp.zero();
    //
    #define gradUpdate(i, n, func) \
        func(n, \
                &U(0), &T(0), &p(0), \
                &mesh.areas(i), &mesh.volumesL(i), &mesh.volumesR(i), \
                &mesh.weights(i), &mesh.deltas(i), &mesh.normals(i), \
                &mesh.linearWeights(i), &mesh.quadraticWeights(i), \
                &mesh.owner(i), &mesh.neighbour(i), \
                &gradU(0), &gradT(0), &gradp(0));

    gradUpdate(0, mesh.nInternalFaces, Function_grad);
    //this->boundaryEnd();    
    for (auto& patch: mesh.boundary) {
        auto& patchInfo = patch.second;
        integer startFace, nFaces;
        tie(startFace, nFaces) = mesh.boundaryFaces.at(patch.first);
        //if (patchInfo.at("type") == "cyclic") {
        if ((patchInfo.at("type") == "cyclic") ||
            (patchInfo.at("type") == "processor") ||
            (patchInfo.at("type") == "processorCyclic")) {
            gradUpdate(startFace, nFaces, Function_coupledGrad);
        } else {
            gradUpdate(startFace, nFaces, Function_boundaryGrad);
        }
    }
    ////cout << "gradU " << gradU.checkNAN() << endl;
    //
    ////cout << "c++: equation 3" << endl;
    this->boundaryInit(this->reqField);    
    this->boundary(mesh.defaultBoundary, gradU);
    this->boundary(mesh.defaultBoundary, gradT);
    this->boundary(mesh.defaultBoundary, gradp);
    this->boundaryEnd();

    gradU.info();
    gradT.info();
    gradp.info();
    //
    vec dtc(mesh.nCells);
    drho.zero();
    drhoU.zero();
    drhoE.zero();
    dtc.zero();
    //objective = this->objective(this, U, T, p);

    #define fluxUpdate(i, n, func) \
        func(n, \
                &U(0), &T(0), &p(0), \
                &gradU(0), &gradT(0), &gradp(0), \
                &mesh.areas(i), &mesh.volumesL(i), &mesh.volumesR(i), \
                &mesh.weights(i), &mesh.deltas(i), &mesh.normals(i), \
                &mesh.linearWeights(i), &mesh.quadraticWeights(i), \
                &mesh.owner(i), &mesh.neighbour(i), \
                &drho(0), &drhoU(0), &drhoE(0));

    fluxUpdate(0, mesh.nInternalFaces, Function_flux);
    //this->boundaryEnd();    
    for (auto& patch: mesh.boundary) {
        auto& patchInfo = patch.second;
        integer startFace, nFaces;
        tie(startFace, nFaces) = mesh.boundaryFaces.at(patch.first);
        //if (patchInfo.at("type") == "cyclic") {
        if ((patchInfo.at("type") == "cyclic") ||
            (patchInfo.at("type") == "processor") ||
            (patchInfo.at("type") == "processorCyclic")) {
            fluxUpdate(startFace, nFaces, Function_coupledFlux);
        } else if (patchInfo.at("type") == "characteristic") {
            fluxUpdate(startFace, nFaces, Function_characteristicFlux);
        } else {
            fluxUpdate(startFace, nFaces, Function_boundaryFlux);
        }
    }
    drho.info();
    drhoU.info();
    drhoE.info();
}

tuple<scalar, scalar> euler(const vec& rho, const mat& rhoU, const vec& rhoE, vec& rhoN, mat& rhoUN, vec& rhoEN, scalar t, scalar dt) {
    const Mesh& mesh = *meshp;
    
    vec drho(rho.shape);
    mat drhoU(rhoU.shape);
    vec drhoE(rhoE.shape);
    scalar objective, dtc;
    rcf->stage = 0;
    rcf->equation(rho, rhoU, rhoE, drho, drhoU, drhoE, objective, dtc);

    for (integer i = 0; i < mesh.nInternalCells; i++) {
        rhoN(i) = rho(i) - dt*drho(i);
        for (integer j = 0; j < 3; j++) {
            rhoUN(i, j) = rhoU(i, j) - dt*drhoU(i, j);
        }
        rhoEN(i) = rhoE(i) - dt*drhoE(i);
    }
    return make_tuple(objective, dtc);
}

tuple<scalar, scalar> SSPRK(const vec& rho, const mat& rhoU, const vec& rhoE, vec& rhoN, mat& rhoUN, vec& rhoEN, scalar t, scalar dt) {
    const Mesh& mesh = *meshp;

    const integer n = 3;
    scalar alpha[n][n] = {{1,0,0},{3./4, 1./4, 0}, {1./3, 0, 2./3}};
    scalar beta[n][n] = {{1,0,0}, {0,1./4,0},{0,0,2./3}};
    scalar gamma[n] = {0, 1, 0.5};
    scalar objective[n], dtc[n];

    vec rhos[n+1] = {{rho.shape, rho.data}, {rho.shape}, {rho.shape}, {rho.shape, rhoN.data}};
    mat rhoUs[n+1] = {{rhoU.shape, rhoU.data}, {rhoU.shape}, {rhoU.shape}, {rhoU.shape, rhoUN.data}};
    vec rhoEs[n+1] = {{rhoE.shape, rhoE.data}, {rhoE.shape}, {rhoE.shape}, {rhoE.shape, rhoEN.data}};
    vec drho(rho.shape);
    mat drhoU(rhoU.shape);
    vec drhoE(rhoE.shape);

    for (integer stage = 0; stage < n; stage++) {
        //solver.t = solver.t0 + gamma[i]*solver.dt
        rcf->stage = stage;
        rcf->equation(rhos[stage], rhoUs[stage], rhoEs[stage], drho, drhoU, drhoE, objective[stage], dtc[stage]);
        integer curr = stage + 1;
        scalar b = beta[stage][stage];
        for (integer i = 0; i < mesh.nInternalCells; i++) {
            rhos[curr](i) = -b*drho(i)*dt;
            for (integer j = 0; j < 3; j++) {
                rhoUs[curr](i, j) = -b*drhoU(i, j)*dt;
            }
            rhoEs[curr](i) = -b*drhoE(i)*dt;
        }
        for (integer prev = 0; prev < curr; prev++) {
            scalar a = alpha[stage][prev];
            for (integer i = 0; i < mesh.nInternalCells; i++) {
                rhos[curr](i) += a*rhos[prev](i);
                for (integer j = 0; j < 3; j++) {
                    rhoUs[curr](i, j) += a*rhoUs[prev](i, j);
                }
                rhoEs[curr](i) += a*rhoEs[prev](i);
            }
        }
    }
    return make_tuple(objective[0], dtc[0]);
}

template <typename dtype, integer shape1, integer shape2>
void RCF::boundary(const Boundary& boundary, arrType<dtype, shape1, shape2>& phi) {
    const Mesh& mesh = *meshp;
    //MPI_Barrier(MPI_COMM_WORLD);

    dtype* phiBuf = NULL;
    integer reqPos = 0;
    if (mesh.nRemotePatches > 0) {
        reqPos = this->reqIndex/(2*mesh.nRemotePatches);
        phiBuf = new dtype[(mesh.nCells-mesh.nLocalCells)*shape1*shape2];
        this->reqBuf[reqPos] = phiBuf;
    }

    for (auto& patch: boundary) {
        string patchType = patch.second.at("type");
        string patchID = patch.first;
        const map<string, string>& patchInfo = mesh.boundary.at(patchID);

        integer startFace, nFaces;
        tie(startFace, nFaces) = mesh.boundaryFaces.at(patch.first);
        integer cellStartFace = mesh.nInternalCells + startFace - mesh.nInternalFaces;

        if (patchType == "cyclic") {
            string neighbourPatchID = patchInfo.at("neighbourPatch");
            integer neighbourStartFace = std::get<0>(mesh.boundaryFaces.at(neighbourPatchID));
            for (integer i = 0; i < nFaces; i++) {
                integer p = mesh.owner(neighbourStartFace + i);
                integer c = cellStartFace + i;
                for (integer j = 0; j < shape1; j++) {
                    for (integer k = 0; k < shape2; k++) {
                        phi(c, j, k) = phi(p, j, k);
                    }
                }
            }
        } else if (patchType == "zeroGradient" || patchType == "empty" || patchType == "inletOutlet") {
            for (integer i = 0; i < nFaces; i++) {
                integer p = mesh.owner(startFace + i);
                integer c = cellStartFace + i;
                for (integer j = 0; j < shape1; j++) {
                    for (integer k = 0; k < shape2; k++) {
                        phi(c, j, k) = phi(p, j, k);
                    }
                }
            }
        } else if (patchType == "symmetryPlane" || patchType == "slip") {
            cout << "implemented this elsewhere" << endl;
            if ((shape1 == 3) && (shape2 == 1)) {
                for (integer i = 0; i < nFaces; i++) {
                    integer f = startFace + i;
                    integer c = cellStartFace + i;
                    integer p = mesh.owner(f);
                    dtype phin = 0.;
                    for (integer j = 0; j < 3; j++) {
                        phin += mesh.normals(f, j)*phi(p, j);
                    }
                    for (integer j = 0; j < 3; j++) {
                        phi(c, j) = phi(p, j) - mesh.normals(f, j)*phin;
                    }
                }
            } else {
                for (integer i = 0; i < nFaces; i++) {
                    integer p = mesh.owner(startFace + i);
                    integer c = cellStartFace + i;
                    for (integer j = 0; j < shape1; j++) {
                        for (integer k = 0; k < shape2; k++) {
                            phi(c, j, k) = phi(p, j, k);
                        }
                    }
                }
            }
        } else if (patchType == "fixedValue") {
            arrType<scalar, shape1, shape2> phiVal(nFaces, patch.second.at("_value"));

            for (integer i = 0; i < nFaces; i++) {
                integer c = cellStartFace + i;
                for (integer j = 0; j < shape1; j++) {
                    for (integer k = 0; k < shape2; k++) {
                        phi(c, j, k) = phiVal(i, j, k);
                    }
                }
            }
        } else if (patchType == "processor" || patchType == "processorCyclic") {
            //cout << "hello " << patchID << endl;
            integer bufStartFace = cellStartFace - mesh.nLocalCells;
            integer size = nFaces*shape1*shape2;
            integer dest = stoi(patchInfo.at("neighbProcNo"));
            for (integer i = 0; i < nFaces; i++) {
                integer p = mesh.owner(startFace + i);
                integer b = bufStartFace + i;
                for (integer j = 0; j < shape1; j++) {
                    for (integer k = 0; k < shape2; k++) {
                        phiBuf[b*shape1*shape2 + j*shape2 + k] = phi(p, j, k);
                    }
                }
            }
            MPI_Request *req = (MPI_Request*) this->req;
            integer tag = (this->stage*1000+1) + this->reqField*100 + mesh.tags.at(patchID);
            //cout << patchID << " " << tag << endl;
            MPI_Isend(&phiBuf[bufStartFace*shape1*shape2], size, MPI_DOUBLE, dest, tag, MPI_COMM_WORLD, &req[this->reqIndex]);
            MPI_Irecv(&phi(cellStartFace), size, MPI_DOUBLE, dest, tag, MPI_COMM_WORLD, &req[this->reqIndex+1]);
            this->reqIndex += 2;
        }
        else if (patchType == "calculated") {
        } 
        //else {
        //    cout << "patch not found " << patchType << " for " << patchID << endl;
        //}
    }
    this->reqField++;
}

void RCF::boundaryInit(integer startField) {
    const Mesh& mesh = *meshp;
    this->reqIndex = 0;
    this->reqField = startField;
    if (mesh.nRemotePatches > 0) {
        //MPI_Barrier(MPI_COMM_WORLD);
        this->req = (void *)new MPI_Request[2*3*mesh.nRemotePatches];
    }
}

void RCF::boundaryEnd() {
    const Mesh& mesh = *meshp;
    if (mesh.nRemotePatches > 0) {
        MPI_Waitall(2*3*mesh.nRemotePatches, ((MPI_Request*)this->req), MPI_STATUSES_IGNORE);
        delete[] ((MPI_Request*)this->req);
        //MPI_Barrier(MPI_COMM_WORLD);
        for (integer i = 0; i < 3; i++) {
            delete[] this->reqBuf[i];
        }
    }
}
