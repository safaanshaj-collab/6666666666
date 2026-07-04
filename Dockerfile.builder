# ============================================================
# Py2APK – Android build environment
# Based on Ubuntu 22.04 with Python, Android SDK, NDK, and Buildozer.
#
# Build this image once:
#   docker build -f docker/Dockerfile.builder -t py2apk-builder:latest .
# ============================================================

FROM ubuntu:22.04

# ── System packages ──────────────────────────────────────────────────────────
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip python3-venv python3-dev \
    openjdk-17-jdk-headless \
    git \
    zip unzip \
    wget curl \
    build-essential \
    autoconf automake libtool \
    pkg-config \
    libffi-dev libssl-dev \
    libltdl-dev \
    ccache \
    zlib1g-dev \
    # Kivy dependencies
    libsdl2-dev libsdl2-image-dev libsdl2-mixer-dev libsdl2-ttf-dev \
    libportmidi-dev \
    libswscale-dev libavformat-dev libavcodec-dev \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# ── Java / Android SDK env ────────────────────────────────────────────────────
ENV JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
ENV ANDROID_HOME=/opt/android-sdk
ENV ANDROID_SDK_ROOT=${ANDROID_HOME}
ENV PATH=${ANDROID_HOME}/cmdline-tools/latest/bin:${ANDROID_HOME}/platform-tools:${PATH}

# ── Android command-line tools ────────────────────────────────────────────────
ARG SDK_TOOLS_VERSION=11076708
RUN mkdir -p ${ANDROID_HOME}/cmdline-tools && \
    wget -q "https://dl.google.com/android/repository/commandlinetools-linux-${SDK_TOOLS_VERSION}_latest.zip" \
         -O /tmp/sdk-tools.zip && \
    unzip -q /tmp/sdk-tools.zip -d /tmp/sdk && \
    mv /tmp/sdk/cmdline-tools ${ANDROID_HOME}/cmdline-tools/latest && \
    rm -rf /tmp/sdk /tmp/sdk-tools.zip

# Accept licenses and install required SDK components
RUN yes | sdkmanager --licenses > /dev/null 2>&1 || true && \
    sdkmanager \
        "platforms;android-33" \
        "build-tools;33.0.2" \
        "platform-tools" \
        "ndk;25.2.9519653"

ENV ANDROID_NDK_HOME=${ANDROID_HOME}/ndk/25.2.9519653
ENV PATH=${ANDROID_NDK_HOME}:${PATH}

# ── Python build tools (Buildozer + python-for-android) ──────────────────────
RUN pip3 install --no-cache-dir --upgrade pip && \
    pip3 install --no-cache-dir \
        buildozer==1.5.0 \
        cython==0.29.36 \
        virtualenv

# ── Build workspace ───────────────────────────────────────────────────────────
# /workspace/src  – source mount (read-only)
# /workspace/output – APK output (writable)
# /workspace/.buildozer – buildozer cache (tmpfs provided by docker run)
WORKDIR /workspace

# Copy entrypoint
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
