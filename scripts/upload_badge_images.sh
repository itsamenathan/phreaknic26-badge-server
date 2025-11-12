#!/usr/bin/env bash

set -euo pipefail

usage() {
    cat <<'EOF'
Usage: upload_badge_images.sh [options]

Options:
  --api-url URL        Target upload endpoint (default: http://localhost:8000/admin/api/images)
  --image-dir PATH     Directory containing PNG artwork (default: /home/itsamenathan/dev/github/tylercrumpton/phreaknic26-esl-badge/images)
  --username VALUE     Basic auth username (default: $WORK_BASIC_AUTH_USERNAME)
  --password VALUE     Basic auth password (default: $WORK_BASIC_AUTH_PASSWORD)
  --dry-run            Print what would be uploaded without calling the API
  -h, --help           Show this message

Environment:
  WORK_BASIC_AUTH_USERNAME / WORK_BASIC_AUTH_PASSWORD supply defaults for --username/--password.
  API_URL, IMAGE_DIR, or CURL_TIMEOUT can also be exported instead of passing flags.
EOF
}

API_URL="${API_URL:-http://localhost:8000/admin/api/images}"
IMAGE_DIR=""
USERNAME="${WORK_BASIC_AUTH_USERNAME:-}"
PASSWORD="${WORK_BASIC_AUTH_PASSWORD:-}"
CURL_TIMEOUT="${CURL_TIMEOUT:-30}"
DRY_RUN=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --api-url)
            API_URL="$2"
            shift 2
            ;;
        --image-dir)
            IMAGE_DIR="$2"
            shift 2
            ;;
        --username)
            USERNAME="$2"
            shift 2
            ;;
        --password)
            PASSWORD="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown argument: $1" >&2
            usage >&2
            exit 1
            ;;
    esac
done

if ! command -v curl >/dev/null 2>&1; then
    echo "error: curl is required but not available in PATH." >&2
    exit 1
fi

if [[ -z "$USERNAME" || -z "$PASSWORD" ]]; then
    echo "error: provide --username/--password or set WORK_BASIC_AUTH_USERNAME/WORK_BASIC_AUTH_PASSWORD." >&2
    exit 1
fi

if [[ ! -d "$IMAGE_DIR" ]]; then
    echo "error: image directory '$IMAGE_DIR' does not exist." >&2
    exit 1
fi

declare -a IMAGE_SEQUENCE=(
    alert.png
    clearance.png
    default.png
    eatfruits.png
    hello.png
    license.png
    mountain.png
    papers.png
    pokemon.png
    sunset.png
    ticket.png
    zelda.png
)

declare -A IMAGE_LABELS=(
    [alert.png]="Alert"
    [clearance.png]="Clearance"
    [default.png]="PhreakNIC"
    [eatfruits.png]="Eat Fruits"
    [hello.png]="Hello"
    [license.png]="License"
    [mountain.png]="Mountain"
    [papers.png]="Papers"
    [pokemon.png]="Pokemon"
    [sunset.png]="Sunset"
    [ticket.png]="Ticket"
    [zelda.png]="Zelda"
)

declare -A IMAGE_COLORS=(
    [alert.png]="white"
    [clearance.png]="black"
    [default.png]="white"
    [eatfruits.png]="black"
    [hello.png]="black"
    [license.png]="black"
    [mountain.png]="white"
    [papers.png]="black"
    [pokemon.png]="black"
    [sunset.png]="white"
    [ticket.png]="black"
    [zelda.png]="black"
)

declare -A IMAGE_FONTS=(
    [alert.png]="ThaleahFat.ttf"
    [clearance.png]="ThaleahFat.ttf"
    [default.png]="ThaleahFat.ttf"
    [eatfruits.png]="ThaleahFat.ttf"
    [hello.png]="ThaleahFat.ttf"
    [license.png]="LicensePlate.ttf"
    [mountain.png]="ThaleahFat.ttf"
    [papers.png]="ThaleahFat.ttf"
    [pokemon.png]="Pokemon Classic.ttf"
    [sunset.png]="ThaleahFat.ttf"
    [ticket.png]="ThaleahFat.ttf"
    [zelda.png]="Triforce.ttf"
)

