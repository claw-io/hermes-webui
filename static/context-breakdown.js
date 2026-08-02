(function(){
  'use strict';
  let requestSeq=0;
  let fetchImpl=(...args)=>fetch(...args);
  let retry=null;
  const known=new Set(['system_prompt','tool_definitions','rules','skills','mcp','subagent_definitions','memory','conversation']);
  const node=id=>document.getElementById(id);
  const cleanTokens=value=>Number.isFinite(Number(value))&&Number(value)>=0?Math.floor(Number(value)):0;
  const formatTokens=value=>{
    const tokens=cleanTokens(value);
    if(tokens>=1e6)return(tokens/1e6).toFixed(1)+'M';
    if(tokens>=1e3)return(tokens/1e3).toFixed(1)+'k';
    return String(tokens);
  };

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
    const categories=(Array.isArray(payload.categories)?payload.categories:[]).map(category=>({
      tokens:cleanTokens(category.tokens),
      id:typeof category.id==='string'?category.id:'unknown',
      label:typeof category.label==='string'?category.label:(typeof category.id==='string'?category.id:'unknown')
    })).filter(category=>category.tokens>0);
    const contextMaximum=cleanTokens(contextLength)||cleanTokens(payload.context_max);
    const compositionTotal=categories.reduce((total,category)=>total+category.tokens,0);
    const denominator=contextMaximum||compositionTotal;
    let remainingPercent=100;
    for(const category of categories){
      const {tokens,id,label}=category;
      const categoryClass=`context-category-${known.has(id)?id:'unknown'}`;
      const rawPercent=denominator?tokens/denominator*100:0;
      const percent=Math.max(0,Math.min(remainingPercent,rawPercent));
      remainingPercent-=percent;
      const segment=document.createElement('span');
      segment.className=`context-breakdown-segment ${categoryClass}`;
      segment.style.width=`${percent}%`;
      segment.title=`${label}: ${formatTokens(tokens)} tokens (${percent.toFixed(1)}%)`;
      bar.append(segment);
      const row=document.createElement('li'),labelWrap=document.createElement('span'),swatch=document.createElement('span'),name=document.createElement('span'),value=document.createElement('span');
      labelWrap.className='context-breakdown-label';
      swatch.className=`context-breakdown-swatch ${categoryClass}`;
      swatch.setAttribute&&swatch.setAttribute('aria-hidden','true');
      name.textContent=label;labelWrap.append(swatch,name);value.textContent=formatTokens(tokens);row.append(labelWrap,value);list.append(row);
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
