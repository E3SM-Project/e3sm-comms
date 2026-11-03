from e3sm_comms.stand_alone_scripts.watermarking.add_e3sm_watermark import add_watermark
from e3sm_comms.utils import IO_DIR

# The `watermark-generator` entry-point is primarily to test
# the stand-alone `add_e3sm_watermark.py` script's functionality.

MEDIA_TYPE: str = "image_png"  # Choices: image_jpg, image_png, video
WATERMARK = f"{IO_DIR}/input/watermark_generator/E3SM_Logo.jpg"


def main():
    if MEDIA_TYPE == "image_jpg":
        """
        Equivalent stand-alone commands:
        python e3sm_comms/stand_alone_scripts/watermarking/add_e3sm_watermark.py ${IO_DIR}/input/watermark_generator/test_image.jpg ${IO_DIR}/input/watermark_generator/E3SM_Logo.jpg ${IO_DIR}/output/watermark_generator/watermarked_image.jpg --config ${IO_DIR}/input/watermark_generator/config_image.toml
        """
        CONFIG = f"{IO_DIR}/input/watermark_generator/config_image.toml"
        INPUT = f"{IO_DIR}/input/watermark_generator/test_image.jpg"
        OUTPUT = f"{IO_DIR}/output/watermark_generator/watermarked_image.jpg"
    elif MEDIA_TYPE == "image_png":
        """
        Equivalent stand-alone commands:
        python e3sm_comms/stand_alone_scripts/watermarking/add_e3sm_watermark.py ${IO_DIR}/input/watermark_generator/test_image.png ${IO_DIR}/input/watermark_generator/E3SM_Logo.jpg ${IO_DIR}/output/watermark_generator/watermarked_image.png --config ${IO_DIR}/input/watermark_generator/config_image.toml
        """
        CONFIG = f"{IO_DIR}/input/watermark_generator/config_image.toml"
        INPUT = f"{IO_DIR}/input/watermark_generator/test_image.png"
        OUTPUT = f"{IO_DIR}/output/watermark_generator/watermarked_image.png"
    elif MEDIA_TYPE == "video":
        """
        Equivalent stand-alone commands:
        python e3sm_comms/stand_alone_scripts/watermarking/add_e3sm_watermark.py ${IO_DIR}/input/watermark_generator/test_video.mp4 ${IO_DIR}/input/watermark_generator/E3SM_Logo.jpg ${IO_DIR}/output/watermark_generator/watermarked_video.mp4 --config ${IO_DIR}/input/watermark_generator/config_video.toml
        """
        CONFIG = f"{IO_DIR}/input/watermark_generator/config_video.toml"
        INPUT = f"{IO_DIR}/input/watermark_generator/test_video.mp4"
        OUTPUT = f"{IO_DIR}/output/watermark_generator/watermarked_video.mp4"
    else:
        raise ValueError(f"Invalid media type {MEDIA_TYPE}")
    add_watermark(INPUT, WATERMARK, OUTPUT, config=CONFIG)
