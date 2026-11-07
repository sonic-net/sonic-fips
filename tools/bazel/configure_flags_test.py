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


if __name__ == '__main__':
    unittest.main()
