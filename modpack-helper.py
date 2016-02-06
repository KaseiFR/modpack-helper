#!/usr/bin/env python3

import sys
import os
import tempfile
import json
import logging
import shutil
import subprocess
import urllib.error
import fnmatch
from pathlib import Path
from zipfile import ZipFile
from argparse import ArgumentParser
from urllib.request import urlretrieve, urlopen, Request
from urllib.parse import urlparse, urlunparse
from concurrent.futures import ThreadPoolExecutor, as_completed

parser = ArgumentParser(description='Update a Minecraft modpack installation from Curse')
parser.add_argument('pack_path', metavar='MODPACK', help='the path of the zipped modpack or the url from which to download it')
parser.add_argument('-d', '--dest', help='the path of the minecraft installation', default='.')
parser.add_argument('-j', dest='threads', help='the maximum concurrent mod downloads', type=int, default=10)
parser.add_argument('-f', '--keep-forge', help='prevent Minecraft Forge from being updated', action='store_true', default=False)
parser.add_argument('-c', '--keep-config', help='prevent existing mod configuration files from being updated', action='store_true', default=False)
parser.add_argument('-s', '--forge-symlink', metavar='LINK', help='attempt to create a symlink LINK to the Forge jar file when updating', default='minecraft_server.jar')
parser.add_argument('-e', '--exclude', help='a file containing a glob pattern per line matching mod files not to be installed', type=open)
parser.add_argument('-v', '--verbose', help='enable debugging output', action='store_true')

#logger = logging.getLogger(__name__)
logger = logging

curseforge_mod_url = 'http://minecraft.curseforge.com/mc-mods/{projectID}'
curseforge_download_path = 'files/{fileID}/download'

forge_installer_url = 'http://files.minecraftforge.net/maven/net/minecraftforge/forge/{version}/forge-{version}-installer.jar'


def mod_url(mod_spec):
    page_url = curseforge_mod_url.format(**mod_spec)
    mod_page = urlopen(Request(page_url, method='HEAD'))

    url = clean_url(mod_page.url) + '/' + curseforge_download_path.format(**mod_spec)

    logger.debug('Mod mapping: {} => {}'.format(mod_spec, url))
    return url


def download(conn_or_url, dest_dir, filename=None):
    buf_size = 64*1024

    conn = urlopen(conn_or_url) if isinstance(conn_or_url, str) else conn_or_url

    if filename is None:
        filename = Path(conn.url).name  # We get the filename after the url redirections

    logger.info('Downloading {} ...'.format(filename))
    path = dest_dir / filename
    with open(str(path), "wb") as f:
        while True:
            data = conn.read(buf_size)
            if not data:
                break
            f.write(data)

    logger.debug('File {} downloaded'.format(filename))
    return path


def download_mod(mod_spec, dest, blacklist=None):
    logger.debug('Starting mod {}'.format(mod_spec))

    # We must follow the redirections to get the final filename
    conn = urlopen(mod_url(mod_spec))
    filename = Path(conn.url).name

    if blacklist and any(fnmatch.fnmatch(filename, p) for p in blacklist):
        logger.info('Excluding mod {}'.format(filename))
        return None
    else:
        return download(conn, dest, filename)


def clean_url(url):
    return urlunparse(urlparse(url)._replace(query='', params='', fragment=''))


def update_forge(mc_version, forge_version, tmp_dir, dest_dir):
    full_version = '{}-{}'.format(mc_version, forge_version)

    logger.info('Updating Forge to {} ...'.format(full_version))

    try:
        forge_installer = download(forge_installer_url.format(version=full_version), tmp_dir)
    except urllib.error.HTTPError as e:
        forge_installer = None
        if e.code != 404:
            raise

    # Bugfix for 1.7.10 Forge URLs
    if not forge_installer:
        full_version += '-' + mc_version
        forge_installer = download(forge_installer_url.format(version=full_version), tmp_dir)

    logger.info('Forge downloaded')

    subprocess.check_call(['java', '-jar', str(forge_installer), '--installServer'], cwd=str(dest_dir))

    forge = dest_dir / forge_installer.name.replace('installer','universal')
    if forge.exists() and args.forge_symlink:
        symlink = dest_dir / args.forge_symlink
        if symlink.exists():
            symlink.unlink()
        symlink.symlink_to(forge.name)  # Relative symlink
    logger.info('Forge update done')


