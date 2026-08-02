import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run_node(body):
    script = f"""
const fs=require('fs'), vm=require('vm');
class Node {{
  constructor(id){{this.id=id;this.textContent='';this.innerHTML='';this.style={{}};this.dataset={{}};}}
  replaceChildren(...children){{this.children=children;}}
  append(...children){{this.children=(this.children||[]).concat(children);}}
  setAttribute(name,value){{this[name]=value;}}
}}
const nodes={{contextBreakdownState:new Node('state'),contextBreakdownBar:new Node('bar'),contextBreakdownList:new Node('list')}};
const document={{getElementById:(id)=>nodes[id]||null,createElement:(tag)=>new Node(tag)}};
const window={{}};
const fetch=()=>Promise.reject(new Error('unset'));
vm.runInNewContext(fs.readFileSync({json.dumps(str(ROOT / 'static/context-breakdown.js'))},'utf8'),{{window,document,fetch,console,setTimeout,clearTimeout}});
{body}
"""
    return subprocess.run(["node", "-e", script], text=True, capture_output=True, check=True).stdout.strip()


def test_render_scales_category_segments_to_context_window_and_matches_legend_swatches():
    output = _run_node("""
window.ContextBreakdown.render({status:'available',categories:[
 {id:'rules',label:'Rules',tokens:20},
 {id:'future',label:'<Future>',tokens:30}
],estimated_total:50},100);
console.log(JSON.stringify({
 widths:nodes.contextBreakdownBar.children.map(x=>x.style.width),
 segments:nodes.contextBreakdownBar.children.map(x=>x.className),
 labels:nodes.contextBreakdownList.children.map(x=>x.children[0].children[1].textContent),
 swatches:nodes.contextBreakdownList.children.map(x=>x.children[0].children[0].className),
 values:nodes.contextBreakdownList.children.map(x=>x.children[1].textContent)
}));
""")
    got = json.loads(output)
    assert got == {
        "widths": ["20%", "30%"],
        "segments": [
            "context-breakdown-segment context-category-rules",
            "context-breakdown-segment context-category-unknown",
        ],
        "labels": ["Rules", "<Future>"],
        "swatches": [
            "context-breakdown-swatch context-category-rules",
            "context-breakdown-swatch context-category-unknown",
        ],
        "values": ["20", "30"],
    }


def test_render_uses_payload_context_max_when_live_meter_length_is_missing():
    output = _run_node("""
window.ContextBreakdown.render({status:'available',context_max:100,categories:[
 {id:'rules',label:'Rules',tokens:20},
 {id:'conversation',label:'Conversation',tokens:30}
]},0);
console.log(JSON.stringify(nodes.contextBreakdownBar.children.map(x=>x.style.width)));
""")
    assert json.loads(output) == ["20%", "30%"]


def test_render_clamps_overfilled_context_segments_without_normalizing():
    output = _run_node("""
window.ContextBreakdown.render({status:'available',categories:[
 {id:'rules',label:'Rules',tokens:80},
 {id:'conversation',label:'Conversation',tokens:80}
]},100);
console.log(JSON.stringify(nodes.contextBreakdownBar.children.map(x=>x.style.width)));
""")
    assert json.loads(output) == ["80%", "20%"]


def test_render_formats_category_tokens_like_context_meter():
    output = _run_node("""
window.ContextBreakdown.render({status:'available',categories:[
 {id:'tool_definitions',label:'Tools',tokens:11557},
 {id:'rules',label:'Rules',tokens:10500},
 {id:'conversation',label:'Conversation',tokens:9999},
 {id:'memory',label:'Memory',tokens:1000000}
]},2000000);
console.log(JSON.stringify(nodes.contextBreakdownList.children.map(x=>x.children[1].textContent)));
""")
    assert json.loads(output) == ["11.6k", "10.5k", "10.0k", "1.0M"]


def test_breakdown_copy_explains_agent_owned_estimate():
    source = (ROOT / "static/index.html").read_text()
    assert "Context composition" in source
    assert "Categories are Hermes Agent estimates from serialized request content (~4 characters/token); the total above comes from the context meter." in source
    assert 'aria-label="Estimated context composition by category"' in source


def test_composition_bar_and_legend_are_visually_identifiable():
    source = (ROOT / "static/style.css").read_text()
    assert ".context-breakdown-bar{display:flex;width:100%;height:12px" in source
    assert ".context-breakdown-segment{display:block;height:100%;min-width:0" in source
    assert ".context-breakdown-swatch{display:inline-block;width:8px;height:8px" in source
    assert ".context-breakdown-label{display:flex;align-items:center" in source


def test_loader_discards_stale_session_and_request_responses():
    output = _run_node("""
let resolvers=[];
window.ContextBreakdown.setFetch(()=>new Promise(resolve=>resolvers.push(resolve)));
let active='a';
const first=window.ContextBreakdown.load('a',()=>active,100);
active='b';
const second=window.ContextBreakdown.load('b',()=>active,100);
resolvers[1]({ok:true,json:async()=>({breakdown:{status:'available',categories:[{id:'rules',label:'B',tokens:2}]}})});
setTimeout(()=>resolvers[0]({ok:true,json:async()=>({breakdown:{status:'available',categories:[{id:'rules',label:'A',tokens:1}]}})}),0);
Promise.all([first,second]).then(()=>console.log(nodes.contextBreakdownList.children[0].children[0].children[1].textContent));
""")
    assert output == "B"


def test_context_menu_loads_active_session_not_stream_id():
    source = (ROOT / "static/ui.js").read_text()
    snippet = source[source.index("function openComposerContextMenu"):source.index("window.openComposerContextMenu")]
    assert "S.session&&S.session.session_id" in snippet
    assert "S.activeId" not in snippet


def test_busy_and_error_states_offer_honest_feedback_and_retry():
    output = _run_node("""
window.ContextBreakdown.render({status:'busy',reason:'turn_in_progress'},100);
const busy=nodes.contextBreakdownState.textContent;
window.ContextBreakdown.render({status:'error'},100);
console.log(JSON.stringify({busy,error:nodes.contextBreakdownState.textContent,retry:nodes.contextBreakdownState.children[0].textContent}));
""")
    assert json.loads(output) == {
        "busy": "Updates after this turn",
        "error": "Detailed context unavailable. ",
        "retry": "Retry",
    }
