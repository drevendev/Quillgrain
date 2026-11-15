"""Stdlib-only verification of bundled rules-only contexts, also shipped unchanged."""
import argparse
import hashlib
import json
import sys
from pathlib import Path, PurePosixPath
import importlib.util


if __package__:
    from . import portable as runtime
else:
    # -I -S deliberately excludes the script directory from sys.path. Load only
    # this bundled sibling, never an ambient module or an engine checkout.
    spec = importlib.util.spec_from_file_location('qg_bundled_runtime',
        Path(__file__).resolve().with_name('portable_runtime.py'))
    runtime = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runtime)

canonical, digest = runtime.canonical, runtime.digest


def read_json(path):
    try:
        return runtime.strict_json(Path(path).read_text(encoding='utf-8-sig'))
    except runtime.QGError as exc:
        raise ValueError(exc.code) from exc


def verify(context, host, lock):
    try:
        runtime.verify_host(context, host, lock)
    except runtime.QGError as exc:
        raise ValueError(exc.code) from exc
    permissions = context['permissions']
    if context['model_host'] != host or permissions['approved_model_hosts'] != [host]:
        raise ValueError('CONTEXT_HOST_MISMATCH')
    if not permissions['retrieval'] or permissions['public_redistribution']:
        raise ValueError('CONTEXT_PERMISSION_MISMATCH')
    if context.get('example_mode') != 'none' or context['examples_selected'] or context.get('corpus_materials'):
        raise ValueError('RULES_ONLY_REQUIRED')
    return context


def bounded(root, name):
    relative = PurePosixPath(name)
    if relative.is_absolute() or '..' in relative.parts or '\\' in name or ':' in name:
        raise ValueError('PATH_ESCAPE')
    path = (root / str(relative)).resolve(strict=True)
    if not path.is_relative_to(root.resolve()) or path == root.resolve():
        raise ValueError('PATH_ESCAPE')
    return path


def profile(root, host):
    manifest = read_json(Path(root) / 'references/profile.json')
    if manifest['schema_version'] != 'quillgrain.skill-profile/v2' or manifest['visibility'] != 'private':
        raise ValueError('PROFILE_MISMATCH')
    if not isinstance(manifest['modes'], dict) or not manifest['modes']:
        raise ValueError('PROFILE_MODES_REQUIRED')
    if manifest['model_host'] != host:
        raise ValueError('CONTEXT_HOST_MISMATCH')
    return manifest


def load_mode(root, register, host):
    root = Path(root)
    manifest = profile(root, host)
    mode = manifest['modes'][register]
    directory = bounded(root, mode['path'])
    for filename in ('context.json', 'quillgrain.lock.json', 'VOICE_CONTEXT.md'):
        path = bounded(root, mode['path'] + '/' + filename)
        if path.parent != directory:
            raise ValueError('PATH_ESCAPE')
        if hashlib.sha256(path.read_bytes()).hexdigest() != mode['files'][filename]:
            raise ValueError('PROFILE_FILE_DIGEST_MISMATCH')
    context = verify(read_json(directory / 'context.json'), host,
                     read_json(directory / 'quillgrain.lock.json'))
    if context['build_id'] != mode['build_id']:
        raise ValueError('PROFILE_BUILD_MISMATCH')
    if (context['language'] != manifest['language'] or context['register'] != register
            or context['visibility'] != manifest['visibility']):
        raise ValueError('CONTEXT_MODE_MISMATCH')
    return context


def main(argv=None):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    p = argparse.ArgumentParser(description='Verify a rules-only profile without the engine.')
    p.add_argument('--host', required=True)
    choice = p.add_mutually_exclusive_group(required=True)
    choice.add_argument('--register')
    choice.add_argument('--verify-all', action='store_true')
    p.add_argument('--show', action='store_true')
    args = p.parse_args(argv)
    if args.show and not args.register:
        p.error('--show requires --register')
    root = Path(__file__).resolve().parents[1]
    try:
        manifest = profile(root, args.host)
        registers = manifest['modes'] if args.verify_all else [args.register]
        contexts = [load_mode(root, r, args.host) for r in registers]
        if args.show:
            print(contexts[0]['prompt_payload'])
        else:
            print(json.dumps({'status': 'VERIFIED', 'host': args.host,
                              'registers': [c['register'] for c in contexts]}))
        return 0
    except (OSError, KeyError, TypeError, ValueError):
        print('PROFILE_CONTEXT_VERIFICATION_FAILED')
        return 3


if __name__ == '__main__':
    raise SystemExit(main())
