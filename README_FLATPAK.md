# Flatpak build & Flathub publishing notes

Build locally (requires `flatpak-builder` and the SDK/runtime installed):

```bash
cd "$(dirname "$0")"
# build and install for the current user
flatpak-builder --user --install --force-clean build-dir flatpak/org.we.VideoPicker.yml

# run the app
flatpak run org.we.VideoPicker
```

Create a distributable bundle (optional):

```bash
# export to a local repo
flatpak build-export repo build-dir
# create a bundle
flatpak build-bundle repo org.we.VideoPicker.flatpak org.we.VideoPicker
```

Publishing to Flathub (high level):

1. Create a public GitHub repository (recommended name: `org.we.VideoPicker`) and put the Flatpak manifest at the repository root or under `/flatpak`.
2. Follow Flathub's app submission docs: fork the `flathub` repo and add a new package under `apps/` that points to your manifest or upstream source. Open a PR against `flathub` and follow their review process.
3. Flathub maintainers will review the manifest and request changes if needed.

Notes:
- If `we-video-picker.py` has Python dependencies, add a dedicated module in the manifest to pip-install them or include a wheel. You may need to use `org.freedesktop.Sdk.Extension.python3` or include modules that install dependencies into `/app/lib/python3/site-packages`.
- The manifest here uses a local `type: dir` source so building requires the project tree available locally when running `flatpak-builder`.
