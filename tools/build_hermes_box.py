"""Build the sealed Hermes box from its pins (docs/HERMES_BOX.md).

Reads boxes/hermes/pin.json and refuses to build unless every pin holds:

- the Hermes source is the pinned commit with the pinned tree, licence file and uv.lock;
- boxes/hermes/requirements.lock is the reviewed file (its SHA-256);
- the base image is named by its pinned digest only.

The source comes from ``--source``, an existing checkout, or is fetched over Git at the
pinned commit into a temporary folder. It is exported with ``git archive`` from that exact
commit (never the working files), leaving out the folders the pin lists, into a temporary
build folder with ALFRED's Dockerfile, settings, runner and gate. Docker then builds it;
the image carries the SHA-256 of pin.json as a label (tools/hermes_fence.py checks it), and
the box echoes pin.json in its first frame, which alfred/hermes_box.py checks before every
task. Network is used only here, at build time: to fetch the source, the base
image and the locked wheels (each checked against its hash by pip).

    python3 tools/build_hermes_box.py                         # fetch the source, build
    python3 tools/build_hermes_box.py --source <checkout>     # use a checkout instead
    python3 tools/build_hermes_box.py --check-only --source <checkout>
    python3 tools/build_hermes_box.py --record <file>         # also write what was built

Exit status: 0 built (or checked), 1 a pin did not hold, 2 a tool failed. Standard library;
runs git and docker as programs.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
BOX = ROOT / 'boxes' / 'hermes'
PIN = BOX / 'pin.json'
LABEL = 'org.alfred.hermes-box.pin'
DEFAULT_REGISTRY = 'docker.io/library/python'
PROXY_VARIABLES = ('HTTPS_PROXY', 'HTTP_PROXY')


class PinBroken(Exception):
    pass


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pin_digest() -> str:
    return sha256(PIN)


def git(source: Path, *args) -> str:
    done = subprocess.run(['git', '-C', str(source), *args], capture_output=True, text=True, check=False)
    if done.returncode != 0:
        raise RuntimeError('git ' + args[0] + ' failed')
    return done.stdout.strip()


def fetch(pin: dict, into: Path) -> Path:
    into.mkdir(parents=True, exist_ok=True)
    git(into, 'init', '-q')
    git(into, 'remote', 'add', 'origin', pin['hermes']['url'])
    git(into, 'fetch', '-q', '--depth', '1', 'origin', pin['hermes']['commit'])
    git(into, 'checkout', '-q', 'FETCH_HEAD')
    return into


def check_source(pin: dict, source: Path) -> None:
    hermes = pin['hermes']
    commit = git(source, 'rev-parse', 'HEAD')
    if commit != hermes['commit']:
        raise PinBroken(f'source is at {commit[:12]}, the pin is {hermes["commit"][:12]}')
    tree = git(source, 'rev-parse', 'HEAD^{tree}')
    if tree != hermes['tree']:
        raise PinBroken('source tree differs from the pinned tree')
    for name, key in (('LICENSE', 'licence_sha256'), ('uv.lock', 'uv_lock_sha256')):
        blob = subprocess.run(['git', '-C', str(source), 'show', f'{commit}:{name}'], capture_output=True, check=False)
        if blob.returncode != 0 or hashlib.sha256(blob.stdout).hexdigest() != hermes[key]:
            raise PinBroken(f'{name} at the pinned commit is not the pinned file')


def check_box(pin: dict) -> None:
    lock = BOX / pin['requirements']['file']
    if sha256(lock) != pin['requirements']['sha256']:
        raise PinBroken('requirements.lock is not the reviewed file')
    digest = pin['base_image']['digest']
    dockerfile = (BOX / 'Dockerfile').read_text(encoding='utf-8')
    if f'@{digest}' not in dockerfile:
        raise PinBroken('the Dockerfile does not name the pinned base image digest')


def export(pin: dict, source: Path, context: Path) -> None:
    """Copy ALFRED's box files and the pinned commit's tree (not the working files)."""
    for name in ('Dockerfile', 'config.yaml', 'pin.json', pin['requirements']['file']):
        shutil.copyfile(BOX / name, context / name)
    shutil.copytree(BOX / 'runner', context / 'runner',
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    archive = context / 'hermes.tar'
    with archive.open('wb') as out:
        done = subprocess.run(['git', '-C', str(source), 'archive', '--format=tar', pin['hermes']['commit']],
                              stdout=out, check=False)
    if done.returncode != 0:
        raise RuntimeError('git archive failed')
    left_out = tuple(pin['hermes']['left_out'])
    target = context / 'hermes'
    target.mkdir()
    with tarfile.open(archive) as tar:
        members = [m for m in tar.getmembers() if m.name.split('/', 1)[0] not in left_out]
        tar.extractall(target, members=members, filter='data')
    archive.unlink()


def build(pin: dict, context: Path, *, registry: str, tag: str, network: str | None) -> str:
    base = f'{registry}@{pin["base_image"]["digest"]}'
    command = ['docker', 'build', '--quiet', '--build-arg', f'BASE={base}',
               '--label', f'{LABEL}={pin_digest()}', '--tag', tag]
    if network:
        command += ['--network', network]
    for name in PROXY_VARIABLES:  # Docker's predefined build arguments; never kept in the image.
        if os.environ.get(name):
            command += ['--build-arg', name]
    done = subprocess.run(command + [str(context)], capture_output=True, text=True, check=False)
    if done.returncode != 0:
        sys.stderr.write(done.stderr[-4000:])
        raise RuntimeError('docker build failed')
    image = subprocess.run(['docker', 'image', 'inspect', '--format', '{{.Id}}', tag],
                           capture_output=True, text=True, check=False).stdout.strip()
    if not image.startswith('sha256:'):
        raise RuntimeError('docker did not report the image')
    return image


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--source', type=Path, help='an existing Hermes checkout at the pinned commit')
    parser.add_argument('--check-only', action='store_true', help='check the pins, build nothing')
    parser.add_argument('--registry', default=DEFAULT_REGISTRY,
                        help='where to fetch the base image; its digest is always the pinned one')
    parser.add_argument('--network', help='docker build --network value, if the build needs one')
    parser.add_argument('--record', type=Path, help='write the built image id and pins as JSON here')
    args = parser.parse_args(argv)
    pin = json.loads(PIN.read_text(encoding='utf-8'))
    try:
        check_box(pin)
        with tempfile.TemporaryDirectory(prefix='alfred-hermes-box-') as scratch:
            source = args.source.resolve() if args.source else fetch(pin, Path(scratch) / 'source')
            check_source(pin, source)
            if args.check_only:
                print('pins hold')
                return 0
            context = Path(scratch) / 'context'
            context.mkdir()
            export(pin, source, context)
            tag = f'alfred/hermes-box:{pin["hermes"]["commit"][:12]}'
            image = build(pin, context, registry=args.registry, tag=tag, network=args.network)
    except PinBroken as broken:
        print(f'pin broken: {broken}', file=sys.stderr)
        return 1
    except (RuntimeError, OSError, KeyError) as failure:
        print(f'build failed: {failure}', file=sys.stderr)
        return 2
    record = {'image': image, 'tag': tag, 'pin_sha256': pin_digest(), 'hermes_commit': pin['hermes']['commit'],
              'base_image_digest': pin['base_image']['digest']}
    if args.record:
        args.record.write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(record))
    return 0


if __name__ == '__main__':
    sys.exit(main())
