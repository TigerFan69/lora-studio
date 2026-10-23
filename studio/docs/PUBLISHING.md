# Publish the community preview on GitHub

1. Create a GitHub account if needed and a new empty repository named `lora-character-kit`. Choose Public when ready for public review. Do not initialize another README/license if uploading these files.
2. Inspect this release folder. Keep settings, datasets, model weights, private adapters, caches, tokens and logs out of it. The included `.gitignore` helps but does not remove files already tracked.
3. From this release folder:

```sh
git init -b main
git add .
git status
git diff --cached --stat
git commit -m "Publish community preview"
git remote add origin https://github.com/YOUR-ACCOUNT/lora-character-kit.git
git push -u origin main
```

Replace YOUR-ACCOUNT. Authenticate using GitHub's supported browser/credential flow; never put a token in the remote URL. Alternatively use GitHub Desktop's Add Local Repository and Publish Repository.

4. Enable Issues in repository settings. Keep the prerequisite warning at the top of the README.
5. On GitHub select Releases → Draft a new release. Create a tag such as `v0.3.0-preview.1`, target the reviewed commit, mark it **pre-release**, and describe the RTX 4080 short-test evidence plus fresh-install and quality limitations.
6. Attach a `.tar.gz` of this folder and its SHA-256 checksum if desired. GitHub also offers automatically generated source tarballs. Avoid including your working Studio folder with live data. Publish only after inspecting the staged files and release notes.
7. Link the release from the Civitai article. Ask testers to report installation problems, hardware, profile/settings, character consistency and confusing UI steps through GitHub Issues.
8. For updates, commit changes, use a new tag and new release assets, and list changes and validation. Do not silently replace a previous tested release.

GitHub is recommended for source, version history and feedback; a release archive provides a convenient download. Archive format alone does not establish safety: users should review source/provenance and compare checksums. A checksum detects changes relative to a trusted copy; it is not a security audit.

Official instructions: https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository

No repository or release has been published by preparing this folder.
