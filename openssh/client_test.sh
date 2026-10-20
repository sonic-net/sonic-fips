#!/bin/sh
# Exercise the newly compiled clients without contacting a server or using keys
# from the build host. The foreign_cc action supplies declared library paths.
set -eu
[ "$#" -eq 1 ]
receipt=$1
test_home=$(mktemp -d /tmp/sonic-openssh-test.XXXXXX)
agent_pid=
cleanup() {
    if [ -n "$agent_pid" ]; then
        kill "$agent_pid" 2>/dev/null || true
        wait "$agent_pid" 2>/dev/null || true
    fi
    rm -rf "$test_home"
}
trap cleanup EXIT HUP INT TERM

# Debian's archive name is 10.0p1, while its pinned version.h says 10.0p2.
# Compare the executable with the actual patched source header.
upstream=$(awk '$1 == "#define" && $2 == "SSH_VERSION" {gsub(/"/, "", $3); print $3}' version.h)
portable=$(awk '$1 == "#define" && $2 == "SSH_PORTABLE" {gsub(/"/, "", $3); print $3}' version.h)
[ -n "$upstream" ] && [ -n "$portable" ]
expected_release="$upstream$portable"
version=$(./ssh -V 2>&1)
case "$version" in
    "$expected_release Debian-7+fips, OpenSSL 3.5.7 "*) ;;
    *) echo "Unexpected source/runtime version: $version" >&2; exit 1 ;;
esac
printf '%s\n' "$version"
./ssh -F /dev/null -G -o CanonicalizeHostname=no example.invalid > "$test_home/config"
grep -q '^hostname example.invalid$' "$test_home/config"
./ssh -Q cipher > "$test_home/ciphers"
grep -q '^aes256-ctr$' "$test_home/ciphers"

./ssh-keygen -q -t rsa -b 2048 -N '' -f "$test_home/key"
./ssh-keygen -lf "$test_home/key.pub" > "$test_home/fingerprint"
./ssh-agent -D -a "$test_home/agent" > "$test_home/agent.log" 2>&1 &
agent_pid=$!
attempt=0
while [ ! -S "$test_home/agent" ]; do
    kill -0 "$agent_pid"
    attempt=$((attempt + 1))
    [ "$attempt" -lt 50 ]
    sleep 0.1
done
SSH_AUTH_SOCK="$test_home/agent" ./ssh-add "$test_home/key"
SSH_AUTH_SOCK="$test_home/agent" ./ssh-add -l > "$test_home/agent-keys"
fingerprint=$(awk '{print $2}' "$test_home/fingerprint")
grep -F "$fingerprint" "$test_home/agent-keys"
SSH_AUTH_SOCK="$test_home/agent" ./ssh-add -D
if remaining=$(SSH_AUTH_SOCK="$test_home/agent" ./ssh-add -l 2>&1); then
    echo 'Agent retained a key after removal' >&2
    exit 1
else
    result=$?
    [ "$result" -eq 1 ]
    printf '%s\n' "$remaining" | grep -q 'The agent has no identities'
fi
kill -0 "$agent_pid"
echo 'Source OpenSSH client config, cipher query, key generation and private agent passed'
printf '{"_generated":{"notice":"AUTO-GENERATED. DO NOT EDIT MANUALLY.","generator":"openssh/client_test.sh"},"status":"passed","program_release":"%s","config_cipher_key_and_private_agent":"passed"}\n' "$expected_release" > "$receipt"
