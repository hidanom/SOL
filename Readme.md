This repository contains the original implementation of an optimal linear bounding approach presented in paper "SOL: Sampling-based Optimal Linear bounding".

See `requirements.txt` for required python packages. Note that Gurobi requires registering a license to run.

Run `make` to compile a c++ implementation of the Seidel's algorithm which solves a linear program with $n$ constraints in $O(n)$ expected time when the number of variables is constant.

See `Test_bounding.ipynb` notebook for SOL usage examples.