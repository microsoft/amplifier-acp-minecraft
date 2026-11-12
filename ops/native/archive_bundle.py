"""Archive only inventoried payload, retaining native links and executable bits."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import sys
import tarfile
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from native_package import validate


def archive(root,output):
    root,output=Path(root).resolve(),Path(output).resolve()
    if output.is_relative_to(root):raise ValueError('Archive destination must be outside the package')
    manifest=validate(root)
    if manifest.get('source_clean') is not True:raise ValueError('Cannot archive a dirty-source native package')
    manifest_bytes=(root/'manifest.json').read_bytes()
    with output.open('xb') as file,gzip.GzipFile(filename='',mode='wb',fileobj=file,mtime=0) as compressed,tarfile.open(fileobj=compressed,mode='w|') as tar:
        for name,entry in sorted({**manifest['files'],'manifest.json':{}}.items()):
            path=root/name;item=tarfile.TarInfo(name);item.mtime=0
            if 'link' in entry:
                item.type=tarfile.SYMTYPE;item.linkname=entry['link'];item.mode=0o777;tar.addfile(item)
            else:
                item.size=path.stat().st_size;item.mode=0o755 if path.stat().st_mode&0o111 else 0o644
                with path.open('rb') as content:tar.addfile(item,content)
    if validate(root)!=manifest or (root/'manifest.json').read_bytes()!=manifest_bytes:
        output.unlink();raise ValueError('Package changed while archiving')
    with output.open('rb') as content:digest=hashlib.file_digest(content,'sha256').hexdigest()
    result={'target':manifest['target'],'source_commit':manifest['source_commit'],
       'sha256':digest,'size':output.stat().st_size,'manifest_sha256':hashlib.sha256(manifest_bytes).hexdigest()}
    output.with_suffix(output.suffix+'.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--bundle',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();print(json.dumps(archive(args.bundle,args.output)))
