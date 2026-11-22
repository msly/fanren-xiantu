# MakeHuman graphical source assets

These files are upstream graphical assets released under **CC0-1.0**. They provide the anatomical head, morph deltas, eye fitting data, and UV-compatible skin/eye images for the Han Li character.

- Upstream repository: https://github.com/makehumancommunity/makehuman
- Pinned repository commit: `a8bc2d54ff0ac92e78ff71431b1023eda42bf482`
- Upstream asset license: `LICENSE.ASSETS.md`
- License explanation: https://www.makehumancommunity.org/about/license.html
- Skin pack provenance: https://static.makehumancommunity.org/assets/assetpacks/makehuman_system_assets.html
- Exact source paths, download URLs, sizes and SHA-256 values: `sources.json`

The `.obj` files include upstream face topology and UVs. The `.target` files contain vertex displacement data. The `.mhclo` file contains barycentric eye fitting data. The `.mhmat` file describes the original material and is retained as provenance.

`tools/hanli_face.py` constructs the project-specific head from this data, aligns it to the existing character rig, and packs its textures into the editable Blender file and exported GLB. The source assets are kept unchanged to make regeneration reproducible. The rest of the character uses the project's custom costume, hair, rig, and animation code.

No MakeHuman/MPFB application source code is copied. Its application licenses are distinct from the CC0 graphical asset license.
