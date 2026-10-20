#!/usr/bin/env python3
"""Add a logo watermark to raster images, image animations, and videos.

QUICK START
===========
Requires Python 3.9 or newer and Pillow 9.1 or newer:

    python -m pip install "Pillow>=9.1"

Video processing also requires FFmpeg and ffprobe installed as system programs
and available on PATH. Installing a Python package named ffmpeg is insufficient.
Check your installation with:

    ffmpeg -version
    ffprobe -version

The FFmpeg build needs libx264 for MP4/MOV/MKV output, or libvpx-vp9 and
libopus for WebM output. Image-only processing does not require FFmpeg.

Basic command (quote filenames that contain spaces):

    python add_e3sm_watermark.py INPUT LOGO OUTPUT [options]

For full usage and this manual:

    python add_e3sm_watermark.py --help

EXAMPLES
========
Full-color logo at the top right of a PNG:

    python add_e3sm_watermark.py figure.png logo.jpg marked.png --position top-right

White logo at 60% opacity, inset 20 pixels from the bottom right:

    python add_e3sm_watermark.py figure.png logo.jpg marked.png --position bottom-right --whiten 1 --opacity 0.6 --margin 20

Logo halfway between original colors and white, with an explicit pixel width:

    python add_e3sm_watermark.py figure.png logo.jpg marked.png --whiten 0.5 --width 280

Watermark the supplied SamudrACE animation inside its map border:

    python add_e3sm_watermark.py "SamudrACE_SST_animation (2).mp4" "E3SM_Logo(1).jpg" marked.mp4 --position bottom-left --frame 300 96 2286 1090 --width 280 --margin 20

These map bounds apply to the supplied 2640 x 1210 animation. They must be
adjusted if the graphic is resized, cropped, or has a different plot layout.
To reproduce the earlier bottom-left placement exactly, also use --x 320
--bottom 1070. The named-position default uses the full canvas.

Preview the first video frame without encoding the entire animation:

    python add_e3sm_watermark.py movie.mp4 logo.jpg marked.mp4 --position center-right --preview preview.png

OUTPUT remains a required positional argument in preview mode, but only the
PNG named by --preview is written. Preview mode also works for still images
and uses the first frame/page of animated or multipage images.

Watermark every frame of an animated GIF:

    python add_e3sm_watermark.py animation.gif logo.png marked.gif --position top-left

CONFIG FILES
============
Instead of repeating options on every run, put them in a TOML or JSON file
and pass it with --config:

    python add_e3sm_watermark.py movie.mp4 logo.jpg marked.mp4 --config watermark.toml

INPUT, LOGO, and OUTPUT stay on the command line. Precedence, highest first:
flags typed on the command line, then the config file, then built-in
defaults. For example, adding --opacity 0.5 to the command above overrides
the file's opacity for that run only.

A TOML config (watermark.toml; comments are allowed):

    # Settings for the SamudrACE animation
    position = "bottom-left"
    frame = [300, 96, 2286, 1090]
    width = 280
    margin = 20
    opacity = 0.85
    whiten = 0
    crf = 17

The same settings as JSON (watermark.json):

    {"position": "bottom-left", "frame": [300, 96, 2286, 1090],
     "width": 280, "margin": 20, "opacity": 0.85, "whiten": 0, "crf": 17}

The file extension (.toml or .json) selects the parser. TOML needs Python
3.11 or newer, or the tomli package on older versions; JSON works everywhere.

Keys are the long option names without the leading dashes: position, frame,
width, scale, margin, opacity, whiten, keep_white (keep-white also works), x,
bottom, crf, and preview. "frame" is a list of four integers, "keep_white" is
true or false, and "preview" is a path string interpreted relative to the
current directory, like the flag. JSON null is treated as "not set". Unknown
keys, wrong value types, and out-of-range values are reported as errors
rather than ignored. To override keep_white = true for one run, pass
--no-keep-white.

POSITION, SIZE, AND COORDINATES
==============================
--position NAME
    One of bottom-left (default), bottom-right, center-left, center-right,
    top-left, or top-right. "Center" means vertically centered, aligned to
    the left or right edge. There is no center-center anchor.

--frame LEFT TOP RIGHT BOTTOM
    Optional placement rectangle, measured in pixels from the canvas's
    upper-left corner. X increases rightward; Y increases downward. RIGHT
    and BOTTOM are exclusive boundaries. For example, --frame 100 50 900 650
    defines an 800 x 600 rectangle. Defaults to the full canvas. This option
    controls placement and scaling; it does not crop the graphic or detect
    plot borders automatically.

--width PIXELS
    Logo width, preserving aspect ratio. Overrides --scale. Must be positive.

--scale FRACTION
    Logo width relative to the placement rectangle's width. Default 0.14
    (14%). Must be greater than zero and at most one, even when --width is
    supplied. A tall logo can still exceed the available height.

--margin PIXELS
    Nonnegative inset from placement edges. Defaults to 1% of the placement
    rectangle's shorter dimension, rounded to the nearest pixel. The logo
    must fit with this margin on both sides of each dimension. Center-left
    and center-right use the margin horizontally and center vertically.

--x PIXELS / --bottom PIXELS
    Optional absolute-coordinate overrides retained from the earlier script.
    --x overrides the logo's left edge; --bottom overrides its bottom edge.
    They take precedence over the corresponding named-position coordinate
    and may move the logo outside --frame, but never outside the canvas.
    The initial frame/size/margin fit check still applies.

COLOR, BACKGROUND, AND TRANSPARENCY
===================================
--opacity VALUE
    Overall opacity from 0 (invisible) to 1 (opaque), default 0.85. Multiplies
    existing logo transparency, rather than replacing it.

--whiten VALUE
    Color blend toward white: 0 retains original colors (default), 0.5 is
    halfway to white, and 1 makes the visible logo white. This is independent
    of opacity. A fully opaque white logo uses --whiten 1 --opacity 1.

--keep-white / --no-keep-white
    Disable removal of near-white logo pixels. By default, near-white pixels
    are made transparent before whitening, which removes the supplied JPEG
    logo's white background. This is a color key applied throughout the logo,
    including any white lettering or internal details. It is not a connected
    background detector. Use --keep-white for a transparent PNG logo whose
    white details should remain, or to retain an opaque white backdrop.
    --no-keep-white restores the default, e.g. to override a config file.

    Keying uses the largest channel difference from white: differences <=12
    become transparent, >=36 retain original alpha, and intermediate values
    blend linearly. Existing alpha is preserved multiplicatively. Darker JPEG
    artifacts may remain; a clean transparent PNG logo gives better edges.
    Whitening happens after keying, followed by Lanczos resizing and opacity.

FORMATS AND OUTPUT BEHAVIOR
==========================
Images:
    Pillow's installed readers and writers determine available formats.
    Common examples are PNG, JPEG, TIFF, BMP, WebP, and GIF. The input is
    detected by content; the output format is chosen from its filename suffix.
    No universal support for every graphics format is implied. SVG/EPS and
    PDF need conversion to a supported raster image before using this script.
    The logo must also be a Pillow-readable raster image; its first frame is
    used if it is animated or multipage.

    Animated/multipage inputs are processed frame by frame. For multiple
    frames, choose GIF, WebP, PNG (APNG), or TIFF output. Durations and loop
    counts are passed to animation writers when available; missing durations
    default to 100 ms. TIFF output stores pages without animation timing.
    Codec quantization, duplicate-frame merging, disposal rules, and changing
    formats may alter playback details. All frames are held in memory, so
    large animations are better handled through a video workflow.

    PNG preserves alpha. JPEG/BMP output is flattened onto white. JPEG uses
    quality 95 with chroma subsampling disabled. Other encoders use Pillow's
    defaults and may be lossy (including WebP); GIF has palette/transparency
    limitations. Processing converts pixels to 8-bit RGBA and is not suitable
    for preserving scientific high-bit-depth or floating-point image data.
    EXIF orientation is applied before placement, potentially swapping the
    displayed width and height. ICC profiles are copied to supported outputs;
    most other metadata, DPI, and EXIF are not retained. No color-managed
    conversion of the logo into the source profile is performed.

Videos:
    Inputs depend on the installed FFmpeg decoders. Outputs are MP4/MOV/MKV
    with H.264, or WebM with VP9. The first video stream is watermarked; all
    audio streams are selected if present. Audio is copied for H.264 outputs
    and encoded to Opus for WebM. Subtitles/data streams are not copied.
    The output container must support copied audio codecs. General input
    metadata is requested, but exact preservation is not guaranteed.

    Video pixels are re-encoded; adding a watermark is not lossless stream
    copying. No frame-rate conversion, resize, or crop is requested. Ordinary
    constant-frame-rate input retains timing, while unusual variable-rate
    files should be checked after encoding. Rotation metadata in quarter-turn
    videos is considered when calculating displayed placement dimensions.
    Even-size output uses yuv420p; odd dimensions use yuv444p, which has more
    limited player compatibility. This is an SDR workflow, not an HDR or
    alpha-video preservation workflow.

--crf VALUE
    Video quality setting, default 17. This script accepts integers 0 through
    51. Lower usually means higher quality and larger files. H.264 and VP9
    have different quality scales; the same number is not equivalent quality.
    This option does not affect still images or previews.

FILES, ERRORS, AND TROUBLESHOOTING
=================================
The input and logo are never intentionally overwritten. Existing destination
paths are rejected; choose a new name or remove unwanted output yourself.
Parent output directories are created as needed. A failed encoding or save
can leave a partial output file; remove it or choose a new name before retrying.

"No module named PIL": install Pillow into the Python environment used to run
this script. "ffmpeg/ffprobe is required": install those programs on PATH.
"Logo and margins do not fit": reduce --width, --scale, or --margin, or enlarge
--frame. "--frame must be inside": check coordinates against displayed pixel
size. FFmpeg codec/container errors: check your FFmpeg build and try MKV when
copied audio is incompatible with MP4. FFmpeg diagnostic messages are printed
to the terminal. An unsupported raster input may fall through to FFmpeg and
produce a video-decoding error. Use a different supported format in that case.

Config file problems are reported as "--config FILE: ..." and name the
offending key. Check spelling, value types, and that the extension matches
the file's format.

The program exits with zero on success and a nonzero status on failure.

IMPLEMENTATION NOTES
====================
Pillow prepares a single RGBA watermark for video; FFmpeg repeats it throughout
encoding. The same logo preparation and placement functions are used for both
image and video paths. Functions below document their parameters and roles.
This script is intended for local command-line use, not as a concurrent output
writer or as a general-purpose image-format or metadata-preservation converter.
"""

