import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
export async function seedDemo(root) {
  const cwd = path.join(root, 'project');
  const folder = path.join(root, 'claude/projects/demo');
  await mkdir(folder, {recursive:true});
  await mkdir(cwd, {recursive:true});
  await writeFile(path.join(cwd, 'README.md'), '# Example workspace\n\nThis is an isolated demo. Upload a screenshot or try a task. No model is called.\n');
  const id = '11111111-1111-4111-8111-111111111111';
  await writeFile(path.join(folder, `${id}.jsonl`), [
    {type:'custom-title', customTitle:'Review the checkout flow'},
    {type:'user', cwd, timestamp:new Date().toISOString(), message:{content:'Review the checkout flow and suggest focused tests.'}},
    {type:'assistant', cwd, timestamp:new Date().toISOString(), message:{model:'demo', content:[{type:'text',text:'The checkout should reject duplicate submissions and preserve the cart if payment fails. Add tests for both transitions.'}]}}
  ].map(r=>JSON.stringify(r)).join('\n'));
}
