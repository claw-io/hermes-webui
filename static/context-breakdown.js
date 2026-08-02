(function(){
  'use strict';
  let requestSeq=0;
  let fetchImpl=(...args)=>fetch(...args);
  let retry=null;
  const known=new Set(['system_prompt','tool_definitions','rules','skills','mcp','subagent_definitions','memory','conversation']);
  const node=id=>document.getElementById(id);
  const cleanTokens=value=>Number.isFinite(Number(value))&&Number(value)>=0?Math.floor(Number(value)):0;

  function render(payload,contextLength){
    const state=node('contextBreakdownState'),bar=node('contextBreakdownBar'),list=node('contextBreakdownList');
    if(!state||!bar||!list)return;
    state.textContent='';state.replaceChildren();bar.replaceChildren();list.replaceChildren();
    const status=payload&&payload.status;
    if(status!=='available'){
      const messages={loading:'Loading estimated categories…',busy:'Updates after this turn',unsupported:'Detailed breakdown is not supported by this Agent',unavailable:'Detailed breakdown becomes available after a compatible turn'};
      if(status==='error'){
        state.textContent='Detailed context unavailable. ';
        const button=document.createElement('button');button.textContent='Retry';button.type='button';button.onclick=()=>retry&&retry();state.append(button);
      }else state.textContent=messages[status]||messages.unavailable;
      return;
    }
    const maximum=cleanTokens(contextLength);
    for(const category of (Array.isArray(payload.categories)?payload.categories:[])){
      const tokens=cleanTokens(category.tokens);
      const id=typeof category.id==='string'?category.id:'unknown';
      const label=typeof category.label==='string'?category.label:id;
      const segment=document.createElement('span');
      segment.className=`context-breakdown-segment context-category-${known.has(id)?id:'unknown'}`;
      segment.style.width=`${maximum?Math.min(100,tokens/maximum*100):0}%`;
      bar.append(segment);
      const row=document.createElement('li'),name=document.createElement('span'),value=document.createElement('span');
      name.textContent=label;value.textContent=String(tokens);row.append(name,value);list.append(row);
    }
  }

  async function load(sessionId,getActiveId,contextLength){
    const seq=++requestSeq;
    render({status:'loading'},contextLength);
    retry=()=>load(sessionId,getActiveId,contextLength);
    try{
      const response=await fetchImpl(`/api/session/context-breakdown?session_id=${encodeURIComponent(sessionId)}`);
      if(!response.ok)throw new Error('request failed');
      const body=await response.json();
      if(seq!==requestSeq||getActiveId()!==sessionId)return false;
      render(body.breakdown,contextLength);return true;
    }catch(error){
      if(seq!==requestSeq||getActiveId()!==sessionId)return false;
      render({status:'error'},contextLength);return false;
    }
  }

  window.ContextBreakdown={render,load,setFetch(fn){fetchImpl=fn;},invalidate(){requestSeq++;}};
})();
