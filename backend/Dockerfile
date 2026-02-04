# Lambda container image for address-splitter API (Python 3.12)
FROM public.ecr.aws/lambda/python:3.12

# System deps for building libpostal + python bindings
RUN dnf -y update && \
    dnf -y install git gcc gcc-c++ make automake autoconf libtool pkgconfig \
      curl tar gzip unzip which file && \
    dnf clean all

# Build + install libpostal
# Pin to a stable commit/tag if desired; using main for now.
RUN git clone https://github.com/openvenues/libpostal.git /tmp/libpostal && \
    cd /tmp/libpostal && \
    ./bootstrap.sh && \
    ./configure --datadir=/opt/libpostal_data && \
    make -j2 && \
    make install && \
    ldconfig && \
    rm -rf /tmp/libpostal

# Install Senzing-trained libpostal data model (overlays default model)
# Docs: https://github.com/Senzing/libpostal-data
RUN mkdir -p /opt/libpostal_data && \
    cd /opt/libpostal_data && \
    curl -L https://public-read-libpostal-data.s3.amazonaws.com/v1.1.0/language_classifier.tar.gz -o language_classifier.tar.gz && \
    curl -L https://public-read-libpostal-data.s3.amazonaws.com/v1.1.0/libpostal_data.tar.gz -o libpostal_data.tar.gz && \
    curl -L https://public-read-libpostal-data.s3.amazonaws.com/v1.2.0/parser.tar.gz -o parser.tar.gz && \
    tar -zxvf language_classifier.tar.gz && \
    tar -zxvf libpostal_data.tar.gz && \
    tar -zxvf parser.tar.gz && \
    rm -f language_classifier.tar.gz libpostal_data.tar.gz parser.tar.gz

ENV LIBPOSTAL_DATA_DIR=/opt/libpostal_data

# Python deps
COPY backend/requirements.txt ${LAMBDA_TASK_ROOT}/requirements.txt
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt

# App code
COPY backend/src/ ${LAMBDA_TASK_ROOT}/

# Lambda entry
CMD ["index.handler"]
