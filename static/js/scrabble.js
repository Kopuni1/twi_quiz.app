console.log("✅ scrabble.js loaded");

// ---------- DOM Elements ----------
const boardEl = document.getElementById("board");
const rackEl = document.getElementById("rack");
const infoEl = document.getElementById("info");
const confirmBtn = document.getElementById("confirm-word");
const shuffleBtn = document.getElementById("shuffle-tiles");
const endBtn = document.getElementById("end-game");
const closeSummaryBtn = document.getElementById("close-summary");
const levelButtons = document.querySelectorAll(".course-btn");
const levelModal = document.getElementById("level-modal");
const scrabbleContainer = document.querySelector(".scrabble-container");

// ---------- State ----------
let dictionary = [];
let dictionarySet = new Set();
let score = 0;
let boardSize = 10;
let currentLevel = "";
let tileIdCounter = 0;
window.newlyPlacedTiles = [];

// ---------- Utility ----------
const normalize = s => String(s).normalize('NFC').toLowerCase();

function showInfo(msg){ infoEl.textContent = msg; infoEl.style.color="#000"; }
function showSuccess(msg){ infoEl.textContent = msg; infoEl.style.color="green"; }
function showFail(msg){ infoEl.textContent = msg; infoEl.style.color="red"; }

function playSound(type){
  try {
    const audio = document.getElementById(type + "-sound") || new Audio(`/static/sounds/${type}.mp3`);
    audio.currentTime = 0;
    audio.play().catch(()=>{});
  } catch(e){}
}

// ---------- Load Dictionary ----------
async function loadDictionary(){
  const dictPath = window.DICT_PATH || "/static/twi_words.json";
  try {
    const res = await fetch(dictPath);
    dictionary = await res.json();
    dictionarySet = new Set(dictionary.map(normalize));
    console.log(`📚 Dictionary loaded: ${dictionary.length} words`);
  } catch(e){
    console.error("Failed to load dictionary", e);
  }
}

// ---------- Board & Rack ----------
function generateBoard(){
  boardEl.innerHTML = "";
  boardEl.style.display="grid";
  boardEl.style.gridTemplateColumns=`repeat(${boardSize},50px)`;
  boardEl.style.gridTemplateRows=`repeat(${boardSize},50px)`;
  boardEl.style.gap="4px";

  for(let r=0;r<boardSize;r++){
    for(let c=0;c<boardSize;c++){
      const cell=document.createElement("div");
      cell.className="board-cell";
      cell.dataset.pos=`${r}-${c}`;
      cell.addEventListener("dragover", e=>e.preventDefault());
      cell.addEventListener("drop", handleDrop);
      cell.addEventListener("dblclick", ()=> {
        const letter=cell.textContent?.trim();
        if(!letter) return;
        addTileBack(letter);
        cell.textContent='';
        window.newlyPlacedTiles = window.newlyPlacedTiles.filter(p=>p!==cell.dataset.pos);
      });
      boardEl.appendChild(cell);
    }
  }
  console.log(`🧩 Board generated (${boardSize}x${boardSize})`);
}

function createTileElement(letter){
  const tile=document.createElement("div");
  tile.className="rack-tile";
  tile.textContent=normalize(letter);
  tile.dataset.tid=`t${++tileIdCounter}`;
  tile.draggable=true;

  tile.addEventListener("dragstart", e=>{
    e.dataTransfer.setData("text/plain", JSON.stringify({id: tile.dataset.tid, letter: normalize(letter)}));
    e.dataTransfer.effectAllowed='move';
    tile.classList.add('dragging');
  });
  tile.addEventListener("dragend", ()=>tile.classList.remove('dragging'));
  return tile;
}

function addTileBack(letter){ rackEl.appendChild(createTileElement(letter)); }
function removeTileByTid(tid){
  const tile=rackEl.querySelector(`[data-tid="${tid}"]`);
  if(tile) tile.remove();
}

function generateRack(){
  rackEl.innerHTML="";
  const count=currentLevel==="beginner"?7:currentLevel==="intermediate"?9:11;
  const letters = ["a","a","a","a","a","a","e","e","e","ɛ","ɛ","o","o","ɔ","ɔ","k","n","s","t","p","m","u","w","y"];
  for(let i=0;i<count;i++){
    const letter=letters[Math.floor(Math.random()*letters.length)];
    rackEl.appendChild(createTileElement(letter));
  }
  console.log(`🎲 Rack generated with ${count} tiles`);
}

