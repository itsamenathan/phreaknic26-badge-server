#!/usr/bin/env python3
"""
Patch a compiled firmware binary to replace the hardcoded image with a new one.

This script:
1. Converts a PNG image to the same 1-bit format used by the firmware
2. Locates the image data in the compiled firmware using magic bytes
3. Replaces the image data in-place, creating a patched firmware binary
"""

from __future__ import annotations

import hashlib
import os
import sys
from io import BytesIO
from pathlib import Path
from typing import Optional, Tuple

from PIL import Image

MAGIC_START = bytes([0x45, 0x41, 0x54, 0x46, 0x52, 0x55, 0x49, 0x54, 0x53])
MAGIC_END = bytes([0x43, 0x52, 0x55, 0x4D, 0x50, 0x53, 0x50, 0x41, 0x43, 0x45])
HASH_MAGIC_START = bytes([0x48, 0x41, 0x53, 0x48, 0x44, 0x41, 0x54, 0x41])
HASH_MAGIC_END = bytes([0x48, 0x41, 0x53, 0x48, 0x45, 0x4E, 0x44])


def _image_to_pixel_data(img: Image.Image, target_width: int, target_height: int) -> Tuple[bytes, int, int]:
    if img.size != (target_width, target_height):
        img = img.resize((target_width, target_height), Image.Resampling.NEAREST)

    img = img.convert("L")
    threshold = 128
    img = img.point(lambda x: 255 if x > threshold else 0, mode="1")

    width, height = img.size
    bytes_per_row = (width + 7) // 8
    pixel_data = bytearray()

    for y in range(height):
        for byte_x in range(bytes_per_row):
            byte_val = 0
            for bit in range(8):
                x = byte_x * 8 + bit
                if x < width:
                    pixel = img.getpixel((x, y))
                    if pixel > 0:
                        byte_val |= 1 << (7 - bit)
            pixel_data.append(byte_val)

    return bytes(pixel_data), width, height


def convert_png_bytes_to_pixel_data(
    png_bytes: bytes,
    target_width: int = 240,
    target_height: int = 96,
) -> Tuple[bytes, int, int]:
    """Convert PNG bytes to the firmware's 1-bit packed format."""
    with Image.open(BytesIO(png_bytes)) as img:
        return _image_to_pixel_data(img, target_width, target_height)


def convert_png_to_pixel_data(
    png_path: Path | str,
    target_width: int = 240,
    target_height: int = 96,
) -> Tuple[bytes, int, int]:
    """Convert PNG file to 1-bit packed byte array matching firmware format."""
    png_path = Path(png_path)
    with png_path.open("rb") as f:
        png_bytes = f.read()
    with Image.open(BytesIO(png_bytes)) as img:
        orig_width, orig_height = img.size
    print(f"Input image size: {orig_width}x{orig_height}")
    if orig_width != target_width or orig_height != target_height:
        print(f"Resizing to {target_width}x{target_height}")
    return convert_png_bytes_to_pixel_data(png_bytes, target_width, target_height)

def find_image_data_location(firmware_data):
    """Find the image data location in firmware using magic bytes"""

    start_offset = firmware_data.find(MAGIC_START)
    if start_offset == -1:
        return None, None, None

    image_start = start_offset + len(MAGIC_START)

    end_offset = firmware_data.find(MAGIC_END, image_start)
    if end_offset == -1:
        return None, None, None

    image_size = end_offset - image_start

    return image_start, image_size, end_offset

def find_hash_location(firmware_data):
    """Find the hash placeholder location in firmware using magic bytes"""

    start_offset = firmware_data.find(HASH_MAGIC_START)
    if start_offset == -1:
        return None, None

    hash_start = start_offset + len(HASH_MAGIC_START)

    end_offset = firmware_data.find(HASH_MAGIC_END, hash_start)
    if end_offset == -1:
        return None, None

    hash_size = end_offset - hash_start

    return hash_start, hash_size


def patch_firmware_bytes(
    firmware_bytes: bytes,
    new_image_data: bytes,
) -> Tuple[bytes, int, int, bytes, Optional[int], Optional[int]]:
    """Patch firmware bytes with new image data and return patched bytes plus metadata."""
    firmware_data = bytearray(firmware_bytes)

    image_start, image_size, _ = find_image_data_location(firmware_data)
    if image_start is None or image_size is None:
        raise RuntimeError(
            "Could not find image data in firmware. Ensure the binary includes the expected magic bytes."
        )

    if len(new_image_data) != image_size:
        raise RuntimeError(
            f"Image size mismatch. Firmware expects {image_size} bytes but received {len(new_image_data)} bytes."
        )

    firmware_data[image_start : image_start + image_size] = new_image_data

    hash_digest = hashlib.sha256(new_image_data).digest()
    hash_bytes = hash_digest[:8]
    hash_start, hash_size = find_hash_location(firmware_data)
    if hash_start is not None and hash_size is not None:
        expected_size = 8
        if hash_size != expected_size:
            raise RuntimeError(
                f"Hash size mismatch. Expected {expected_size} bytes but firmware reserves {hash_size} bytes."
            )
        firmware_data[hash_start : hash_start + expected_size] = hash_bytes

    return bytes(firmware_data), image_start, image_size, hash_bytes, hash_start, hash_size


