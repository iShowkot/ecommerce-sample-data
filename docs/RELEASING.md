# Releasing

A release's CSVs point their image and download URLs at the release's own tag, so a tagged file keeps working even if the images change later.

1. **Images.** Generate and review them (with `scripts/images.py`, or another tool plus `--from-raw`), then commit:

   ```sh
   python3 scripts/images.py
   python3 scripts/build.py && python3 scripts/check.py --require-images
   ```

2. **Release candidate.** Build with the candidate's tag, commit, tag and push:

   ```sh
   python3 scripts/build.py --ref v1.0.0-rc.1
   python3 scripts/check.py --require-images
   git commit -am "Build v1.0.0-rc.1"
   git tag v1.0.0-rc.1 && git push origin main v1.0.0-rc.1
   python3 scripts/check.py --online   # every URL should load once the tag is pushed
   ```

3. **Test the imports** with the files from the tag, on a fresh WooCommerce site and a Shopify development store. Note the versions you tested on.

4. **Release.** Repeat step 2 with `--ref v1.0.0` and the tag `v1.0.0`. Update `CHANGELOG.md` and the "tested with" note in the README, then create a GitHub release from the tag with the CSVs attached.

5. **Back to development.** Afterwards, `python3 scripts/build.py` (ref `main`) points the files on `main` back at the branch.
