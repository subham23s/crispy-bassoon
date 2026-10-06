/* Optional build-only workaround for filesystems that reject copy_file_range.
 * Normal `npm run build` does not load this shim. Preserve COPYFILE_EXCL and
 * propagate permission/read/write failures instead of hiding failed copies.
 */
const fs = require('node:fs');
const promises = require('node:fs/promises');
const { pipeline } = require('node:stream/promises');
const original = promises.copyFile.bind(promises);

async function copyFile(source, destination, mode = 0) {
  try {
    await original(source, destination, mode);
  } catch (error) {
    if (!['EPERM', 'ENOSYS', 'EXDEV', 'ENOTSUP'].includes(error.code) || (mode & fs.constants.COPYFILE_FICLONE_FORCE)) throw error;
    const metadata = await promises.stat(source);
    await pipeline(fs.createReadStream(source), fs.createWriteStream(destination, {
      flags: mode & fs.constants.COPYFILE_EXCL ? 'wx' : 'w',
      mode: metadata.mode,
    }));
  }
}

promises.copyFile = copyFile;
fs.promises.copyFile = copyFile;
fs.copyFile = (source, destination, mode, callback) => {
  if (typeof mode === 'function') { callback = mode; mode = 0; }
  copyFile(source, destination, mode).then(() => callback(null), callback);
};
