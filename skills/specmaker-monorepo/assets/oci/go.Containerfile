# Stage 1: Builder
FROM ghcr.io/ayunaoss/ayuna-oci-builder:trixie-slim AS builder

ARG AYUNA_UID
ARG AYUNA_GID
ARG AYUNA_HOME
ARG AYUNA_PROJECT=my-service

COPY --chown=${AYUNA_UID}:${AYUNA_GID} . ${AYUNA_HOME}/${AYUNA_PROJECT}
WORKDIR ${AYUNA_HOME}/${AYUNA_PROJECT}
USER ayuna

# Build from the committed go.mod/go.sum; never modify them inside the image.
RUN go mod download && \
    go build -mod=readonly -trimpath -o ${AYUNA_HOME}/${AYUNA_PROJECT}/bin/app . && \
    chmod +x ${AYUNA_HOME}/${AYUNA_PROJECT}/bin/app

# Stage 2: Runner
FROM ghcr.io/ayunaoss/ayuna-oci-base:trixie-slim AS runner

ARG AYUNA_UID
ARG AYUNA_GID
ARG AYUNA_HOME
ARG AYUNA_PROJECT=my-service

# Optional: the OpenDAL Go binding (github.com/apache/opendal/bindings/go) loads
# libffi at run time through purego, so it needs libffi8. Remove if unused.
USER root
RUN apt-get update && \
    apt-get install -y --no-install-recommends libffi8 && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR ${AYUNA_HOME}/${AYUNA_PROJECT}
USER ayuna

COPY --from=builder --chown=${AYUNA_UID}:${AYUNA_GID} ${AYUNA_HOME}/${AYUNA_PROJECT}/bin/app ./bin/app

# Exec form does not expand ${...}, so the binary has a fixed name.
ENTRYPOINT ["./bin/app"]