import argparse
import importlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, BinaryIO, Optional, TextIO

from PIL import Image, ImageOps, UnidentifiedImageError

POSITIONS: tuple[str, ...] = (
    "bottom-left",
    "bottom-right",
    "center-left",
    "center-right",
    "top-left",
    "top-right",
)


CONFIG_OPTIONS: tuple[str, ...] = (
    "position",
    "frame",
    "width",
    "scale",
    "margin",
    "opacity",
    "whiten",
    "keep_white",
    "x",
    "bottom",
    "crf",
    "preview",
)


def find_toml_module() -> Optional[Any]:
    """Return a TOML reader module (tomllib or tomli), or None if neither exists.

    tomllib ships with Python 3.11+. Older Pythons can install tomli, which has
    the same load() interface.
    """
    name: str
    for name in ("tomllib", "tomli"):
        try:
            return importlib.import_module(name)
        except ModuleNotFoundError:
            continue
    return None


def is_int(value: Any) -> bool:
    """Return True for integers, excluding bools (a bool is an int in Python)."""
    return isinstance(value, int) and not isinstance(value, bool)


def parse_config(data: Any) -> dict[str, Any]:
    """Validate decoded config data and convert it to argparse defaults.

    Args:
        data: Result of decoding a JSON or TOML document; must be a table.

    Returns:
        A dict keyed by argparse destination names (for example keep_white),
        with values already converted to the types the script expects. Keys
        may use hyphens or underscores. None values are treated as unset.
        Numeric range checks (opacity, scale, and so on) happen later in
        main(), exactly as for command-line values.

    Raises:
        ValueError: Unknown keys, duplicate keys, or values of the wrong type.
    """
    if not isinstance(data, dict):
        raise ValueError("the top level must be a table of option names and values.")
    values: dict[str, Any] = {}
    key: Any
    value: Any
    for key, value in data.items():
        name: str = str(key).replace("-", "_")
        if name not in CONFIG_OPTIONS:
            raise ValueError(
                f"unknown option '{key}'. Valid options: "
                + ", ".join(CONFIG_OPTIONS)
                + "."
            )
        if name in values:
            raise ValueError(f"option '{name}' is given more than once.")
        if value is None:
            continue
        if name == "position":
            if value not in POSITIONS:
                raise ValueError(f"'position' must be one of: {', '.join(POSITIONS)}.")
            values[name] = value
        elif name == "frame":
            if (
                not isinstance(value, list)
                or len(value) != 4
                or not all(is_int(n) for n in value)
            ):
                raise ValueError(
                    "'frame' must be a list of four integers: "
                    "[left, top, right, bottom]."
                )
            values[name] = list(value)
        elif name in ("width", "margin", "x", "bottom", "crf"):
            if not is_int(value):
                raise ValueError(f"'{name}' must be an integer.")
            values[name] = value
        elif name in ("scale", "opacity", "whiten"):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"'{name}' must be a number.")
            values[name] = float(value)
        elif name == "keep_white":
            if not isinstance(value, bool):
                raise ValueError("'keep_white' must be true or false.")
            values[name] = value
        else:  # preview
            if not isinstance(value, str) or not value:
                raise ValueError("'preview' must be a non-empty path string.")
            values[name] = Path(value)
    return values


