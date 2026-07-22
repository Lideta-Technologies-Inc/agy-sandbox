#!/bin/bash

# Get the directory where this script is located (works from any working directory)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --- INPUT VALIDATION ---
if [ -z "$1" ]; then
    echo "❌ Error: Please provide a project directory path."
    echo "Usage: $0 /path/to/your/project [studio|vertex]"
    exit 1
fi

# Resolve to an absolute path on the host computer
TARGET_DIR=$(realpath "$1")

if [ ! -d "$TARGET_DIR" ]; then
    echo "❌ Error: Directory '$TARGET_DIR' does not exist."
    exit 1
fi

# --- PROVIDER SELECTION ---
# Default to 'studio' (Google AI Studio) if no provider is specified
PROVIDER=$(echo "${2:-studio}" | tr '[:upper:]' '[:lower:]')

if [ "$PROVIDER" != "vertex" ] && [ "$PROVIDER" != "studio" ]; then
    echo "❌ Error: Invalid provider '$PROVIDER'. Supported options: 'studio' or 'vertex'."
    echo "Usage: $0 /path/to/your/project [studio|vertex]"
    exit 1
fi

# Get current host user details automatically
HOST_UID=$(id -u)
HOST_GID=$(id -g)

# Extract the directory name to safely prefix the container (e.g., "my-api")
DIR_NAME=$(basename "$TARGET_DIR")
CONTAINER_NAME="agy-${DIR_NAME}"
IMAGE_NAME="antigravity-sandbox-${HOST_UID}" # Appending UID prevents collisions on shared systems
HOST_USER=$(whoami)
CONFIG_DIR="/home/$HOST_USER/.config/antigravity"
GEMINI_CONFIG_DIR="/home/$HOST_USER/.gemini"

# Determine the home directory used inside the container
if [ "$HOST_UID" = "1000" ]; then
    CONTAINER_HOME="/home/ubuntu"
else
    CONTAINER_HOME="/home/developer"
fi

# Ensure host config folder exists for Gemini auth persistence
if [ ! -d "$CONFIG_DIR" ]; then
    echo "❌ Error: Directory '$CONFIG_DIR' does not exist. You might need a sudo password to create it"
    sudo mkdir -p "$CONFIG_DIR"
fi

if [ ! -d "$GEMINI_CONFIG_DIR" ]; then
    echo "❌ Error: Directory '$GEMINI_CONFIG_DIR' does not exist. You might need a sudo password to create it"
    sudo mkdir -p "$GEMINI_CONFIG_DIR"
fi

echo "========================================================"
echo "Target Project:   $TARGET_DIR"
echo "Container Name:   $CONTAINER_NAME"
echo "Mapping Host ID:  $HOST_UID:$HOST_GID"
echo "Selected Provider: $PROVIDER"
echo "========================================================"

# --- STEP 1: DYNAMIC STATE CHECKER ---
if [ "$(docker ps -q -f name=^${CONTAINER_NAME}$)" ]; then
    echo "✔ Container '$CONTAINER_NAME' is already running."
    echo "Connecting to your active remote agent workspace..."
    docker exec -it "$CONTAINER_NAME" agy init --remote
    exit 0

elif [ "$(docker ps -a -q -f name=^${CONTAINER_NAME}$)" ]; then
    echo "⚠ Container '$CONTAINER_NAME' exists but is stopped. Waking it up..."
    docker start "$CONTAINER_NAME"
    docker exec -it "$CONTAINER_NAME" agy init --remote
    exit 0

else
    echo "➜ Project sandbox not found. Provisioning clean infrastructure..."
fi

# --- STEP 2: BUILD SCRIPT IMAGE ---
if [[ "$(docker images -q $IMAGE_NAME 2> /dev/null)" == "" ]]; then
    echo "Building base Docker image '$IMAGE_NAME'..."
    docker build \
      --build-arg USER_UID="$HOST_UID" \
      --build-arg USER_GID="$HOST_GID" \
      -f "$SCRIPT_DIR/Dockerfile_permissive" \
      -t "$IMAGE_NAME" "$SCRIPT_DIR"
fi

# --- STEP 3: DYNAMIC PROVIDER CONFIGURATION ---
DOCKER_PROVIDER_ARGS=()

if [ "$PROVIDER" = "vertex" ]; then
    ADC_HOST_PATH="$HOME/.config/gcloud/application_default_credentials.json"
    
    # Quick sanity check on the host for the credential file
    if [ ! -f "$ADC_HOST_PATH" ]; then
        echo "❌ Error: ADC credentials file not found at '$ADC_HOST_PATH'."
        echo "Please run this command on your host first to log in:"
        echo "  gcloud auth application-default login"
        exit 1
    fi

    # Mount credentials into the container user's actual home directory to prevent permissions issues
    DOCKER_PROVIDER_ARGS+=(
        -v "$HOME/.config/gcloud:$CONTAINER_HOME/.config/gcloud:ro"
        -e GOOGLE_APPLICATION_CREDENTIALS="$CONTAINER_HOME/.config/gcloud/application_default_credentials.json"
        -e CLOUD_SDK_PROJECT="lideta-products"
        -e GOOGLE_CLOUD_PROJECT="lideta-products"
    )
    echo "✦ Configured container to use Vertex AI with host credentials."
else
    # Google AI Studio configuration
    # If you have a host-level GEMINI_API_KEY, we pass it down
    if [ -n "$GEMINI_API_KEY" ]; then
        DOCKER_PROVIDER_ARGS+=( -e GEMINI_API_KEY="$GEMINI_API_KEY" )
    fi
    echo "✦ Configured container to use Google AI Studio."
fi

# --- STEP 4: RUN ISOLATED CONTAINER ---
echo "Spawning background sandbox daemon..."
docker run -d \
  --name "$CONTAINER_NAME" \
  --restart unless-stopped \
  -v "$TARGET_DIR":/workspace \
  -v "$CONFIG_DIR":"$CONTAINER_HOME"/.config/antigravity \
  -v "$GEMINI_CONFIG_DIR":"$CONTAINER_HOME"/.gemini_host:ro \
  -v /home/"$HOST_USER"/.cache/uv:"$CONTAINER_HOME"/.cache/uv \
  -v /home/"$HOST_USER"/.local/share/uv:"$CONTAINER_HOME"/.local/share/uv \
  "${DOCKER_PROVIDER_ARGS[@]}" \
  "$IMAGE_NAME" \
  tail -f /dev/null

# Brief pause to ensure docker engine process allocation complete
sleep 1.5

echo "✔ Sandbox '$CONTAINER_NAME' successfully initialized!"
echo "--------------------------------------------------------"
docker exec -it "$CONTAINER_NAME" agy init --remote
echo "--------------------------------------------------------"
