
FROM nvidia/cuda:12.4.1-devel-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       ca-certificates \
       git \
       cmake \
       ninja-build \
       build-essential \
       libcurl4-openssl-dev \
    && rm -rf /var/lib/apt/lists/*

ARG LLAMA_COMMIT=5c8854fd88319125125dc4b836c98b1b215b0f23

WORKDIR /opt

RUN git clone https://github.com/ggml-org/llama.cpp.git \
    && cd llama.cpp \
    && git checkout --detach "${LLAMA_COMMIT}" \
    && test "$(git rev-parse HEAD)" = "${LLAMA_COMMIT}"


WORKDIR /opt/llama.cpp

# CUDA driver stub is required at link time.
# Never add the stubs directory to runtime LD_LIBRARY_PATH.
RUN test -f /usr/local/cuda/lib64/stubs/libcuda.so \
    && ln -sf libcuda.so \
       /usr/local/cuda/lib64/stubs/libcuda.so.1

RUN cmake -S . -B build \
      -G Ninja \
      -DGGML_CUDA=ON \
      -DCMAKE_CUDA_ARCHITECTURES=89 \
      -DCMAKE_BUILD_TYPE=Release \
      -DLLAMA_BUILD_TESTS=OFF \
      -DCMAKE_EXE_LINKER_FLAGS="-Wl,-rpath-link,/usr/local/cuda/lib64/stubs" \
    && cmake --build build \
      --target llama-server \
      --parallel 4

EXPOSE 8080

ENTRYPOINT ["/opt/llama.cpp/build/bin/llama-server"]