// ---------- Drag & Drop ----------
function handleDrop(e){
  e.preventDefault();
  const cell=e.target;
  try{
    const payload=JSON.parse(e.dataTransfer.getData('text/plain')||'{}');
    const letter=payload.letter;
    const tid=payload.id;
    if(!letter) return;
    cell.textContent=normalize(letter);
    if(tid) removeTileByTid(tid);
    if(!window.newlyPlacedTiles.includes(cell.dataset.pos)) window.newlyPlacedTiles.push(cell.dataset.pos);
  } catch(err){ console.error("drop parse error",err); }
}

// ---------- Confirm Word ----------
function confirmWord(){
  showInfo('');
  const cells=Array.from(boardEl.children);
  if(!cells.length || !window.newlyPlacedTiles.length){ showFail("Place new tiles first"); playSound("fail"); return; }

  const wordsFound=[];
  const pushWord=(word,pos)=>{ if(word.length>1 && pos.some(p=>window.newlyPlacedTiles.includes(p))) wordsFound.push({word,pos}); };

  window.newlyPlacedTiles.forEach(posStr=>{
    const [r,c]=posStr.split("-").map(Number);

    // horizontal
    let startC=c,endC=c;
    while(startC>0 && cells[r*boardSize+startC-1].textContent) startC--;
    while(endC<boardSize-1 && cells[r*boardSize+endC+1].textContent) endC++;
    let hWord='',hPos=[];
    for(let cc=startC;cc<=endC;cc++){
      const idx=r*boardSize+cc;
      const ch=normalize(cells[idx].textContent||'');
      if(ch){ hWord+=ch; hPos.push(`${r}-${cc}`); }
    }
    pushWord(hWord,hPos);

    // vertical
    let startR=r,endR=r;
    while(startR>0 && cells[(startR-1)*boardSize+c].textContent) startR--;
    while(endR<boardSize-1 && cells[(endR+1)*boardSize+c].textContent) endR++;
    let vWord='',vPos=[];
    for(let rr=startR;rr<=endR;rr++){
      const idx=rr*boardSize+c;
      const ch=normalize(cells[idx].textContent||'');
      if(ch){ vWord+=ch; vPos.push(`${rr}-${c}`); }
    }
    pushWord(vWord,vPos);
  });

  // deduplicate
  const seen=new Set();
  const finalWords=wordsFound.filter(o=>{ const k=o.pos.join(","); if(seen.has(k)) return false; seen.add(k); return true; });

  if(!finalWords.length){ showFail("No valid words formed"); playSound("fail"); return; }

  let totalScore=0,hasInvalid=false;
  cells.forEach(c=>c.classList.remove("wrong-word"));

  finalWords.forEach(o=>{
    const norm=normalize(o.word);
    if(!dictionarySet.has(norm)){
      hasInvalid=true;
      o.pos.forEach(p=>{ const cell=boardEl.querySelector(`[data-pos="${p}"]`); if(cell) cell.classList.add("wrong-word"); });
    } else totalScore+=norm.length*10;
  });

  if(hasInvalid){
    showFail(finalWords.filter(o=>!dictionarySet.has(normalize(o.word))).map(o=>`❌ "${o.word}"`).join("\n"));
    playSound("fail");
  } else {
    score+=totalScore;
    showSuccess(`✅ Words accepted! +${totalScore} points (Total: ${score})`);
    playSound("success");
    generateRack();
  }

  window.newlyPlacedTiles=[];
}

// ---------- Event Listeners ----------
confirmBtn?.addEventListener("click", confirmWord);

shuffleBtn?.addEventListener("click", () => {
  generateRack();
  showInfo("Tiles exchanged.");
  playSound("success");
});

endBtn?.addEventListener("click", () => {
  scrabbleContainer?.classList.add("hidden");
  document.getElementById("summary-modal")?.classList.add("active");
  document.getElementById("final-score").textContent = `Final Score: ${score}`;
});

closeSummaryBtn?.addEventListener("click", () => {
  document.getElementById("summary-modal")?.classList.remove("active");
  levelModal?.classList.add("active");
});

// Level Selection Buttons
levelButtons.forEach(btn => {
  btn.addEventListener("click", () => {
    currentLevel = btn.dataset.level;
    levelModal?.classList.remove("active");
    scrabbleContainer?.classList.remove("hidden");

    score = 0;
    boardSize = 10;
    generateBoard();
    generateRack();
    showInfo(`Level: ${currentLevel} | Score: ${score}`);
    playSound("success");
  });
});

// ---------- Init ----------
loadDictionary();