def load_config(path: Path) -> dict[str, Any]:
    """Read a .toml or .json config file and return validated option defaults.

    The suffix selects the parser. Raises OSError if the file cannot be read
    and ValueError for syntax errors, a missing TOML reader, an unsupported
    suffix, or invalid contents (see parse_config).
    """
    suffix: str = path.suffix.lower()
    data: Any
    if suffix == ".json":
        text_handle: TextIO
        with path.open(encoding="utf-8") as text_handle:
            data = json.load(text_handle)
    elif suffix == ".toml":
        toml: Optional[Any] = find_toml_module()
        if toml is None:
            raise ValueError(
                "TOML files need Python 3.11+ or the 'tomli' package; "
                "use a .json config on this Python."
            )
        binary_handle: BinaryIO
        with path.open("rb") as binary_handle:
            data = toml.load(binary_handle)
    else:
        raise ValueError("config files must end in .toml or .json.")
    return parse_config(data)


def prepare_logo(
    path: Path,
    width: int,
    opacity: float,
    keep_white: bool,
    whiten: float = 0.0,
) -> Image.Image:
    """Return a resized RGBA logo with background keying and color controls.

    Args:
        path: Path to a Pillow-readable logo (first frame only).
        width: Positive target width in pixels; height follows aspect ratio.
        opacity: Alpha multiplier in [0, 1].
        keep_white: If True, skip near-white color-key background removal.
        whiten: Blend RGB toward white by this fraction in [0, 1].

    Existing transparency survives keying and whitening. The caller validates
    numeric ranges. Opening or decoding an unsupported logo raises a Pillow
    or OS error. The returned image is independent of the source file handle.
    """
    source: Image.Image
    with Image.open(path) as source:
        logo: Image.Image = ImageOps.exif_transpose(source).convert("RGBA")
    if not keep_white:
        # Smoothly key near-white pixels, preserving existing transparency.
        pixels: list[tuple[int, int, int, int]] = []
        r: int
        g: int
        b: int
        a: int
        for r, g, b, a in (
            logo.get_flattened_data()
            if hasattr(logo, "get_flattened_data")
            else logo.getdata()
        ):
            distance: int = max(255 - r, 255 - g, 255 - b)
            factor: float = max(0.0, min(1.0, (distance - 12) / 24))
            pixels.append((r, g, b, round(a * factor)))
        logo.putdata(pixels)
    # Whiten only the logo colors, after removing the original white background.
    # Preserve alpha so whitening does not restore the background rectangle.
    if whiten:
        alpha: Image.Image = logo.getchannel("A")
        rgb: Image.Image = Image.blend(
            logo.convert("RGB"), Image.new("RGB", logo.size, "white"), whiten
        )
        logo = rgb.convert("RGBA")
        logo.putalpha(alpha)
    height: int = max(1, round(width * logo.height / logo.width))
    logo = logo.resize((width, height), Image.Resampling.LANCZOS)
    logo.putalpha(logo.getchannel("A").point(lambda a: round(a * opacity)))
    return logo


