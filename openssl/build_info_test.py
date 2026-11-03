"""Run OpenSSL's real build-info generator with independent execution roots."""
from pathlib import Path
import subprocess
import sys


def generate(root, flags, *, export_root=True):
    env = {"LC_ALL": "C", "SOURCE_DATE_EPOCH": "1787585182"}
    if export_root:
        env["EXT_BUILD_ROOT"] = root
    return subprocess.check_output(
        # Preserve the declared launcher's path through this test's runfiles.
        # Resolving its symlink would discard the adjacent declared tool data.
        [str(Path(sys.argv[1]).absolute()), str(Path(sys.argv[2]).resolve()), flags, "debian-amd64"],
        env=env,
    )


def compiler_text(generated):
    # Decode the generator's documented array rather than evaluating C/Perl.
    body = generated.decode().split("static const char compiler_flags[] = {\n", 1)[1].split("'\\0'", 1)[0]
    result = []
    position = 0
    while position < len(body):
        if body[position].isspace() or body[position] == ",":
            position += 1
            continue
        assert body[position] == "'", body[position:]
        position += 1
        if body[position] == "\\":
            position += 1
            assert body[position] in ("\\", "'")
        result.append(body[position])
        position += 1
        assert body[position] == "'"
        position += 1
    return "".join(result)


first = "/private/worker-a/sandbox/17/execroot/_main"
second = "/independent/worker-b/sandbox/903/execroot/_main"
arguments = "{root}/external/gcc/bin/gcc -O2 -g --sysroot={root}/external/sysroot -I{root}/bazel-out/include -ffile-prefix-map={root}=. -DNAME='sonic'"
a = generate(first, arguments.format(root=first))
b = generate(second, arguments.format(root=second))
assert a == b
expected = "compiler: " + arguments.format(root=".")
assert compiler_text(a) == expected
assert generate(first, arguments.format(root=first).replace("-O2", "-O3")) != a
assert compiler_text(generate(first, arguments.format(root=first), export_root=False)) == "compiler: " + arguments.format(root=first)
# A sibling whose name merely starts with the root is a different location.
boundary = first + "-other/header.h " + first + "/header.h"
assert compiler_text(generate(first, boundary)) == "compiler: " + first + "-other/header.h ./header.h"
print("Actual OpenSSL build-info generator preserves flags and removes only the execution-root prefix")
