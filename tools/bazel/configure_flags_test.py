"""Run the owner adapter through real Autoconf, GCC and recursive Make."""
import hashlib
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest

ADAPTER = Path(sys.argv.pop(1)).resolve()
COMPONENT = sys.argv.pop(1)
assert COMPONENT in ('openssh', 'krb5')
PKGCONF = Path(sys.argv.pop(1)).resolve() if COMPONENT == 'openssh' else None


class ConfigureFlagsTest(unittest.TestCase):
    def test_long_dependency_flags(self):
        tools = {name: shutil.which(name) for name in ('gcc', 'make', 'autoconf', 'autoheader', 'readelf')}
        self.assertTrue(all(tools.values()), 'native CI installs the declared compiler/configure test tools')
        version = subprocess.check_output([tools['gcc'], '-dumpversion'], text=True).strip()
        self.assertEqual(version.split('.')[0], '14', 'this regression covers the selected native GCC14 contract')
        with tempfile.TemporaryDirectory(prefix=COMPONENT + '-flags-') as temporary:
            root = Path(temporary)
            (root / 'dependency').mkdir()
            (root / 'dependency/chosen.h').write_text('#define CHOSEN 41\n')
            (root / 'source').mkdir()
            (root / 'source/chosen.h').write_text('#define CHOSEN 42\n')
            (root / 'sub').mkdir()
            source = '''#include <stdio.h>
#include <chosen.h>
#ifndef MESSAGE
#error missing quoted define
#endif
int main(void) { printf("%d:%s\\n", CHOSEN, MESSAGE); return 0; }
'''
            (root / 'probe.c').write_text(source)
            (root / 'configure.ac').write_text('''AC_INIT([flags-probe], [1])
AC_CONFIG_SRCDIR([probe.c])
AC_CONFIG_HEADERS([config.h])
AC_PROG_CC
AC_PROG_CPP
AC_RUN_IFELSE([AC_LANG_SOURCE([[int main(void) { return 0; }]])],
              [], [AC_MSG_ERROR([runtime probe failed])])
AC_RUN_IFELSE([AC_LANG_SOURCE([[int main(void) { return 1; }]])],
              [AC_MSG_ERROR([negative runtime probe passed])], [])
AC_PREPROC_IFELSE([AC_LANG_SOURCE([[#include <chosen.h>
#if CHOSEN != 41
#error dependency header precedence changed
#endif
]])], [], [AC_MSG_ERROR([preprocessor failed])])
AC_COMPILE_IFELSE([AC_LANG_SOURCE([[#include <chosen.h>
const char *message = MESSAGE;
int value = CHOSEN;
]])], [], [AC_MSG_ERROR([compiler flags failed])])
AC_CONFIG_FILES([Makefile sub/Makefile])
AC_OUTPUT
''')
            (root / 'Makefile.in').write_text('all:\n\t$(MAKE) -C sub\n')
            (root / 'sub/Makefile.in').write_text('''CC = @CC@
CFLAGS = @CFLAGS@
CPPFLAGS = @CPPFLAGS@
LDFLAGS = @LDFLAGS@
all:
	$(CC) $(CFLAGS) -I../source $(CPPFLAGS) ../probe.c $(LDFLAGS) -o ../make-probe
	../make-probe > ../make-result
''')
            # Model the declared build-tools layout without exporting target
            # libraries to the host shell. CI supplies the native runtime here;
            # the full source build separately checks the target sysroot.
            runtime = root / 'runtime'
            (runtime / 'bin').mkdir(parents=True)
            (runtime / 'usr').mkdir()
            (runtime / 'bin/autoconf').symlink_to(tools['autoconf'])
            (runtime / 'usr/lib').mkdir()
            for library in Path('/usr/lib').glob('*/ld-linux-*.so.*'):
                (runtime / 'usr/lib' / library.name).symlink_to(library)
            dependency = root / 'deps'
            env = {**os.environ, 'CC': tools['gcc'], 'AUTOCONF': str(runtime / 'bin/autoconf'),
                   'EXT_BUILD_DEPS': str(dependency),
                   'AUTOHEADER': tools['autoheader'],
                   'CFLAGS': '-O2 -g -ffile-prefix-map=' + str(root) + '=.'}
            env.pop('LD_LIBRARY_PATH', None)
            if COMPONENT == 'openssh':
                env.update(EXT_BUILD_ROOT=str(root), BAZEL_PKGCONFIG_FILES='',
                           PKGCONFIG=str(PKGCONF))
            if COMPONENT == 'krb5':
                # The adapter discovers this directory before writing its
                # original crypto-test target. This fixture does not run or
                # claim to validate crypto; the separate package CI does that.
                crypto = dependency / 'build/usr/lib/test-native/libcrypto.so.3'
                crypto.parent.mkdir(parents=True)
                crypto.touch()
                (root / 'config').mkdir()
                env.update(KERBEROS_BUILD_TOOLS='/usr', EXT_BUILD_ROOT=str(root),
                           EXT_BUILD_DEPS=str(dependency), BAZEL_PKGCONFIG_FILES='',
                           BAZEL_PKGCONF='/bin/true')
            short_cpp = "-DMESSAGE='\"quoted value\"' -isystem " + str(root / 'dependency')
            short_ld = '-Wl,--build-id -Wl,--defsym,flag_order=11 -Wl,--defsym,flag_order=29'
            results = []
            for long in (False, True):
                cpp, ld = short_cpp, short_ld
                if long:
                    index = 0
                    while len(cpp.encode()) < 95000:
                        cpp += ' -isystem' + str(root / ('unused-header-' + str(index)))
                        index += 1
                    while len(ld.encode()) < 55000:
                        ld += ' -L' + str(root / ('unused-library-' + str(index)))
                        index += 1
                    self.assertLess(len(cpp.encode()), 131072)
                    self.assertLess(len(ld.encode()), 131072)
                    # Reproduce the real failure at GCC->cc1, rather than
                    # substituting a shell environment-size simulation.
                    legacy = subprocess.run([tools['gcc'], *shlex.split(env['CFLAGS']),
                                             *shlex.split(cpp), *shlex.split(ld),
                                             '-x', 'c', '-o', 'legacy', 'probe.c'],
                                            cwd=root, capture_output=True, text=True)
                    self.assertNotEqual(legacy.returncode, 0)
                    self.assertIn('Argument list too long', legacy.stderr)
                current = {**env, 'CPPFLAGS': cpp, 'LDFLAGS': ld}
                for command in (['/bin/sh', str(ADAPTER)], [tools['make']]):
                    result = subprocess.run(command, cwd=root, env=current, capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                generated = (root / 'configure').read_text()
                self.assertEqual(generated.count("ac_try='\"$SONIC_PROBE_LOADER\" --library-path"), 2)
                self.assertNotIn("ac_try='./conftest", generated)
                self.assertEqual((root / 'make-result').read_text(), '42:quoted value\n')
                symbols = subprocess.check_output([tools['readelf'], '-Ws', str(root / 'make-probe')], text=True)
                value = next(line.split()[1] for line in symbols.splitlines() if line.endswith(' flag_order'))
                self.assertEqual(int(value, 16), 29, 'link options reordered')
                debug = subprocess.check_output([tools['readelf'], '-p', '.debug_line_str', '-p', '.debug_str', str(root / 'make-probe')], text=True)
                self.assertNotIn(str(root), debug, 'driver prefix maps lost')
                results.append(hashlib.sha256((root / 'make-probe').read_bytes()).hexdigest())
            self.assertEqual(results[0], results[1], 'response transport changed compiled bytes')
            # A generator change must not silently skip interception.
            changed_generator = root / 'changed-autoconf'
            changed_generator.write_text('#!/bin/sh\n' + shlex.quote(tools['autoconf']) +
                                         ' "$@"\n' +
                                         "sed -i \"s|ac_try='./conftest|ac_try='./unexpected|g\" configure\n")
            changed_generator.chmod(0o755)
            autoconf = runtime / 'bin/autoconf'
            autoconf.unlink()
            autoconf.symlink_to(changed_generator)
            rejected = subprocess.run(['/bin/sh', str(ADAPTER)], cwd=root,
                                      env={**env, 'CPPFLAGS': short_cpp, 'LDFLAGS': short_ld},
                                      capture_output=True, text=True)
            self.assertNotEqual(rejected.returncode, 0, 'changed generator bypassed the loader assertion')
            self.assertNotIn("ac_try='./conftest", (root / 'configure').read_text())
            autoconf.unlink()
            autoconf.symlink_to(tools['autoconf'])
            bad = subprocess.run(['/bin/sh', str(ADAPTER)], cwd=root,
                                 env={**env, 'CPPFLAGS': '-Wl,--as-needed', 'LDFLAGS': ''},
                                 capture_output=True, text=True)
            self.assertNotEqual(bad.returncode, 0)
            self.assertIn('CPPFLAGS must contain GCC preprocessor options', bad.stderr)


@unittest.skipUnless(COMPONENT == 'openssh', 'OpenSSH declared libedit metadata only')
class ConfigurePkgconfigTest(unittest.TestCase):
    """Run the actual metadata staging and pkgconf, without compiling code."""

    LIBEDIT = '''prefix=/usr
libdir=${prefix}/lib/target
includedir=${prefix}/include
Name: libedit
Description: Declared fixture for OpenSSH's libedit query
Version: 1
Requires.private: tinfo
Libs: -L${libdir} -ledit
Cflags: -I${includedir}/editline
'''
    TINFO = '''prefix=/usr
libdir=${prefix}/lib/target
Name: tinfo
Description: Declared private dependency fixture
Version: 1
Libs: -L${libdir} -ltinfo
'''

    def run_metadata(self, files, query, tool_with_spaces=False, inherited_system_cflags=False):
        adapter = ADAPTER.read_text()
        start = adapter.index('\n', adapter.index('"$AUTOHEADER"')) + 1
        end = adapter.index('# Autoconf runs target conftest ELFs.', start)
        with tempfile.TemporaryDirectory(prefix='openssh-pkgconfig-') as temporary:
            root = Path(temporary)
            for relative, content in files.items():
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)
            host = root / 'host'
            host.mkdir()
            (host / 'libedit.pc').write_text(self.LIBEDIT.replace('-ledit', '-lHOST_POISON'))
            # Staging uses only the established shell/filesystem tools. The
            # declared pkgconf launcher is the sole metadata executable.
            commands = root / 'commands'
            commands.mkdir()
            for name in ('mkdir', 'basename', 'cmp', 'ln', 'chmod'):
                executable = shutil.which(name)
                self.assertIsNotNone(executable)
                (commands / name).symlink_to(executable)
            pkgconf = PKGCONF
            if tool_with_spaces:
                pkgconf = root / 'declared tool with spaces' / 'pkgconf'
                pkgconf.parent.mkdir()
                pkgconf.symlink_to(PKGCONF)
            dependency = root / 'deps'
            env = {'PATH': str(commands), 'LC_ALL': 'C',
                   'EXT_BUILD_ROOT': str(root), 'EXT_BUILD_DEPS': str(dependency),
                   'BAZEL_PKGCONFIG_FILES': ' '.join(files), 'PKGCONFIG': str(pkgconf),
                   'PKG_CONFIG_LIBDIR': str(host), 'PKG_CONFIG_PATH': str(host)}
            if inherited_system_cflags:
                env.update(PKG_CONFIG_ALLOW_SYSTEM_CFLAGS='1',
                           PKG_CONFIG_SYSTEM_INCLUDE_PATH='/unrelated-probe/include')
            script = 'set -eu\n' + adapter[start:end] + query + '\n'
            result = subprocess.run(['/bin/sh', '-s'], input=script, text=True,
                                    cwd=root, env=env, capture_output=True, timeout=5)
            return result, str(dependency)

    def test_shared_sdk_include_does_not_override_source_headers(self):
        # Actual libedit-dev 3.1-20250104-1 metadata includes both the generic
        # SDK root and /editline. The generic -I outranks source CcInfo's
        # -isystem even when upstream also passes -I for that same source dir.
        metadata = '''prefix=/usr
exec_prefix=${prefix}
libdir=${prefix}/lib/x86_64-linux-gnu
includedir=${prefix}/include
Name: libedit
Description: command line editor library
Version: 3.1
Requires:
Libs: -L${libdir} -ledit
Libs.private: -ltermcap -lbsd
Cflags: -I${includedir} -I${includedir}/editline
'''
        for inherited in (False, True):
            for spaces in (False, True):
                with self.subTest(inherited=inherited, spaces=spaces):
                    result, deps = self.run_metadata(
                        {'declared/libedit.pc': metadata},
                        '"$PKGCONFIG" --cflags libedit\n'
                        '"$PKGCONFIG" --libs libedit\n'
                        '"$PKGCONFIG" --static --libs libedit\n'
                        'printf "%s|%s\\n" "${PKG_CONFIG_ALLOW_SYSTEM_CFLAGS-unset}" '
                        '"${PKG_CONFIG_SYSTEM_INCLUDE_PATH-unset}"',
                        tool_with_spaces=spaces,
                        inherited_system_cflags=inherited)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    headers, libraries, static, parent = result.stdout.splitlines()
                    self.assertEqual(shlex.split(headers),
                                     ['-I' + deps + '/include/usr/include/editline'])
                    self.assertEqual(shlex.split(libraries), ['-L' + deps + '/lib', '-ledit'])
                    self.assertEqual(shlex.split(static),
                                     ['-L' + deps + '/lib', '-ledit', '-ltermcap', '-lbsd'])
                    self.assertEqual(parent, '1|/unrelated-probe/include' if inherited else 'unset|unset')

    def test_declared_metadata_avoids_fallback_and_host_paths(self):
        result, deps = self.run_metadata(
            {'declared/libedit.pc': self.LIBEDIT, 'declared/tinfo.pc': self.TINFO},
            '"$PKGCONFIG" --exists libedit\n'
            '"$PKGCONFIG" --libs libedit\n'
            '"$PKGCONFIG" --cflags libedit\n'
            '"$PKGCONFIG" --static --libs libedit')
        self.assertEqual(result.returncode, 0, result.stderr)
        dynamic, headers, static = result.stdout.splitlines()
        self.assertIn('-ledit', dynamic)
        self.assertIn('-L' + deps + '/lib', dynamic)
        self.assertIn('-I' + deps + '/include/usr/include/editline', headers)
        self.assertIn('-ltinfo', static)
        for forbidden in ('-lcurses', 'HOST_POISON', '/usr/lib/target'):
            self.assertNotIn(forbidden, result.stdout)

    def test_upstream_quoted_executable_and_argument_boundaries(self):
        # Match OpenSSH's quoted executable call, rather than splitting a
        # command string. A tool path with spaces must remain one filename.
        result, deps = self.run_metadata(
            {'declared/libedit.pc': self.LIBEDIT, 'declared/tinfo.pc': self.TINFO},
            '"$PKGCONFIG" --exists libedit\n'
            '"$PKGCONFIG" --define-variable=quoted="one value" --variable=quoted libedit\n'
            '"$PKGCONFIG" --libs libedit', tool_with_spaces=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        quoted, libraries = result.stdout.splitlines()
        self.assertEqual(quoted, 'one value')
        self.assertIn('-L' + deps + '/lib', libraries)
        self.assertIn('-ledit', libraries)
        self.assertNotIn('-lcurses', libraries)

    def test_missing_declared_metadata_does_not_use_host(self):
        result, _ = self.run_metadata({}, '"$PKGCONFIG" --exists libedit')
        self.assertNotEqual(result.returncode, 0)

    def test_duplicate_metadata_must_match(self):
        for conflict in (False, True):
            with self.subTest(conflict=conflict):
                duplicate = self.LIBEDIT.replace('-ledit', '-lWRONG') if conflict else self.LIBEDIT
                result, _ = self.run_metadata(
                    {'declared/libedit.pc': self.LIBEDIT, 'duplicate/libedit.pc': duplicate,
                     'declared/tinfo.pc': self.TINFO},
                    '"$PKGCONFIG" --libs libedit')
                if conflict:
                    self.assertNotEqual(result.returncode, 0)
                else:
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn('-ledit', result.stdout)


@unittest.skipUnless(COMPONENT == 'openssh', 'OpenSSH link diagnostics only')
class ConfigureDiagnosticsTest(unittest.TestCase):
    """Exercise the actual failure wrapper with shell-only configure fixtures."""

    def run_diagnostic(self, log, status=37, broken_stderr=False):
        adapter = ADAPTER.read_text()
        start = adapter.index('report_libedit_link_failure() (')
        end = adapter.index('# Match Debian', start)
        with tempfile.TemporaryDirectory(prefix='openssh-link-diagnostic-') as temporary:
            root = Path(temporary)
            if log is not None:
                (root / 'config.log').write_text(log)
            (root / 'config.h').write_text('untouched\n')
            configure = root / 'configure'
            configure.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > arguments\nexit ' + str(status) + '\n')
            configure.chmod(0o755)
            script = 'set -eu\n' + adapter[start:end] + 'printf "post-configure\\n"\n'
            command = ['/bin/sh', '-s', '--', '--with-libedit', '--with-ssl-dir=/declared/openssl']
            read_fd = write_fd = None
            try:
                if broken_stderr:
                    read_fd, write_fd = os.pipe()
                    os.close(read_fd)
                    read_fd = None
                result = subprocess.run(command, input=script, text=True, cwd=root,
                                        env={'PATH': '/nonexistent', 'LC_ALL': 'C'},
                                        stdout=subprocess.PIPE,
                                        stderr=write_fd if broken_stderr else subprocess.PIPE,
                                        timeout=5)
            finally:
                if write_fd is not None:
                    os.close(write_fd)
            arguments = (root / 'arguments').read_text().splitlines()
            self.assertEqual(arguments[:2], command[-2:])
            self.assertEqual(len(arguments), 3)
            self.assertIn('Debian-7+fips', arguments[2])
            self.assertEqual((root / 'config.h').read_text(), 'untouched\n')
            return result

    @staticmethod
    def failure_log(command='configure:105: cc -o conftest -ledit >&5'):
        return ('ENV_BEFORE=private-value\n'
                'configure:100: checking for el_init in -ledit\n' + command + '\n'
                "/declared/ld: libedit.so: undefined reference to `tgetent'\n"
                'configure:105: $? = 1\n'
                'configure: failed program was:\n'
                '| SOURCE_PROGRAM_MUST_NOT_BE_PRINTED\n'
                'configure:110: result: no\n'
                '## Cache variables. ##\n'
                'ac_cv_private=PRIVATE_CACHE_VALUE\n'
                'ENV_AFTER=private-value\n')

    def test_failed_link_excerpt_and_exit(self):
        result = self.run_diagnostic(self.failure_log())
        self.assertEqual(result.returncode, 37)
        self.assertIn('undefined reference', result.stderr)
        self.assertIn('cc -o conftest -ledit', result.stderr)
        self.assertIn('$? = 1', result.stderr)
        self.assertEqual(result.stdout, '')
        for private in ['ENV_BEFORE', 'SOURCE_PROGRAM', 'Cache variables', 'PRIVATE_CACHE', 'ENV_AFTER']:
            self.assertNotIn(private, result.stderr)

    def test_long_command_keeps_following_link_error(self):
        command = 'configure:105: cc -o conftest ' + '-L/declared/library ' * 6000
        result = self.run_diagnostic(self.failure_log(command))
        self.assertEqual(result.returncode, 37)
        self.assertIn('[line clipped]', result.stderr)
        self.assertIn('undefined reference', result.stderr)
        self.assertLess(len(result.stderr.encode()), 17000)
        self.assertLessEqual(max(map(len, result.stderr.splitlines())), 2063)

    def test_success_and_unrelated_or_incomplete_logs_are_quiet(self):
        for log in [None, '', 'ENV_ONLY=private\n',
                    self.failure_log().replace('result: no', 'result: yes'),
                    self.failure_log().split('configure:110: result: no')[0]]:
            with self.subTest(log=log):
                result = self.run_diagnostic(log)
                self.assertEqual(result.returncode, 37)
                self.assertEqual(result.stderr, '')
        success = self.run_diagnostic(self.failure_log(), status=0)
        self.assertEqual(success.returncode, 0)
        self.assertEqual(success.stderr, '')
        self.assertEqual(success.stdout, 'post-configure\n')

    def test_limits_sensitive_lines_and_broken_output(self):
        command = ('configure:105: cc TOKEN=must-not-leak\n'
                   'configure:106: https://private.invalid/must-not-leak\n' +
                   ('/declared/ld: undefined reference ' + 'x' * 2000 + '\n') * 80)
        result = self.run_diagnostic(self.failure_log(command))
        self.assertEqual(result.returncode, 37)
        self.assertNotIn('must-not-leak', result.stderr)
        self.assertLess(len(result.stderr.encode()), 17000)
        self.assertLessEqual(len(result.stderr.splitlines()), 33)
        broken = self.run_diagnostic(self.failure_log(), broken_stderr=True)
        self.assertEqual(broken.returncode, 37)


if __name__ == '__main__':
    unittest.main()