def placement(
    size: tuple[int, int],
    logo_size: tuple[int, int],
    args: argparse.Namespace,
) -> tuple[int, int]:
    """Compute and validate the watermark's upper-left pixel coordinates.

    Args:
        size: Displayed canvas (width, height) in pixels.
        logo_size: Prepared logo (width, height) in pixels.
        args: Namespace containing frame, margin, position, x, and bottom.

    Returns:
        Integer (x, y) coordinates for alpha compositing or FFmpeg overlay.

    Raises:
        ValueError: Invalid bounds, insufficient room, or out-of-canvas result.

    Absolute x/bottom overrides apply after the named anchor and can leave
    the placement frame while remaining inside the overall canvas.
    """
    w: int
    h: int
    w, h = size
    left: int
    top: int
    right: int
    bottom: int
    left, top, right, bottom = args.frame or (0, 0, w, h)
    if not (0 <= left < right <= w and 0 <= top < bottom <= h):
        raise ValueError("--frame must be inside the image/video.")
    margin: int = (
        args.margin
        if args.margin is not None
        else round(min(right - left, bottom - top) * 0.01)
    )
    lw: int
    lh: int
    lw, lh = logo_size
    if margin < 0 or lw + 2 * margin > right - left or lh + 2 * margin > bottom - top:
        raise ValueError("Logo and margins do not fit inside the placement frame.")
    vertical: str
    horizontal: str
    vertical, horizontal = args.position.split("-")
    x: int = left + margin if horizontal == "left" else right - margin - lw
    y: int = {
        "top": top + margin,
        "center": top + (bottom - top - lh) // 2,
        "bottom": bottom - margin - lh,
    }[vertical]
    # Compatibility with the previous script: optional pixel overrides.
    x = args.x if args.x is not None else x
    y = args.bottom - lh if args.bottom is not None else y
    if not (0 <= x <= w - lw and 0 <= y <= h - lh):
        raise ValueError("Logo placement lies outside the canvas.")
    return x, y


