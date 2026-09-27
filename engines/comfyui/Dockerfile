# ComfyUI for Raytone Models, on NVIDIA's PyTorch container (CUDA 13.2, sm_110 for the Jetson AGX
# Thor). Built locally with scripts/build-engine comfyui; the engine runs it by image ID.
FROM nvcr.io/nvidia/pytorch@sha256:222d8b18e671be5c3ef91cb41727a2572a0b23f59ded6c39f373a96946f6f2ba

# v0.37.0: native MiniMax H3 nodes
ARG COMFYUI_COMMIT=73c9bad4d21e7addbe1d13bc92eee0f1431b017d

RUN git clone https://github.com/Comfy-Org/ComfyUI.git /opt/ComfyUI \
 && git -C /opt/ComfyUI checkout --detach "$COMFYUI_COMMIT"

# NVIDIA's torch and torchvision stay (the image's pip constraints pin them). torchaudio is not in
# the image, and PyPI's aarch64 wheel is built for CUDA 13.0, which torchaudio refuses next to
# CUDA 13.2: the CPU build is used, since ComfyUI calls only its tensor functions (resample, mel).
RUN grep -vE '^(torch|torchvision|torchaudio)([^a-z_-]|$)' /opt/ComfyUI/requirements.txt > /tmp/requirements.txt \
 && pip install --no-cache-dir -r /tmp/requirements.txt \
 && PIP_CONSTRAINT= pip install --no-cache-dir --no-deps --index-url https://download.pytorch.org/whl/cpu torchaudio==2.11.0 \
 && python3 -c "import torch, torchaudio, torchvision; print(torch.__version__, torchaudio.__version__, torchvision.__version__)"

COPY raytone-comfyui /usr/local/bin/raytone-comfyui
RUN chmod 0755 /usr/local/bin/raytone-comfyui
LABEL org.raytone.models.engine=comfyui org.raytone.models.comfyui-commit=$COMFYUI_COMMIT