def copytree(src, dst, override=True):
    if not os.path.exists(dst):
        os.makedirs(dst)
    for item in os.listdir(src):
        s = os.path.join(src, item)
        d = os.path.join(dst, item)
        if os.path.isdir(s):
            copytree(s, d)
        elif override or not os.path.exists(d):
            shutil.copy2(s, d)


def run(args, tmp_dir):
    tmp_dir = Path(tmp_dir)

    base_dir = Path(args.dest)
    if not base_dir.exists():
        base_dir.mkdir(parents=True)
    base_dir = base_dir.resolve()

    if Path(args.pack_path).exists():
        pack_path = args.pack_path
        logger.info('Found local modpack {}'.format(pack_path))
    else:
        pack_path = tmp_dir / 'modpack.zip'
        logger.info('Downloading the modpack to {} ...'.format(pack_path))
        pack_path, _ = urlretrieve(args.pack_path, str(pack_path))
        logger.info('  Done')

    modpack = ZipFile(pack_path)

    manifest = json.loads(modpack.open('manifest.json').read().decode('utf-8'))
    logger.info('Modpack: {name} (Version {version})'.format(**manifest))

    if args.exclude:
        mod_blacklist = list(line.rstrip() for line in args.exclude)
        logger.debug('Mod blacklist: {}'.format(mod_blacklist))
        args.exclude.close()
    else:
        mod_blacklist = None

    # Download the mod files
    mod_store = tmp_dir / 'mod_store'
    mod_store.mkdir()
    logger.info('Starting mod downloads, this may take a while')
    with ThreadPoolExecutor(args.threads) as executor:
        futures = []

        for mod in manifest['files']:
            futures.append(executor.submit(download_mod, mod, mod_store, blacklist=mod_blacklist))

        bonus = manifest.get('directDownload', [])
        for entry in bonus:
            url, filename = (entry.get(x) for x in ('url', 'filename'))
            if url is None or filename is None:
                logger.warning('Error while handling entry {}'.format(entry), file=sys.stderr)
                continue
            futures.append(executor.submit(download, url, mod_store, filename))

        # Re-raise the exceptions which might have happened
        for f in as_completed(futures):
            e = f.exception()
            if e:
                for g in futures: g.cancel()
            if isinstance(e, urllib.error.HTTPError):
                logger.error('Error while fetching {}'.format(e.url))
            f.result()
    logger.info('  Done')

    # Backup some config
    subdirs = {d: base_dir / d for d in ('mods', 'config')}
    backups = {k: d.with_suffix('.bak') for k, d in subdirs.items()}
    for k, d in subdirs.items():
        if d.exists():
            b = backups[k]
            if b.exists():
                shutil.rmtree(str(b))
            d.replace(b)
        d.mkdir()

    # Update Forge
    if not args.keep_forge:
        mc_spec = manifest.get('minecraft', {})
        mc_version = mc_spec.get('version')
        forge_ids = [x['id'].replace('forge-', '') for x in mc_spec.get('modLoaders', []) if x.get('id', '').startswith('forge-')]
        if mc_version and forge_ids:
            update_forge(mc_version, forge_ids[0], tmp_dir, base_dir)
        else:
            logger.warning('Could not extract Forge informations from the manifest')
            logger.debug('minecraft : {}\nmodLoaders : {}'.format(manifest.get('minecraft'), manifest.get('modLoaders')))

    # Install mod files
    logger.info('Installing mods...')
    copytree(str(mod_store), str(subdirs['mods']))

    # Apply ovverides
    logger.info('Applying custom config...')
    overrides = manifest.get('overrides')
    if overrides is not None:
        overrides = Path(overrides)
        todo = [entry for entry in modpack.namelist() if Path(entry) > overrides]
        modpack.extractall(str(tmp_dir), todo)
        copytree(str(tmp_dir / overrides), str(base_dir))

    if args.keep_config and backups['config'].exists():
        copytree(str(backups['config']), str(subdirs['config']))

    logger.info('Modpack {name} successfully installed'.format(**manifest))

if __name__ == '__main__':
    args = parser.parse_args()
    logging.basicConfig(format='%(message)s', level=(logging.DEBUG if args.verbose else logging.INFO))

    with tempfile.TemporaryDirectory() as tmp:
        run(args, tmp)
