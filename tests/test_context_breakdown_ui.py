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
}}
const nodes={{contextBreakdownState:new Node('state'),contextBreakdownBar:new Node('bar'),contextBreakdownList:new Node('list')}};
const document={{getElementById:(id)=>nodes[id]||null,createElement:(tag)=>new Node(tag)}};
const window={{}};
const fetch=()=>Promise.reject(new Error('unset'));
vm.runInNewContext(fs.readFileSync({json.dumps(str(ROOT / 'static/context-breakdown.js'))},'utf8'),{{window,document,fetch,console,setTimeout,clearTimeout}});
{body}
"""
    return subprocess.run(["node", "-e", script], text=True, capture_output=True, check=True).stdout.strip()


def test_render_uses_context_length_denominator_and_safe_unknown_category():
    output = _run_node("""
window.ContextBreakdown.render({status:'available',categories:[
 {id:'rules',label:'Rules',tokens:20},
 {id:'future',label:'<Future>',tokens:30}
],estimated_total:50},100);
console.log(JSON.stringify({
 widths:nodes.contextBreakdownBar.children.map(x=>x.style.width),
 labels:nodes.contextBreakdownList.children.map(x=>x.children[0].textContent),
 values:nodes.contextBreakdownList.children.map(x=>x.children[1].textContent)
}));
""")
    got = json.loads(output)
    assert got == {"widths": ["20%", "30%"], "labels": ["Rules", "<Future>"], "values": ["20", "30"]}


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
Promise.all([first,second]).then(()=>console.log(nodes.contextBreakdownList.children[0].children[0].textContent));
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
