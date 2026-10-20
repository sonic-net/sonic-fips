"""Attach existing core symbols while forwarding its sealed runtime unchanged."""

load("@sonic_build_infra//binary:debug_symbols.bzl", "DebugSymbolsInfo")

def _sealed_runtime_impl(ctx):
    symbols = ctx.actions.declare_directory(ctx.label.name + ".core_debug")
    ctx.actions.run_shell(
        inputs = [ctx.file.core_debug],
        tools = [ctx.attr._readelf[DefaultInfo].files_to_run],
        outputs = [symbols],
        arguments = [ctx.executable._readelf.path, ctx.file.core_debug.path, symbols.path],
        command = """set -eu
identifier=$("$1" -n "$2" | sed -n 's/.*Build ID: //p')
test -n "$identifier"
case "$identifier" in *[!0-9a-f]*) exit 1 ;; esac
mkdir -p "$3/.build-id/${identifier:0:2}"
destination="$3/.build-id/${identifier:0:2}/${identifier:2}.debug"
cp "$2" "$destination"
""",
        mnemonic = "PreserveSealedSymbols",
        progress_message = "Collecting existing sealed-module symbols for %{label}",
    )
    return [
        ctx.attr.tar[DefaultInfo],
        DebugSymbolsInfo(symbols = depset(
            [symbols],
            transitive = [ctx.attr.tar[DebugSymbolsInfo].symbols],
        )),
    ]

sealed_runtime = rule(
    implementation = _sealed_runtime_impl,
    attrs = {
        "tar": attr.label(mandatory = True, providers = [DebugSymbolsInfo]),
        "core_debug": attr.label(mandatory = True, allow_single_file = True),
        "_readelf": attr.label(
            default = "@sonic_build_infra//toolchains/binutils:readelf",
            executable = True,
            cfg = "exec",
        ),
    },
)
