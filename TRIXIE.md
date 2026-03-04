# Trixie (Debian 13) FIPS Support

## OpenSSL 3.5.x Compatibility

OpenSSL 3.5.x (shipped in Debian Trixie) introduces several changes that affect FIPS patch compatibility:

### Test Data File Reorganization

OpenSSL 3.5.x split monolithic test data files into per-algorithm files:
- `evppkey.txt` → `evppkey_rsa.txt`, `evppkey_ecc.txt`, `evppkey_dsa.txt`, etc.
- `evpciph.txt` → `evpciph_aes_common.txt`, `evpciph_des.txt`, etc.
- `evpmac.txt` → `evpmac_common.txt`, `evpmac_blake.txt`, etc.

### Patch Compatibility

Of the 7 Bookworm FIPS debian patches, only 3 are needed for Trixie:

| Patch | Status | Notes |
|-------|--------|-------|
| `20-support-fips-test.patch` | ✅ Applies (with fuzz) | FIPS test enablement |
| `70-disable-evp-iv-check.patch` | ✅ Applies (with offset) | EVP IV check bypass |
| `Remove-the-provider-section.patch` | ✅ Already in Debian | Part of Trixie upstream |
| `30-disable-some-evppkey-tests-for-fips.patch` | ❌ Not needed | Target file split; tests pass |
| `40-disable-test-cases-with-fips-enabled.patch` | ❌ Not needed | Partial hunks fail; tests pass |
| `50-disable-some-evpciph-test-for-fips.patch` | ❌ Not needed | Target file split; tests pass |
| `60-disable-evpmac-tests-for-fips.patch` | ❌ Not needed | Target file split; tests pass |

### Test Results

Full test suite (343 files, 4471 tests) passes with only the 3 compatible patches applied.
No `DEB_BUILD_OPTIONS=nocheck` workaround needed.

### Package Differences from Bookworm

| Bookworm (OpenSSL 3.0.x) | Trixie (OpenSSL 3.5.x) |
|---------------------------|------------------------|
| `libssl3` | `libssl3t64` (t64 transition) |
| FIPS provider in `openssl` | Separate `openssl-provider-fips` package |
| — | Post-quantum: ML-DSA, ML-KEM, SLH-DSA |
| 18 FIPS self-tests | 41 FIPS self-tests |

### SymCrypt Compatibility

SymCrypt and SymCrypt-OpenSSL build and work on Trixie without modification:
- `openssl fipsinstall` passes all 41 self-tests
- SymCrypt provider loads alongside default and FIPS providers