def get_logo(
    size: tuple[int, int], args: argparse.Namespace
) -> tuple[Image.Image, tuple[int, int]]:
    """Prepare a logo and placement for one displayed canvas size.

    Explicit args.width takes priority over args.scale. Returns a pair:
    (RGBA Pillow image, (left_x, top_y)). Bounds validation is delegated to
    placement(); failures propagate to the command-line error handler.
    """
    frame_width: int = args.frame[2] - args.frame[0] if args.frame else size[0]
    width: int = (
        args.width
        if args.width is not None
        else max(1, round(frame_width * args.scale))
    )
    if width <= 0:
        raise ValueError("--width must be positive.")
    logo: Image.Image = prepare_logo(
        args.logo, width, args.opacity, args.keep_white, args.whiten
    )
    return logo, placement(size, logo.size, args)


def images(args: argparse.Namespace, destination: Path) -> None:
    """Composite the logo onto an image, animation, or multipage raster.

    Args:
        args: Parsed options; input and logo identify source files.
        destination: Output Path; suffix determines Pillow's writer.

    Preview mode selects one frame. Otherwise all decoded frames/pages are
    composited, collected in memory, and saved together. Animation duration,
    loop information, and selected ICC metadata are passed when applicable.
    Conversion and metadata limits are described in the module manual.
    """
    source: Image.Image
    with Image.open(args.input) as source:
        count: int = getattr(source, "n_frames", 1)
        if (
            count > 1
            and not args.preview
            and destination.suffix.lower()
            not in (".gif", ".webp", ".png", ".tif", ".tiff")
        ):
            raise ValueError(
                "Multiple frames require GIF, WebP, PNG (APNG), or TIFF output."
            )
        frames: list[Image.Image] = []
        durations: list[int] = []
        loop: Optional[int] = source.info.get("loop")
        icc: Optional[bytes] = source.info.get("icc_profile")
        i: int
        for i in range(1 if args.preview else count):
            source.seek(i)
            frame: Image.Image = ImageOps.exif_transpose(source).convert("RGBA")
            logo: Image.Image
            xy: tuple[int, int]
            logo, xy = get_logo(frame.size, args)
            frame.alpha_composite(logo, xy)
            frames.append(frame)
            durations.append(source.info.get("duration", 100))
        options: dict[str, Any] = {}
        suffix: str = destination.suffix.lower()
        if suffix in (".jpg", ".jpeg", ".bmp"):
            # Flatten transparency onto white for formats without alpha.
            base: Image.Image = Image.new("RGB", frames[0].size, "white")
            base.paste(frames[0], mask=frames[0].getchannel("A"))
            frames[0] = base
            if suffix in (".jpg", ".jpeg"):
                options.update(quality=95, subsampling=0)
        if icc and suffix in (".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"):
            options["icc_profile"] = icc
        if len(frames) > 1:
            options.update(save_all=True, append_images=frames[1:])
            if suffix not in (".tif", ".tiff"):
                options["duration"] = durations
                if loop is not None:
                    options["loop"] = loop
            if suffix == ".gif":
                options["disposal"] = 2
        frames[0].save(destination, **options)


