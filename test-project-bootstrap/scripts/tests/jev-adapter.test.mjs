import test from 'node:test';
import assert from 'node:assert/strict';
const adapter=await import(new URL('../../assets/typescript-runtime/framework/jev-adapter.ts',import.meta.url));
const config={endpoint:'https://api.typesafe.ai/v1/systemone',apiKey:'mock-only',model:'jev-1.13.0',modelVersion:'1.13.0',budgetCapUsd:0.02,maxCostPerCallUsd:0.01,maxCalls:2,maxInputChars:4096,timeoutMs:5000};
const request={kind:'api_semantic_judgment',evaluationGoal:'Classify the evidence',responseExcerpt:'Synthetic response',options:['valid','invalid']};
function mock(answer={type:'choice',choice:'valid',probabilities:{valid:0.9,invalid:0.1},confidence:0.8},usage={input_tokens:10,output_tokens:2,cost:0.001}) {
  globalThis.fetch=async()=>new Response(JSON.stringify({model:config.model,answers:{judgment:answer},usage}));
}
test('reject arbitrary endpoint before fetch',async()=>{
  let called=false; globalThis.fetch=async()=>{called=true;throw Error('forbidden');};
  await assert.rejects(adapter.evaluateApiSemantics(request,{...config,endpoint:'https://example.com'},new adapter.JevBudget()),/official pinned/);
  assert.equal(called,false);
});
test('missing confidence does not become certainty',async()=>{
  mock({type:'choice',choice:'valid',probabilities:{valid:0.9,invalid:0.1}});
  await assert.rejects(adapter.evaluateApiSemantics(request,config,new adapter.JevBudget()),/Finite non-negative/);
});
test('keep worst-case reservation across failed calls',async()=>{
  globalThis.fetch=async()=>{throw Error('mock timeout');}; const budget=new adapter.JevBudget();
  await assert.rejects(adapter.evaluateApiSemantics(request,config,budget),/reservation retained/);
  await assert.rejects(adapter.evaluateApiSemantics(request,config,budget),/reservation retained/);
  await assert.rejects(adapter.evaluateApiSemantics(request,config,budget),/budget exhausted/);
  assert.equal(budget.reservedCostUsd,0.02);
});
test('missing charge stays unknown and usage is retained',async()=>{
  mock(undefined,{input_tokens:10,output_tokens:2});
  const result=await adapter.evaluateApiSemantics(request,config,new adapter.JevBudget());
  assert.equal(result.usage.costUsd,null); assert.equal(result.confidence,0.8);
});
test('unknown labels and malformed distributions are rejected',async()=>{
  mock({type:'choice',choice:'other',probabilities:{valid:0.9,invalid:0.1},confidence:0.8});
  await assert.rejects(adapter.evaluateApiSemantics(request,config,new adapter.JevBudget()),/Unknown Choice/);
});
test('UI selection requires fresh unchanged candidate',async()=>{
  const candidates=[{id:'valid',tag:'button',visible:true,enabled:true},{id:'invalid',tag:'button',visible:true,enabled:true}];
  const snapshot={snapshotId:'s1',pageUrl:'http://fixture/',capturedAt:new Date(Date.now()-1000).toISOString(),candidates};
  mock();
  await assert.rejects(adapter.selectUiCandidate({kind:'ui_candidate_selection',stepDescription:'Choose button',snapshot},config,new adapter.JevBudget(),async()=>snapshot),/fresh revalidation/);
  mock();
  const result=await adapter.selectUiCandidate({kind:'ui_candidate_selection',stepDescription:'Choose button',snapshot},config,new adapter.JevBudget(),async()=>({...snapshot,snapshotId:'s2',capturedAt:new Date().toISOString()}));
  assert.equal(result.selectedId,'valid');
});
test('expired and future UI snapshots are rejected before fetch',async()=>{
  let called=false;globalThis.fetch=async()=>{called=true;throw Error('forbidden');};
  for (const capturedAt of ['2000-01-01T00:00:00Z',new Date(Date.now()+60000).toISOString()]) {
    const snapshot={snapshotId:'old',pageUrl:'http://fixture/',capturedAt,candidates:[]};
    await assert.rejects(adapter.selectUiCandidate({kind:'ui_candidate_selection',stepDescription:'Choose',snapshot},config,new adapter.JevBudget(),async()=>snapshot),/expired or from the future/);
  }
  assert.equal(called,false);
});
