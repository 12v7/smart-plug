
const evtDictionary = {
  'upload':'On Upload',
  'reset':'On Reset'
//'key0':'On Key 0'...
};
const cmdDictionary = {
  's':'SAY',
  'w':'WAIT'
//'a':'CH.A'...
};

function createEventDiv(title) {

  let evtDiv = document.createElement('div');
  evtDiv.classList.add('evt')

  let evtHead      = document.createElement('div');
  let evtHeadTitle = document.createElement('div');
  let evtHeadPlus  = document.createElement('img');
  let evtHeadCross = document.createElement('img');
  evtHead.classList.add('head');
  evtHeadTitle.classList.add('title');
  evtHeadPlus.classList.add('addbutton');
  evtHeadCross.classList.add('delbutton');
  evtHeadPlus.title = 'New command';
  evtHeadCross.title = 'Delete event';
  evtHeadPlus.src = 'plus.svg';
  evtHeadCross.src = 'close.svg';
  evtHeadPlus.addEventListener('click', showNewCommandMenu);
  evtHeadCross.addEventListener('click', (evt)=>evt.target.parentElement.parentElement.remove());
  evtHeadTitle.appendChild(document.createTextNode(title));

  evtHead.appendChild(evtHeadTitle);
  evtHead.appendChild(evtHeadPlus);
  evtHead.appendChild(evtHeadCross);

  evtDiv.appendChild(evtHead);
  return evtDiv;
}

function createCmdDiv(title, args) {

  let cmdDiv   = document.createElement('div');
  let titleDiv = document.createElement('div');
  let argsDiv  = document.createElement('div');
  let button   = document.createElement('img');

  cmdDiv.classList.add('cmd');
  cmdDiv.classList.add('cmd_' + title[0]);
  titleDiv.classList.add('title');
  argsDiv.classList.add('args');
  button.classList.add('delbutton');
  button.title = 'Delete command';
  button.setAttribute('src', 'close.svg');
  button.addEventListener('click', (evt)=>evt.target.parentElement.remove());

  titleDiv.appendChild(document.createTextNode(title));
  argsDiv.appendChild(document.createTextNode(args));
  argsDiv.setAttribute('contenteditable', true);

  cmdDiv.appendChild(titleDiv);
  cmdDiv.appendChild(argsDiv);
  cmdDiv.appendChild(button);

  return cmdDiv;
}

function createDivsFromString(str) {

  for (evtStr of str.split('@')) {
    const epc = evtStr.split(':')
    let evtDiv;
    let commandStr;
    switch (epc.length) {
    case 1: 
      evtDiv = createEventDiv('On Upload');
      commandStr = epc[0];
      break;
    case 2:
      evtDiv = createEventDiv(evtDictionary[epc[0]]);
      commandStr = epc[1];
      break;
    }

    let rexp = /([a-z]+)([0-9\.]+)/ig;
    while ((found = rexp.exec(commandStr)) !== null)
      evtDiv.appendChild(createCmdDiv(cmdDictionary[found[1]], found[2]));

    document.querySelector("#evt_container").appendChild( evtDiv );
  }
}

function getUploadStringsFromDivs() {

  str = '';
  for (let evt of document.querySelectorAll('.evt')) {
    let evtHead;
    for (const cmd of evt.children) {
      if (!evtHead) {
        evtHead = cmd.children[0].innerText;
        for(let k in evtDictionary) {
          if (evtDictionary[k] == evtHead) {
            if (k != 'upload')
              str += `@${k}:`;
            break;
          }
        }
      } else {
        for (k in cmdDictionary) {
          if (cmdDictionary[k]==cmd.children[0].innerText)
            str += k;
        }
        str += cmd.children[1].innerText;
      }
    }
  }
  return str;
}

function createMenu(items, x, y, eventDiv) {

  const cmdMenu = x && y && eventDiv;
  let bgDiv = document.createElement('div');
  bgDiv.id = 'menubg'
  bgDiv.addEventListener('click', destroyMenu);
  document.body.appendChild(bgDiv);

  let menuDiv   = document.createElement('div');
  menuDiv.id = 'menu';
  if (cmdMenu) {
    menuDiv.style.left = x + "px";
    menuDiv.style.top = y + "px";
  }

  for (item of items) {
    let itemDiv = document.createElement('div');
    itemDiv.classList.add('menuitem');
    itemDiv.appendChild(document.createTextNode(item));

    if (cmdMenu)
      itemDiv.addEventListener('click', (e)=>{eventDiv.appendChild(createCmdDiv(e.target.innerText, "0"));destroyMenu();});
    else
      itemDiv.addEventListener('click', (e)=>{document.querySelector("#evt_container").appendChild(createEventDiv(e.target.innerText));destroyMenu();});

    menuDiv.appendChild(itemDiv);
  }

  document.body.appendChild(menuDiv);
}

function destroyMenu() {
  document.getElementById('menubg').remove();
  document.getElementById('menu').remove();
}

function showNewCommandMenu(evt) {
  createMenu(Object.values(cmdDictionary), evt.clientX, evt.clientY, evt.target.parentElement.parentElement);
}

function showNewEventMenu() {

  let eventTypes = Object.values(evtDictionary); // prevent duplicating "on upload" event
  for (let node of document.querySelectorAll('.evt')) {
    if (node.childNodes[0].childNodes[0].innerText == evtDictionary['upload']) {
      eventTypes = eventTypes.slice(1);
      break;
    }
  }

  createMenu(eventTypes);
}

function uploadToMCU() {
  const prg = getUploadStringsFromDivs();
  console.log(prg);
  fetch(`/setprog?${prg}`);
}

window.onload = function() {

  for (let i=0; i<CFG.keyCount; i++)
    evtDictionary['key'+i] = 'On Key '+i;

  for (let i=0; i<CFG.outCount; i++)
    cmdDictionary[String.fromCharCode(97+i)] = 'CH.'+String.fromCharCode(65+i);

  if (CFG.program)
    createDivsFromString(CFG.program);

  document.getElementById('app_version').innerText = "v"+CFG.version;
}
