const tg=window.Telegram?.WebApp;
if(tg){tg.ready();tg.expand();}

let groups=[],current=null,filter='all',stack=['home'];

fetch('/static/assets/about_hero_exact.b64?v=1',{cache:'no-store'})
.then(r=>r.text())
.then(s=>{
 const el=document.getElementById('aboutHeroImg');
 if(el)el.src='data:image/jpeg;base64,'+s.trim()
});

fetch('/api/groups',{cache:'no-store'})
.then(r=>r.json())
.then(x=>{
 groups=x;
 renderGroups()
});

function show(id){
 document.querySelectorAll('.screen').forEach(s=>s.classList.remove('active'));
 document.getElementById(id).classList.add('active');
 if(stack.at(-1)!==id)stack.push(id);
 document.getElementById('back').style.visibility=id==='home'?'hidden':'visible';
 document.querySelectorAll('.nav').forEach(n=>n.classList.toggle('active',n.dataset.id===id));
 scrollTo(0,0)
}

function goBack(){
 if(stack.length>1){
  stack.pop();
  const id=stack.pop();
  show(id)
 }
}

function setFilter(f,el){
 filter=f;
 document.querySelectorAll('.chip').forEach(x=>x.classList.remove('active'));
 el.classList.add('active');
 renderGroups()
}
function renderGroups(){
 const list=document.getElementById('groupList');
 const count=document.getElementById('count');
 if(!list)return;

 let q=(document.getElementById('search')?.value||'').toLowerCase();

 let arr=groups.filter(g=>{
  let text=JSON.stringify(g).toLowerCase();
  if(q && !text.includes(q))return false;

  if(filter==='young' && !g.young)return false;
  if(filter==='noPets' && g.pets)return false;
  if(filter==='ust' && !text.includes('уст'))return false;
  if(filter==='perv' && !text.includes('перв'))return false;

  return true;
 });

 count.innerText=`Найдено: ${arr.length}`;

 list.innerHTML=arr.map((g,i)=>`
 <div class="card" onclick="openGroup(${i})">
   <div class="pic" style="background-image:url('${g.image||''}')"></div>
   <div class="cardbody">
     <h3>${g.name||'Домашняя церковь'}</h3>
     <div class="meta">
       ${g.area||''}<br>
       ${g.leader||''}
     </div>
   </div>
 </div>
 `).join('');
}


function openGroup(i){
 current=groups[i];

 document.getElementById('dName').innerText=current.name||'';
 document.getElementById('dLeaders').innerText=current.leader||'';

 const pic=document.getElementById('detailPic');
 if(pic)pic.style.backgroundImage=`url('${current.image||''}')`;

 show('detail');
}


function openRoute(){
 if(!current)return;

 if(current.route){
  window.open(current.route,'_blank');
 }else{
  alert('Маршрут пока не указан');
 }
}


function sendApp(e){
 e.preventDefault();

 let data={
  name:document.getElementById('name').value,
  telegram:document.getElementById('telegram').value,
  comment:document.getElementById('comment').value,
  group:current?.name||''
 };

 fetch('/api/visit',{
  method:'POST',
  headers:{'Content-Type':'application/json'},
  body:JSON.stringify(data)
 })
 .then(()=>show('success'));
}