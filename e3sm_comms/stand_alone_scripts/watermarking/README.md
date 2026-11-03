# About

The `add_e3sm_watermark.py` script adds the E3SM watermark to images and videos of various formats. While it can be run as part of the Comms team's conda dev environment, most users will want to run it stand-alone.

# How to run as a stand-alone script

The script has an in-depth "QUICK START" guide at the top of the file. A very brief overview is provided below.

## Step 1. Get the files

Visit https://github.com/E3SM-Project/e3sm-comms/tree/main/e3sm_comms/stand_alone_scripts/:
- Copy the text of `add_e3sm_watermark.py` to a file in your workspace
- Download `E3SM_Logo.jpg` and copy it to your workspace.

## Step 2. Get the runtime dependencies

The script has a few dependencies. If you are using a `conda` environment, you'll need these lines in your `conda/dev.yml`:
```bash
  - ffmpeg # For ffmpeg and ffprobe
  - pillow # For PIL
```
If you are not using `conda`, just make sure you have those dependencies otherwise installed.

# Step 3. Set up parameters

Set up a config file like:
```
position = "bottom-left"
scale = 0.14
margin = 20
opacity = 0.85
whiten = 1
```

You can also pass in parameters directly on the command line. See script's "QUICK START" guide for details.

# Step 4. Run

Example:
```bash
python add_e3sm_watermark.py input_path/image_to_watermark.png E3SM_logo.jpg output_path/watermarked_image.png --config config.toml
```

In the example above, the script adds the watermark, `E3SM_logo.jpg` to the input image, `input_path/image_to_watermark.png`, using the parameters as defined in `config.toml`. It places the watermarked image at `output_path/watermarked_image.png`.
