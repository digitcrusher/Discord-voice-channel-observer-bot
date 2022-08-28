'use strict';

function leftPad(string, count, fill) {
  let result = string.toString();
  while(result.length < count) {
    result = fill + result;
  }
  return result;
}

function dateToString(date) {
  const weekday = [
    'Sunday',
    'Monday',
    'Tuesday',
    'Wednesday',
    'Thursday',
    'Friday',
    'Saturday',
  ][date.getDay()];
  const day = date.getDate();
  const month = [
    'January',
    'February',
    'March',
    'April',
    'May',
    'June',
    'July',
    'August',
    'September',
    'October',
    'November',
    'December',
  ][date.getMonth()];
  const year = date.getFullYear();
  const hours = leftPad(date.getHours(), 2, '0');
  const minutes = leftPad(date.getMinutes(), 2, '0');
  const seconds = leftPad(date.getSeconds(), 2, '0');
  return `${weekday}, ${day} ${month} ${year} ${hours}:${minutes}:${seconds}`;
}

function moveIndicator(position) {
  const timeline = document.getElementById('timeline');
  position = Math.min(position, timeline.clientHeight);

  const indicator = document.getElementById('indicator');
  indicator.style.setProperty('--position', position + 'px');
  indicator.innerText = '';

  position = Math.max(position, 0);
  for(const period of timeline.children) {
    if(period === indicator) continue;

    const height = period.clientHeight;
    const time = new Date(period.dataset.begin * 1000), end = new Date(period.dataset.end * 1000);
    time.setMilliseconds(time.getMilliseconds() + (end - time) * position / height);
    indicator.innerText = dateToString(time);

    position -= height; // HACK: Rounded down heights cause off-by-one pixel errors here.
    if(position < 0) break;
  }
}

let mouseY = 0;
let requestId = null;
function updateMouse() {
  window.cancelAnimationFrame(requestId);
  requestId = window.requestAnimationFrame(function(timestamp) {
    const timeline = document.getElementById('timeline');
    let offset = 0;
    let elem = timeline;
    while(elem !== null) {
      offset += elem.offsetTop;
      elem = elem.offsetParent;
    }
    moveIndicator(mouseY + window.scrollY - offset);
  });
}

document.onmousemove = function(event) {
  mouseY = event.clientY;
  updateMouse();
};
document.onscroll = function(event) {
  updateMouse();
};

window.onload = function() {
  for(const elem of document.getElementsByTagName('time')) {
    elem.innerText = dateToString(new Date(elem.dataset.timestamp * 1000));
  }
  for(const elem of document.getElementsByClassName('comment')) {
    elem.setAttribute('title', `Commented on ${dateToString(new Date(elem.dataset.timestamp * 1000))}`);
  }
  updateMouse();
};
