/* Optional historical probes read verified ZIP snapshots; current UI never loads this helper. */
const fs=require('fs'),path=require('path'),{execFileSync}=require('child_process');
const root=path.resolve(__dirname,'..'),manifest=require('./20261022/cleanup_latest/archived_html.json');
module.exports=function readHtmlSnapshot(relative){
 const file=path.resolve(root,relative);if(!file.startsWith(root+path.sep))throw Error('Snapshot must remain inside the workspace');
 if(fs.existsSync(file))return fs.readFileSync(file,'utf8');
 const ref=manifest[relative];if(!ref)throw Error('Unknown historical HTML snapshot: '+relative);
 return execFileSync('python',['-c','import sys,zipfile;sys.stdout.buffer.write(zipfile.ZipFile(sys.argv[1]).read(sys.argv[2]))',path.join(root,ref.archive),ref.member],{encoding:'utf8',maxBuffer:32*1024*1024});
};
