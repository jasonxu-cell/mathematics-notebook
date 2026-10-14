const { packager } = require('@electron/packager');
const path = require('node:path');
const { existsSync } = require('node:fs');

(async () => {
  const root = path.resolve(__dirname, '..');
  const kernel = path.join(root, 'build/kernel/mathematics-kernel');
  if (!existsSync(path.join(kernel, 'mathematics-kernel'))) throw new Error('先运行 .venv/bin/python scripts/build-kernel.py 构建计算内核。');
  const version = require('electron/package.json').version;
  // github.com 直连不稳定:@electron/get 的缓存键一旦对不上就会联网下载并超时。
  // 本地缓存里已有对应 zip 时直接喂给 packager,完全离线打包。
  const os = require('node:os');
  const cacheZip = path.join(os.homedir(), 'Library/Caches/electron');
  let electronZipDir;
  if (existsSync(cacheZip)) {
    for (const dir of require('node:fs').readdirSync(cacheZip)) {
      const candidate = path.join(cacheZip, dir, `electron-v${version}-darwin-arm64.zip`);
      if (existsSync(candidate)) { electronZipDir = path.dirname(candidate); break; }
    }
  }
  const applications = await packager({
    dir: root, name: 'Mathematics Notebook', platform: 'darwin', arch: 'arm64',
    out: path.join(root, 'dist'), overwrite: true, asar: true,
    appBundleId: 'local.mathematics.notebook', appVersion: require('../package.json').version,
    icon: path.join(root, 'assets', 'mathematics.icns'),
    electronVersion: version,
    ...(electronZipDir ? { electronZipDir } : {}),
    extraResource: [kernel],
    ignore: [/^\/\.venv(?:\/|$)/, /^\/build(?:\/|$)/, /^\/dist(?:\/|$)/, /^\/tests(?:\/|$)/, /^\/scripts(?:\/|$)/, /__pycache__/, /^\/backend(?:\/|$)/, /^\/\.state(?:\/|$)/],
    prune: true,
  });
  console.log(applications.join('\n'));
})().catch(error => { console.error(error); process.exitCode = 1; });
