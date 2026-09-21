const grid=document.querySelector('#product-grid');
const empty=document.querySelector('#empty-state');
const search=document.querySelector('#search');
const chips=document.querySelector('#category-chips');
const dialog=document.querySelector('#product-dialog');
let products=window.PRODUCTS||[];
let selectedCategory='';
let lastProductsJson=JSON.stringify(products);
const esc=value=>String(value??'').replace(/[&<>'"]/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[ch]));

// Product artwork: the model writes categories freely, so pick an icon by
// keyword across category, tags, and name, and fall back to a generic crate.
const ICONS={
  gauge:'<path d="M4 18a8 8 0 1 1 16 0"/><path d="M12 18l4.6-5.2"/><circle cx="12" cy="18" r="1.5"/>',
  climate:'<path d="M10 14.9V5.2a2 2 0 1 1 4 0v9.7a4 4 0 1 1-4 0z"/><path d="M12 9.2v5.9"/>',
  network:'<circle cx="12" cy="5" r="2.2"/><circle cx="5" cy="19" r="2.2"/><circle cx="19" cy="19" r="2.2"/><path d="M12 7.2v3.6M11 11.6 6.6 17M13 11.6 17.4 17"/>',
  chip:'<rect x="7" y="7" width="10" height="10" rx="1.6"/><rect x="10.2" y="10.2" width="3.6" height="3.6" rx=".6"/><path d="M10 4.2V7M14 4.2V7M10 17v2.8M14 17v2.8M4.2 10H7M4.2 14H7M17 10h2.8M17 14h2.8"/>',
  rack:'<rect x="3" y="4.5" width="18" height="6.5" rx="1.6"/><rect x="3" y="13" width="18" height="6.5" rx="1.6"/><path d="M6.8 7.75h.02M6.8 16.25h.02"/>',
  power:'<path d="M13.2 3 5.5 13.6h5.4L10.8 21l7.7-10.6h-5.4z"/>',
  motor:'<circle cx="12" cy="12" r="4"/><path d="M12 3.2V7M12 17v3.8M3.2 12H7M17 12h3.8M6 6l2.5 2.5M15.5 15.5 18 18M18 6l-2.5 2.5M8.5 15.5 6 18"/>',
  vision:'<rect x="3" y="7" width="12.5" height="10" rx="2.2"/><path d="m15.5 11 5.5-3.2v8.4L15.5 13z"/>',
  safety:'<path d="M12 3.2l7.2 3v5.9c0 4.1-3.1 6.7-7.2 8.7-4.1-2-7.2-4.6-7.2-8.7V6.2z"/><path d="m9.2 12 2 2 3.6-3.8"/>',
  crate:'<path d="M12 3.2l8 4.4v8.8L12 20.8 4 16.4V7.6z"/><path d="M4 7.6 12 12l8-4.4M12 12v8.8"/>'
};
const ICON_RULES=[
  [/pressure|psi|\bbar\b|pneumat|hydraul|flow|valve/,'gauge'],
  [/environment|climate|temperatur|humid|air|particul|thermal|weather|gas/,'climate'],
  [/network|ethernet|switch|router|gateway|connectiv|wireless|modbus|opc/,'network'],
  [/controller|automation|plc|edge|compute|processor|logic|embedded/,'chip'],
  [/appliance|server|rack|storage|monitoring|observab|data|logging/,'rack'],
  [/power|energy|electric|supply|volt|battery|ups|drive/,'power'],
  [/motor|pump|actuator|mechanic|robot|convey|bearing/,'motor'],
  [/camera|vision|optic|imaging|scanner|inspect/,'vision'],
  [/safety|protect|secur|shield|guard|complian/,'safety']
];
function iconFor(product){
  // Match the strongest signal first: a controller described as being for
  // "manufacturing environments" is a controller, not an environment sensor.
  const fields=[product.category,(product.tags||[]).join(' '),product.name,product.short_description];
  for(const field of fields){
    const text=String(field||'').toLowerCase();
    if(!text)continue;
    const hit=ICON_RULES.find(([pattern])=>pattern.test(text));
    if(hit)return hit[1];
  }
  return 'crate';
}
function iconMarkup(kind){
  return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[kind]}</svg>`;
}

function card(product){
  const kind=iconFor(product);
  const tags=(product.tags||[]).slice(0,3).map(t=>`<span class="tag">${esc(t)}</span>`).join('');
  return `<article class="product-card" data-kind="${kind}">
    <div class="card-media">${iconMarkup(kind)}<span class="product-index">${esc(product.id)}</span></div>
    <div class="card-body">
      <span class="category">${esc(product.category)}</span>
      <h2>${esc(product.name)}</h2>
      <p class="maker">${esc(product.manufacturer)}</p>
      <p class="description">${esc(product.short_description)}</p>
      <div class="tags">${tags}</div>
      <button class="text-button" data-product-id="${esc(product.id)}">View details <span>→</span></button>
    </div>
  </article>`;
}

function refreshCategories(){
  const values=[...new Set(products.map(p=>p.category).filter(Boolean))].sort();
  if(selectedCategory&&!values.includes(selectedCategory))selectedCategory='';
  chips.innerHTML=[['','All products'],...values.map(v=>[v,v])]
    .map(([value,label])=>`<button class="chip${value===selectedCategory?' active':''}" role="tab" aria-selected="${value===selectedCategory}" data-category="${esc(value)}">${esc(label)}</button>`)
    .join('');
}
function render(){
  const term=search.value.trim().toLowerCase();
  const shown=products.filter(p=>(!selectedCategory||p.category===selectedCategory)&&(!term||[p.name,p.manufacturer,p.short_description,...(p.tags||[])].join(' ').toLowerCase().includes(term)));
  grid.innerHTML=shown.map(card).join('');
  empty.hidden=shown.length>0;
  document.querySelector('#result-count').textContent=`${shown.length} result${shown.length===1?'':'s'}`;
  document.querySelector('#product-count').textContent=`${products.length} product${products.length===1?'':'s'} published`;
}
function showProduct(id){
  const p=products.find(item=>item.id===id);
  if(!p)return;
  dialog.querySelector('#dialog-content').innerHTML=`<div class="dialog-body"><div class="dialog-head" data-kind="${iconFor(p)}"><div class="dialog-icon">${iconMarkup(iconFor(p))}</div><div><span class="category">${esc(p.category)}</span><h2>${esc(p.name)}</h2><p class="maker">${esc(p.manufacturer)}</p></div></div><p class="description">${esc(p.long_description)}</p><h3>Technical specifications</h3><div class="specs">${Object.entries(p.technical_specs||{}).map(([k,v])=>`<div><small>${esc(k)}</small><br><strong>${esc(v)}</strong></div>`).join('')}</div><a href="/products/${encodeURIComponent(p.id)}">Open complete product record →</a></div>`;
  dialog.showModal();
}
grid.addEventListener('click',e=>{const button=e.target.closest('[data-product-id]');if(button)showProduct(button.dataset.productId)});
chips.addEventListener('click',e=>{const chip=e.target.closest('[data-category]');if(!chip)return;selectedCategory=chip.dataset.category;refreshCategories();render()});
dialog.querySelector('.close').onclick=()=>dialog.close();
dialog.addEventListener('click',e=>{if(e.target===dialog)dialog.close()});
search.addEventListener('input',render);
async function poll(){try{const [productResponse,statusResponse]=await Promise.all([fetch('/api/products'),fetch('/api/status')]);if(productResponse.ok){const next=await productResponse.json();const snapshot=JSON.stringify(next);if(snapshot!==lastProductsJson){lastProductsJson=snapshot;products=next;refreshCategories();render()}}if(statusResponse.ok){const status=await statusResponse.json();document.querySelector('#status-copy').textContent=status.running?'Agent processing supplier feed…':'Supplier feed connected'}}catch(_){document.querySelector('#status-copy').textContent='Feed connection unavailable'}}
refreshCategories();render();setInterval(poll,2500);
