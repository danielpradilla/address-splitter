# Lambda container image for address-splitter API (Python 3.12)
FROM public.ecr.aws/lambda/python:3.12

# System deps for building libpostal + python bindings
RUN dnf -y update && \
    # Base image often includes curl-minimal; avoid conflicts by installing curl-minimal explicitly.
    dnf -y install git gcc gcc-c++ make automake autoconf libtool pkgconfig \
      curl-minimal tar gzip unzip which file && \
    dnf clean all

# Build + install libpostal
# Pin to a stable commit/tag if desired; using main for now.
RUN git clone https://github.com/openvenues/libpostal.git /tmp/libpostal && \
    cd /tmp/libpostal && \
    ./bootstrap.sh && \
    # Keep a single canonical data directory for all model files.
    ./configure --datadir=/opt/libpostal_data/libpostal && \
    make -j2 && \
    make install && \
    rm -rf /tmp/libpostal && \
    # Ensure dynamic loader can find libpostal at runtime (Lambda base image lacks ldconfig)
    (ln -sf /usr/local/lib/libpostal.so.1 /usr/lib64/libpostal.so.1 || true) && \
    (ln -sf /usr/local/lib/libpostal.so.1 /usr/lib/libpostal.so.1 || true)

# Use the default libpostal model installed during `make install`.
# (Senzing overlay disabled while investigating Lambda init/import latency.)

ENV LIBPOSTAL_DATA_DIR=/opt/libpostal_data/libpostal
# Ensure shared libs (libpostal.so.1) are discoverable
ENV LD_LIBRARY_PATH=/usr/local/lib:/usr/local/lib64:/usr/lib64:/usr/lib

# Python deps
COPY backend/requirements.txt ${LAMBDA_TASK_ROOT}/requirements.txt
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt

# App code
COPY backend/src/ ${LAMBDA_TASK_ROOT}/

# Lambda entry
CMD ["index.handler"]
