FROM ubuntu:24.04
RUN apt-get update && apt-get install -y --no-install-recommends \
      git ca-certificates build-essential libsqlite3-dev zlib1g-dev && \
    rm -rf /var/lib/apt/lists/*
RUN git clone --depth 1 https://github.com/felt/tippecanoe.git /tmp/tc && \
    cd /tmp/tc && make -j"$(nproc)" && make install && rm -rf /tmp/tc
WORKDIR /work
ENTRYPOINT ["tippecanoe"]