def video(args: argparse.Namespace, destination: Path) -> None:
    """Overlay a prepared PNG logo using FFmpeg, or extract a PNG preview.

    Probes displayed dimensions, including common quarter-turn rotation,
    prepares the watermark once in a temporary directory, and runs FFmpeg
    without a shell. The temporary PNG is removed when this function exits.
    The static logo's last frame repeats for the main video's duration.

    Raises ValueError for missing programs, no video stream, or unsupported
    output suffix. Subprocess errors propagate with FFmpeg diagnostics.
    A failed encode may leave a partial destination file.
    """
    executable: str
    for executable in ("ffmpeg", "ffprobe"):
        if not shutil.which(executable):
            raise ValueError(f"{executable} is required for video processing.")
    info: dict[str, Any] = json.loads(
        subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height:stream_tags=rotate:stream_side_data=rotation",
                "-of",
                "json",
                str(args.input),
            ]
        )
    )
    if not info.get("streams"):
        raise ValueError("Input contains no video stream.")
    stream: dict[str, Any] = info["streams"][0]
    size: tuple[int, int] = (stream["width"], stream["height"])
    rotation: float = float(stream.get("tags", {}).get("rotate", 0))
    side: dict[str, Any]
    for side in stream.get("side_data_list", []):
        rotation = float(side.get("rotation", rotation))
    if round(rotation) % 180 == 90:
        # Explicit swap (equivalent to size[::-1]) keeps the fixed-length
        # tuple[int, int] type that type checkers can verify.
        size = (size[1], size[0])
    logo: Image.Image
    x: int
    y: int
    logo, (x, y) = get_logo(size, args)
    suffix: str = destination.suffix.lower()
    if not args.preview and suffix not in (".mp4", ".mov", ".mkv", ".webm"):
        raise ValueError("Choose MP4, MOV, MKV, or WebM for video output.")
    folder: str
    with tempfile.TemporaryDirectory(prefix="watermark_") as folder:
        logo_path: Path = Path(folder) / "logo.png"
        logo.save(logo_path)
        # yuv444p handles odd frame sizes without resizing or cropping.
        pixel_format: str = "yuv420p" if all(n % 2 == 0 for n in size) else "yuv444p"
        graph: str = (
            f"[0:v:0][1:v:0]overlay={x}:{y}:eof_action=repeat:"
            "repeatlast=1:format=auto[out]"
        )
        command: list[str] = [
            "ffmpeg",
            "-hide_banner",
            "-n",
            "-filter_complex_threads",
            "1",
            "-i",
            str(args.input),
            "-i",
            str(logo_path),
            "-filter_complex",
            graph,
            "-map",
            "[out]",
        ]
        if args.preview:
            command += ["-frames:v", "1", "-update", "1"]
        else:
            command += ["-map", "0:a?", "-map_metadata", "0", "-pix_fmt", pixel_format]
            if suffix == ".webm":
                command += [
                    "-c:v",
                    "libvpx-vp9",
                    "-crf",
                    str(args.crf),
                    "-b:v",
                    "0",
                    "-c:a",
                    "libopus",
                ]
            else:
                command += [
                    "-c:v",
                    "libx264",
                    "-preset",
                    "medium",
                    "-crf",
                    str(args.crf),
                    "-c:a",
                    "copy",
                ]
                if suffix in (".mp4", ".mov"):
                    command += ["-movflags", "+faststart"]
        subprocess.run(command + [str(destination)], check=True)