declare -A IMAGE_SECRETS=(
    [alert.png]=""
    [clearance.png]=""
    [default.png]=""
    [eatfruits.png]=""
    [hello.png]=""
    [license.png]=""
    [mountain.png]=""
    [papers.png]=""
    [pokemon.png]=""
    [sunset.png]=""
    [ticket.png]=""
    [zelda.png]=""
)

declare -A IMAGE_DISPLAY_ORDERS=(
    [alert.png]=30
    [clearance.png]=40
    [default.png]=10
    [eatfruits.png]=50
    [hello.png]=20
    [license.png]=60
    [mountain.png]=70
    [papers.png]=80
    [pokemon.png]=90
    [sunset.png]=100
    [ticket.png]=110
    [zelda.png]=120
)

validate_metadata() {
    local image="$1"
    local key
    for key in IMAGE_LABELS IMAGE_COLORS IMAGE_FONTS IMAGE_DISPLAY_ORDERS; do
        declare -n map_ref="$key"
        if [[ -z "${map_ref[$image]:-}" ]]; then
            echo "error: missing $key entry for $image" >&2
            return 1
        fi
    done
}

upload_image() {
    local image="$1"
    local path="$IMAGE_DIR/$image"
    if [[ ! -f "$path" ]]; then
        echo "warning: skipping $image (file not found at $path)" >&2
        return 0
    fi

    validate_metadata "$image"

    local label="${IMAGE_LABELS[$image]}"
    local color="${IMAGE_COLORS[$image]}"
    local font="${IMAGE_FONTS[$image]}"
    local secret="${IMAGE_SECRETS[$image]:-}"
    local order="${IMAGE_DISPLAY_ORDERS[$image]}"
    local requires_code="false"
    if [[ -n "$secret" ]]; then
        requires_code="true"
    fi

    if (( DRY_RUN == 1 )); then
        printf '* %s -> label="%s", color=%s, font=%s, secret=%s, requires_secret=%s, order=%s\n' \
            "$image" "$label" "$color" "$font" "${secret:-<none>}" "$requires_code" "$order"
        return 0
    fi

    local body_file
    body_file="$(mktemp)"
    local http_code
    http_code="$(
        curl \
            --silent \
            --show-error \
            --user "${USERNAME}:${PASSWORD}" \
            --request POST \
            --url "$API_URL" \
            --form "image_file=@${path};type=image/png" \
            --form-string "image_label=${label}" \
            --form-string "image_color=${color}" \
            --form-string "image_font=${font}" \
            ${secret:+--form-string "secret_code=${secret}"} \
            --form-string "requires_secret_code=${requires_code}" \
            --form-string "display_order=${order}" \
            --max-time "$CURL_TIMEOUT" \
            --output "$body_file" \
            --write-out "%{http_code}"
    )" || {
        local exit_code=$?
        rm -f "$body_file"
        echo "error: curl failed for ${image} (exit code $exit_code)" >&2
        return $exit_code
    }

    if [[ "$http_code" =~ ^2 ]]; then
        printf '✓ %s uploaded (HTTP %s)\n' "$label" "$http_code"
    else
        printf '✗ %s failed (HTTP %s)\n' "$label" "$http_code" >&2
        sed 's/^/    /' "$body_file" >&2
        rm -f "$body_file"
        return 1
    fi
    rm -f "$body_file"
}

main() {
    printf 'Uploading %d images from %s to %s\n' "${#IMAGE_SEQUENCE[@]}" "$IMAGE_DIR" "$API_URL"
    local image
    for image in "${IMAGE_SEQUENCE[@]}"; do
        upload_image "$image"
    done
}

main "$@"
