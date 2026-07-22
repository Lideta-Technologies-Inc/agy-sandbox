FROM ubuntu:24.04

ARG USER_UID=1001
ARG USER_GID=1001

RUN apt-get update && apt-get install -y curl git gh sudo nodejs npm && rm -rf /var/lib/apt/lists/*

# Dynamically handle user creation without touching or breaking UID 1000
RUN if [ "$USER_UID" = "1000" ]; then \
        echo "ubuntu ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers; \
    else \
        groupadd --gid $USER_GID developer && \
        useradd --uid $USER_UID --gid $USER_GID -m -s /bin/bash developer && \
        echo "developer ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers; \
    fi

USER ${USER_UID:-1001}
WORKDIR /workspace

RUN curl -fsSL https://antigravity.google/cli/install.sh | bash
RUN curl -LsSf https://astral.sh/install.sh | sh

ENV PATH="/home/developer/.local/bin:/home/ubuntu/.local/bin:${PATH}"
CMD ["bash"]