def patch_firmware(firmware_path, new_image_data, output_path=None):
    """Patch the firmware binary with new image data and hash"""

    with open(firmware_path, 'rb') as f:
        firmware_data = f.read()

    print(f"Firmware size: {len(firmware_data)} bytes")

    try:
        (
            patched_bytes,
            image_start,
            image_size,
            hash_bytes,
            hash_start,
            hash_size,
        ) = patch_firmware_bytes(firmware_data, new_image_data)
    except RuntimeError as exc:
        print("ERROR:", exc)
        print("Make sure the firmware was compiled with the updated image_data.h")
        print("that includes the magic bytes.")
        return False

    print(f"Found image data at offset: 0x{image_start:04X}")
    print(f"Image size in firmware: {image_size} bytes")
    print(f"New image size: {len(new_image_data)} bytes")
    print("Patching image data...")

    hash_hex = hash_bytes.hex().upper()
    print(f"Image hash (SHA256, first 8 bytes): {hash_hex}")

    if hash_start is None or hash_size is None:
        print("WARNING: Could not find hash section in firmware!")
        print("Hash will not be embedded. Firmware may be using older image_data.h")
    else:
        print(f"Found hash section at offset: 0x{hash_start:04X}")
        
        if hash_size != 8:
            print(f"WARNING: Hash size mismatch! Expected 8 bytes, found {hash_size}")
        else:
            print("Patching hash...")

    # Generate output filename if not specified
    if output_path is None:
        output_path = f"patched-{hash_hex}.bin"
        print(f"Auto-generated output filename: {output_path}")

    with open(output_path, 'wb') as f:
        f.write(patched_bytes)

    print(f"Patched firmware written to: {output_path}")

    # Verify image data
    verify_data = patched_bytes[image_start:image_start + image_size]
    if verify_data == new_image_data:
        print("Verification: SUCCESS - Image data correctly written")
    else:
        print("Verification: FAILED - Image data mismatch!")
        return False

    # Verify hash if section was found
    if hash_start is not None and hash_size == 8:
        verify_hash = patched_bytes[hash_start:hash_start + 8]
        if verify_hash == hash_bytes:
            print("Verification: SUCCESS - Hash correctly written")
        else:
            print("Verification: FAILED - Hash mismatch!")
            return False

    return True

def main():
    # Get the repository root (parent of scripts/)
    repo_root = Path(__file__).parent.parent.resolve()

    # Default paths
    default_firmware = repo_root / "firmware" / "main.bin"
    default_image = repo_root / "images" / "default.png"

    if len(sys.argv) == 1:
        # No arguments - use defaults
        firmware_path = default_firmware
        image_path = default_image
        output_path = None
        print(f"Using default firmware: {firmware_path}")
        print(f"Using default image: {image_path}")
    elif len(sys.argv) == 2:
        # One argument - custom firmware, default image
        firmware_path = Path(sys.argv[1])
        image_path = default_image
        output_path = None
        print(f"Using default image: {image_path}")
    elif len(sys.argv) == 3:
        # Two arguments - custom firmware and image
        firmware_path = Path(sys.argv[1])
        image_path = Path(sys.argv[2])
        output_path = None
    elif len(sys.argv) == 4:
        # Three arguments - custom firmware, image, and output
        firmware_path = Path(sys.argv[1])
        image_path = Path(sys.argv[2])
        output_path = Path(sys.argv[3])
    else:
        print("Usage: python3 patch_firmware_image.py [firmware.bin] [new_image.png] [output.bin]")
        print()
        print("Arguments:")
        print("  firmware.bin   - Input compiled firmware binary (default: firmware/main.bin)")
        print("  new_image.png  - New image to insert (default: images/default.png, will be resized to 240x96)")
        print("  output.bin     - Optional output path (default: auto-generated)")
        print()
        print("Examples:")
        print("  python3 patch_firmware_image.py                        # Use all defaults")
        print("  python3 patch_firmware_image.py main.bin               # Custom firmware, default image")
        print("  python3 patch_firmware_image.py main.bin myimage.png   # Custom firmware and image")
        print("  python3 patch_firmware_image.py main.bin img.png out.bin  # All custom")
        sys.exit(1)

    if not os.path.exists(firmware_path):
        print(f"ERROR: Firmware file not found: {firmware_path}")
        sys.exit(1)

    if not os.path.exists(image_path):
        print(f"ERROR: Image file not found: {image_path}")
        sys.exit(1)

    print("=" * 60)
    print("Firmware Image Patcher")
    print("=" * 60)

    print("\nStep 1: Converting image...")
    new_image_data, width, height = convert_png_to_pixel_data(str(image_path))
    print(f"Converted to {width}x{height}, {len(new_image_data)} bytes")

    print("\nStep 2: Patching firmware...")
    success = patch_firmware(str(firmware_path), new_image_data, str(output_path) if output_path else None)

    if success:
        print("\n" + "=" * 60)
        print("SUCCESS! Firmware patched successfully.")
        print("=" * 60)
        sys.exit(0)
    else:
        print("\n" + "=" * 60)
        print("FAILED! Could not patch firmware.")
        print("=" * 60)
        sys.exit(1)

if __name__ == "__main__":
    main()
