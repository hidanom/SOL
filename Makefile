all:
	g++ -Wall -Wextra -Wno-unused-parameter -fPIC -shared \
		-I/usr/include/python3.10 -I/usr/include/Eigen -I./SOL/libcpp \
		SOL/libcpp/py_sdlp.cpp -o ./SOL/py_sdlp.so \
		-Wl,--disable-new-dtags,-rpath, \
		-lboost_python310 \
		-lboost_numpy310 