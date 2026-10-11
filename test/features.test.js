import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,mkdir,writeFile,rm,symlink,readFile} from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {createServer} from '../src/server.js';
import {applyClaudeEvent} from '../src/protocol.js';
const token = 'feature-test-secret-123456789';
async function fixture(t) {
  const root = await mkdtemp(path.join(os.tmpdir(),'claude-features-'));
  const cwd = path.join(root,'project'); await mkdir(cwd);
  const app = await createServer({cwd,claudeHome:path.join(root,'claude'),dataDir:path.join(root,'data'),claudeBin:'claude',token});
  await new Promise(r=>app.server.listen(0,'127.0.0.1',r));
  const base = `http://127.0.0.1:${app.server.address().port}`;
  t.after(async()=>{await app.close();await rm(root,{recursive:true,force:true});});
  return {...app,root,cwd,base,request:(route,init={})=>fetch(base+route,{...init,headers:{Authorization:`Bearer ${token}`,...init.headers}})};
}
test('uploads round-trip Unicode files without overwriting and downloads are attachments', async t=>{
  const app = await fixture(t);
  assert.equal((await fetch(app.base+'/api/files')).status,401);
  const route='/api/files/upload?name='+encodeURIComponent('设计.png');
  const first=await app.request(route,{method:'POST',body:'image bytes'}); assert.equal(first.status,201);
  const file=await first.json(); assert.equal(await readFile(file.absolutePath,'utf8'),'image bytes');
  const second=await (await app.request(route,{method:'POST',body:'second'})).json(); assert.notEqual(file.path,second.path);
  const downloaded=await app.request('/api/files/download?path='+encodeURIComponent(file.path));
  assert.equal(await downloaded.text(),'image bytes'); assert.match(downloaded.headers.get('content-disposition'),/attachment/);
  assert.match(downloaded.headers.get('content-security-policy'),/sandbox/);
  const list=await (await app.request('/api/files?path=webdesk-uploads')).json(); assert.equal(list.entries.length,2);
});
test('file API blocks traversal, hidden secrets, symlinks, oversized and cross-site writes',async t=>{
  const app=await fixture(t);
  await writeFile(path.join(app.cwd,'.env'),'secret'); await writeFile(path.join(app.cwd,'private.key'),'secret');
  await symlink(app.root,path.join(app.cwd,'escape'));
  for(const value of ['../data','.env','private.key','escape/data','/etc/passwd']) {
    const response=await app.request('/api/files/download?path='+encodeURIComponent(value)); assert.ok([400,403].includes(response.status),value);
  }
  assert.equal((await app.request('/api/files/upload?name=..%2Fevil',{method:'POST',body:'x'})).status,400);
  assert.equal((await app.request('/api/files/upload?name=x',{method:'POST',headers:{Origin:'https://evil.example'},body:'x'})).status,403);
  assert.equal((await app.request('/api/files/upload?name=big',{method:'POST',body:Buffer.alloc(25*1024*1024+1)})).status,413);
  const listing=await (await app.request('/api/files')).json(); assert.deepEqual(listing.entries,[]);
  await symlink(app.root,path.join(app.cwd,'webdesk-uploads'));
  assert.equal((await app.request('/api/files/upload?name=x',{method:'POST',body:'x'})).status,403);
});
test('budget and fork validation rejects invalid values before invoking Claude',async t=>{
  const app=await fixture(t);
  for(const input of [{maxBudgetUsd:0},{maxBudgetUsd:-1},{maxBudgetUsd:'2'},{maxBudgetUsd:Infinity},{maxBudgetUsd:1001},{forkSession:true},{forkSession:'yes'},{permissionMode:'bypassPermissions'}])
    await assert.rejects(app.tasks.validate({prompt:'test',...input}),e=>e.status===400);
});
test('streamed text is not doubled; tool/subagent output is excluded; errors and usage survive',()=>{
  const item={output:''};
  const events=[
    {type:'system',session_id:'session'},
    {type:'stream_event',event:{type:'message_start'}},
    {type:'stream_event',event:{type:'content_block_delta',delta:{type:'thinking_delta',thinking:'private reasoning'}}},
    {type:'stream_event',event:{type:'content_block_delta',delta:{type:'text_delta',text:'Hello 世界'}}},
    {type:'assistant',message:{content:[{type:'text',text:'Hello 世界'}]}},
    {type:'assistant',parent_tool_use_id:'subagent',message:{content:[{type:'text',text:'nested'}]}},
    {type:'assistant',message:{content:[{type:'text',text:'Second turn'}]}},
    {type:'result',is_error:true,subtype:'error_max_budget_usd',total_cost_usd:0.5,usage:{input_tokens:123},permission_denials:[{tool_name:'Bash'}]}
  ];
  for(const e of events) applyClaudeEvent(item,e);
  assert.equal(item.output,'Hello 世界\n\nSecond turn\n\n');
  assert.equal(item.costUsd,0.5);assert.equal(item.usage.input_tokens,123);assert.equal(item.error,'error_max_budget_usd');assert.equal(item.permissionDenials[0].tool_name,'Bash');
});
test('result-only output is retained and long text has a bounded size',()=>{
  const item={output:''};applyClaudeEvent(item,{type:'result',result:'answer',is_error:false});assert.equal(item.output,'answer');
  applyClaudeEvent(item,{type:'assistant',message:{content:[{type:'text',text:'x'.repeat(2_000_001)}]}});
  assert.equal(item.output.length,2_000_000);assert.equal(item.truncated,true);
});
