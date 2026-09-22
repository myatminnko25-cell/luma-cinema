(function(){
'use strict';
var pending,button=document.getElementById('install-app');
function standalone(){return window.matchMedia('(display-mode: standalone)').matches||navigator.standalone}
button.hidden=!!standalone();
window.addEventListener('beforeinstallprompt',function(e){e.preventDefault();pending=e;button.hidden=false});
window.addEventListener('appinstalled',function(){pending=null;button.hidden=true});
button.onclick=async function(){if(pending){var event=pending;pending=null;await event.prompt();await event.userChoice}else{document.getElementById('help').click()}};
if('serviceWorker' in navigator){window.addEventListener('load',function(){navigator.serviceWorker.register('/sw.js').catch(function(){/* Browsing still works without installation. */})})}
})();
