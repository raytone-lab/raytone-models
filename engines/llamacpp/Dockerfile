# llama.cpp's server for Raytone Models, built for the Jetson AGX Thor (sm_110) with CUDA 13.0:
# CUDA 13.2 builds give garbage on sm_110 (ggml-org/llama.cpp#27763). Built locally with
# scripts/build-engine llamacpp; the engine runs it by image ID.
FROM nvidia/cuda@sha256:5dc1bca23d05bd37b011be68ec470c03b403a5da07ec3a86e41af9470e9d0cc6 AS build
# 13.0.2-devel-ubuntu24.04

# b11221
ARG LLAMA_CPP_COMMIT=136887b665180c13c6209a4ce0673637b6cd3afd
ARG CUDA_ARCHITECTURES=110

RUN apt-get update && apt-get install -y --no-install-recommends git cmake build-essential ca-certificates \
 && rm -rf /var/lib/apt/lists/*
RUN git clone https://github.com/ggml-org/llama.cpp.git /src \
 && git -C /src checkout --detach "$LLAMA_CPP_COMMIT"
RUN cmake -S /src -B /src/build -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES="$CUDA_ARCHITECTURES" \
      -DGGML_NATIVE=OFF -DLLAMA_CURL=OFF -DBUILD_SHARED_LIBS=OFF -DLLAMA_BUILD_TESTS=OFF -DCMAKE_BUILD_TYPE=Release \
 && cmake --build /src/build --target llama-server -j "$(nproc)"

FROM nvidia/cuda@sha256:6a0e31b59e70890446f2c17356d6efc0d54260090a8c63d6ca7c2ad049db95d2
# 13.0.2-runtime-ubuntu24.04
ARG LLAMA_CPP_COMMIT
COPY --from=build /src/build/bin/llama-server /usr/local/bin/llama-server
LABEL org.raytone.models.engine=llamacpp org.raytone.models.llama-cpp-commit=$LLAMA_CPP_COMMIT
ENTRYPOINT []
