import os
import webbrowser
from threading import Timer
import pandas as pd
from flask import Flask, request, jsonify

app = Flask(__name__)
db_file = 'drone_tasks.csv'

ui_template = r"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Drone Gantt Studio</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/frappe-gantt/0.6.1/frappe-gantt.min.js"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/frappe-gantt/0.6.1/frappe-gantt.css">
    
    <style>
        .bar-default .bar { fill: #9ca3af !important; }
        .bar-default .bar-progress { fill: #6b7280 !important; }
        .active { background-color: #3b82f6 !important; color: white !important; border-color: #3b82f6 !important; }
        input:focus { outline: none; border-color: #3b82f6; ring: 2px; }
        /* Add a pointer cursor to indicate bars are clickable */
        .gantt .bar-wrapper { cursor: pointer; } 
    </style>
</head>
<body class="bg-gray-100 p-8 font-sans">
    <div class="max-w-6xl mx-auto bg-white p-6 rounded-lg shadow-lg">
        
        <div class="flex justify-between items-center mb-4 border-b pb-4">
            <div>
                <h1 class="text-3xl font-bold text-gray-800">Drone Gantt Studio</h1>
                <p class="text-sm text-gray-500 mt-1">Editing local file: <span class="font-bold text-blue-600" id="file-label">drone_tasks.csv</span></p>
            </div>
            <div class="flex gap-4">
                <div class="flex gap-2">
                    <button id="btn-day" onclick="set_view('Day')" class="active px-4 py-2 border rounded text-sm transition text-gray-700">Day</button>
                    <button id="btn-week" onclick="set_view('Week')" class="px-4 py-2 border rounded text-sm transition text-gray-700">Week</button>
                    <button id="btn-month" onclick="set_view('Month')" class="px-4 py-2 border rounded text-sm transition text-gray-700">Month</button>
                </div>
                <button onclick="push_local()" id="save-btn" class="bg-green-600 text-white px-6 py-2 rounded text-sm font-bold shadow hover:bg-green-700 transition">Save to CSV</button>
            </div>
        </div>

        <div class="mb-6 bg-gray-50 p-4 rounded-lg border border-gray-200 flex flex-wrap gap-3 items-end shadow-inner">
            <div class="flex-1 min-w-[180px]">
                <label class="block text-xs font-bold text-gray-600 uppercase mb-1">Task Name</label>
                <input id="t-name" type="text" placeholder="e.g. Test Flight" class="w-full border border-gray-300 rounded px-3 py-2 text-sm">
            </div>
            <div>
                <label class="block text-xs font-bold text-gray-600 uppercase mb-1">Start Date</label>
                <input id="t-start" type="date" class="w-full border border-gray-300 rounded px-3 py-2 text-sm">
            </div>
            <div>
                <label class="block text-xs font-bold text-gray-600 uppercase mb-1">End Date</label>
                <input id="t-end" type="date" class="w-full border border-gray-300 rounded px-3 py-2 text-sm">
            </div>
            <div class="w-28">
                <label class="block text-xs font-bold text-gray-600 uppercase mb-1">Assignee</label>
                <input id="t-assign" type="text" placeholder="e.g. GH, KD" class="w-full border border-gray-300 rounded px-3 py-2 text-sm">
            </div>
            
            <div class="flex gap-2 h-[38px]">
                <button id="btn-save-task" onclick="save_task()" class="bg-blue-600 text-white px-5 py-2 rounded text-sm font-bold shadow hover:bg-blue-700 transition">Add Task</button>
                <button id="btn-del" onclick="delete_task()" class="hidden bg-red-600 text-white px-4 py-2 rounded text-sm font-bold shadow hover:bg-red-700 transition">Delete</button>
                <button id="btn-cancel" onclick="reset_form()" class="hidden bg-gray-400 text-white px-4 py-2 rounded text-sm font-bold shadow hover:bg-gray-500 transition">Cancel</button>
            </div>
        </div>

        <div class="border rounded-lg overflow-hidden bg-white min-h-[400px]">
            <div id="chart-target"></div>
        </div>
    </div>

    <script>
        const $ = id => document.getElementById(id);

        const team_colors = {
            'KD': { r: 59,  g: 130, b: 246 }, 
            'SI': { r: 234, g: 179, b: 8 },   
            'GH': { r: 239, g: 68,  b: 68 },  
            'DS': { r: 0,   g: 0,   b: 0 },   
            'AL': { r: 255, g: 255, b: 255 }  
        };

        let items = [];
        let chart = null;
        let view_mode = 'Day';
        let edit_id = null; 

        const today = new Date().toISOString().split('T')[0];
        const tmrw = new Date(Date.now() + 86400000).toISOString().split('T')[0];
        $('t-start').value = today;
        $('t-end').value = tmrw;

        function save_task() {
            const name = $('t-name').value.trim();
            const start = $('t-start').value;
            const end = $('t-end').value;
            const assign = $('t-assign').value.trim();

            if (!name || !start || !end) return alert("Fill out Name, Start, and End dates.");

            if (edit_id) {
                let t = items.find(i => i.id === edit_id);
                if (t) {
                    t.name = name;
                    t.start = start;
                    t.end = end;
                    t.assignee = assign;
                    t.custom_class = blend_colors(assign);
                }
            } else {
                items.push({
                    id: 'Task_' + Date.now(),
                    name: name,
                    start: start,
                    end: end,
                    progress: 0,
                    assignee: assign,
                    custom_class: blend_colors(assign)
                });
            }

            reset_form();
            draw_chart();
        }

        function load_edit(t) {
            edit_id = t.id;
            $('t-name').value = t.name;
            $('t-start').value = t.start;
            $('t-end').value = t.end;
            $('t-assign').value = t.assignee;
            
            $('btn-save-task').textContent = "Update Task";
            $('btn-del').classList.remove('hidden');$('btn-cancel').classList.remove('hidden');
        }

        function delete_task() {
            if (!edit_id) return;
            items = items.filter(i => i.id !== edit_id);
            reset_form();
            draw_chart();
        }

        function reset_form() {
            edit_id = null;
            $('t-name').value = '';
            $('t-assign').value = '';$('t-start').value = today;
            $('t-end').value = tmrw;
            
            $('btn-save-task').textContent = "Add Task";
            $('btn-del').classList.add('hidden');$('btn-cancel').classList.add('hidden');
        }

        function blend_colors(assign_str) {
            if (!assign_str) return 'bar-default';

            let parts = String(assign_str).toUpperCase().match(/[A-Z]+/g) || [];
            let valid = parts.filter(p => team_colors[p]);
            if (!valid.length) return 'bar-default';

            let unique = [...new Set(valid)].sort();
            let [r, g, b] = [0, 0, 0];
            
            unique.forEach(i => {
                r += team_colors[i].r; 
                g += team_colors[i].g; 
                b += team_colors[i].b;
            });
            
            r = Math.round(r / unique.length);
            g = Math.round(g / unique.length);
            b = Math.round(b / unique.length);

            let cls = 'bar-' + unique.join('-');

            if (!$('style-' + cls)) {
                let s = document.createElement('style');
                s.id = 'style-' + cls;
                let css = `.${cls} .bar { fill: rgb(${r},${g},${b}) !important; }
                           .${cls} .bar-progress { fill: rgb(${Math.max(0,r-40)},${Math.max(0,g-40)},${Math.max(0,b-40)}) !important; }`;
                
                if (r > 240 && g > 240 && b > 240) css += `.${cls} .bar { stroke: #9ca3af !important; stroke-width: 1px !important; }`;
                
                s.innerHTML = css;
                document.head.appendChild(s);
            }
            return cls;
        }

        function format_date(raw) {
            if (!raw) return '';
            const d = new Date(raw);
            if (!isNaN(d.getTime())) return d.toISOString().split('T')[0];
            
            const p = String(raw).split(/[\/\-]/);
            if (p.length === 3) {
                let y = p[2].length === 2 ? "20" + p[2] : p[2];
                return `${y}-${p[0].padStart(2, '0')}-${p[1].padStart(2, '0')}`;
            }
            return '';
        }

        async function fetch_local() {
            try {
                const res = await fetch('/api/load');
                const data = await res.json();
                
                if (data.file) $('file-label').textContent = data.file;
                
                if (data.items && data.items.length) {
                    let parsed = data.items.map((t, i) => {
                        let s_raw = t['Start Date'] || t.Start || t.start || t.start_date || '';
                        let e_raw = t['End Date'] || t.End || t.end || t.end_date || '';
                        
                        return {
                            id: String(t.ID || t.id || 'Task_' + i),
                            name: String(t['Task Name'] || t.Name || t.name || t.Task || 'Unnamed'),
                            start: format_date(s_raw),
                            end: format_date(e_raw),
                            progress: parseInt(t.Progress || t.progress || t['% Complete'] || 0) || 0,
                            assignee: String(t.Assignee || t.assignee || t.Resource || ''),
                        };
                    });

                    items = parsed.filter(t => t.start && t.end).map(t => {
                        t.custom_class = blend_colors(t.assignee);
                        return t;
                    });
                }
                
                if (!items || !items.length) {
                    items = [{ id: 'Task_1', name: 'Initial setup', start: today, end: tmrw, progress: 0, assignee: 'KD', custom_class: blend_colors('KD') }];
                }
                
                draw_chart();
            } catch (err) {
                console.error("Load failed:", err);
            }
        }

        async function push_local() {
            const btn = $('save-btn');
            btn.textContent = "Saving...";
            
            const payload = items.map(t => ({
                "ID": t.id,
                "Task Name": t.name,
                "Start Date": t.start,
                "End Date": t.end,
                "Progress": t.progress,
                "Assignee": t.assignee
            }));

            try {
                const res = await fetch('/api/save', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });

                if (res.ok) {
                    btn.textContent = "Saved to CSV!";
                    btn.classList.replace('bg-green-600', 'bg-blue-600');
                    setTimeout(() => {
                        btn.textContent = "Save to CSV";
                        btn.classList.replace('bg-blue-600', 'bg-green-600');
                    }, 2000);
                } else throw new Error("Save rejected");
            } catch(e) {
                alert("Save error. Is the terminal script still running?");
                btn.textContent = "Save to CSV";
            }
        }

        function draw_chart() {
            $('chart-target').innerHTML = '';
            chart = new Gantt("#chart-target", items, {
                view_mode: view_mode,
                date_format: 'YYYY-MM-DD',
                on_click: t => load_edit(t),
                on_date_change: (t, s, e) => {
                    t.start = s.toISOString().split('T')[0];
                    t.end = e.toISOString().split('T')[0];
                },
                on_progress_change: (t, p) => t.progress = p
            });
        }

        function set_view(mode) {
            view_mode = mode;
            ['day', 'week', 'month'].forEach(m => {
                $(`btn-${m}`).classList.remove('active', 'bg-blue-600', 'text-white');
                $(`btn-${m}`).classList.add('text-gray-700');
            });
            let active = $(`btn-${mode.toLowerCase()}`);
            active.classList.add('active', 'bg-blue-600', 'text-white');
            active.classList.remove('text-gray-700');
            chart.change_view_mode(mode);
        }

        window.onload = fetch_local;
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return ui_template

@app.route('/api/load', methods=['GET'])
def fetch_csv():
    if os.path.exists(db_file):
        try:
            df = pd.read_csv(db_file).fillna('')
            return jsonify({"file": db_file, "items": df.to_dict(orient='records')})
        except Exception as e:
            print(f"CSV Read Error: {e}")
            return jsonify({"file": db_file, "items": []})
    return jsonify({"file": db_file, "items": []})

@app.route('/api/save', methods=['POST'])
def save_csv():
    df = pd.DataFrame(request.json)
    df.to_csv(db_file, index=False)
    return jsonify({"status": "success"})

def launch_ui():
    if not os.environ.get("WERKZEUG_RUN_MAIN"):
        webbrowser.open_new('http://127.0.0.1:5000/')

if __name__ == '__main__':
    Timer(1.5, launch_ui).start()
    app.run(port=5000, debug=False)