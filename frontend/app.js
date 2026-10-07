// Docshift frontend: plain JavaScript, talks to the FastAPI backend under /api.
const $ = s => document.querySelector(s);
const kb = n => n > 1048576 ? (n / 1048576).toFixed(2) + ' MB' : Math.max(1, Math.round(n / 1024)) + ' KB';
const esc = t => String(t).replace(/[&<>]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));
const sel = (label, id, opts) => `<label>${label} <select id="${id}">${opts.map(o => `<option value="${o[0]}">${o[1]}</option>`).join('')}</select></label>`;

let limits = { max_files: 5, max_merge_files: 20, max_file_mb: 25 };
let TOOLS = [], cur, files = [], busy = false;

function defineTools() {
  const n = limits.max_files;
  TOOLS = [
    { id: 'img', t: 'JPEG to PDF', s: 'images into PDF', api: 'images-to-pdf', max: n, accept: 'image/*', go: 'Create PDF',
      d: `Turn up to ${n} images into a PDF. Use the arrows to set page order.`,
      opts: sel('Output', 'mode', [['one', 'One combined PDF'], ['separate', 'One PDF per image']]) + sel('Page size', 'size', [['a4', 'A4 with margin'], ['fit', 'Match image size']]) },
    { id: 'p2w', t: 'PDF to Word', s: 'editable .docx', api: 'pdf-to-word', max: n, accept: '.pdf,application/pdf', go: 'Convert to Word',
      d: `Convert up to ${n} PDFs into editable Word documents. Scanned PDFs are not supported.`, opts: '' },
    { id: 'w2p', t: 'Word to PDF', s: '.docx into PDF', api: 'word-to-pdf', max: n, accept: '.docx', go: 'Convert to PDF',
      d: `Turn up to ${n} .docx files into PDFs. Older .doc files are not supported.`, opts: '' },
    { id: 'cmp', t: 'Compress PDF', s: 'smaller file size', api: 'compress', max: n, accept: '.pdf,application/pdf', go: 'Compress PDFs',
      d: `Shrink up to ${n} PDFs. Text stays selectable.`,
      opts: sel('Quality', 'level', [['balanced', 'Balanced'], ['high', 'High quality'], ['small', 'Smallest file']]) },
    { id: 'mrg', t: 'Merge PDFs', s: `up to ${limits.max_merge_files} into one`, api: 'merge', max: limits.max_merge_files, accept: '.pdf,application/pdf', go: 'Merge PDFs',
      d: `Join up to ${limits.max_merge_files} PDFs into one file, in the order shown. Use the arrows to reorder.`, opts: '' },
  ];
  cur = TOOLS[0];
}

function tabs() {
  $('#tabs').innerHTML = TOOLS.map(t => `<button class="tab" role="tab" aria-selected="${t === cur}" data-id="${t.id}"><b>${t.t}</b><span>${t.s}</span></button>`).join('');
  document.querySelectorAll('.tab').forEach(b => b.onclick = () => {
    if (busy) return;
    cur = TOOLS.find(t => t.id === b.dataset.id); files = []; tabs(); panel();
  });
}

function panel() {
  $('#panel').innerHTML = `<h2>${cur.t}</h2><p class="d">${cur.d}</p>
    <label class="drop" id="drop"><input type="file" id="inp" accept="${cur.accept}" multiple><strong>Choose files</strong> or drop them here (up to ${cur.max})</label>
    <div class="note" id="cnt"></div><ul class="files" id="list"></ul><div class="opts">${cur.opts}</div>
    <button class="btn" id="go" disabled>${cur.go}</button><div id="res"></div>
    <p class="hint">Each file can be up to ${limits.max_file_mb} MB.</p>`;
  const add = fs => {
    fs = [...fs]; const room = Math.max(cur.max - files.length, 0);
    files = files.concat(fs.slice(0, room)); list();
    $('#res').innerHTML = fs.length > room ? `<div class="res err">The limit is ${cur.max} files at once. ${fs.length - room} extra file(s) were not added.</div>` : '';
  };
  $('#inp').onchange = e => { add(e.target.files); e.target.value = ''; };
  const d = $('#drop');
  d.ondragover = e => { e.preventDefault(); d.classList.add('over'); };
  d.ondragleave = () => d.classList.remove('over');
  d.ondrop = e => { e.preventDefault(); d.classList.remove('over'); add(e.dataTransfer.files); };
  $('#go').onclick = run; list();
}

function list() {
  $('#cnt').textContent = `${files.length} of ${cur.max} files added`;
  $('#list').innerHTML = files.map((f, i) => `<li><span class="n">${esc(f.name)}</span><span class="sz">${kb(f.size)}</span>${files.length > 1 ? `<button class="ib" data-up="${i}" aria-label="Move up">\u2191</button>` : ''}<button class="ib" data-rm="${i}" aria-label="Remove">\u00D7</button></li>`).join('');
  document.querySelectorAll('[data-rm]').forEach(b => b.onclick = () => { files.splice(+b.dataset.rm, 1); list(); });
  document.querySelectorAll('[data-up]').forEach(b => b.onclick = () => { const i = +b.dataset.up; if (i > 0) { [files[i - 1], files[i]] = [files[i], files[i - 1]]; list(); } });
  $('#go').disabled = !files.length || busy;
}

async function run() {
  const res = $('#res'), form = new FormData();
  files.forEach(f => form.append('files', f));
  document.querySelectorAll('.opts select').forEach(s => form.append(s.id, s.value));
  busy = true; $('#go').disabled = true;
  res.innerHTML = '<div class="res">Working... large files can take a minute.</div>';
  try {
    const r = await fetch(`/api/${cur.api}`, { method: 'POST', body: form });
    if (!r.ok) {
      let msg = 'Something went wrong. Please try again.';
      try { msg = (await r.json()).detail || msg; } catch (_) {}
      throw new Error(msg);
    }
    const blob = await r.blob();
    const name = decodeURIComponent(r.headers.get('X-Filename') || 'result');
    const note = decodeURIComponent(r.headers.get('X-Note') || '');
    const url = URL.createObjectURL(blob);
    res.innerHTML = `<div class="res"><div class="ok">Done: ${esc(name)} (${kb(blob.size)})</div>${note ? `<div class="note">${esc(note)}</div>` : ''}<a class="btn" style="display:inline-block;text-decoration:none" href="${url}" download="${esc(name)}">Save file</a></div>`;
  } catch (e) {
    res.innerHTML = `<div class="res err">${esc(e.message)}</div>`;
  }
  busy = false; $('#go').disabled = !files.length;
}

(async function init() {
  try { limits = await (await fetch('/api/limits')).json(); } catch (_) { /* use defaults */ }
  defineTools(); tabs(); panel();
})();