def main() -> None:
    """Parse CLI options and any --config file, then validate and dispatch.

    Pillow recognition determines the image route; unrecognized input is
    offered to FFmpeg. Expected processing failures become a readable error
    and nonzero exit. Existing destination paths are rejected before writing.
    """
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "input", type=Path, help="Source raster image, animation, or video"
    )
    parser.add_argument(
        "logo", type=Path, help="Raster logo; first frame used if animated"
    )
    parser.add_argument(
        "output",
        type=Path,
        help="New output filename; required but unused with --preview",
    )
    parser.add_argument(
        "--config",
        type=Path,
        metavar="FILE",
        help="Read options from a .toml or .json file; flags on the command "
        "line override it",
    )
    parser.add_argument(
        "--position",
        choices=POSITIONS,
        default="bottom-left",
        help="Anchor inside the placement frame (default bottom-left)",
    )
    parser.add_argument(
        "--frame",
        type=int,
        nargs=4,
        metavar=("LEFT", "TOP", "RIGHT", "BOTTOM"),
        help="Placement bounds in pixels; defaults to the full canvas",
    )
    parser.add_argument(
        "--width", type=int, help="Positive logo width in pixels; overrides --scale"
    )
    parser.add_argument(
        "--scale",
        type=float,
        default=0.14,
        help="Fraction of placement-frame width (default .14)",
    )
    parser.add_argument(
        "--margin",
        type=int,
        help="Nonnegative inset in pixels; default 1%% of shorter frame dimension",
    )
    parser.add_argument(
        "--opacity",
        type=float,
        default=0.85,
        help="Transparency: 0 invisible, 1 fully opaque (default .85)",
    )
    parser.add_argument(
        "--whiten",
        type=float,
        default=0.0,
        help="Color fade: 0 original colors, 1 white logo (default 0)",
    )
    parser.add_argument(
        "--keep-white",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Preserve near-white logo pixels instead of making them transparent",
    )
    parser.add_argument("--x", type=int, help="Override logo left edge in pixels")
    parser.add_argument(
        "--bottom", type=int, help="Override logo bottom edge in pixels"
    )
    parser.add_argument(
        "--crf",
        type=int,
        default=17,
        help="Video quality, 0–51; lower means higher quality (default 17)",
    )
    parser.add_argument(
        "--preview", type=Path, help="Write a PNG of the first frame instead"
    )
    args: argparse.Namespace = parser.parse_args()
    if args.config is not None:
        # Config values become the parser's defaults, so explicit flags still win.
        config_values: dict[str, Any]
        try:
            config_values = load_config(args.config)
        except (ValueError, OSError) as exc:
            parser.error(f"--config {args.config}: {exc}")
        parser.set_defaults(**config_values)
        args = parser.parse_args()
    destination: Path = args.preview or args.output
    if not args.input.is_file() or not args.logo.is_file():
        parser.error("Input and logo must exist.")
    if (
        destination.resolve() in (args.input.resolve(), args.logo.resolve())
        or destination.exists()
    ):
        parser.error(
            "Choose a new output path; inputs and existing files cannot be overwritten."
        )
    if (
        not 0 <= args.opacity <= 1
        or not 0 <= args.whiten <= 1
        or not 0 < args.scale <= 1
        or not 0 <= args.crf <= 51
    ):
        parser.error(
            "Opacity and whiten: 0–1; scale: greater than 0 and at most 1; CRF: 0–51."
        )
    if args.preview and destination.suffix.lower() != ".png":
        parser.error("--preview must name a PNG file.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        try:
            with Image.open(args.input):
                pass
            is_image: bool = True
        except UnidentifiedImageError:
            is_image = False
        if is_image:
            images(args, destination)
        else:
            video(args, destination)
    except (ValueError, OSError, KeyError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"Error: {exc}\n")
    print(f"Created: {destination}")


if __name__ == "__main__":
    main()
