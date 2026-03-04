# Copilot Instructions for sonic-fips

## Project Overview

sonic-fips provides Federal Information Processing Standards (FIPS) compliant builds of critical cryptographic and security packages for SONiC. It patches and rebuilds packages like OpenSSL, OpenSSH, Python, Golang, and Kerberos to meet FIPS 140-2/140-3 compliance requirements.

## Architecture

```
sonic-fips/
├── Makefile              # Top-level build orchestration
├── rules/                # Build rules for individual packages
├── src/                  # Source patches and build scripts
│   ├── openssl/          # FIPS-compliant OpenSSL build
│   ├── openssh/          # FIPS-compliant OpenSSH build
│   ├── python3.9/        # FIPS-compliant Python build
│   ├── golang/           # FIPS-compliant Go build
│   ├── krb5/             # FIPS-compliant Kerberos build
│   └── symcrypt/         # SymCrypt OpenSSL provider
├── .azure-pipelines/     # Azure DevOps CI
└── azure-pipelines.yml   # CI pipeline
```

### Key Concepts
- **FIPS compliance**: All cryptographic modules must use FIPS-validated algorithms
- **SymCrypt**: Microsoft's FIPS-validated cryptographic library used as the OpenSSL backend
- **Package patching**: Modifies upstream Debian packages to use FIPS-compliant crypto
- **Debian packaging**: Produces `.deb` packages that replace standard versions in SONiC

## Build Instructions

```bash
# Build in debian:bullseye Docker container
# Install build tools (see .azure-pipelines for exact dependencies)

# List available targets
make list

# Build specific packages
make target/symcrypt-openssl_0.3_amd64.deb
make target/openssl_1.1.1n-0+deb11u3+fips_amd64.deb

# Shorthand targets
make symcrypt
make openssl
```

## Language & Style

- **Primary language**: Makefiles and Shell scripts
- **Packaging**: Standard Debian packaging conventions (debian/ directory structure)
- **Version strings**: Include `+fips` suffix to distinguish from upstream packages
- **Patches**: Use quilt patch format for upstream source modifications

## PR Guidelines

- **Signed-off-by**: Required on all commits
- **CLA**: Sign Linux Foundation EasyCLA
- **Security review**: Changes to cryptographic code require careful review
- **FIPS validation**: Do not modify FIPS boundary code without understanding validation implications
- **CI**: Azure pipeline checks must pass

## Gotchas

- **FIPS boundary**: Changes within the FIPS cryptographic module boundary can invalidate certification
- **Version pinning**: Package versions must match the validated versions exactly
- **Build environment**: Must build in the specified Debian version container
- **Upstream sync**: When rebasing on newer upstream versions, FIPS patches must be carefully ported
- **Testing**: FIPS self-tests run at module initialization — verify they pass after changes
