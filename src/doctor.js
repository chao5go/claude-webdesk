import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
const exec = promisify(execFile);
export async function doctor(options) {
  console.log(`Node ${process.version}\nWorkspace: ${options.cwd}`);
  let failed = false;
  try {
    const {stdout} = await exec(options.claudeBin,['--version'],{timeout:10000});
    console.log('Claude: ' + stdout.trim());
    const help = (await exec(options.claudeBin,['--help'],{timeout:10000})).stdout;
    for(const flag of ['--output-format','--include-partial-messages','--permission-prompts','--max-budget-usd','--fork-session']) {
      if(!help.includes(flag)) {console.log('Missing CLI capability: '+flag);failed=true;}
    }
  } catch {console.log('Claude CLI unavailable. Install/sign in to Claude Code or set --claude-bin.');failed=true;}
  try {
    const python = options.pluginOptions?.['claude-history']?.pythonBin || process.env.CLAUDE_WEBDESK_PYTHON || 'python3';
    const {stdout} = await exec(python,['-c','import sys; assert sys.version_info >= (3,10); print(sys.version.split()[0])'],{timeout:3000});
    console.log('History plugin: Python '+stdout.trim());
  } catch {console.log('History plugin: Python 3.10+ unavailable (optional; task workbench still works).');}
  console.log('No model called. Authentication and model access must be checked in Claude CLI.');
  return failed ? 1 : 0;
}
