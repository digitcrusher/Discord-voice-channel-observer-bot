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
  const indicator = document.getElementById('indicator');
  indicator.style.setProperty('--position', Math.min(position, timeline.clientHeight) + 'px');
  indicator.innerText = '';

  for(const period of timeline.children) {
    if(period === indicator) continue;

    // offsetTop is unfortunately rounded to the nearest integer which may cause off-by-one pixel errors.
    const offset = period.offsetTop, height = period.clientHeight;
    if(position < offset && indicator.innerText !== '') break;

    const time = new Date(period.dataset.begin * 1000), end = new Date(period.dataset.end * 1000);
    time.setMilliseconds(time.getMilliseconds() + (end - time) * Math.min((position - offset) / height, 1));
    indicator.style.setProperty('--position', Math.min(position, offset + height) + 'px');
    indicator.innerText = dateToString(time);
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
