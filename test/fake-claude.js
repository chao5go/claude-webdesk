#!/usr/bin/env node
import { spawn } from "node:child_process";
let prompt = "";
for await (const chunk of process.stdin) prompt += chunk;
if (prompt.includes("slow")) {
  const child = spawn(process.execPath, ["-e", "setInterval(()=>{},1000)"], {
    stdio: "ignore",
  });
  console.log(JSON.stringify({ type: "test.child", pid: child.pid }));
  process.on("SIGINT", () => process.exit(130));
  process.on("SIGTERM", () => process.exit(143));
  setInterval(() => console.error("working"), 100);
} else if (prompt.includes("fail")) {
  console.error("fixture failed");
  process.exitCode = 1;
} else {
  const send = data => console.log(JSON.stringify(data));
  send({type:'system',subtype:'init',session_id:'11111111-1111-4111-8111-111111111111'});
  const text = '## 完成\n\n```js\nconst answer = 42;\n```';
  send({type:'stream_event',event:{type:'message_start'}});
  send({type:'stream_event',event:{type:'content_block_delta',delta:{type:'text_delta',text}}});
  send({type:'assistant',message:{content:[{type:'text',text}]}});
  send({type:'result',is_error:false,total_cost_usd:0.0123,usage:{input_tokens:120,output_tokens:42,cache_read_input_tokens:80},num_turns:1});
  console.error("\u001b[32mfixture done\u001b[0m");
  console.log(
    JSON.stringify({
      type: "test.args",
      args: process.argv.slice(2),
      prompt,
      serverToken: process.env.CLAUDE_REMOTE_WEB_TOKEN || process.env.CLAUDE_WEBDESK_TOKEN || null,
    }),
  );
}
