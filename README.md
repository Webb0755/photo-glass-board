# Photo Glass Board

Photo Glass Board is a small Python command-line tool for turning a photo into a
presentation-style image board. It uses the photo itself as a blurred and
darkened background, places the sharp photo above it, and renders camera
metadata underneath in a Times New Roman italic style.

## Features

- Blurred photo background board inspired by mobile photo-sharing layouts.
- Floating sharp photo with subtle shadow and border.
- Default margins:
  - left and right: 5% of the photo width
  - top: 10% of the photo height
  - bottom: 20% of the photo height
- Automatic EXIF extraction for focal length, aperture, shutter speed, ISO,
  shooting date, camera brand, and camera model when available.
- Manual overrides for location, camera model, brand, date, focal length,
  aperture, ISO, shutter speed, and full caption text.
- Metadata fields that cannot be read from EXIF are omitted automatically unless
  you add them manually.
- macOS Times New Roman Italic font support, with fallback serif fonts on other
  systems.

## Installation

Install from the local project directory:

```bash
python3 -m pip install .
```

For one-off use without installing:

```bash
python3 -m pip install -r requirements-photo-board.txt
python3 photo_glass_board.py input.jpg -o output.jpg
```

## Usage

After installation:

```bash
photo-glass-board input.jpg -o output.jpg --location "Zhuhai"
```

Without installation:

```bash
python3 photo_glass_board.py input.jpg -o output.jpg --location "Zhuhai"
```

Example with manual metadata:

```bash
photo-glass-board DSC03412.JPG \
  -o DSC03412_board.jpg \
  --brand SONY \
  --camera "SONY ILCE-7M4" \
  --location "Zhuhai" \
  --focal-length 105mm \
  --aperture f/8 \
  --shutter 1/320s \
  --iso 160
```

If a field is missing from EXIF, add only the missing value:

```bash
photo-glass-board input.jpg -o output.jpg --location "Zhuhai" --iso 160
```

To add a custom field that is not covered by the built-in options:

```bash
photo-glass-board input.jpg -o output.jpg --extra-info "ND Filter" --extra-info "Tripod"
```

## Useful Options

```text
--side-margin-ratio      Left/right margin ratio. Default: 0.05
--top-margin-ratio       Top margin ratio. Default: 0.10
--bottom-margin-ratio    Bottom caption area ratio. Default: 0.20
--background-blur        Blur radius for the background board. Default: 58
--background-dim         Darkening blend for the background board. Default: 0.30
--location               Manually add a shooting location.
--date                   Manually add a shooting date.
--focal-length           Manually add focal length, e.g. 105mm.
--aperture               Manually add aperture, e.g. f/8.
--shutter                Manually add shutter speed, e.g. 1/320s.
--iso                    Manually add ISO, e.g. 160 or ISO160.
--extra-info             Add any extra caption field. Can be used repeatedly.
--brand                  Centered brand line override.
--caption                Full centered caption override.
--camera                 Right-side camera model override.
```

## Notes

The script reads EXIF metadata using Pillow. Some exported or edited images may
strip EXIF fields. Missing fields are not printed as placeholders; use the
manual options when you want to add them back.

## License

MIT License. See [LICENSE](LICENSE).
