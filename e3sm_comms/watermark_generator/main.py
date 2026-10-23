from e3sm_comms.stand_alone_scripts.watermarking.add_e3sm_watermark import add_watermark
from e3sm_comms.utils import IO_DIR

MEDIA_TYPE: str = "image"  # Choices: image, video
WATERMARK = f"{IO_DIR}/input/watermark_generator/E3SM_Logo.jpg"


def main():
    if MEDIA_TYPE == "image":
        CONFIG = f"{IO_DIR}/input/watermark_generator/config_image.toml"
        INPUT = f"{IO_DIR}/input/watermark_generator/test_image.jpg"
        OUTPUT = f"{IO_DIR}/output/watermark_generator/watermarked_image.jpg"
    elif MEDIA_TYPE == "video":
        CONFIG = f"{IO_DIR}/input/watermark_generator/config_video.toml"
        INPUT = f"{IO_DIR}/input/watermark_generator/test_video.mp4"
        OUTPUT = f"{IO_DIR}/output/watermark_generator/watermarked_video.mp4"
    else:
        raise ValueError(f"Invalid media type {MEDIA_TYPE}")
    add_watermark(INPUT, WATERMARK, OUTPUT, config=CONFIG)
