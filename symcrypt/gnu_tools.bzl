"""Select the GNU tools that run on the executor and operate on the target ELF."""

load("@sonic_build_infra//toolchains/gcc:defs.bzl", "bin")
load("@sonic_build_infra//toolchains/gcc:gcc.bzl", "gcc_repo_name")

_EXEC_CPUS = {
    "aarch64": ["x86_64", "aarch64"],
    "x86_64": ["x86_64"],
}
_TOOLS = ["ld", "objcopy", "strip", "gnu_tool_runtime"]
_GCC_VERSION = "14.2.0"

def declare_gnu_tools():
    """Bind each target CPU before rules_foreign_cc switches build_data to exec."""
    for tool in _TOOLS:
        for target_cpu, exec_cpus in _EXEC_CPUS.items():
            by_executor = {}
            for exec_cpu in exec_cpus:
                if tool == "gnu_tool_runtime":
                    repo = gcc_repo_name(target_cpu, _GCC_VERSION, exec_cpu)
                    label = "@{}//:multicall_support_files".format(repo)
                else:
                    label = bin(target_cpu, _GCC_VERSION, tool, exec_cpu = exec_cpu)
                by_executor["@platforms//cpu:" + exec_cpu] = label
            native.alias(name = target_cpu + "_" + tool, actual = select(by_executor))

        # Keep the public native tool labels available to existing callers.
        native.alias(
            name = tool,
            actual = select({
                "@platforms//cpu:" + cpu: ":" + cpu + "_" + tool
                for cpu in _EXEC_CPUS
            }),
        )

def gnu_build_data(cpu):
    """Return the tool labels and their matched loader and shared libraries."""
    return [":" + cpu + "_" + tool for tool in _TOOLS]

def gnu_cmake_tools(cpu):
    """Configure Clang's GNU linker and SymCrypt's ELF postprocessing tools."""
    ld_flag = "--ld-path=$(execpath :{}_ld)".format(cpu)
    return {
        "CMAKE_EXE_LINKER_FLAGS": ld_flag,
        "CMAKE_MODULE_LINKER_FLAGS": ld_flag,
        "CMAKE_OBJCOPY": "$(execpath :{}_objcopy)".format(cpu),
        "CMAKE_SHARED_LINKER_FLAGS": ld_flag,
        "CMAKE_STRIP": "$(execpath :{}_strip)".format(cpu),
    }
