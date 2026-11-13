*sonic-fips builds:*

[![main build](https://dev.azure.com/mssonic/build/_apis/build/status/Azure.sonic-fips?branchName=main&label=main)](https://dev.azure.com/mssonic/build/_build/latest?definitionId=412&branchName=main)

# SONiC: Software for Open Networking in the Cloud

## sonic-fips

Support Federal Information Processing Standards (FIPS) for SONiC

### To Build
1. Setup build env

   It can be built in the docker container of the image debian:bullseye.
   To install the build tools, you can simply copy and run the [installing script](https://github.com/sonic-net/sonic-fips/blob/112504659c8904a3fbca2803dea4e8203369b16c/.azure-pipelins/build-template.yml#L31).

2. Show build targets

  ```
  $ make list
  target/python3.9_3.9.2-1+fips_amd64.deb
  target/openssh-server_8.4p1-5+deb11u1+fips_amd64.deb
  target/openssl_1.1.1n-0+deb11u3+fips_amd64.deb
  target/symcrypt-openssl_0.3_amd64.deb
  target/golang-1.15_1.15.15-1~deb11u4+fips_all.deb
  target/libk5crypto3_1.18.3-6+deb11u1+fips_amd64.deb
  ```

3. Build

  Make a target as list in step 2
  ```
  make target/symcrypt-openssl_0.3_amd64.deb
  make target/openssl_1.1.1n-0+deb11u3+fips_amd64.deb
  ```
  To build the symcrypt debian packages and openssl packages, it can be simplified to:
  ```
  make symcrypt
  make openssl
  ```
  To make all targets:
  ```
  make all
  ```
### To test

1. Setup kvm env

  ```
  wget 'https://sonic-build.azurewebsites.net/api/sonic/artifacts?branchName=master&platform=vs&target=target%2Fsonic-vs.img.gz' -O sonic-vs.img.gz
  gunzip sonic-vs.img.gz
  virt-install \
    --name test01 \
    --ram 4096 \
    --disk path=/projects/test/test-kvm-3/sonic-vs.img \
    --vcpus 2 \
    --os-type linux \
    --os-variant debian11 \
    --network bridge=virbr0 \
    --graphics vnc,port=5900,listen=0.0.0.0 \
    --console pty,target_type=serial \
    --force --debug --boot hd
  virsh console test01
  ```

2. Download the fips packages

  Skip the step if you want to use you own build packages.
  ```
  wget 'https://sonic-build.azurewebsites.net/api/sonic/artifacts?branchName=main&definitionId=412&artifactName=fips-symcrypt-amd64&format=zip&target=/' -O target.zip
  unzip target.zip
  ```
  You can list all the artifacts: https://sonic-build.azurewebsites.net/ui/sonic/pipelines/412/builds?branchName=main

3. Install the fips packages

  ```
  sudo dpkg -i symcyprt*.deb
  sudo dpkg -i libssl*.deb
  sudo dpkg -i openssl*.deb
  ```

4. Enable FIPS in kvm

  ```
  admin@sonic:~$ sudo sonic-installer set-fips --enable-fips
  Done
  Set FIPS for the image successfully
  ```
  Reboot is requried if the fip option changed. You can verify if the symcrypt engine enabled.

  ```
  admin@sonic:~$ openssl engine -vv | grep symcrypt
  (symcrypt) SCOSSL (SymCrypt engine for OpenSSL)
  admin@sonic:~$ 
  ```

### GitHub release archives

A successful **main** pipeline run (both the three-architecture build stage and the test stage) publishes GitHub Releases only; no CDN upload is used. PR and fork builds cannot run the publishing stage. Configure a masked Azure pipeline secret variable named `GITHUB_TOKEN` with GitHub **Contents: write** permission for `sonic-net/sonic-fips` before enabling the stage; do not put its value in YAML or command arguments. The publishing agent needs `gh`, `dpkg-deb`, and Python 3.

The job downloads the **current run's** `fips-symcrypt-amd64`, `fips-symcrypt-arm64`, and `fips-symcrypt-armhf` pipeline artifacts. It checks each `.deb` filename against its Debian `Package`, `Version`, and `Architecture` metadata, requires the SymCrypt package version to match `src/SymCrypt-OpenSSL-Debian/debian/control` in every architecture, and rejects conflicting duplicates or inconsistent `all` packages. The current version is `1.8.0-24-gd744cf2-3`; later source version bumps need no publisher change. The release stage and its script both restrict publication to the canonical non-PR `main` build; offline publisher tests also run in the test stage on PRs. Each release contains exactly:

- `fips-symcrypt-amd64.tar.gz`
- `fips-symcrypt-arm64.tar.gz`
- `fips-symcrypt-armhf.tar.gz`
- `SHA256SUMS` (SHA-256 of those three archives)

The normal tag is the verified SymCrypt Debian version. If that release exists and its archived **`.deb` filenames and SHA-256 contents** are identical, the job skips publishing. If they differ, the job uses the immutable `<version>-build-<AzureBuildId>` fallback tag. An existing fallback with identical packages is also skipped; a different fallback, a draft/prerelease, an incomplete/corrupt release, or an orphaned tag causes a loud failure for manual inspection. The script creates a tag only if absent, never updates a tag or replaces an asset. It uploads to a draft, downloads all assets again, checks archive sums and package hashes against the input artifacts, verifies the tag still points to the source commit, and only then publishes. A failed operation may leave a draft or an orphaned tag requiring manual attention; retries do not silently repair them.

For an offline check of the publisher: `python3 -m unittest discover -s tests -v`. This release workflow verifies package integrity and provenance within the current Azure run; it does **not** assert FIPS certification or validation.
